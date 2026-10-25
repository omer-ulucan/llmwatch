"""
A scriptable fake OpenAI-compatible server for tests (no network).

Usage:
    fake = FakeProvider()
    fake.reply("Hello!", usage=(10, 3))          # queue a response
    fake.fail(429, retry_after="2")              # queue an error
    client = fake.client()                        # LLMClient wired to it
    fake.requests                                 # JSON bodies it received

Unqueued requests get a default "ok" reply. Streaming requests are answered as SSE
using the same queued replies, split into chunks.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from llmwatch.llm import LLMClient, ProviderConfig


@dataclass
class Reply:
    content: str = "ok"
    reasoning: str | None = None
    reasoning_field: str = "reasoning_content"
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: tuple[int, int] | None = (5, 2)
    reasoning_tokens: int | None = None
    finish_reason: str = "stop"
    status: int = 200
    error_body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    exception: Exception | None = None


class FakeProvider:
    def __init__(self, models: list[str] | None = None, name: str = "fake"):
        self.name = name
        self.models = models or ["fake-model"]
        self.queue: list[Reply] = []
        self.requests: list[dict[str, Any]] = []
        self.paths: list[str] = []
        self.headers: list[httpx.Headers] = []

    # ── scripting ────────────────────────────────────────────

    def reply(self, content: str = "ok", usage=(5, 2), **kwargs) -> "FakeProvider":
        self.queue.append(Reply(content=content, usage=usage, **kwargs))
        return self

    def call_tool(
        self, name: str, arguments: dict | str, call_id: str = "call_1", **kw
    ):
        args = arguments if isinstance(arguments, str) else json.dumps(arguments)
        self.queue.append(
            Reply(
                content=kw.pop("content", ""),
                tool_calls=[{"id": call_id, "name": name, "arguments": args}],
                finish_reason="tool_calls",
                **kw,
            )
        )
        return self

    def fail(self, status: int, message: str = "boom", retry_after: str | None = None):
        headers = {"retry-after": retry_after} if retry_after else {}
        self.queue.append(
            Reply(
                status=status,
                error_body={"error": {"message": message, "type": "fake"}},
                headers=headers,
            )
        )
        return self

    def raise_(self, exc: Exception) -> "FakeProvider":
        self.queue.append(Reply(exception=exc))
        return self

    # ── wiring ───────────────────────────────────────────────

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport())

    def config(self, **overrides) -> ProviderConfig:
        return ProviderConfig(
            name=self.name,
            base_url="http://fake.local/v1",
            api_key="sk-fake",
            **overrides,
        )

    def client(self, **overrides) -> LLMClient:
        return LLMClient(self.config(**overrides), http_client=self.http_client())

    # ── server ───────────────────────────────────────────────

    def _next(self) -> Reply:
        return self.queue.pop(0) if self.queue else Reply()

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.paths.append(path)
        self.headers.append(request.headers)
        body = json.loads(request.content) if request.content else {}
        self.requests.append(body)

        if path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": m, "object": "model", "created": 0, "owned_by": "fake"}
                        for m in self.models
                    ],
                },
            )
        if path.endswith("/embeddings"):
            inputs = (
                body["input"] if isinstance(body["input"], list) else [body["input"]]
            )
            data = [
                {"object": "embedding", "index": i, "embedding": _embed(text)}
                for i, text in enumerate(inputs)
            ]
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": list(reversed(data)),  # order must not be trusted
                    "model": body["model"],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1},
                },
            )

        reply = self._next()
        if reply.exception is not None:
            raise reply.exception
        if reply.status != 200:
            return httpx.Response(
                reply.status, json=reply.error_body, headers=reply.headers
            )
        if body.get("stream"):
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=self._sse(body, reply),
            )
        return httpx.Response(200, json=self._completion(body, reply))

    def _usage(self, reply: Reply):
        if reply.usage is None:
            return None
        usage = {
            "prompt_tokens": reply.usage[0],
            "completion_tokens": reply.usage[1],
            "total_tokens": sum(reply.usage),
        }
        if reply.reasoning_tokens is not None:
            usage["completion_tokens_details"] = {
                "reasoning_tokens": reply.reasoning_tokens
            }
        return usage

    def _completion(self, body, reply: Reply) -> dict:
        message: dict[str, Any] = {"role": "assistant", "content": reply.content}
        if reply.reasoning is not None:
            message[reply.reasoning_field] = reply.reasoning
        if reply.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in reply.tool_calls
            ]
        return {
            "id": "chatcmpl-fake",
            "object": "chat.completion",
            "created": 0,
            "model": body.get("model", "fake-model"),
            "choices": [
                {"index": 0, "message": message, "finish_reason": reply.finish_reason}
            ],
            "usage": self._usage(reply),
        }

    def _sse(self, body, reply: Reply) -> bytes:
        model = body.get("model", "fake-model")

        def chunk(delta=None, finish=None, usage=None, choices=True):
            payload = {
                "id": "chatcmpl-fake",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model,
                "choices": (
                    [{"index": 0, "delta": delta or {}, "finish_reason": finish}]
                    if choices
                    else []
                ),
            }
            if usage is not None:
                payload["usage"] = usage
            return f"data: {json.dumps(payload)}\n\n"

        out = [chunk({"role": "assistant", "content": ""})]
        if reply.reasoning:
            for piece in _pieces(reply.reasoning):
                out.append(chunk({reply.reasoning_field: piece}))
        for piece in _pieces(reply.content):
            out.append(chunk({"content": piece}))
        for i, tc in enumerate(reply.tool_calls):
            args = tc["arguments"]
            half = len(args) // 2
            out.append(
                chunk(
                    {
                        "tool_calls": [
                            {
                                "index": i,
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": args[:half],
                                },
                            }
                        ]
                    }
                )
            )
            out.append(
                chunk(
                    {
                        "tool_calls": [
                            {"index": i, "function": {"arguments": args[half:]}}
                        ]
                    }
                )
            )
        out.append(chunk({}, finish=reply.finish_reason))
        include_usage = (body.get("stream_options") or {}).get("include_usage")
        if include_usage and reply.usage is not None:
            out.append(chunk(usage=self._usage(reply), choices=False))
        out.append("data: [DONE]\n\n")
        return "".join(out).encode()


def _pieces(text: str, size: int = 4) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] if text else []


def _embed(text: str) -> list[float]:
    """Deterministic toy embedding: letter frequencies (a-z)."""
    counts = [0.0] * 26
    for ch in text.lower():
        if "a" <= ch <= "z":
            counts[ord(ch) - 97] += 1
    return counts
