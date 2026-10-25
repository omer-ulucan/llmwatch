"""
Module: types.py
Purpose: Provider-neutral request/response types for the LLM client.
WHY: Every provider is reached through the OpenAI-compatible API, but callers (chat,
agent, evals) should depend on small, stable types rather than SDK objects.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

Message = dict[str, Any]  # OpenAI chat message: {"role": ..., "content": ...}


@dataclass(frozen=True)
class ProviderConfig:
    """How to reach one OpenAI-compatible endpoint."""

    name: str
    base_url: str
    api_key: str | None = None
    # Preset type ("openai", "gemini", "ollama", "vllm", ...), drives small quirks.
    preset: str = "custom"
    timeout_s: float = 120.0
    # Ask for token usage on streams (stream_options.include_usage). A few servers
    # reject the option; their presets turn it off.
    stream_usage: bool = True


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    # Part of output_tokens spent on hidden reasoning, when the provider says so.
    reasoning_tokens: int = 0
    # False when the provider didn't report usage. We never guess token counts.
    reported: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ToolCall:
    id: str
    name: str
    # JSON-encoded arguments exactly as the model produced them.
    arguments: str


@dataclass
class ChatResult:
    content: str
    reasoning: str | None
    tool_calls: list[ToolCall]
    usage: Usage
    finish_reason: str | None
    model: str
    latency_ms: float


@dataclass
class StreamChunk:
    type: Literal["delta", "reasoning", "tool_calls", "usage", "done"]
    text: str = ""
    usage: Usage | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None


ErrorKind = Literal[
    "rate_limit",
    "server",
    "timeout",
    "connection",
    "auth",
    "permission",
    "not_found",
    "bad_request",
    "unknown",
]

# How a provider failure is reported to our own API clients.
HTTP_STATUS_FOR_KIND: dict[str, int] = {
    "rate_limit": 429,
    "timeout": 504,
    "connection": 502,
    "server": 502,
    # The provider rejected our credentials: a configuration problem upstream.
    "auth": 502,
    "permission": 502,
    "bad_request": 400,
    "not_found": 400,
    "unknown": 502,
}

RETRYABLE_KINDS: frozenset[str] = frozenset(
    {"rate_limit", "server", "timeout", "connection"}
)


class LLMError(Exception):
    """A normalised provider error.

    WHY: Callers need one question answered: should I retry, and when? Rate limits,
    5xx, timeouts and dropped connections are retryable; bad requests, auth and
    unknown models are not.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: ErrorKind,
        provider: str,
        status: int | None = None,
        retry_after_s: float | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.provider = provider
        self.status = status
        self.retry_after_s = retry_after_s

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE_KINDS

    @property
    def http_status(self) -> int:
        return HTTP_STATUS_FOR_KIND.get(self.kind, 502)

    @property
    def error_type(self) -> str:
        """Short label stored on failed call logs."""
        return self.kind

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"LLMError(kind={self.kind!r}, status={self.status}, "
            f"provider={self.provider!r}, message={self.message!r})"
        )


def summarize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Drops None values so request bodies only carry what the caller set."""
    return {k: v for k, v in params.items() if v is not None}
