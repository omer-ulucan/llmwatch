"""
Module: agent.py
Purpose: Agent execution and trace viewing endpoints.
WHY: This router exposes the agent's SSE streaming execution endpoint and trace retrieval
endpoints. It follows the same pattern as chat.py (JWT auth, background logging) but adds
SSE streaming for real-time step-by-step observation.
"""

import json
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user
from llmwatch.config import logger
from llmwatch.db.engine import get_session
from llmwatch.exceptions import ResourceNotFoundException
from llmwatch.models.schemas import AgentRunRequest
from llmwatch.rate_limit import (
    agent_limit,
    ip_key,
    limiter,
    per_ip_limit,
    rate_limit_key,
)
from llmwatch.services.agent_service import get_agent_service
from llmwatch.services.mlflow_service import get_mlflow_service
from llmwatch.services.observability import (
    TraceRepository,
    save_trace,
    trace_to_dict,
)
from llmwatch.tools.registry import available_tools

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/run")
@limiter.limit(agent_limit, key_func=rate_limit_key)
@limiter.limit(per_ip_limit, key_func=ip_key)
async def run_agent(
    request: Request,
    data: AgentRunRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Runs a ReAct agent with the specified tools and streams events via SSE.
    WHY: SSE (Server-Sent Events) is the ideal transport for real-time step streaming.
    Unlike WebSockets, SSE is unidirectional (server→client) which is exactly what we
    need — the client sends one request and receives a stream of step events.

    Returns text/event-stream content type with each event as:
        data: {json}\n\n
    """
    workspace_id = current_user["workspace_id"]
    agent_svc = get_agent_service()
    mlflow_svc = get_mlflow_service()

    async def event_generator():
        """
        Async generator that yields SSE-formatted events.
        WHY: FastAPI's StreamingResponse consumes this generator and sends each
        chunk to the client as it's yielded — enabling real-time streaming.
        """
        trace_data = None

        async for event in agent_svc.run_agent(
            prompt=data.prompt,
            model=data.model,
            company_id=workspace_id,
            tools=data.tools,
            max_iterations=data.max_iterations,
        ):
            # Format as SSE: "data: {json}\n\n"
            event_json = event.model_dump_json()
            yield f"data: {event_json}\n\n"

            # If this is the run_end event, extract trace data for background saving
            if event.event_type == "run_end":
                try:
                    summary = json.loads(event.content)
                    trace_data = {
                        "run_id": event.run_id,
                        "timestamp": event.timestamp,
                        "prompt": data.prompt[:1000],
                        "model_used": data.model,
                        "tools_enabled": data.tools,
                        "tools_used": summary.get("tools_used", []),
                        "total_steps": summary.get("total_steps", 0),
                        "total_latency_ms": summary.get("total_latency_ms", 0),
                        "total_tokens": summary.get("total_tokens", 0),
                        "total_cost_usd": summary.get("total_cost_usd", 0),
                        "success": summary.get("success", False),
                        "final_answer": "",
                        "steps": [],
                        "user_id": current_user["user_id"],
                    }
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Failed to parse run_end summary: {e}")

        # WHY: Persist once the client has every event. Awaited here (not a
        # background thread) and save_trace logs failures instead of hiding them.
        if trace_data:
            await save_trace(workspace_id, trace_data)

            def log_to_mlflow():
                try:
                    mlflow_svc.log_llm_call(
                        company_id=workspace_id,
                        model_name=data.model,
                        thinking_mode=False,
                        prompt_length=len(data.prompt),
                        latency_ms=trace_data.get("total_latency_ms", 0),
                        input_tokens=trace_data.get("total_tokens", 0),
                        output_tokens=0,
                        cost_usd=trace_data.get("total_cost_usd", 0),
                        success=trace_data.get("success", False),
                        prompt_preview=data.prompt[:50],
                        response_preview=trace_data.get("final_answer", "")[:200],
                        error_type=None,
                    )
                except Exception as e:
                    logger.error(f"Background MLFlow agent logging failed: {str(e)}")

            background_tasks.add_task(log_to_mlflow)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )


@router.get("/tools")
async def list_tools(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns the agent tools this server allows.
    WHY: Some tools are opt-in (code execution), so the UI asks instead of assuming.
    """
    return {"tools": available_tools()}


@router.get("/traces")
async def get_traces(
    request: Request,
    limit: int = 50,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns a list of recent agent traces for the authenticated user's workspace.
    WHY: Powers the /traces list view in the frontend. Steps are left out of the
    list (they're fetched on drill-down).
    """
    traces = await TraceRepository(session, current_user["workspace_id"]).recent(
        min(max(limit, 1), 200)
    )
    return {"traces": [trace_to_dict(t, include_steps=False) for t in traces]}


@router.get("/traces/{run_id}")
async def get_trace(
    request: Request,
    run_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns the full trace for a specific agent run, including all steps.
    WHY: Powers the /traces/:runId detail view with the step timeline/waterfall.
    """
    trace = await TraceRepository(session, current_user["workspace_id"]).get(run_id)
    if trace is None:
        raise ResourceNotFoundException("Trace not found")
    return {"trace": trace_to_dict(trace)}


@router.get("/analytics")
async def agent_analytics(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns aggregate agent metrics for the dashboard.
    WHY: Powers the agent KPI cards on the dashboard — total runs, success rate,
    avg steps, avg latency, total cost, and tool usage breakdown.
    """
    traces = await TraceRepository(session, current_user["workspace_id"]).recent(200)

    if not traces:
        return {
            "total_runs": 0,
            "success_rate": 0.0,
            "avg_steps": 0.0,
            "avg_latency_ms": 0.0,
            "total_cost_usd": 0.0,
            "tool_usage": {},
            "model_breakdown": {},
        }

    total_runs = len(traces)
    successful = sum(1 for t in traces if t.success)

    tool_usage: Dict[str, int] = {}
    model_breakdown: Dict[str, int] = {}
    for trace in traces:
        for tool_name in trace.tools_used:
            tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1
        model_breakdown[trace.model_name] = model_breakdown.get(trace.model_name, 0) + 1

    return {
        "total_runs": total_runs,
        "success_rate": round(successful / total_runs * 100, 1),
        "avg_steps": round(sum(t.total_steps for t in traces) / total_runs, 1),
        "avg_latency_ms": round(
            sum(t.total_latency_ms for t in traces) / total_runs, 1
        ),
        "total_cost_usd": sum(t.total_cost_usd for t in traces),
        "tool_usage": tool_usage,
        "model_breakdown": model_breakdown,
    }
