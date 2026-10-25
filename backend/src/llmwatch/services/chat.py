"""
Module: chat.py (service)
Purpose: Builds chat requests against the model registry and records their outcome.
WHY: The non-streaming and streaming endpoints share everything except transport:
model resolution, message assembly, reasoning knobs, cost and logging.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.llm import LLMError, Usage, compute_cost
from llmwatch.llm.reasoning import reasoning_controls
from llmwatch.models.schemas import ChatCompletionRequest
from llmwatch.providers.models import ResolvedModel, resolve_model
from llmwatch.services.observability import record_llm_call


@dataclass
class PreparedChat:
    resolved: ResolvedModel
    messages: list[dict[str, Any]]
    params: dict[str, Any]
    prompt_preview: str
    started: float = field(default_factory=time.perf_counter)

    @property
    def model_used(self) -> str:
        return self.resolved.label

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.started) * 1000

    def cost(self, usage: Usage) -> float | None:
        m = self.resolved.model
        return compute_cost(usage, m.input_price_per_mtok, m.output_price_per_mtok)


async def prepare_chat(
    session: AsyncSession, workspace_id: str, data: ChatCompletionRequest
) -> PreparedChat:
    """Resolves the model (400 if unusable) and assembles messages and params."""
    resolved = await resolve_model(session, workspace_id, data.model)
    model = resolved.model

    prefix, params = reasoning_controls(
        resolved.provider.preset, model.supports_reasoning, data.thinking_mode
    )
    messages: list[dict[str, Any]] = list(prefix)
    if data.system_prompt:
        messages.append({"role": "system", "content": data.system_prompt})
    messages.extend(m.model_dump() for m in data.messages or [])
    if data.prompt:
        messages.append({"role": "user", "content": data.prompt})

    params.update(
        temperature=data.temperature,
        max_tokens=data.max_tokens,
        top_p=data.top_p,
    )
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    return PreparedChat(resolved, messages, params, last_user)


def _log_base(prepared: PreparedChat, current_user: dict, thinking: bool) -> dict:
    return {
        "source": "chat",
        "user_id": current_user["user_id"],
        "api_key_id": current_user["api_key_id"],
        "model_ref_id": prepared.resolved.model.id,
        "model_name": prepared.resolved.model.model_id,
        "provider_name": prepared.resolved.provider.name,
        "prompt_preview": prepared.prompt_preview,
        "thinking_mode": thinking,
    }


async def log_success(
    prepared: PreparedChat,
    current_user: dict,
    *,
    thinking: bool,
    response: str,
    usage: Usage,
    latency_ms: float,
) -> None:
    await record_llm_call(
        current_user["workspace_id"],
        **_log_base(prepared, current_user, thinking),
        response_preview=response,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        cost_usd=prepared.cost(usage) or 0.0,
        latency_ms=latency_ms,
        success=True,
    )


async def log_failure(
    prepared: PreparedChat,
    current_user: dict,
    *,
    thinking: bool,
    error_type: str,
    message: str,
    status: int | None = None,
    response: str = "",
    usage: Usage | None = None,
) -> None:
    usage = usage or Usage()
    await record_llm_call(
        current_user["workspace_id"],
        **_log_base(prepared, current_user, thinking),
        response_preview=response,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=prepared.cost(usage) or 0.0,
        latency_ms=prepared.elapsed_ms(),
        success=False,
        error_type=error_type,
        error_message=message,
        status_code=status,
    )


async def log_llm_error(
    prepared: PreparedChat, current_user: dict, *, thinking: bool, err: LLMError
) -> None:
    await log_failure(
        prepared,
        current_user,
        thinking=thinking,
        error_type=err.kind,
        message=err.message,
        status=err.status,
    )
