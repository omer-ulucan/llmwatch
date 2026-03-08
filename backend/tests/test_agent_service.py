"""
Tests for the AgentService orchestration layer.

WHY: The AgentService is the core agent execution engine. We test:
- build_tools factory correctly selects and binds tools
- AgentService._get_langchain_llm extracts the LLM from strategies
- The full async event generator yields the expected event sequence
"""

from unittest.mock import MagicMock, patch, AsyncMock
from typing import List

import pytest

from services.tracing_service import AgentEvent


def _agent_executor_available() -> bool:
    """Check if AgentExecutor can be imported (fails on Python 3.14)."""
    try:
        from langchain.agents import AgentExecutor, create_react_agent  # noqa: F401

        return True
    except (ImportError, Exception):
        return False


_skip_agent = pytest.mark.skipif(
    not _agent_executor_available(),
    reason="langchain.agents.AgentExecutor not importable on this Python version",
)


# ── build_tools Tests ──────────────────────────────────────


@_skip_agent
class TestBuildTools:
    """Tests for the tool factory function."""

    def test_build_tools_all(self):
        """Verify build_tools returns all 4 tools when all are requested."""
        from services.agent_service import build_tools

        tools = build_tools(
            "company-123", ["web_search", "code_execute", "db_query", "doc_analyze"]
        )
        assert len(tools) == 4

        tool_names = [t.name for t in tools]
        assert "web_search" in tool_names
        assert "execute_python" in tool_names  # code_execute maps to execute_python
        assert "query_llm_logs" in tool_names  # db_query maps to query_llm_logs
        assert "analyze_document" in tool_names

    def test_build_tools_subset(self):
        """Verify build_tools returns only requested tools."""
        from services.agent_service import build_tools

        tools = build_tools("company-123", ["web_search"])
        assert len(tools) == 1
        assert tools[0].name == "web_search"

    def test_build_tools_empty(self):
        """Verify build_tools returns empty list for no tools."""
        from services.agent_service import build_tools

        tools = build_tools("company-123", [])
        assert tools == []

    def test_build_tools_ignores_unknown(self):
        """Verify build_tools silently ignores unknown tool names."""
        from services.agent_service import build_tools

        tools = build_tools("company-123", ["web_search", "nonexistent_tool"])
        assert len(tools) == 1
        assert tools[0].name == "web_search"

    def test_build_tools_db_query_is_company_scoped(self):
        """Verify the db_query tool is factory-created with the company_id."""
        from services.agent_service import build_tools

        tools_a = build_tools("company-A", ["db_query"])
        tools_b = build_tools("company-B", ["db_query"])

        # Each should be a different tool instance (factory creates new each time)
        assert tools_a[0] is not tools_b[0]


# ── AgentService Unit Tests ────────────────────────────────


@_skip_agent
class TestAgentServiceGetLLM:
    """Tests for the _get_langchain_llm method."""

    def test_get_langchain_llm_valid_model(self):
        """Verify _get_langchain_llm returns the strategy's client for valid models."""
        from services.agent_service import AgentService

        mock_llm_service = MagicMock()
        mock_client = MagicMock()
        mock_strategy = MagicMock()
        mock_strategy.client = mock_client
        mock_llm_service.strategies = {"gemini": mock_strategy}

        service = AgentService(mock_llm_service)
        result = service._get_langchain_llm("gemini")

        assert result is mock_client

    def test_get_langchain_llm_invalid_model(self):
        """Verify _get_langchain_llm raises ValueError for unknown models."""
        from services.agent_service import AgentService

        mock_llm_service = MagicMock()
        mock_llm_service.strategies = {}

        service = AgentService(mock_llm_service)

        with pytest.raises(ValueError, match="Unsupported model"):
            service._get_langchain_llm("gpt-4")


# ── AgentService.run_agent Integration Test ────────────────


@_skip_agent
class TestAgentServiceRunAgent:
    """Tests for the agent execution async generator."""

    @pytest.mark.asyncio
    async def test_run_agent_yields_run_start_event(self):
        """Verify run_agent yields a run_start event as its first event."""
        from services.agent_service import AgentService

        mock_llm_service = MagicMock()
        mock_client = MagicMock()
        mock_strategy = MagicMock()
        mock_strategy.client = mock_client
        mock_llm_service.strategies = {"gemini": mock_strategy}

        service = AgentService(mock_llm_service)

        # Mock create_react_agent and AgentExecutor to avoid needing real LLM
        with (
            patch("services.agent_service.create_react_agent") as mock_create,
            patch("services.agent_service.AgentExecutor") as MockExecutor,
        ):
            mock_executor_instance = MagicMock()
            # Simulate a simple agent run that returns immediately
            mock_executor_instance.invoke.return_value = {
                "input": "test",
                "output": "test answer",
                "intermediate_steps": [],
            }
            MockExecutor.return_value = mock_executor_instance

            events: List[AgentEvent] = []
            async for event in service.run_agent(
                prompt="test prompt",
                model="gemini",
                company_id="test-company",
                tools=["web_search"],
                max_iterations=3,
            ):
                events.append(event)

        # Should have at least run_start and run_end
        assert len(events) >= 2
        assert events[0].event_type == "run_start"
        assert events[-1].event_type == "run_end"
        assert "gemini" in events[0].content

    @pytest.mark.asyncio
    async def test_run_agent_run_end_contains_summary_json(self):
        """Verify the run_end event content is valid JSON with summary fields."""
        import json
        from services.agent_service import AgentService

        mock_llm_service = MagicMock()
        mock_strategy = MagicMock()
        mock_strategy.client = MagicMock()
        mock_llm_service.strategies = {"qwen": mock_strategy}

        service = AgentService(mock_llm_service)

        with (
            patch("services.agent_service.create_react_agent"),
            patch("services.agent_service.AgentExecutor") as MockExecutor,
        ):
            mock_executor_instance = MagicMock()
            mock_executor_instance.invoke.return_value = {
                "input": "test",
                "output": "answer",
                "intermediate_steps": [],
            }
            MockExecutor.return_value = mock_executor_instance

            events: List[AgentEvent] = []
            async for event in service.run_agent(
                prompt="test",
                model="qwen",
                company_id="company-x",
                tools=[],
                max_iterations=5,
            ):
                events.append(event)

        run_end = events[-1]
        assert run_end.event_type == "run_end"

        summary_data = json.loads(run_end.content)
        assert "total_steps" in summary_data
        assert "total_latency_ms" in summary_data
        assert "model_used" in summary_data
        assert summary_data["model_used"] == "qwen"
        assert summary_data["success"] is True
