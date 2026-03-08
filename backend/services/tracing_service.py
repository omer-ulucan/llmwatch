"""
Module: tracing_service.py
Purpose: Provides the TracingCallbackHandler for LangChain agent execution and AgentEvent data model.
WHY: By extending LangChain's BaseCallbackHandler, we capture every agent step (thinking, tool calls,
tool results, final answers) as structured events. These events serve double duty: streamed to the
frontend via SSE in real-time AND persisted to DynamoDB for the trace viewer.
"""

import time
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal, Union
from uuid import UUID

from pydantic import BaseModel
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.outputs import LLMResult

from config import logger


class AgentEvent(BaseModel):
    """
    Represents a single step in an agent execution trace.
    WHY: This is the universal data contract between the backend (callback handler),
    the SSE stream, and the frontend trace viewer.
    """

    run_id: str
    step_index: int
    event_type: Literal[
        "run_start",
        "thinking",
        "tool_call",
        "tool_result",
        "final_answer",
        "error",
        "run_end",
    ]
    content: str
    tool_name: Optional[str] = None
    tool_input: Optional[str] = None
    latency_ms: Optional[float] = None
    tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    timestamp: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AgentRunSummary(BaseModel):
    """Summary metrics emitted as the final 'run_end' event payload."""

    run_id: str
    total_steps: int
    total_latency_ms: float
    total_tokens: int
    total_cost_usd: float
    tools_used: List[str]
    model_used: str
    success: bool


class TracingCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that captures agent execution events.

    WHY: This is the core observability integration. Instead of a separate tracing SDK,
    we hook directly into LangChain's callback system to capture every step as it happens.
    Events are accumulated in a list and also pushed to an asyncio.Queue for real-time
    SSE streaming.
    """

    def __init__(self, run_id: str, model_name: str):
        super().__init__()
        self.run_id = run_id
        self.model_name = model_name
        self.events: List[AgentEvent] = []
        self.step_index = 0
        self._llm_start_time: Optional[float] = None
        self._tool_start_time: Optional[float] = None
        self._total_tokens = 0
        self._total_cost = 0.0
        self._tools_used: List[str] = []
        self._run_start_time = time.perf_counter()

        # WHY: asyncio.Queue bridges sync callbacks → async SSE generator.
        # LangChain callbacks are sync, but FastAPI's StreamingResponse needs async.
        self.event_queue: asyncio.Queue[Optional[AgentEvent]] = asyncio.Queue()

    def _emit(self, event: AgentEvent) -> None:
        """Record event and push to the async queue for SSE streaming."""
        self.events.append(event)
        try:
            self.event_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"Event queue full, dropping event: {event.event_type}")

    # ── LLM callbacks ──────────────────────────────────────

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when the LLM starts generating. Record start time for latency tracking."""
        self._llm_start_time = time.perf_counter()

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """
        Called when the LLM finishes generating.
        WHY: We emit a 'thinking' event here because in ReAct, each LLM call represents
        the agent's reasoning step (the 'Thought:' in ReAct format).
        """
        latency_ms = None
        if self._llm_start_time is not None:
            latency_ms = (time.perf_counter() - self._llm_start_time) * 1000
            self._llm_start_time = None

        # Extract token counts from LLM response metadata
        tokens = 0
        if response.llm_output:
            token_usage = response.llm_output.get("token_usage", {})
            tokens = token_usage.get("total_tokens", 0)
            if tokens == 0:
                tokens = token_usage.get("prompt_tokens", 0) + token_usage.get(
                    "completion_tokens", 0
                )
        self._total_tokens += tokens

        # Extract the actual text content from the LLM response
        content = ""
        if response.generations and response.generations[0]:
            content = response.generations[0][0].text

        event = AgentEvent(
            run_id=self.run_id,
            step_index=self.step_index,
            event_type="thinking",
            content=content[:2000],  # Truncate to keep SSE payloads manageable
            latency_ms=latency_ms,
            tokens=tokens,
        )
        self.step_index += 1
        self._emit(event)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when the LLM errors. Emit an error event."""
        event = AgentEvent(
            run_id=self.run_id,
            step_index=self.step_index,
            event_type="error",
            content=f"LLM error: {str(error)[:500]}",
        )
        self.step_index += 1
        self._emit(event)

    # ── Agent action callbacks (tool calls) ────────────────

    def on_agent_action(
        self,
        action: AgentAction,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """
        Called when the agent decides to use a tool.
        WHY: This captures the agent's decision (tool name + input) before the tool executes.
        """
        self._tool_start_time = time.perf_counter()
        tool_name = action.tool
        tool_input = str(action.tool_input)[:1000]

        if tool_name not in self._tools_used:
            self._tools_used.append(tool_name)

        event = AgentEvent(
            run_id=self.run_id,
            step_index=self.step_index,
            event_type="tool_call",
            content=f"Calling tool: {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input,
        )
        self.step_index += 1
        self._emit(event)

    # ── Tool callbacks ─────────────────────────────────────

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool finishes execution. Captures the tool's output."""
        latency_ms = None
        if self._tool_start_time is not None:
            latency_ms = (time.perf_counter() - self._tool_start_time) * 1000
            self._tool_start_time = None

        # Determine tool name from the most recent tool_call event
        tool_name = None
        for evt in reversed(self.events):
            if evt.event_type == "tool_call" and evt.tool_name:
                tool_name = evt.tool_name
                break

        event = AgentEvent(
            run_id=self.run_id,
            step_index=self.step_index,
            event_type="tool_result",
            content=str(output)[:2000],  # Truncate large tool outputs
            tool_name=tool_name,
            latency_ms=latency_ms,
        )
        self.step_index += 1
        self._emit(event)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool errors. Emit an error event."""
        event = AgentEvent(
            run_id=self.run_id,
            step_index=self.step_index,
            event_type="error",
            content=f"Tool error: {str(error)[:500]}",
        )
        self.step_index += 1
        self._emit(event)

    # ── Agent finish callback ──────────────────────────────

    def on_agent_finish(
        self,
        finish: AgentFinish,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """
        Called when the agent produces its final answer.
        WHY: This is the terminal event — after this, we emit a run_end summary and signal
        the SSE stream to close.
        """
        final_output = finish.return_values.get("output", str(finish.return_values))

        event = AgentEvent(
            run_id=self.run_id,
            step_index=self.step_index,
            event_type="final_answer",
            content=final_output[:5000],
        )
        self.step_index += 1
        self._emit(event)

    # ── Chain error callback ───────────────────────────────

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when the agent chain itself errors (not a tool or LLM error)."""
        event = AgentEvent(
            run_id=self.run_id,
            step_index=self.step_index,
            event_type="error",
            content=f"Agent error: {str(error)[:500]}",
        )
        self.step_index += 1
        self._emit(event)

    # ── Summary helpers ────────────────────────────────────

    def build_summary(self, success: bool) -> AgentRunSummary:
        """
        Build the final run summary after the agent completes.
        WHY: This is emitted as the last SSE event and also stored in DynamoDB.
        """
        total_latency_ms = (time.perf_counter() - self._run_start_time) * 1000

        return AgentRunSummary(
            run_id=self.run_id,
            total_steps=self.step_index,
            total_latency_ms=round(total_latency_ms, 2),
            total_tokens=self._total_tokens,
            total_cost_usd=round(self._total_cost, 8),
            tools_used=self._tools_used,
            model_used=self.model_name,
            success=success,
        )

    def build_trace_data(
        self, prompt: str, tools_enabled: List[str], success: bool
    ) -> Dict[str, Any]:
        """
        Build the complete trace data dict for DynamoDB storage.
        WHY: One item per run (not per step) — DynamoDB items can be 400KB,
        and a trace with 20 steps fits easily. Single-item reads are faster and cheaper.
        """
        summary = self.build_summary(success)

        # Find the final answer content
        final_answer = ""
        for evt in reversed(self.events):
            if evt.event_type == "final_answer":
                final_answer = evt.content
                break

        return {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt[:1000],
            "model_used": self.model_name,
            "tools_enabled": tools_enabled,
            "tools_used": self._tools_used,
            "total_steps": summary.total_steps,
            "total_latency_ms": summary.total_latency_ms,
            "total_tokens": summary.total_tokens,
            "total_cost_usd": summary.total_cost_usd,
            "success": success,
            "final_answer": final_answer[:5000],
            "steps": [evt.model_dump(exclude_none=True) for evt in self.events],
        }

    def signal_done(self) -> None:
        """Signal the SSE consumer that the stream is complete."""
        try:
            self.event_queue.put_nowait(None)
        except asyncio.QueueFull:
            logger.warning("Could not signal done — event queue full")
