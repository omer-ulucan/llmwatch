"""
Module: schemas.py
Purpose: Pydantic v2 schemas for request and response validation.
WHY: Strict typing and explicit forbid of extra fields stops injection vulnerabilities at the API boundary.
"""
from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Optional

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
