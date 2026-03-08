"""
Module: analytics.py
Purpose: Provides endpoints for reporting cost and performance metrics to the frontend.
WHY: Delivering rapid analytics depends on targeted GSI queries and aggregation.
"""

from decimal import Decimal
from fastapi import APIRouter, Depends, Request
from typing import Dict, Any, List
from auth.dependencies import get_current_user
from services.dynamo_service import get_dynamo_service


router = APIRouter(prefix="/analytics", tags=["Analytics"])


def to_float(value) -> float:
    """Safely convert DynamoDB Decimal or any numeric type to float."""
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@router.get("/summary")
async def get_summary(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Computes overarching platform KPIs for a given tenant.
    """
    company_id = current_user["company_id"]
    dynamo_service = get_dynamo_service()

    # WHY: In a true prod app we'd maintain counters or run Athena.
    # For hackathon/MVP we aggregate the last N logs in memory.
    logs = dynamo_service.get_logs(company_id=company_id, limit=500)

    total_cost = sum(to_float(log.get("cost_usd", 0)) for log in logs)
    avg_latency = sum(to_float(log.get("latency_ms", 0)) for log in logs) / max(
        len(logs), 1
    )
    error_count = sum(1 for log in logs if not log.get("success", True))

    qwen_logs = [l for l in logs if l.get("model_name") == "qwen"]
    gemini_logs = [l for l in logs if l.get("model_name") == "gemini"]

    return {
        "total_cost_usd": round(total_cost, 6),
        "avg_latency_ms": round(avg_latency, 2),
        "total_requests": len(logs),
        "error_rate_pct": round((error_count / max(len(logs), 1)) * 100, 2),
        "model_breakdown": {
            "qwen": {
                "requests": len(qwen_logs),
                "cost": round(
                    sum(to_float(l.get("cost_usd", 0)) for l in qwen_logs), 6
                ),
            },
            "gemini": {
                "requests": len(gemini_logs),
                "cost": round(
                    sum(to_float(l.get("cost_usd", 0)) for l in gemini_logs), 6
                ),
            },
        },
    }


@router.get("/logs")
async def get_logs_list(
    limit: int = 50,
    model: str = "all",
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Provides a paginated view of granular invocation traces.
    """
    dynamo_service = get_dynamo_service()
    logs = dynamo_service.get_logs(company_id=current_user["company_id"], limit=limit)
    if model != "all":
        logs = [l for l in logs if l.get("model_name") == model]

    # WHY: Convert Decimal values to float for JSON serialization
    sanitized_logs = []
    for log in logs:
        sanitized = {}
        for k, v in log.items():
            sanitized[k] = float(v) if isinstance(v, Decimal) else v
        sanitized_logs.append(sanitized)

    return sanitized_logs


@router.get("/timeseries")
async def get_timeseries(
    hours: int = 24, current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Groups metrics into time buckets suitable for charting.
    """
    dynamo_service = get_dynamo_service()
    logs = dynamo_service.get_logs(company_id=current_user["company_id"], limit=100)

    timestamps = []
    costs = []
    latencies = []
    request_counts = []

    # Iterate and build arrays for Recharts AreaChart
    for log in reversed(logs):  # Ascending order for charts
        timestamps.append(log.get("timestamp"))
        costs.append(to_float(log.get("cost_usd", 0)))
        latencies.append(to_float(log.get("latency_ms", 0)))
        request_counts.append(1)

    return {
        "timestamps": timestamps,
        "costs": costs,
        "latencies": latencies,
        "request_counts": request_counts,
    }
