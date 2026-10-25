"""
Module: analytics.py (service)
Purpose: SQL aggregation of LLM call logs over a real time window.
WHY: The old endpoints summed the latest 500 (or 100) rows in Python, ignored the
`hours` parameter, and only knew two hardcoded model names. Everything here is
computed by the database over [start, end), works the same on SQLite and Postgres,
and scales with indexes (workspace_id, created_at) instead of row caps.

Definitions:
  - error: success = false, except client-cancelled streams (error_type
    "cancelled"), which are counted separately and excluded from the error rate
  - percentiles: nearest-rank (the smallest value with at least p% of samples at or
    below it)
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import BigInteger, Integer, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from llmwatch.db.models import LLMLog
from llmwatch.exceptions import ValidationException

MAX_WINDOW = timedelta(days=366)
CANCELLED = "cancelled"

# (max window, bucket seconds): pick the first whose window is long enough.
_AUTO_BUCKETS = [
    (timedelta(hours=2), 60),
    (timedelta(hours=6), 300),
    (timedelta(hours=48), 3600),
    (timedelta(days=14), 6 * 3600),
    (MAX_WINDOW, 86400),
]
_NAMED_BUCKETS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "1d": 86400}


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def previous(self) -> "Window":
        return Window(self.start - self.duration, self.start)


def _parse_dt(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationException(f"{name} must be an ISO-8601 datetime") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def resolve_window(
    hours: float | None = None,
    start: str | None = None,
    end: str | None = None,
    *,
    now: datetime | None = None,
) -> Window:
    """`?from=&to=` if given (to defaults to now), otherwise the last `hours`."""
    now = now or datetime.now(UTC)
    if start:
        window = Window(_parse_dt(start, "from"), _parse_dt(end, "to") if end else now)
    else:
        if end:
            raise ValidationException("`to` requires `from`")
        h = 24.0 if hours is None else hours
        if h <= 0:
            raise ValidationException("hours must be positive")
        window = Window(now - timedelta(hours=h), now)
    if window.end <= window.start:
        raise ValidationException("`from` must be before `to`")
    if window.duration > MAX_WINDOW:
        raise ValidationException("The time window can be at most 366 days")
    return window


def bucket_seconds(window: Window, bucket: str | None = None) -> int:
    if bucket:
        if bucket not in _NAMED_BUCKETS:
            raise ValidationException(
                f"bucket must be one of {', '.join(_NAMED_BUCKETS)}"
            )
        seconds = _NAMED_BUCKETS[bucket]
        if window.duration.total_seconds() / seconds > 2000:
            raise ValidationException("Too many buckets; pick a larger bucket")
        return seconds
    for max_window, seconds in _AUTO_BUCKETS:
        if window.duration <= max_window:
            return seconds
    return 86400


@dataclass
class LogFilters:
    model: str | None = None
    provider: str | None = None
    source: str | None = None
    # "success", "error" or "cancelled"
    status: str | None = None
    q: str | None = None


def _is_error() -> ColumnElement[bool]:
    return and_(
        LLMLog.success.is_(False),
        or_(LLMLog.error_type.is_(None), LLMLog.error_type != CANCELLED),
    )


def _is_cancelled() -> ColumnElement[bool]:
    return and_(LLMLog.success.is_(False), LLMLog.error_type == CANCELLED)


def _conditions(workspace_id: str, window: Window, f: LogFilters | None) -> list:
    conds: list = [
        LLMLog.workspace_id == workspace_id,
        LLMLog.created_at >= window.start,
        LLMLog.created_at < window.end,
    ]
    if f is None:
        return conds
    if f.model:
        conds.append(LLMLog.model_name == f.model)
    if f.provider:
        conds.append(LLMLog.provider_name == f.provider)
    if f.source:
        conds.append(LLMLog.source == f.source)
    if f.status == "success":
        conds.append(LLMLog.success.is_(True))
    elif f.status == "error":
        conds.append(_is_error())
    elif f.status == "cancelled":
        conds.append(_is_cancelled())
    elif f.status:
        raise ValidationException("status must be success, error or cancelled")
    if f.q:
        needle = f"%{f.q.strip().lower()}%"
        conds.append(
            or_(
                func.lower(LLMLog.prompt_preview).like(needle),
                func.lower(LLMLog.response_preview).like(needle),
                func.lower(func.coalesce(LLMLog.error_message, "")).like(needle),
                func.lower(LLMLog.model_name).like(needle),
            )
        )
    return conds


async def _percentiles(
    session: AsyncSession, conds: list, count: int, ps: tuple[float, ...]
) -> dict[float, float | None]:
    out: dict[float, float | None] = {}
    for p in ps:
        if count == 0:
            out[p] = None
            continue
        rank = max(1, math.ceil(p * count))
        stmt = (
            select(LLMLog.latency_ms)
            .where(*conds)
            .order_by(LLMLog.latency_ms)
            .offset(rank - 1)
            .limit(1)
        )
        out[p] = (await session.execute(stmt)).scalar_one()
    return out


def _metrics_columns():
    return (
        func.count().label("requests"),
        func.coalesce(func.sum(case((_is_error(), 1), else_=0)), 0).label("errors"),
        func.coalesce(func.sum(case((_is_cancelled(), 1), else_=0)), 0).label(
            "cancelled"
        ),
        func.coalesce(func.sum(LLMLog.cost_usd), 0.0).label("cost"),
        func.avg(LLMLog.latency_ms).label("avg_latency"),
        func.coalesce(func.sum(LLMLog.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(LLMLog.output_tokens), 0).label("output_tokens"),
    )


def _error_rate(errors: int, requests: int, cancelled: int) -> float:
    considered = requests - cancelled
    return round(errors / considered * 100, 2) if considered > 0 else 0.0


async def _totals(session: AsyncSession, conds: list) -> dict[str, Any]:
    row = (await session.execute(select(*_metrics_columns()).where(*conds))).one()
    requests = int(row.requests)
    pct = await _percentiles(session, conds, requests, (0.5, 0.95))
    return {
        "total_requests": requests,
        "total_errors": int(row.errors),
        "total_cancelled": int(row.cancelled),
        "total_cost_usd": float(row.cost),
        "avg_latency_ms": round(float(row.avg_latency), 2) if requests else 0.0,
        "p50_latency_ms": pct[0.5],
        "p95_latency_ms": pct[0.95],
        "error_rate_pct": _error_rate(int(row.errors), requests, int(row.cancelled)),
        "input_tokens": int(row.input_tokens),
        "output_tokens": int(row.output_tokens),
    }


def _delta_pct(current: float | None, previous: float | None) -> float | None:
    """Percent change; None when there is no meaningful baseline."""
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


async def summary(
    session: AsyncSession,
    workspace_id: str,
    window: Window,
    filters: LogFilters | None = None,
) -> dict[str, Any]:
    conds = _conditions(workspace_id, window, filters)
    current = await _totals(session, conds)
    previous = await _totals(
        session, _conditions(workspace_id, window.previous(), filters)
    )

    by_model_stmt = (
        select(LLMLog.model_name, LLMLog.provider_name, *_metrics_columns())
        .where(*conds)
        .group_by(LLMLog.model_name, LLMLog.provider_name)
        .order_by(func.count().desc())
    )
    breakdown = {}
    for row in (await session.execute(by_model_stmt)).all():
        key = (
            f"{row.provider_name}/{row.model_name}"
            if row.provider_name
            else row.model_name
        )
        breakdown[key] = {
            "model": row.model_name,
            "provider": row.provider_name,
            "requests": int(row.requests),
            "errors": int(row.errors),
            "cost": float(row.cost),
            "avg_latency_ms": round(float(row.avg_latency or 0.0), 2),
            "input_tokens": int(row.input_tokens),
            "output_tokens": int(row.output_tokens),
            "error_rate_pct": _error_rate(
                int(row.errors), int(row.requests), int(row.cancelled)
            ),
        }

    compared = (
        "total_requests",
        "total_cost_usd",
        "avg_latency_ms",
        "p95_latency_ms",
        "error_rate_pct",
    )
    return {
        "window": {"from": window.start.isoformat(), "to": window.end.isoformat()},
        **current,
        "model_breakdown": breakdown,
        "previous": {k: previous[k] for k in compared},
        "deltas_pct": {k: _delta_pct(current[k], previous[k]) for k in compared},
    }


def _epoch(session: AsyncSession):
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        return cast(func.strftime("%s", LLMLog.created_at), Integer)
    return cast(func.extract("epoch", LLMLog.created_at), BigInteger)


async def timeseries(
    session: AsyncSession,
    workspace_id: str,
    window: Window,
    bucket: str | None = None,
    filters: LogFilters | None = None,
) -> dict[str, Any]:
    seconds = bucket_seconds(window, bucket)
    bucket_col = ((_epoch(session) // seconds) * seconds).label("bucket")
    stmt = (
        select(bucket_col, *_metrics_columns())
        .where(*_conditions(workspace_id, window, filters))
        .group_by(bucket_col)
    )
    rows = {int(r.bucket): r for r in (await session.execute(stmt)).all()}

    first = int(window.start.timestamp()) // seconds * seconds
    last = (
        int((window.end - timedelta(microseconds=1)).timestamp()) // seconds * seconds
    )
    buckets = []
    for ts in range(first, last + 1, seconds):
        r = rows.get(ts)
        buckets.append(
            {
                "ts": datetime.fromtimestamp(ts, UTC).isoformat(),
                "requests": int(r.requests) if r else 0,
                "errors": int(r.errors) if r else 0,
                "cost_usd": float(r.cost) if r else 0.0,
                "avg_latency_ms": round(float(r.avg_latency), 2) if r else None,
                "input_tokens": int(r.input_tokens) if r else 0,
                "output_tokens": int(r.output_tokens) if r else 0,
            }
        )
    return {
        "window": {"from": window.start.isoformat(), "to": window.end.isoformat()},
        "bucket_seconds": seconds,
        "buckets": buckets,
        # Flat arrays kept for the current dashboard chart.
        "timestamps": [b["ts"] for b in buckets],
        "costs": [b["cost_usd"] for b in buckets],
        "latencies": [b["avg_latency_ms"] or 0.0 for b in buckets],
        "request_counts": [b["requests"] for b in buckets],
    }


async def list_logs(
    session: AsyncSession,
    workspace_id: str,
    window: Window,
    filters: LogFilters,
    *,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[LLMLog], int]:
    conds = _conditions(workspace_id, window, filters)
    total = (
        await session.execute(select(func.count()).select_from(LLMLog).where(*conds))
    ).scalar_one()
    stmt = (
        select(LLMLog)
        .where(*conds)
        .order_by(LLMLog.created_at.desc(), LLMLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.execute(stmt)).scalars().all()), int(total)


async def iter_logs(
    session: AsyncSession,
    workspace_id: str,
    window: Window,
    filters: LogFilters,
    limit: int,
):
    stmt = (
        select(LLMLog)
        .where(*_conditions(workspace_id, window, filters))
        .order_by(LLMLog.created_at.desc(), LLMLog.id.desc())
        .limit(limit)
    )
    result = await session.stream_scalars(stmt)
    async for log in result:
        yield log
