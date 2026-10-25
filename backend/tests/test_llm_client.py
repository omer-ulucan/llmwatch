"""
Tests for the OpenAI-compatible LLM client, against a fake provider (no network).
"""

import httpx
import pytest

import tests.fake_llm as fake_llm_module
from llmwatch.llm import LLMError, Usage, collect, compute_cost, split_reasoning
from tests.fake_llm import FakeProvider, Reply

MESSAGES = [{"role": "user", "content": "hi"}]


@pytest.fixture
def fake():
    return FakeProvider(models=["b-model", "a-model"])


# ── chat ────────────────────────────────────────────────────


async def test_chat_returns_content_and_reported_usage(fake):
    fake.reply("Hello there", usage=(17, 4))
    result = await fake.client().chat("a-model", MESSAGES)

    assert result.content == "Hello there"
    assert result.usage == Usage(
        input_tokens=17, output_tokens=4, reasoning_tokens=0, reported=True
    )
    assert result.finish_reason == "stop"
    assert result.model == "a-model"
    assert result.latency_ms >= 0


async def test_missing_usage_is_flagged_not_guessed(fake):
    """Regression: Gemini usage used to fall back to len(text) // 4."""
    fake.reply("x" * 400, usage=None)
    result = await fake.client().chat("a-model", MESSAGES)

    assert result.usage.reported is False
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0


async def test_reasoning_tokens_are_reported(fake):
    fake.reply("42", usage=(10, 50), reasoning_tokens=45)
    result = await fake.client().chat("a-model", MESSAGES)
    assert result.usage.reasoning_tokens == 45


@pytest.mark.parametrize("field_name", ["reasoning_content", "reasoning"])
async def test_reasoning_field_is_surfaced(fake, field_name):
    fake.reply("42", reasoning="Let me think", reasoning_field=field_name)
    result = await fake.client().chat("a-model", MESSAGES)

    assert result.content == "42"
    assert result.reasoning == "Let me think"


@pytest.mark.parametrize("tag", ["think", "thought"])
async def test_inline_think_tags_are_split_out(fake, tag):
    fake.reply(f"<{tag}>step 1\nstep 2</{tag}>\n\nThe answer is 4.")
    result = await fake.client().chat("a-model", MESSAGES)

    assert result.content == "The answer is 4."
    assert result.reasoning == "step 1\nstep 2"


async def test_no_reasoning_means_none_not_a_placeholder(fake):
    """Regression: Gemini "thinking" used to be a hardcoded string."""
    fake.reply("plain answer")
    result = await fake.client().chat("a-model", MESSAGES)
    assert result.reasoning is None


async def test_params_are_passed_through_and_none_dropped(fake):
    await fake.client().chat(
        "a-model",
        MESSAGES,
        temperature=0,
        max_tokens=64,
        top_p=None,
        reasoning_effort="high",
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    body = fake.requests[-1]
    assert body["model"] == "a-model"
    assert body["messages"] == MESSAGES
    assert body["temperature"] == 0
    assert body["max_tokens"] == 64
    assert "top_p" not in body
    assert body["reasoning_effort"] == "high"
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


async def test_api_key_and_base_url_are_used(fake):
    await fake.client().chat("a-model", MESSAGES)
    assert fake.paths[-1] == "/v1/chat/completions"
    assert fake.headers[-1]["authorization"] == "Bearer sk-fake"


async def test_keyless_local_provider_still_sends_a_placeholder(fake):
    from llmwatch.llm import LLMClient, ProviderConfig

    client = LLMClient(
        ProviderConfig(name="ollama", base_url="http://fake.local/v1", api_key=None),
        http_client=fake.http_client(),
    )
    await client.chat("a-model", MESSAGES)
    assert fake.headers[-1]["authorization"] == "Bearer not-needed"


async def test_tool_calls_are_parsed(fake):
    fake.call_tool("web_search", {"query": "llmwatch"}, call_id="call_9")
    result = await fake.client().chat(
        "a-model",
        MESSAGES,
        tools=[{"type": "function", "function": {"name": "web_search"}}],
    )
    (call,) = result.tool_calls
    assert call.id == "call_9"
    assert call.name == "web_search"
    assert call.arguments == '{"query": "llmwatch"}'
    assert result.finish_reason == "tool_calls"


# ── errors ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "status,kind,retryable",
    [
        (429, "rate_limit", True),
        (500, "server", True),
        (502, "server", True),
        (503, "server", True),
        (400, "bad_request", False),
        (422, "bad_request", False),
        (401, "auth", False),
        (403, "permission", False),
        (404, "not_found", False),
    ],
)
async def test_http_errors_are_normalized(fake, status, kind, retryable):
    fake.fail(status, message="nope")
    with pytest.raises(LLMError) as info:
        await fake.client().chat("a-model", MESSAGES)
    err = info.value
    assert err.kind == kind
    assert err.status == status
    assert err.retryable is retryable
    assert err.provider == "fake"
    assert err.message == "nope"


@pytest.mark.parametrize(
    "header,expected",
    [("7", 7.0), ("0.5", 0.5), ("Wed, 21 Oct 2015 07:28:00 GMT", 0.0)],
)
async def test_retry_after_is_parsed(fake, header, expected):
    fake.fail(429, retry_after=header)
    with pytest.raises(LLMError) as info:
        await fake.client().chat("a-model", MESSAGES)
    assert info.value.retry_after_s == pytest.approx(expected)


async def test_retry_after_ms_takes_precedence(fake):
    fake.queue.append(
        Reply(
            status=429,
            error_body={"error": {"message": "slow down"}},
            headers={"retry-after-ms": "1500", "retry-after": "9"},
        )
    )
    with pytest.raises(LLMError) as info:
        await fake.client().chat("a-model", MESSAGES)
    assert info.value.retry_after_s == pytest.approx(1.5)


async def test_timeouts_are_retryable(fake):
    fake.raise_(httpx.ReadTimeout("slow"))
    with pytest.raises(LLMError) as info:
        await fake.client().chat("a-model", MESSAGES)
    assert info.value.kind == "timeout"
    assert info.value.retryable


async def test_connection_errors_are_retryable(fake):
    fake.raise_(httpx.ConnectError("refused"))
    with pytest.raises(LLMError) as info:
        await fake.client().chat("a-model", MESSAGES)
    assert info.value.kind == "connection"
    assert info.value.retryable


async def test_sdk_does_not_retry_on_its_own(fake):
    """Retries belong to callers (the eval runner backs off per provider)."""
    fake.fail(503)
    fake.reply("would succeed on a silent retry")
    with pytest.raises(LLMError):
        await fake.client().chat("a-model", MESSAGES)
    assert len(fake.requests) == 1


# ── streaming ───────────────────────────────────────────────


async def test_stream_yields_deltas_then_usage_and_done(fake):
    fake.reply("Hello streaming world", usage=(9, 3))
    chunks = [c async for c in fake.client().stream("a-model", MESSAGES)]

    deltas = [c.text for c in chunks if c.type == "delta"]
    assert len(deltas) > 1
    assert "".join(deltas) == "Hello streaming world"
    assert [c.type for c in chunks[-2:]] == ["usage", "done"]
    assert chunks[-2].usage.input_tokens == 9
    assert chunks[-1].finish_reason == "stop"
    assert fake.requests[-1]["stream_options"] == {"include_usage": True}


async def test_stream_usage_can_be_disabled_per_provider(fake):
    fake.reply("hi")
    result = await collect(fake.client(stream_usage=False).stream("a-model", MESSAGES))
    assert "stream_options" not in fake.requests[-1]
    assert result["usage"] is None


async def test_stream_reasoning_field(fake):
    fake.reply("4", reasoning="2 plus 2 is 4")
    result = await collect(fake.client().stream("a-model", MESSAGES))
    assert result["content"] == "4"
    assert result["reasoning"] == "2 plus 2 is 4"


async def test_stream_inline_think_tags(fake, monkeypatch):
    # vLLM/llama.cpp emit the tags as whole tokens; content splits around them.
    monkeypatch.setattr(
        fake_llm_module,
        "_pieces",
        lambda text, size=4: ["<think>", "ab", "cd", "</think>", "ans", "wer"],
    )
    fake.reply("<think>abcd</think>answer")
    result = await collect(fake.client().stream("a-model", MESSAGES))
    assert result["content"] == "answer"
    assert result["reasoning"] == "abcd"


async def test_stream_assembles_tool_calls(fake):
    fake.call_tool("fetch_url", {"url": "https://example.com"})
    result = await collect(fake.client().stream("a-model", MESSAGES))
    (call,) = result["tool_calls"]
    assert call.name == "fetch_url"
    assert call.arguments == '{"url": "https://example.com"}'
    assert result["finish_reason"] == "tool_calls"


async def test_stream_errors_are_normalized(fake):
    fake.fail(429, retry_after="3")
    with pytest.raises(LLMError) as info:
        async for _ in fake.client().stream("a-model", MESSAGES):
            pass
    assert info.value.kind == "rate_limit"
    assert info.value.retry_after_s == 3.0


# ── models and embeddings ───────────────────────────────────


async def test_list_models_is_sorted(fake):
    assert await fake.client().list_models() == ["a-model", "b-model"]
    assert fake.paths[-1] == "/v1/models"


async def test_embeddings_are_returned_in_input_order(fake):
    vectors = await fake.client().embed("emb", ["aaa", "bbb"])
    assert vectors[0][0] == 3.0 and vectors[0][1] == 0.0
    assert vectors[1][1] == 3.0


# ── helpers ─────────────────────────────────────────────────


def test_split_reasoning_without_tags():
    assert split_reasoning("hello") == ("hello", None)


def test_compute_cost_per_million_tokens():
    usage = Usage(input_tokens=2_000, output_tokens=500, reported=True)
    assert compute_cost(usage, 0.50, 3.00) == pytest.approx(0.001 + 0.0015)


def test_compute_cost_unpriced_model_is_none():
    assert compute_cost(Usage(input_tokens=10, output_tokens=10), None, None) is None


def test_compute_cost_free_model_is_zero():
    assert compute_cost(Usage(input_tokens=10, output_tokens=10), 0.0, 0.0) == 0.0
