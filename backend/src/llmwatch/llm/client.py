"""
Module: client.py
Purpose: One async client for every OpenAI-compatible provider.
WHY: OpenAI, Gemini (OpenAI-compatible endpoint), OpenRouter, Groq, Together, Ollama,
vLLM and LM Studio all speak the same chat-completions API, so a single client with
a custom base_url replaces per-provider LangChain wrappers. It reports the token
usage the provider returns (never a guess), surfaces reasoning text where the
provider exposes it, and turns SDK exceptions into LLMError with a retryable flag.

Retries are deliberately left to callers (the eval runner backs off per provider);
the SDK's own retries are disabled so failures are visible and countable.
"""

import email.utils
import re
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import openai
from openai import AsyncOpenAI

from llmwatch.llm.types import (
    ChatResult,
    LLMError,
    Message,
    ProviderConfig,
    StreamChunk,
    ToolCall,
    Usage,
    summarize_params,
)

# Reasoning some models emit inline in the content instead of a separate field.
_THINK_TAG = re.compile(r"<(think|thought)>(.*?)</\1>", re.DOTALL)


def split_reasoning(content: str) -> tuple[str, str | None]:
    """Separates <think>/<thought> blocks from the visible answer."""
    blocks = [m.group(2).strip() for m in _THINK_TAG.finditer(content)]
    if not blocks:
        return content, None
    visible = _THINK_TAG.sub("", content).strip()
    return visible, "\n\n".join(b for b in blocks if b) or None


def _extra(obj: Any, name: str) -> Any:
    """Reads a field the SDK doesn't model (providers add their own)."""
    value = getattr(obj, name, None)
    if value is None:
        extra = getattr(obj, "model_extra", None) or {}
        value = extra.get(name)
    return value


def _reasoning_field(obj: Any) -> str | None:
    # vLLM / DeepSeek use reasoning_content; OpenRouter and Ollama use reasoning.
    for name in ("reasoning_content", "reasoning"):
        value = _extra(obj, name)
        if isinstance(value, str) and value:
            return value
    return None


def _usage(raw: Any) -> Usage:
    if raw is None:
        return Usage()
    details = getattr(raw, "completion_tokens_details", None)
    reasoning = getattr(details, "reasoning_tokens", None) if details else None
    return Usage(
        input_tokens=int(getattr(raw, "prompt_tokens", 0) or 0),
        output_tokens=int(getattr(raw, "completion_tokens", 0) or 0),
        reasoning_tokens=int(reasoning or 0),
        reported=True,
    )


def _parse_retry_after(headers: httpx.Headers | None) -> float | None:
    if not headers:
        return None
    if ms := headers.get("retry-after-ms"):
        try:
            return max(float(ms) / 1000, 0.0)
        except ValueError:
            pass
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - datetime.now(UTC)).total_seconds(), 0.0)


def normalize_error(exc: Exception, provider: str) -> LLMError:
    """Maps OpenAI SDK / httpx exceptions onto LLMError."""
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, openai.APITimeoutError | httpx.TimeoutException):
        return LLMError("Request timed out", kind="timeout", provider=provider)
    if isinstance(exc, openai.APIConnectionError | httpx.TransportError):
        return LLMError(
            f"Could not reach provider: {exc}", kind="connection", provider=provider
        )
    if isinstance(exc, openai.APIStatusError):
        status = exc.status_code
        if status == 429:
            kind = "rate_limit"
        elif status >= 500:
            kind = "server"
        elif status == 401:
            kind = "auth"
        elif status == 403:
            kind = "permission"
        elif status == 404:
            kind = "not_found"
        elif status in (400, 409, 413, 422):
            kind = "bad_request"
        elif status == 408:
            kind = "timeout"
        else:
            kind = "unknown"
        message = _status_message(exc)
        return LLMError(
            message,
            kind=kind,
            provider=provider,
            status=status,
            retry_after_s=_parse_retry_after(exc.response.headers)
            if exc.response is not None
            else None,
        )
    return LLMError(str(exc) or type(exc).__name__, kind="unknown", provider=provider)


def _status_message(exc: openai.APIStatusError) -> str:
    body = exc.body
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        if isinstance(error, str):
            return error
    return exc.message or f"HTTP {exc.status_code}"


class LLMClient:
    """Chat, stream, list models and embed against one provider."""

    def __init__(
        self,
        provider: ProviderConfig,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.provider = provider
        self._sdk = AsyncOpenAI(
            base_url=provider.base_url,
            # WHY: Local servers (Ollama, vLLM, LM Studio) need no key, but the SDK
            # refuses an empty one.
            api_key=provider.api_key or "not-needed",
            timeout=provider.timeout_s,
            max_retries=0,
            http_client=http_client,
        )

    async def close(self) -> None:
        await self._sdk.close()

    def _request(self, model: str, messages: list[Message], params: dict[str, Any]):
        body = summarize_params(params)
        extra_body = body.pop("extra_body", None) or {}
        return {"model": model, "messages": messages, **body}, extra_body

    async def chat(
        self, model: str, messages: list[Message], **params: Any
    ) -> ChatResult:
        """One non-streaming completion. Params are passed through (temperature,
        max_tokens, tools, response_format, reasoning_effort, extra_body, ...)."""
        request, extra_body = self._request(model, messages, params)
        started = time.perf_counter()
        try:
            resp = await self._sdk.chat.completions.create(
                **request, extra_body=extra_body or None
            )
        except Exception as exc:
            raise normalize_error(exc, self.provider.name) from exc
        latency_ms = (time.perf_counter() - started) * 1000

        if not resp.choices:
            raise LLMError(
                "Provider returned no choices",
                kind="server",
                provider=self.provider.name,
            )
        choice = resp.choices[0]
        message = choice.message
        content = message.content or ""
        reasoning = _reasoning_field(message)
        if reasoning is None:
            content, reasoning = split_reasoning(content)
        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (message.tool_calls or [])
            if getattr(tc, "function", None) is not None
        ]
        return ChatResult(
            content=content,
            reasoning=reasoning,
            tool_calls=tool_calls,
            usage=_usage(resp.usage),
            finish_reason=choice.finish_reason,
            model=resp.model or model,
            latency_ms=latency_ms,
        )

    async def stream(
        self, model: str, messages: list[Message], **params: Any
    ) -> AsyncIterator[StreamChunk]:
        """
        Streams a completion as StreamChunk events: "delta" and "reasoning" text as it
        arrives, then "tool_calls" (assembled), "usage" (if reported) and "done".
        """
        request, extra_body = self._request(model, messages, params)
        if self.provider.stream_usage:
            request["stream_options"] = {"include_usage": True}
        try:
            stream = await self._sdk.chat.completions.create(
                **request, stream=True, extra_body=extra_body or None
            )
        except Exception as exc:
            raise normalize_error(exc, self.provider.name) from exc

        usage: Usage | None = None
        finish_reason: str | None = None
        calls: dict[int, dict[str, str]] = {}
        # Inline <think> tags arrive split across chunks; track whether we're in one.
        in_think = False
        try:
            async for chunk in stream:
                if chunk.usage is not None:
                    usage = _usage(chunk.usage)
                for choice in chunk.choices or []:
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                    delta = choice.delta
                    if delta is None:
                        continue
                    if reasoning := _reasoning_field(delta):
                        yield StreamChunk(type="reasoning", text=reasoning)
                    if delta.content:
                        for kind, text in _split_think_stream(delta.content, in_think):
                            if kind == "toggle":
                                in_think = not in_think
                            elif text:
                                yield StreamChunk(type=kind, text=text)
                    for tc in delta.tool_calls or []:
                        slot = calls.setdefault(
                            tc.index, {"id": "", "name": "", "arguments": ""}
                        )
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function is not None:
                            slot["name"] += tc.function.name or ""
                            slot["arguments"] += tc.function.arguments or ""
        except Exception as exc:
            raise normalize_error(exc, self.provider.name) from exc

        if calls:
            yield StreamChunk(
                type="tool_calls",
                tool_calls=[ToolCall(**calls[i]) for i in sorted(calls)],
            )
        if usage is not None:
            yield StreamChunk(type="usage", usage=usage)
        yield StreamChunk(type="done", finish_reason=finish_reason)

    async def list_models(self) -> list[str]:
        """Model ids from GET {base_url}/models."""
        try:
            page = await self._sdk.models.list()
        except Exception as exc:
            raise normalize_error(exc, self.provider.name) from exc
        return sorted({m.id for m in page.data})

    async def embed(self, model: str, inputs: list[str]) -> list[list[float]]:
        try:
            resp = await self._sdk.embeddings.create(model=model, input=inputs)
        except Exception as exc:
            raise normalize_error(exc, self.provider.name) from exc
        return [item.embedding for item in sorted(resp.data, key=lambda d: d.index)]


_OPEN_TAGS = ("<think>", "<thought>")
_CLOSE_TAGS = ("</think>", "</thought>")


def _split_think_stream(text: str, in_think: bool):
    """Splits a streamed content delta on <think>/<thought> tags.

    Yields ("delta" | "reasoning", text) pieces and ("toggle", "") at tag
    boundaries. Assumes tags arrive whole within one delta, which is how vLLM and
    llama.cpp tokenize them.
    """
    while text:
        tags = _CLOSE_TAGS if in_think else _OPEN_TAGS
        positions = [(text.find(t), t) for t in tags if text.find(t) != -1]
        if not positions:
            yield ("reasoning" if in_think else "delta", text)
            return
        pos, tag = min(positions)
        if pos:
            yield ("reasoning" if in_think else "delta", text[:pos])
        yield ("toggle", "")
        in_think = not in_think
        text = text[pos + len(tag) :]


async def collect(stream: AsyncIterator[StreamChunk]) -> dict[str, Any]:
    """Drains a stream into content/reasoning/usage (tests, non-UI callers)."""
    content, reasoning = [], []
    result: dict[str, Any] = {"usage": None, "tool_calls": [], "finish_reason": None}
    async for chunk in stream:
        if chunk.type == "delta":
            content.append(chunk.text)
        elif chunk.type == "reasoning":
            reasoning.append(chunk.text)
        elif chunk.type == "usage":
            result["usage"] = chunk.usage
        elif chunk.type == "tool_calls":
            result["tool_calls"] = chunk.tool_calls
        elif chunk.type == "done":
            result["finish_reason"] = chunk.finish_reason
    result["content"] = "".join(content)
    result["reasoning"] = "".join(reasoning) or None
    return result
