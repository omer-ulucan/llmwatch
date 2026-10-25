"""
Module: chat.py
Purpose: Exposes the primary AI generation endpoints.
WHY: Chat interactions represent the core value proposition of the system.
By injecting the JWT token dependencies we secure this route by default.
"""

import time
from typing import Any, Dict

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from llmwatch.auth.dependencies import get_current_user
from llmwatch.config import logger
from llmwatch.exceptions import LLMServiceException
from llmwatch.models.schemas import ChatCompletionRequest, ChatCompletionResponse
from llmwatch.rate_limit import (
    chat_limit,
    ip_key,
    limiter,
    per_ip_limit,
    rate_limit_key,
)
from llmwatch.services.llm_service import get_llm_service
from llmwatch.services.mlflow_service import get_mlflow_service
from llmwatch.services.observability import record_llm_call

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/completions", response_model=ChatCompletionResponse)
@limiter.limit(chat_limit, key_func=rate_limit_key)
@limiter.limit(per_ip_limit, key_func=ip_key)
async def chat_completions(
    request: Request,
    data: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Submits a conversational turn to the designated LLM strategy.
    """
    workspace_id = current_user["workspace_id"]
    llm_service = get_llm_service()

    # Generate Response
    started = time.perf_counter()
    try:
        result = await llm_service.execute_chat(
            prompt=data.prompt, model=data.model, thinking_mode=data.thinking_mode
        )
    except LLMServiceException as exc:
        err = getattr(exc, "llm_error", None)
        if err is not None:
            # WHY: Failed calls count toward the error rate; logged before raising
            # because background tasks don't run for error responses.
            await record_llm_call(
                workspace_id,
                source="chat",
                user_id=current_user["user_id"],
                api_key_id=current_user["api_key_id"],
                model_name=data.model,
                prompt_preview=data.prompt,
                latency_ms=(time.perf_counter() - started) * 1000,
                thinking_mode=data.thinking_mode,
                success=False,
                error_type=err.kind,
                error_message=err.message,
                status_code=err.status,
            )
        raise

    # WHY: Logging runs after the response is sent, so the client never waits on it.
    # record_llm_call stores to the database and logs (rather than hides) failures.
    background_tasks.add_task(
        record_llm_call,
        workspace_id,
        source="chat",
        user_id=current_user["user_id"],
        api_key_id=current_user["api_key_id"],
        model_name=data.model,
        prompt_preview=data.prompt,
        response_preview=result["response"],
        latency_ms=result["latency_ms"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=result["cost_usd"],
        thinking_mode=data.thinking_mode,
        success=True,
    )

    def log_to_mlflow():
        try:
            get_mlflow_service().log_llm_call(
                company_id=workspace_id,
                model_name=data.model,
                thinking_mode=data.thinking_mode,
                prompt_length=len(data.prompt),
                latency_ms=result["latency_ms"],
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_usd=result["cost_usd"],
                success=True,
                prompt_preview=data.prompt[:50],
                response_preview=result["response"][:200],
                error_type=None,
            )
        except Exception as e:
            logger.error(f"Background MLFlow logging failed: {str(e)}")

    background_tasks.add_task(log_to_mlflow)

    return result
