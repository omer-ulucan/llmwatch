"""
Module: events.py
Purpose: The agent's SSE event contract and run summary.
WHY: This is the universal data contract between the agent loop, the SSE stream,
the stored trace (steps) and the frontend timeline. Fields beyond the original
contract are optional, so older clients keep working.
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

EventType = Literal[
    "run_start",
    "thinking",
    "tool_call",
    "tool_result",
    "final_answer",
    "error",
    "run_end",
]


class AgentEvent(BaseModel):
    """One step in an agent run (streamed as SSE and stored in the trace)."""

    run_id: str
    step_index: int
    event_type: EventType
    content: str
    tool_name: str | None = None
    tool_input: str | None = None
    latency_ms: float | None = None
    # Total tokens of the model call this event reports (input + output).
    tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    # True for tool results that are errors.
    is_error: bool | None = None
    # Error classification on "error" events (rate_limit, timeout, ...).
    error_type: str | None = None
    timestamp: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


class AgentRunSummary(BaseModel):
    """Summary metrics emitted as the final 'run_end' event payload."""

    run_id: str
    total_steps: int
    total_latency_ms: float
    total_tokens: int
    total_cost_usd: float
    tools_used: list[str]
    model_used: str
    success: bool
    # "success", "error" or "cancelled"
    status: str = "success"
    llm_calls: int = 0
    # False if any model call had no price set (its cost counts as 0).
    priced: bool = True
