"""
Module: chat.py
Purpose: Chat completions against any configured model, plain or streamed (SSE).
WHY: Chat interactions represent the core value proposition of the system.
Both endpoints resolve the model through the workspace registry, report the token
usage the provider returned, and log every call, including failures and streams the
client abandoned.

SSE events (POST /chat/stream), one JSON object per `data:` line:
  {"type": "start", "model_used", "model_id"}
  {"type": "reasoning", "text"}            reasoning text, when the provider sends it
  {"type": "delta", "text"}                answer text
  {"type": "usage", "input_tokens", "output_tokens", "reasoning_tokens"}
  {"type": "error", "error_type", "message"}
  {"type": "done", "latency_ms", "cost_usd", "priced", "finish_reason"}
"""

import json
from collections.abc import AsyncIterator
from typing import Any, Dict

import anyio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user
from llmwatch.db.engine import get_session
from llmwatch.exceptions import LLMServiceException
from llmwatch.llm import LLMError, StreamChunk, Usage
from llmwatch.models.schemas import ChatCompletionRequest, ChatCompletionResponse
from llmwatch.rate_limit import (
    chat_limit,
    ip_key,
    limiter,
    per_ip_limit,
    rate_limit_key,
)
from llmwatch.security.crypto import SecretDecryptionError
from llmwatch.services import chat as chat_service
from llmwatch.services.mlflow_service import get_mlflow_service

router = APIRouter(prefix="/chat", tags=["Chat"])


def _as_http_error(err: LLMError) -> LLMServiceException:
    return LLMServiceException(
        f"{err.provider}: {err.message}",
        provider=err.provider,
        http_status=err.http_status,
        error_type=err.kind,
        retry_after_s=err.retry_after_s,
    )


def _client(prepared: chat_service.PreparedChat):
    try:
        return prepared.resolved.client()
    except SecretDecryptionError as exc:
        raise LLMServiceException(
            str(exc), provider=prepared.resolved.provider.name, error_type="decryption"
        ) from exc


def _mirror_to_mlflow(prepared, workspace_id, thinking, usage: Usage, cost, latency):
    try:
        get_mlflow_service().log_llm_call(
            company_id=workspace_id,
            model_name=prepared.resolved.model.model_id,
            thinking_mode=thinking,
            prompt_length=len(prepared.prompt_preview),
            latency_ms=latency,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost,
            success=True,
            prompt_preview=prepared.prompt_preview[:50],
            response_preview="",
            error_type=None,
        )
    except Exception:  # pragma: no cover - mlflow is optional and best effort
        pass


@router.post("/completions", response_model=ChatCompletionResponse)
@limiter.limit(chat_limit, key_func=rate_limit_key)
@limiter.limit(per_ip_limit, key_func=ip_key)
async def chat_completions(
    request: Request,
    data: ChatCompletionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    One completion, returned when finished.
    """
    prepared = await chat_service.prepare_chat(
        session, current_user["workspace_id"], data
    )
    client = _client(prepared)
    try:
        result = await client.chat(
            prepared.resolved.model.model_id, prepared.messages, **prepared.params
        )
    except LLMError as err:
        # WHY: Failed calls count toward the error rate.
        await chat_service.log_llm_error(
            prepared, current_user, thinking=data.thinking_mode, err=err
        )
        raise _as_http_error(err) from err

    cost = prepared.cost(result.usage)
    await chat_service.log_success(
        prepared,
        current_user,
        thinking=data.thinking_mode,
        response=result.content,
        usage=result.usage,
        latency_ms=result.latency_ms,
    )
    _mirror_to_mlflow(
        prepared,
        current_user["workspace_id"],
        data.thinking_mode,
        result.usage,
        cost or 0.0,
        result.latency_ms,
    )
    return ChatCompletionResponse(
        response=result.content,
        thinking_content=result.reasoning if data.thinking_mode else None,
        latency_ms=result.latency_ms,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        reasoning_tokens=result.usage.reasoning_tokens,
        usage_reported=result.usage.reported,
        cost_usd=cost or 0.0,
        priced=cost is not None,
        model_used=prepared.model_used,
        model_id=prepared.resolved.model.id,
        finish_reason=result.finish_reason,
        thinking_mode=data.thinking_mode,
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/stream")
@limiter.limit(chat_limit, key_func=rate_limit_key)
@limiter.limit(per_ip_limit, key_func=ip_key)
async def chat_stream(
    request: Request,
    data: ChatCompletionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Streams a completion as Server-Sent Events (see the module docstring).
    """
    prepared = await chat_service.prepare_chat(
        session, current_user["workspace_id"], data
    )
    client = _client(prepared)
    stream = client.stream(
        prepared.resolved.model.model_id, prepared.messages, **prepared.params
    )

    # WHY: Pull the first chunk before answering, so a provider that fails right
    # away (bad key, rate limit, unknown model) gets a real HTTP status instead of
    # a 200 stream that only contains an error.
    try:
        first = await anext(stream)
    except LLMError as err:
        await chat_service.log_llm_error(
            prepared, current_user, thinking=data.thinking_mode, err=err
        )
        raise _as_http_error(err) from err

    async def events() -> AsyncIterator[str]:
        content: list[str] = []
        usage = Usage()
        finish_reason = None
        outcome = "cancelled"
        error: LLMError | None = None

        def render(chunk: StreamChunk) -> str | None:
            nonlocal usage, finish_reason
            if chunk.type == "delta":
                content.append(chunk.text)
                return _sse({"type": "delta", "text": chunk.text})
            if chunk.type == "reasoning":
                if not data.thinking_mode:
                    return None
                return _sse({"type": "reasoning", "text": chunk.text})
            if chunk.type == "usage" and chunk.usage is not None:
                usage = chunk.usage
                return _sse(
                    {
                        "type": "usage",
                        "input_tokens": usage.input_tokens,
                        "output_tokens": usage.output_tokens,
                        "reasoning_tokens": usage.reasoning_tokens,
                    }
                )
            if chunk.type == "done":
                finish_reason = chunk.finish_reason
            return None

        try:
            yield _sse(
                {
                    "type": "start",
                    "model_used": prepared.model_used,
                    "model_id": prepared.resolved.model.id,
                }
            )
            pending = [first]
            while True:
                for chunk in pending:
                    if (event := render(chunk)) is not None:
                        yield event
                if await request.is_disconnected():
                    break
                try:
                    pending = [await anext(stream)]
                except StopAsyncIteration:
                    outcome = "success"
                    break
            if outcome == "success":
                cost = prepared.cost(usage)
                yield _sse(
                    {
                        "type": "done",
                        "latency_ms": round(prepared.elapsed_ms(), 1),
                        "cost_usd": cost or 0.0,
                        "priced": cost is not None,
                        "finish_reason": finish_reason,
                    }
                )
        except LLMError as err:
            outcome, error = "error", err
            yield _sse(
                {"type": "error", "error_type": err.kind, "message": err.message}
            )
        finally:
            # WHY: On disconnect Starlette cancels this generator inside an anyio
            # cancel scope, which would cancel every await below too; shield the
            # cleanup so the upstream stream is closed and the call is logged.
            with anyio.CancelScope(shield=True):
                await _finish(outcome, error, "".join(content), usage)

    async def _finish(outcome, error, text, usage) -> None:
        # Closing the generator closes the upstream HTTP stream too.
        await stream.aclose()
        if outcome == "success":
            await chat_service.log_success(
                prepared,
                current_user,
                thinking=data.thinking_mode,
                response=text,
                usage=usage,
                latency_ms=prepared.elapsed_ms(),
            )
        elif outcome == "error" and error is not None:
            await chat_service.log_failure(
                prepared,
                current_user,
                thinking=data.thinking_mode,
                error_type=error.kind,
                message=error.message,
                status=error.status,
                response=text,
                usage=usage,
            )
        else:
            await chat_service.log_failure(
                prepared,
                current_user,
                thinking=data.thinking_mode,
                error_type="cancelled",
                message="Client disconnected before the stream finished",
                response=text,
                usage=usage,
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering for SSE
        },
    )
