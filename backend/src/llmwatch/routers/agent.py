"""
Module: agent.py
Purpose: Agent execution (SSE), cancellation, and trace viewing endpoints.
WHY: POST /agent/run streams one AgentEvent per `data:` line while the native agent
loop runs (llmwatch.agent.loop). The run is cancelled when the client disconnects
or POST /agent/runs/{run_id}/cancel is called, and its trace is completed whatever
the outcome.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Dict

import anyio
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.agent.loop import AgentRequest, AgentRun, registry
from llmwatch.agent.tools import ALL_TOOLS, available_tool_names
from llmwatch.auth.dependencies import get_current_user
from llmwatch.db.engine import get_session
from llmwatch.db.models import AgentTrace
from llmwatch.exceptions import LLMServiceException, ResourceNotFoundException
from llmwatch.models.schemas import AgentRunRequest
from llmwatch.providers.models import resolve_model
from llmwatch.rate_limit import (
    agent_limit,
    ip_key,
    limiter,
    per_ip_limit,
    rate_limit_key,
)
from llmwatch.security.crypto import SecretDecryptionError
from llmwatch.services.observability import TraceRepository, trace_to_dict

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/run")
@limiter.limit(agent_limit, key_func=rate_limit_key)
@limiter.limit(per_ip_limit, key_func=ip_key)
async def run_agent(
    request: Request,
    data: AgentRunRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Runs the agent with the selected tools and streams events via SSE.
    WHY: SSE (Server-Sent Events) is the ideal transport for real-time step streaming.

    Returns text/event-stream content type with each event as:
        data: {json}\\n\\n
    Event types: run_start, thinking, tool_call, tool_result, final_answer, error,
    run_end (whose content is the JSON run summary).
    """
    workspace_id = current_user["workspace_id"]
    resolved = await resolve_model(session, workspace_id, data.model)
    try:
        client = resolved.client()
    except SecretDecryptionError as exc:
        raise LLMServiceException(
            str(exc), provider=resolved.provider.name, error_type="decryption"
        ) from exc

    run = AgentRun(
        AgentRequest(
            prompt=data.prompt,
            tools=data.tools,
            max_iterations=data.max_iterations,
            workspace_id=workspace_id,
            user_id=current_user["user_id"],
            api_key_id=current_user["api_key_id"],
        ),
        resolved,
        client,
    )
    active = registry.register(run.run_id, workspace_id)
    run.cancel = active.cancel

    async def event_generator():
        try:
            async for event in run.events():
                yield f"data: {event.model_dump_json(exclude_none=True)}\n\n"
                if await request.is_disconnected():
                    active.cancel.set()
        finally:
            # WHY: On disconnect Starlette cancels this generator inside an anyio
            # cancel scope; shield so the trace is still completed.
            with anyio.CancelScope(shield=True):
                await run.save()
                registry.unregister(run.run_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
            "X-Run-Id": run.run_id,
        },
    )


@router.post("/runs/{run_id}/cancel", status_code=202)
async def cancel_run(
    run_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Cancels a running agent run of this workspace (on this server process)."""
    if not registry.cancel(run_id, current_user["workspace_id"]):
        raise ResourceNotFoundException("No running agent run with this id")
    return {"run_id": run_id, "status": "cancelling"}


@router.get("/tools")
async def list_tools(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns the agent tools this server allows.
    WHY: Some tools are opt-in (code execution), so the UI asks instead of assuming.
    """
    names = available_tool_names()
    return {
        "tools": names,
        "details": [
            {"name": n, "description": ALL_TOOLS[n].description} for n in names
        ],
    }


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
    hours: float = Query(24 * 30, gt=0, le=24 * 366),
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Aggregate agent metrics over the last `hours` (default 30 days): runs, success
    rate, average steps and latency, total cost, tool and model usage.
    """
    since = datetime.now(UTC) - timedelta(hours=hours)
    conds = [
        AgentTrace.workspace_id == current_user["workspace_id"],
        AgentTrace.created_at >= since,
        AgentTrace.status != "running",
    ]
    row = (
        await session.execute(
            select(
                func.count(),
                func.avg(AgentTrace.total_steps),
                func.avg(AgentTrace.total_latency_ms),
                func.coalesce(func.sum(AgentTrace.total_cost_usd), 0.0),
            ).where(*conds)
        )
    ).one()
    total_runs = int(row[0])
    successful = (
        await session.execute(
            select(func.count()).where(*conds, AgentTrace.status == "success")
        )
    ).scalar_one()

    model_rows = (
        await session.execute(
            select(AgentTrace.model_name, func.count())
            .where(*conds)
            .group_by(AgentTrace.model_name)
        )
    ).all()
    # tools_used is a JSON list; counted here for the windowed rows only.
    tool_usage: Dict[str, int] = {}
    for (tools_used,) in (
        await session.execute(select(AgentTrace.tools_used).where(*conds))
    ).all():
        for name in tools_used or []:
            tool_usage[name] = tool_usage.get(name, 0) + 1

    return {
        "total_runs": total_runs,
        "success_rate": round(successful / total_runs * 100, 1) if total_runs else 0.0,
        "avg_steps": round(float(row[1] or 0), 1),
        "avg_latency_ms": round(float(row[2] or 0), 1),
        "total_cost_usd": float(row[3]),
        "tool_usage": tool_usage,
        "model_breakdown": {name: int(count) for name, count in model_rows},
    }
