"""
Tests for Pydantic v2 request/response schemas in models/schemas.py.
"""

import pytest
from pydantic import ValidationError

from llmwatch.models.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)

# ── RegisterRequest ──────────────────────────────────────────────────────


class TestRegisterRequest:
    def test_valid(self):
        r = RegisterRequest(email="a@b.com", password="securepass", company_name="Acme")
        assert r.email == "a@b.com"
        assert r.company_name == "Acme"

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(email="a@b.com", password="short", company_name="X")
        assert (
            "min_length" in str(exc_info.value).lower()
            or "at least" in str(exc_info.value).lower()
        )

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="not-an-email", password="securepass", company_name="X"
            )

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.com",
                password="securepass",
                company_name="X",
                is_admin=True,  # extra field
            )


# ── LoginRequest ─────────────────────────────────────────────────────────


class TestLoginRequest:
    def test_valid(self):
        r = LoginRequest(email="user@example.com", password="p")
        assert r.email == "user@example.com"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.com", password="p", token="sneaky")


# ── TokenResponse ────────────────────────────────────────────────────────


class TestTokenResponse:
    def test_valid(self):
        t = TokenResponse(access_token="abc", token_type="bearer", expires_in=3600)
        assert t.access_token == "abc"
        assert t.expires_in == 3600


# ── ChatCompletionRequest ────────────────────────────────────────────────


class TestChatCompletionRequest:
    def test_valid_qwen(self):
        r = ChatCompletionRequest(prompt="hello", model="qwen")
        assert r.thinking_mode is False

    def test_valid_gemini_thinking(self):
        r = ChatCompletionRequest(prompt="explain", model="gemini", thinking_mode=True)
        assert r.thinking_mode is True

    def test_any_model_reference_is_accepted_at_the_schema_level(self):
        # Whether it exists is checked against the workspace registry (400).
        assert ChatCompletionRequest(prompt="hi", model="OpenAI/gpt-x").model

    def test_empty_model_rejected(self):
        with pytest.raises(ValidationError):
            ChatCompletionRequest(prompt="hi", model="")

    def test_prompt_too_long(self):
        with pytest.raises(ValidationError):
            ChatCompletionRequest(prompt="x" * 50_001, model="qwen")

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            ChatCompletionRequest(prompt="hi", model="qwen", foo="bar")

    def test_prompt_or_messages_required(self):
        with pytest.raises(ValidationError):
            ChatCompletionRequest(model="qwen")

    def test_messages_history(self):
        r = ChatCompletionRequest(
            model="qwen",
            messages=[
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            temperature=0.2,
        )
        assert [m.role for m in r.messages] == ["user", "assistant"]

    def test_unknown_message_role_rejected(self):
        with pytest.raises(ValidationError):
            ChatCompletionRequest(
                model="qwen", messages=[{"role": "tool", "content": "x"}]
            )

    @pytest.mark.parametrize("field,value", [("temperature", 3), ("top_p", 0)])
    def test_sampling_params_are_bounded(self, field, value):
        with pytest.raises(ValidationError):
            ChatCompletionRequest(prompt="hi", model="qwen", **{field: value})


# ── ChatCompletionResponse ───────────────────────────────────────────────


class TestChatCompletionResponse:
    def test_valid(self):
        r = ChatCompletionResponse(
            response="Hello!",
            latency_ms=123.4,
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.001,
            model_used="qwen",
            thinking_mode=False,
        )
        assert r.thinking_content is None

    def test_with_thinking_content(self):
        r = ChatCompletionResponse(
            response="Hello!",
            thinking_content="I thought about it",
            latency_ms=100.0,
            input_tokens=5,
            output_tokens=15,
            cost_usd=0.0,
            model_used="gemini",
            thinking_mode=True,
        )
        assert r.thinking_content == "I thought about it"
