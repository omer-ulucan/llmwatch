"""
Module: analytics.py
Purpose: Provides endpoints for reporting cost and performance metrics to the frontend.
WHY: Delivering rapid analytics depends on targeted GSI queries and aggregation.
"""
from fastapi import APIRouter, Depends, Request
from typing import Dict, Any, List
from auth.dependencies import get_current_user
from services.dynamo_service import dynamo_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])

@router.get("/summary")
async def get_summary(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Computes overarching platform KPIs for a given tenant.
    """
    company_id = current_user["company_id"]
    
    # WHY: In a true prod app we'd maintain counters or run Athena. 
    # For hackathon/MVP we aggregate the last N logs in memory.
    logs = dynamo_service.get_logs(company_id=company_id, limit=500)
    
    total_cost = sum(log.get("cost_usd", 0) for log in logs)
    avg_latency = sum(log.get("latency_ms", 0) for log in logs) / max(len(logs), 1)
    error_count = sum(1 for log in logs if not log.get("success", True))
    
    qwen_logs = [l for l in logs if l.get("model_name") == "qwen"]
    gemini_logs = [l for l in logs if l.get("model_name") == "gemini"]

    return {
        "total_cost_usd": total_cost,
        "avg_latency_ms": avg_latency,
        "total_requests": len(logs),
        "error_rate_pct": (error_count / max(len(logs), 1)) * 100,
        "model_breakdown": {
            "qwen": {
                "requests": len(qwen_logs),
                "cost": sum(l.get("cost_usd", 0) for l in qwen_logs)
            },
            "gemini": {
                "requests": len(gemini_logs),
                "cost": sum(l.get("cost_usd", 0) for l in gemini_logs)
            }
        }
    }

@router.get("/logs")
async def get_logs_list(
    limit: int = 50,
    model: str = "all",
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Provides a paginated view of granular invocation traces.
    """
    logs = dynamo_service.get_logs(company_id=current_user["company_id"], limit=limit)
    if model != "all":
        logs = [l for l in logs if l.get("model_name") == model]
    return logs

@router.get("/timeseries")
async def get_timeseries(
    hours: int = 24,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Groups metrics into time buckets suitable for charting.
    """
    # Simplified mock chart builder
    logs = dynamo_service.get_logs(company_id=current_user["company_id"], limit=100)
    
    timestamps = []
    costs = []
    latencies = []
    request_counts = []
    
    # Iterate and build arrays for Recharts AreaChart
    for log in reversed(logs): # Ascending order for charts
        timestamps.append(log.get("timestamp"))
        costs.append(log.get("cost_usd", 0))
        latencies.append(log.get("latency_ms", 0))
        request_counts.append(1)
        
    return {
        "timestamps": timestamps,
        "costs": costs,
        "latencies": latencies,
        "request_counts": request_counts
    }
