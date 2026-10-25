"""
Module: observability.py
Purpose: Persists and reads LLM call logs and agent traces (SQL).
WHY: Replaces the DynamoDB writes, which never stored anything: boto3 rejects Python
floats ("Float types are not supported"), latency and cost are floats, and the error
was swallowed inside a background thread, so the dashboard was always empty.

Writes happen after the response (the client never waits on logging), each in its
own session, and failures are logged with enough context to notice and debug them.
"""

from datetime import UTC, datetime
from typing import Any

from llmwatch.config import logger
from llmwatch.db.engine import get_sessionmaker
from llmwatch.db.models import AgentTrace, LLMLog
from llmwatch.db.repository import WorkspaceRepository

PROMPT_PREVIEW_CHARS = 200
RESPONSE_PREVIEW_CHARS = 500
ERROR_MESSAGE_CHARS = 1000


class LogRepository(WorkspaceRepository[LLMLog]):
    model = LLMLog

    async def recent(self, limit: int = 50, model_name: str | None = None):
        stmt = self.select().order_by(LLMLog.created_at.desc()).limit(limit)
        if model_name:
            stmt = stmt.where(LLMLog.model_name == model_name)
        return (await self.session.execute(stmt)).scalars().all()


class TraceRepository(WorkspaceRepository[AgentTrace]):
    model = AgentTrace

    async def recent(self, limit: int = 50):
        stmt = self.select().order_by(AgentTrace.created_at.desc()).limit(limit)
        return (await self.session.execute(stmt)).scalars().all()


async def record_llm_call(workspace_id: str, **fields: Any) -> str | None:
    """
    Stores one LLM call. Never raises: a logging failure must not fail the request,
    but it is logged loudly (with the workspace) instead of disappearing.

    Returns:
        The log id, or None if it could not be stored.
    """
    fields["prompt_preview"] = (fields.get("prompt_preview") or "")[
        :PROMPT_PREVIEW_CHARS
    ]
    fields["response_preview"] = (fields.get("response_preview") or "")[
        :RESPONSE_PREVIEW_CHARS
    ]
    if fields.get("error_message"):
        fields["error_message"] = fields["error_message"][:ERROR_MESSAGE_CHARS]
    try:
        async with get_sessionmaker()() as session:
            log = LogRepository(session, workspace_id).add(LLMLog(**fields))
            await session.commit()
            return log.id
    except Exception:
        logger.exception(
            f"Failed to store LLM call log (workspace={workspace_id}, "
            f"model={fields.get('model_name')})"
        )
        return None


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


async def save_trace(workspace_id: str, trace_data: dict[str, Any]) -> str | None:
    """
    Stores a finished agent run. Never raises (see record_llm_call).

    Args:
        trace_data: run_id, timestamp, prompt, model_used, tools_enabled,
            tools_used, total_steps, total_latency_ms, total_tokens,
            total_cost_usd, success, final_answer, steps, and optionally
            status, error, user_id.
    """
    status = trace_data.get("status") or (
        "success" if trace_data.get("success") else "error"
    )
    try:
        async with get_sessionmaker()() as session:
            trace = TraceRepository(session, workspace_id).add(
                AgentTrace(
                    id=trace_data["run_id"],
                    created_at=_parse_timestamp(trace_data.get("timestamp")),
                    finished_at=datetime.now(UTC),
                    user_id=trace_data.get("user_id"),
                    model_name=trace_data.get("model_used") or "unknown",
                    prompt=trace_data.get("prompt", ""),
                    tools_enabled=list(trace_data.get("tools_enabled") or []),
                    tools_used=list(trace_data.get("tools_used") or []),
                    status=status,
                    total_steps=int(trace_data.get("total_steps") or 0),
                    total_latency_ms=float(trace_data.get("total_latency_ms") or 0),
                    total_tokens=int(trace_data.get("total_tokens") or 0),
                    total_cost_usd=float(trace_data.get("total_cost_usd") or 0),
                    final_answer=trace_data.get("final_answer") or "",
                    error=trace_data.get("error"),
                    steps=list(trace_data.get("steps") or []),
                )
            )
            await session.commit()
            return trace.id
    except Exception:
        logger.exception(
            f"Failed to store agent trace (workspace={workspace_id}, "
            f"run_id={trace_data.get('run_id')})"
        )
        return None


def log_to_dict(log: LLMLog) -> dict[str, Any]:
    """The /analytics/logs item shape the frontend expects."""
    return {
        "log_id": log.id,
        "timestamp": log.created_at.isoformat(),
        "model_name": log.model_name,
        "provider_name": log.provider_name,
        "source": log.source,
        "prompt_preview": log.prompt_preview,
        "response_preview": log.response_preview,
        "latency_ms": log.latency_ms,
        "input_tokens": log.input_tokens,
        "output_tokens": log.output_tokens,
        "cost_usd": log.cost_usd,
        "success": log.success,
        "error_type": log.error_type or "none",
        "error_message": log.error_message,
        "status_code": log.status_code,
        "thinking_mode": log.thinking_mode,
    }


def trace_to_dict(trace: AgentTrace, *, include_steps: bool = True) -> dict[str, Any]:
    """The /agent/traces item shape the frontend expects."""
    data = {
        "run_id": trace.id,
        "company_id": trace.workspace_id,
        "workspace_id": trace.workspace_id,
        "timestamp": trace.created_at.isoformat(),
        "prompt": trace.prompt,
        "model_used": trace.model_name,
        "tools_enabled": trace.tools_enabled,
        "tools_used": trace.tools_used,
        "status": trace.status,
        "total_steps": trace.total_steps,
        "total_latency_ms": trace.total_latency_ms,
        "total_tokens": trace.total_tokens,
        "total_cost_usd": trace.total_cost_usd,
        "success": trace.success,
        "final_answer": trace.final_answer,
        "error": trace.error,
    }
    if include_steps:
        data["steps"] = trace.steps
    return data


async def recent_logs_for(workspace_id: str, limit: int = 100) -> list[LLMLog]:
    """Convenience for callers without a request session (e.g. agent tools)."""
    async with get_sessionmaker()() as session:
        return list(await LogRepository(session, workspace_id).recent(limit))
