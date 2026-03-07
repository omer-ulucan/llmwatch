"""
Module: chat.py
Purpose: Exposes the primary AI generation endpoints.
WHY: Chat interactions represent the core value proposition of the system.
By injecting the JWT token dependencies we secure this route by default.
"""
from fastapi import APIRouter, Depends, Request
from typing import Dict, Any
from models.schemas import ChatCompletionRequest, ChatCompletionResponse
from auth.dependencies import get_current_user
from services.llm_service import llm_service
from services.mlflow_service import mlflow_service
from services.dynamo_service import dynamo_service
import asyncio

router = APIRouter(prefix="/chat", tags=["Chat"])

@router.post("/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: Request,
    data: ChatCompletionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Submits a conversational turn to the designated LLM strategy.
    """
    company_id = current_user["company_id"]
    
    # Generate Response
    result = await llm_service.execute_chat(
        prompt=data.prompt,
        model=data.model,
        thinking_mode=data.thinking_mode
    )
    
    # WHY: We run MLOps DB and MLFlow logging as background tasks
    # Async tasks keep the API responsive for the user without waiting for disk/network writes.
    async def log_operations():
        # DynamoDB Log
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
            "error_type": "none"
        }
        dynamo_service.save_log(company_id=company_id, log_data=log_data)
        
        # MLFlow Log
        mlflow_service.log_llm_call(
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
            error_type=None
        )

    # Fire and forget logging
    asyncio.create_task(log_operations())
    
    return result
