"""
Module: schemas.py
Purpose: Pydantic v2 schemas for request and response validation.
WHY: Strict typing and explicit forbid of extra fields stops injection vulnerabilities at the API boundary.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from llmwatch.tools.registry import ALL_TOOLS, available_tools


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(..., min_length=8)
    workspace_name: Optional[str] = Field(None, min_length=1, max_length=200)
    # Deprecated alias of workspace_name, accepted for older clients.
    company_name: Optional[str] = Field(None, min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def _bcrypt_length_limit(cls, v: str) -> str:
        # WHY: bcrypt only uses the first 72 bytes; refuse longer passwords instead
        # of silently ignoring the rest.
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return v

    @model_validator(mode="after")
    def _require_workspace_name(self) -> "RegisterRequest":
        if not (self.workspace_name or self.company_name):
            raise ValueError("workspace_name is required")
        return self

    @property
    def resolved_workspace_name(self) -> str:
        return (self.workspace_name or self.company_name or "").strip()


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
    workspace_id: str
    # Deprecated alias of workspace_id, kept for older clients.
    company_id: str


class UserInfo(BaseModel):
    id: Optional[str]
    email: Optional[str]
    role: str


class WorkspaceInfo(BaseModel):
    id: str
    name: str
    created_at: datetime


class MeResponse(BaseModel):
    user: UserInfo
    workspace: WorkspaceInfo
    auth_method: str


class DeleteWorkspaceRequest(BaseModel):
    """Typed confirmation, so a stray request can't wipe a workspace."""

    model_config = ConfigDict(extra="forbid")
    confirm_name: str


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
    tools: List[str] = Field(default_factory=available_tools)
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
        for t in v:
            if t not in ALL_TOOLS:
                raise ValueError(f"Invalid tool: {t}. Must be one of {list(ALL_TOOLS)}")
            if t not in available_tools():
                raise ValueError(
                    f"Tool {t} is disabled on this server"
                    + (
                        " (set ENABLE_CODE_EXECUTION=true to enable it)"
                        if t == "code_execute"
                        else ""
                    )
                )
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
