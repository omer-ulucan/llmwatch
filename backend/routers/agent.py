"""
Module: agent.py
Purpose: Agent execution and trace viewing endpoints.
WHY: This router exposes the agent's SSE streaming execution endpoint and trace retrieval
endpoints. It follows the same pattern as chat.py (JWT auth, background logging) but adds
SSE streaming for real-time step-by-step observation.
"""

import json
from decimal import Decimal
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse

from auth.dependencies import get_current_user
from config import logger
from models.schemas import AgentRunRequest
from services.agent_service import AgentService, get_agent_service
from services.dynamo_service import DynamoDBService, get_dynamo_service
from services.mlflow_service import MLFlowService, get_mlflow_service

router = APIRouter(prefix="/agent", tags=["Agent"])


def _decimal_default(obj: Any) -> Any:
    """JSON serializer for DynamoDB Decimal values.
    WHY: DynamoDB returns numbers as Decimal objects. json.dumps() can't handle
    them natively, so we convert to float/int."""
    if isinstance(obj, Decimal):
        if obj == int(obj):
            return int(obj)
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


@router.post("/run")
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
    company_id = current_user["company_id"]
    agent_svc = get_agent_service()
    dynamo_svc = get_dynamo_service()
    mlflow_svc = get_mlflow_service()

    async def event_generator():
        """
        Async generator that yields SSE-formatted events.
        WHY: FastAPI's StreamingResponse consumes this generator and sends each
        chunk to the client as it's yielded — enabling real-time streaming.
        """
        trace_data = None
        last_event = None

        async for event in agent_svc.run_agent(
            prompt=data.prompt,
            model=data.model,
            company_id=company_id,
            tools=data.tools,
            max_iterations=data.max_iterations,
        ):
            # Format as SSE: "data: {json}\n\n"
            event_json = event.model_dump_json()
            yield f"data: {event_json}\n\n"
            last_event = event

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
                    }
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Failed to parse run_end summary: {e}")

        # After streaming completes, save trace in background
        if trace_data:
            # Collect the full steps from the agent service's callback
            # The agent_service stores _trace_data on the callback after completion
            def save_trace():
                try:
                    dynamo_svc.save_trace(
                        company_id=company_id,
                        trace_data=trace_data,
                    )
                    logger.info(f"Trace {trace_data['run_id']} saved to DynamoDB")
                except Exception as e:
                    logger.error(f"Background trace save failed: {str(e)}")

                try:
                    mlflow_svc.log_llm_call(
                        company_id=company_id,
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

            background_tasks.add_task(save_trace)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )


@router.get("/traces")
async def get_traces(
    request: Request,
    limit: int = 50,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns a list of recent agent traces for the authenticated user's company.
    WHY: Powers the /traces list view in the frontend.
    """
    company_id = current_user["company_id"]
    dynamo_svc = get_dynamo_service()
    traces = dynamo_svc.get_traces(company_id, limit=limit)

    # Strip the heavy 'steps' list from the list view for performance
    # WHY: The list view only needs summary metadata. Steps are fetched on drill-down.
    summaries = []
    for trace in traces:
        summary = {k: v for k, v in trace.items() if k != "steps"}
        summaries.append(summary)

    return {"traces": json.loads(json.dumps(summaries, default=_decimal_default))}


@router.get("/traces/{run_id}")
async def get_trace(
    request: Request,
    run_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns the full trace for a specific agent run, including all steps.
    WHY: Powers the /traces/:runId detail view with the step timeline/waterfall.
    """
    company_id = current_user["company_id"]
    dynamo_svc = get_dynamo_service()
    trace = dynamo_svc.get_trace_by_id(company_id, run_id)

    if trace is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Trace not found")

    return {"trace": json.loads(json.dumps(trace, default=_decimal_default))}


@router.get("/analytics")
async def agent_analytics(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns aggregate agent metrics for the dashboard.
    WHY: Powers the agent KPI cards on the dashboard — total runs, success rate,
    avg steps, avg latency, total cost, and tool usage breakdown.
    """
    company_id = current_user["company_id"]
    dynamo_svc = get_dynamo_service()

    # Fetch recent traces for aggregation
    # WHY: For a hackathon demo, aggregating in-memory from recent traces is fine.
    # Production would use DynamoDB aggregation pipelines or pre-computed metrics.
    traces = dynamo_svc.get_traces(company_id, limit=200)

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
    successful = sum(1 for t in traces if t.get("success", False))
    total_steps = sum(float(t.get("total_steps", 0)) for t in traces)
    total_latency = sum(float(t.get("total_latency_ms", 0)) for t in traces)
    total_cost = sum(float(t.get("total_cost_usd", 0)) for t in traces)

    # Tool usage breakdown
    tool_usage: Dict[str, int] = {}
    for trace in traces:
        for tool_name in trace.get("tools_used", []):
            tool_usage[tool_name] = tool_usage.get(tool_name, 0) + 1

    # Model breakdown
    model_breakdown: Dict[str, int] = {}
    for trace in traces:
        model = str(trace.get("model_used", "unknown"))
        model_breakdown[model] = model_breakdown.get(model, 0) + 1

    return {
        "total_runs": total_runs,
        "success_rate": round(successful / total_runs * 100, 1)
        if total_runs > 0
        else 0.0,
        "avg_steps": round(total_steps / total_runs, 1) if total_runs > 0 else 0.0,
        "avg_latency_ms": round(total_latency / total_runs, 1)
        if total_runs > 0
        else 0.0,
        "total_cost_usd": round(total_cost, 6),
        "tool_usage": tool_usage,
        "model_breakdown": model_breakdown,
    }
