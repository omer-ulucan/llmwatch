"""
Module: schemas.py
Purpose: Pydantic v2 schemas for request and response validation.
WHY: Strict typing and explicit forbid of extra fields stops injection vulnerabilities at the API boundary.
"""

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
from typing import List, Optional


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(..., min_length=8)
    company_name: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(..., max_length=10000)
    model: str = Field(..., pattern="^(qwen|gemini)$")
    thinking_mode: bool = False


class ChatCompletionResponse(BaseModel):
    response: str
    thinking_content: Optional[str] = None
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model_used: str
    thinking_mode: bool


# ── Agent Schemas ──────────────────────────────────────────


class AgentRunRequest(BaseModel):
    """Request body for POST /agent/run.
    WHY: Validates and constrains agent execution parameters at the API boundary.
    """

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(..., max_length=10000)
    model: str
    tools: List[str] = ["web_search", "code_execute", "db_query", "doc_analyze"]
    max_iterations: int = 10

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        if v not in ("qwen", "gemini"):
            raise ValueError("Model must be 'qwen' or 'gemini'")
        return v

    @field_validator("tools")
    @classmethod
    def validate_tools(cls, v: List[str]) -> List[str]:
        valid = {"web_search", "code_execute", "db_query", "doc_analyze"}
        for t in v:
            if t not in valid:
                raise ValueError(f"Invalid tool: {t}. Must be one of {valid}")
        return v

    @field_validator("max_iterations")
    @classmethod
    def validate_max_iterations(cls, v: int) -> int:
        if v < 1 or v > 20:
            raise ValueError("max_iterations must be between 1 and 20")
        return v
