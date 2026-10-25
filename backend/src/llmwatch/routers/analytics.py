"""
Module: analytics.py
Purpose: Provides endpoints for reporting cost and performance metrics to the frontend.
WHY: Reads the LLM call logs stored in the SQL database. The response shapes match
what the dashboard expects today; real time windows and SQL aggregation follow.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user
from llmwatch.db.engine import get_session
from llmwatch.services.observability import LogRepository, log_to_dict

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
async def get_summary(
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Computes overarching platform KPIs for a given tenant.
    """
    logs = await LogRepository(session, current_user["workspace_id"]).recent(500)

    total_cost = sum(log.cost_usd for log in logs)
    avg_latency = sum(log.latency_ms for log in logs) / max(len(logs), 1)
    error_count = sum(1 for log in logs if not log.success)

    qwen_logs = [log for log in logs if log.model_name == "qwen"]
    gemini_logs = [log for log in logs if log.model_name == "gemini"]

    return {
        # WHY: Full precision; per-call costs are often below $0.000001 and
        # rounding here compounds in aggregates. The UI formats for display.
        "total_cost_usd": total_cost,
        "avg_latency_ms": round(avg_latency, 2),
        "total_requests": len(logs),
        "error_rate_pct": round((error_count / max(len(logs), 1)) * 100, 2),
        "model_breakdown": {
            "qwen": {
                "requests": len(qwen_logs),
                "cost": sum(log.cost_usd for log in qwen_logs),
            },
            "gemini": {
                "requests": len(gemini_logs),
                "cost": sum(log.cost_usd for log in gemini_logs),
            },
        },
    }


@router.get("/logs")
async def get_logs_list(
    limit: int = 50,
    model: str = "all",
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Provides a paginated view of granular invocation traces.
    """
    repo = LogRepository(session, current_user["workspace_id"])
    logs = await repo.recent(limit, model_name=None if model == "all" else model)
    return [log_to_dict(log) for log in logs]


@router.get("/timeseries")
async def get_timeseries(
    hours: int = 24,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Groups metrics into time buckets suitable for charting.
    """
    logs = await LogRepository(session, current_user["workspace_id"]).recent(100)

    timestamps = []
    costs = []
    latencies = []
    request_counts = []

    # Iterate and build arrays for Recharts AreaChart
    for log in reversed(logs):  # Ascending order for charts
        timestamps.append(log.created_at.isoformat())
        costs.append(log.cost_usd)
        latencies.append(log.latency_ms)
        request_counts.append(1)

    return {
        "timestamps": timestamps,
        "costs": costs,
        "latencies": latencies,
        "request_counts": request_counts,
    }
