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


class RegisterResponse(BaseModel):
    message: str
    company_id: str


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


# ── API Key Schemas ───────────────────────────────────────


class CreateApiKeyRequest(BaseModel):
    """Request body for creating a new API key.
    WHY: Validates the key name at the API boundary — prevents empty or excessively long names.
    """

    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=64)


class CreateApiKeyResponse(BaseModel):
    """Response after creating or regenerating an API key.
    WHY: The raw_key is returned ONCE at creation time — it is never stored or retrievable again.
    """

    key_id: str
    name: str
    raw_key: str
    prefix: str
    created_at: str


class ApiKeyResponse(BaseModel):
    """Single API key metadata (without raw key) for list views.
    WHY: Only the masked prefix is returned — the full key is never recoverable after creation.
    """

    key_id: str
    name: str
    prefix: str
    created_at: str
    last_used_at: Optional[str] = None
    request_count: int = 0
    is_active: bool = True


class ApiKeyListResponse(BaseModel):
    """Wrapper for listing API keys.
    WHY: Consistent envelope pattern matching the rest of the API.
    """

    keys: List[ApiKeyResponse]
