"""
Tests for the TracingCallbackHandler and AgentEvent/AgentRunSummary models.

WHY: The tracing system is the backbone of agent observability. We test that:
- AgentEvent is constructed correctly with auto-generated timestamps
- TracingCallbackHandler emits correct events for each callback type
- Events are pushed to the async queue for SSE streaming
- build_summary and build_trace_data produce correct output
"""

import asyncio
import time
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from services.tracing_service import AgentEvent, AgentRunSummary, TracingCallbackHandler


# ── AgentEvent Model Tests ─────────────────────────────────


class TestAgentEvent:
    """Tests for the AgentEvent Pydantic model."""

    def test_event_auto_generates_timestamp(self):
        """Verify AgentEvent generates a UTC ISO timestamp when not provided."""
        event = AgentEvent(
            run_id="test-run",
            step_index=0,
            event_type="run_start",
            content="Starting",
        )
        assert event.timestamp != ""
        # Should be parseable as an ISO datetime
        parsed = datetime.fromisoformat(event.timestamp)
        assert parsed.tzinfo is not None

    def test_event_preserves_provided_timestamp(self):
        """Verify AgentEvent uses a provided timestamp."""
        ts = "2025-01-01T00:00:00+00:00"
        event = AgentEvent(
            run_id="test-run",
            step_index=0,
            event_type="thinking",
            content="Thinking...",
            timestamp=ts,
        )
        assert event.timestamp == ts

    def test_event_optional_fields_default_to_none(self):
        """Verify optional fields default to None."""
        event = AgentEvent(
            run_id="test-run",
            step_index=0,
            event_type="thinking",
            content="Content",
        )
        assert event.tool_name is None
        assert event.tool_input is None
        assert event.latency_ms is None
        assert event.tokens is None
        assert event.cost_usd is None

    def test_event_with_tool_fields(self):
        """Verify tool fields are preserved."""
        event = AgentEvent(
            run_id="test-run",
            step_index=1,
            event_type="tool_call",
            content="Calling web_search",
            tool_name="web_search",
            tool_input="AI news 2025",
            latency_ms=150.5,
        )
        assert event.tool_name == "web_search"
        assert event.tool_input == "AI news 2025"
        assert event.latency_ms == 150.5

    def test_event_serialization(self):
        """Verify AgentEvent serializes to JSON correctly."""
        event = AgentEvent(
            run_id="test-run",
            step_index=0,
            event_type="final_answer",
            content="The answer is 42",
        )
        json_str = event.model_dump_json()
        assert "test-run" in json_str
        assert "final_answer" in json_str
        assert "The answer is 42" in json_str


# ── AgentRunSummary Model Tests ────────────────────────────


class TestAgentRunSummary:
    """Tests for the AgentRunSummary Pydantic model."""

    def test_summary_construction(self):
        """Verify AgentRunSummary stores all fields correctly."""
        summary = AgentRunSummary(
            run_id="test-run",
            total_steps=5,
            total_latency_ms=1234.56,
            total_tokens=500,
            total_cost_usd=0.001,
            tools_used=["web_search", "code_execute"],
            model_used="gemini",
            success=True,
        )
        assert summary.total_steps == 5
        assert summary.total_latency_ms == 1234.56
        assert summary.tools_used == ["web_search", "code_execute"]
        assert summary.success is True


# ── TracingCallbackHandler Tests ───────────────────────────


class TestTracingCallbackHandler:
    """Tests for the LangChain callback handler that powers tracing."""

    def _make_handler(self, run_id: str = "test-run") -> TracingCallbackHandler:
        """Helper to create a handler with a known run_id."""
        return TracingCallbackHandler(run_id=run_id, model_name="gemini")

    def test_handler_initializes_correctly(self):
        """Verify handler starts with clean state."""
        handler = self._make_handler()
        assert handler.run_id == "test-run"
        assert handler.model_name == "gemini"
        assert handler.step_index == 0
        assert handler.events == []
        assert handler._total_tokens == 0

    def test_emit_pushes_to_events_and_queue(self):
        """Verify _emit adds to both the events list and the async queue."""
        handler = self._make_handler()
        event = AgentEvent(
            run_id="test-run",
            step_index=0,
            event_type="thinking",
            content="test",
        )

        handler._emit(event)

        assert len(handler.events) == 1
        assert handler.events[0] is event
        assert not handler.event_queue.empty()

    def test_on_llm_start_records_start_time(self):
        """Verify on_llm_start sets the LLM start timestamp."""
        handler = self._make_handler()
        handler.on_llm_start(
            serialized={},
            prompts=["test"],
            run_id=uuid4(),
        )
        assert handler._llm_start_time is not None

    def test_on_llm_end_emits_thinking_event(self):
        """Verify on_llm_end emits a 'thinking' event with content and latency."""
        from langchain_core.outputs import LLMResult, Generation

        handler = self._make_handler()
        handler._llm_start_time = time.perf_counter() - 0.1  # 100ms ago

        result = LLMResult(
            generations=[[Generation(text="I think we should search")]],
            llm_output={"token_usage": {"total_tokens": 42}},
        )

        handler.on_llm_end(response=result, run_id=uuid4())

        assert len(handler.events) == 1
        event = handler.events[0]
        assert event.event_type == "thinking"
        assert "search" in event.content
        assert event.latency_ms is not None
        assert event.latency_ms > 0
        assert event.tokens == 42
        assert handler._total_tokens == 42
        assert handler.step_index == 1

    def test_on_llm_error_emits_error_event(self):
        """Verify on_llm_error emits an 'error' event."""
        handler = self._make_handler()
        handler.on_llm_error(
            error=RuntimeError("LLM timeout"),
            run_id=uuid4(),
        )

        assert len(handler.events) == 1
        assert handler.events[0].event_type == "error"
        assert "LLM timeout" in handler.events[0].content

    def test_on_agent_action_emits_tool_call_event(self):
        """Verify on_agent_action emits a 'tool_call' event with correct tool metadata."""
        from langchain_core.agents import AgentAction

        handler = self._make_handler()
        action = AgentAction(
            tool="web_search",
            tool_input="latest AI papers",
            log="",
        )

        handler.on_agent_action(action=action, run_id=uuid4())

        assert len(handler.events) == 1
        event = handler.events[0]
        assert event.event_type == "tool_call"
        assert event.tool_name == "web_search"
        assert "latest AI papers" in (event.tool_input or "")
        assert "web_search" in handler._tools_used

    def test_on_agent_action_deduplicates_tools_used(self):
        """Verify tools_used doesn't duplicate the same tool."""
        from langchain_core.agents import AgentAction

        handler = self._make_handler()
        action = AgentAction(tool="web_search", tool_input="query1", log="")
        handler.on_agent_action(action=action, run_id=uuid4())
        handler.on_agent_action(action=action, run_id=uuid4())

        assert handler._tools_used == ["web_search"]

    def test_on_tool_end_emits_tool_result_event(self):
        """Verify on_tool_end emits a 'tool_result' event with latency."""
        from langchain_core.agents import AgentAction

        handler = self._make_handler()
        # First emit a tool_call so tool_name can be extracted
        action = AgentAction(tool="code_execute", tool_input="print(1)", log="")
        handler.on_agent_action(action=action, run_id=uuid4())
        handler._tool_start_time = time.perf_counter() - 0.05  # 50ms ago

        handler.on_tool_end(output="1", run_id=uuid4())

        # Should have tool_call + tool_result
        assert len(handler.events) == 2
        result_event = handler.events[1]
        assert result_event.event_type == "tool_result"
        assert result_event.content == "1"
        assert result_event.tool_name == "code_execute"
        assert result_event.latency_ms is not None

    def test_on_tool_error_emits_error_event(self):
        """Verify on_tool_error emits an 'error' event."""
        handler = self._make_handler()
        handler.on_tool_error(
            error=RuntimeError("Tool crashed"),
            run_id=uuid4(),
        )
        assert handler.events[0].event_type == "error"
        assert "Tool crashed" in handler.events[0].content

    def test_on_agent_finish_emits_final_answer(self):
        """Verify on_agent_finish emits a 'final_answer' event."""
        from langchain_core.agents import AgentFinish

        handler = self._make_handler()
        finish = AgentFinish(
            return_values={"output": "The answer is 42."},
            log="",
        )

        handler.on_agent_finish(finish=finish, run_id=uuid4())

        assert len(handler.events) == 1
        assert handler.events[0].event_type == "final_answer"
        assert "42" in handler.events[0].content

    def test_on_chain_error_emits_error(self):
        """Verify on_chain_error emits an 'error' event."""
        handler = self._make_handler()
        handler.on_chain_error(
            error=RuntimeError("Chain broke"),
            run_id=uuid4(),
        )
        assert handler.events[0].event_type == "error"
        assert "Chain broke" in handler.events[0].content

    def test_build_summary(self):
        """Verify build_summary produces correct aggregated metrics."""
        handler = self._make_handler()
        handler.step_index = 5
        handler._total_tokens = 200
        handler._total_cost = 0.0005
        handler._tools_used = ["web_search", "code_execute"]

        summary = handler.build_summary(success=True)

        assert summary.run_id == "test-run"
        assert summary.total_steps == 5
        assert summary.total_tokens == 200
        assert summary.total_cost_usd == 0.0005
        assert summary.tools_used == ["web_search", "code_execute"]
        assert summary.model_used == "gemini"
        assert summary.success is True
        assert summary.total_latency_ms > 0

    def test_build_trace_data(self):
        """Verify build_trace_data produces correct dict for DynamoDB storage."""
        from langchain_core.agents import AgentFinish

        handler = self._make_handler()
        # Simulate a minimal execution
        finish = AgentFinish(return_values={"output": "Done."}, log="")
        handler.on_agent_finish(finish=finish, run_id=uuid4())

        trace = handler.build_trace_data(
            prompt="What is 2+2?",
            tools_enabled=["code_execute"],
            success=True,
        )

        assert trace["run_id"] == "test-run"
        assert trace["prompt"] == "What is 2+2?"
        assert trace["model_used"] == "gemini"
        assert trace["tools_enabled"] == ["code_execute"]
        assert trace["success"] is True
        assert trace["final_answer"] == "Done."
        assert len(trace["steps"]) == 1
        assert trace["steps"][0]["event_type"] == "final_answer"

    def test_signal_done_sends_sentinel(self):
        """Verify signal_done pushes None to the queue as a sentinel."""
        handler = self._make_handler()
        handler.signal_done()

        item = handler.event_queue.get_nowait()
        assert item is None

    def test_content_truncation_in_on_llm_end(self):
        """Verify long LLM output is truncated to 2000 chars."""
        from langchain_core.outputs import LLMResult, Generation

        handler = self._make_handler()
        long_text = "x" * 5000

        result = LLMResult(
            generations=[[Generation(text=long_text)]],
            llm_output=None,
        )

        handler.on_llm_end(response=result, run_id=uuid4())

        assert len(handler.events[0].content) == 2000
