"""
Module: chat.py
Purpose: Exposes the primary AI generation endpoints.
WHY: Chat interactions represent the core value proposition of the system.
By injecting the JWT token dependencies we secure this route by default.
"""

from fastapi import APIRouter, Depends, Request, BackgroundTasks
from typing import Dict, Any
from models.schemas import ChatCompletionRequest, ChatCompletionResponse
from auth.dependencies import get_current_user
from services.llm_service import get_llm_service
from services.mlflow_service import get_mlflow_service
from services.dynamo_service import get_dynamo_service
from config import logger

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: Request,
    data: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Submits a conversational turn to the designated LLM strategy.
    """
    company_id = current_user["company_id"]
    llm_service = get_llm_service()

    # Generate Response
    result = await llm_service.execute_chat(
        prompt=data.prompt, model=data.model, thinking_mode=data.thinking_mode
    )

    # WHY: We run DB and MLFlow logging as background tasks via FastAPI's BackgroundTasks.
    # This keeps the API responsive and properly handles exceptions (logged, not swallowed).
    log_data = {
        "prompt_preview": data.prompt[:50],
        "response_preview": result["response"][:200],
        "latency_ms": result["latency_ms"],
        "input_tokens": result["input_tokens"],
        "output_tokens": result["output_tokens"],
        "cost_usd": result["cost_usd"],
        "model_name": data.model,
        "thinking_mode": data.thinking_mode,
        "success": True,
        "error_type": "none",
    }

    def run_logging():
        try:
            dynamo_service = get_dynamo_service()
            dynamo_service.save_log(company_id=company_id, log_data=log_data)
        except Exception as e:
            logger.error(f"Background DynamoDB logging failed: {str(e)}")

        try:
            mlflow_svc = get_mlflow_service()
            mlflow_svc.log_llm_call(
                company_id=company_id,
                model_name=data.model,
                thinking_mode=data.thinking_mode,
                prompt_length=len(data.prompt),
                latency_ms=result["latency_ms"],
                input_tokens=result["input_tokens"],
                output_tokens=result["output_tokens"],
                cost_usd=result["cost_usd"],
                success=True,
                prompt_preview=log_data["prompt_preview"],
                response_preview=log_data["response_preview"],
                error_type=None,
            )
        except Exception as e:
            logger.error(f"Background MLFlow logging failed: {str(e)}")

    background_tasks.add_task(run_logging)

    return result
