"""
Module: analytics.py
Purpose: Cost, latency and error metrics over a time window, plus the raw call log.
WHY: Every number is aggregated by the database over the requested window
(`?hours=` or `?from=&to=`), see llmwatch.services.analytics.
"""

import csv
import io
from collections.abc import AsyncIterator
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user
from llmwatch.db.engine import get_session, get_sessionmaker
from llmwatch.db.models import LLMLog
from llmwatch.services import analytics as svc
from llmwatch.services.observability import log_to_dict

router = APIRouter(prefix="/analytics", tags=["Analytics"])

CSV_MAX_ROWS = 100_000


def window_params(
    hours: float | None = Query(None, gt=0, description="Last N hours (default 24)"),
    start: str | None = Query(None, alias="from", description="ISO-8601 start"),
    end: str | None = Query(None, alias="to", description="ISO-8601 end"),
) -> svc.Window:
    return svc.resolve_window(hours, start, end)


def filter_params(
    model: str | None = None,
    provider: str | None = None,
    source: str | None = Query(None, description="chat, agent or eval"),
    status: str | None = Query(None, description="success, error or cancelled"),
    q: str | None = Query(None, max_length=200, description="Search text"),
) -> svc.LogFilters:
    return svc.LogFilters(
        model=model, provider=provider, source=source, status=status, q=q
    )


@router.get("/summary")
async def get_summary(
    window: svc.Window = Depends(window_params),
    filters: svc.LogFilters = Depends(filter_params),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Totals, p50/p95 latency, error rate, per-model breakdown, and the same metrics
    for the previous window of equal length (with percentage deltas).
    """
    return await svc.summary(session, current_user["workspace_id"], window, filters)


@router.get("/timeseries")
async def get_timeseries(
    bucket: str | None = Query(None, description="1m, 5m, 15m, 1h, 6h or 1d"),
    window: svc.Window = Depends(window_params),
    filters: svc.LogFilters = Depends(filter_params),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Zero-filled time buckets (size chosen from the window unless given).
    """
    return await svc.timeseries(
        session, current_user["workspace_id"], window, bucket, filters
    )


@router.get("/logs")
async def get_logs_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    window: svc.Window = Depends(window_params),
    filters: svc.LogFilters = Depends(filter_params),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Paginated call log, newest first, with filters and text search.
    """
    logs, total = await svc.list_logs(
        session,
        current_user["workspace_id"],
        window,
        filters,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [log_to_dict(log) for log in logs],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/filters")
async def get_filter_options(
    window: svc.Window = Depends(window_params),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Distinct models and providers seen in the window (for filter dropdowns)."""
    conds = svc._conditions(current_user["workspace_id"], window, None)
    models = (
        await session.execute(select(LLMLog.model_name).where(*conds).distinct())
    ).scalars()
    providers = (
        await session.execute(select(LLMLog.provider_name).where(*conds).distinct())
    ).scalars()
    return {
        "models": sorted(m for m in models if m),
        "providers": sorted(p for p in providers if p),
    }


CSV_COLUMNS = [
    "timestamp",
    "source",
    "provider_name",
    "model_name",
    "success",
    "error_type",
    "status_code",
    "latency_ms",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "prompt_preview",
    "response_preview",
    "error_message",
]


def csv_safe(value: Any) -> Any:
    """Neutralises spreadsheet formulas (CSV injection)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


@router.get("/logs.csv")
async def export_logs_csv(
    window: svc.Window = Depends(window_params),
    filters: svc.LogFilters = Depends(filter_params),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    The filtered call log as CSV (newest first, at most 100,000 rows).
    """
    workspace_id = current_user["workspace_id"]

    async def rows() -> AsyncIterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_COLUMNS)
        # WHY: Own session: the body is streamed after the handler returns.
        async with get_sessionmaker()() as session:
            async for log in svc.iter_logs(
                session, workspace_id, window, filters, CSV_MAX_ROWS
            ):
                item = log_to_dict(log)
                writer.writerow([csv_safe(item.get(col)) for col in CSV_COLUMNS])
                if buffer.tell() > 64_000:
                    yield buffer.getvalue()
                    buffer.seek(0)
                    buffer.truncate()
        yield buffer.getvalue()

    filename = f"llmwatch-logs-{window.start:%Y%m%d%H%M}-{window.end:%Y%m%d%H%M}.csv"
    return StreamingResponse(
        rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
