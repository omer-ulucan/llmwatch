"""
Module: loop.py
Purpose: The agent: a native async tool-calling loop over the OpenAI-compatible API.
WHY: Replaces LangChain's ReAct AgentExecutor, which ran in a worker thread and
pushed events into an asyncio.Queue from that thread (not thread-safe; streams could
stall), never summed cost, and left the stored trace empty. Here everything runs on
the event loop:

  model call -> tool calls? -> run tools, append results -> model call -> ...
  until the model answers without tools, max_iterations is reached, an error
  happens, or the run is cancelled.

Each model call is one step with its own latency, tokens and cost (from the model's
registry prices), and is also written to llm_logs (source "agent", trace_id = run
id) so agent spend appears in analytics. The trace is recorded as "running" when the
run starts and completed with every step and the final answer when it ends, whatever
the outcome.
"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from llmwatch.agent.events import AgentEvent, AgentRunSummary
from llmwatch.agent.tools import (
    Tool,
    ToolContext,
    ToolResult,
    build_toolset,
    canonical_name,
    run_tool,
)
from llmwatch.config import logger
from llmwatch.llm import LLMClient, LLMError, Usage, compute_cost
from llmwatch.providers.models import ResolvedModel
from llmwatch.services import observability

T = TypeVar("T")

SYSTEM_PROMPT = """You are a capable assistant that can use tools.
Today's date is {today}.

- Use a tool when it gives you information you don't have or work you can't do
  reliably yourself; otherwise answer directly.
- You may call tools several times. Read each result before deciding what to do next.
- When you have enough information, reply with the final answer as plain text and
  do not call any more tools."""

# Stored per step; full content is still sent to the model.
STEP_CONTENT_CHARS = 5000


class RunCancelled(Exception):
    """The run was cancelled (cancel endpoint or client disconnect)."""


@dataclass
class ActiveRun:
    workspace_id: str
    cancel: asyncio.Event = field(default_factory=asyncio.Event)


class RunRegistry:
    """In-process registry of running agent runs, for the cancel endpoint.

    WHY: Cancellation has to reach the coroutine executing the run. With several
    server processes a cancel request may land on another one; the client
    disconnecting still cancels the run either way.
    """

    def __init__(self):
        self._runs: dict[str, ActiveRun] = {}

    def register(self, run_id: str, workspace_id: str) -> ActiveRun:
        run = ActiveRun(workspace_id)
        self._runs[run_id] = run
        return run

    def unregister(self, run_id: str) -> None:
        self._runs.pop(run_id, None)

    def cancel(self, run_id: str, workspace_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None or run.workspace_id != workspace_id:
            return False
        run.cancel.set()
        return True


registry = RunRegistry()


@dataclass
class AgentRequest:
    prompt: str
    tools: list[str]
    max_iterations: int = 10
    workspace_id: str = ""
    user_id: str | None = None
    api_key_id: str | None = None


class AgentRun:
    """One agent execution. Iterate `events()`; `summary` is set at the end."""

    def __init__(
        self,
        request: AgentRequest,
        resolved: ResolvedModel,
        client: LLMClient,
        *,
        run_id: str | None = None,
        cancel: asyncio.Event | None = None,
    ):
        self.request = request
        self.resolved = resolved
        self.client = client
        self.run_id = run_id or str(uuid.uuid4())
        self.cancel = cancel or asyncio.Event()
        self.toolset: dict[str, Tool] = build_toolset(request.tools)
        self.steps: list[AgentEvent] = []
        self.summary: AgentRunSummary | None = None
        self.status = "running"
        self.final_answer = ""
        self.error: str | None = None
        self._started = time.perf_counter()
        self._step_index = 0
        self._tokens = 0
        self._cost = 0.0
        self._priced = True
        self._llm_calls = 0
        self._tools_used: list[str] = []

    # ── helpers ─────────────────────────────────────────────

    def _event(self, event_type, content: str, **fields) -> AgentEvent:
        event = AgentEvent(
            run_id=self.run_id,
            step_index=self._step_index,
            event_type=event_type,
            content=content,
            **fields,
        )
        self._step_index += 1
        self.steps.append(event)
        return event

    async def _until_cancelled(self, awaitable: Awaitable[T]) -> T:
        """Awaits `awaitable`, aborting it as soon as the run is cancelled."""
        task = asyncio.ensure_future(awaitable)
        waiter = asyncio.ensure_future(self.cancel.wait())
        try:
            done, _ = await asyncio.wait(
                {task, waiter}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            waiter.cancel()
        if task in done:
            return task.result()
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        raise RunCancelled()

    def _messages(self) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    today=datetime.now(UTC).strftime("%Y-%m-%d")
                ),
            },
            {"role": "user", "content": self.request.prompt},
        ]

    def _step_cost(self, usage: Usage) -> float | None:
        m = self.resolved.model
        return compute_cost(usage, m.input_price_per_mtok, m.output_price_per_mtok)

    async def _log_call(self, **fields) -> None:
        await observability.record_llm_call(
            self.request.workspace_id,
            source="agent",
            trace_id=self.run_id,
            user_id=self.request.user_id,
            api_key_id=self.request.api_key_id,
            model_ref_id=self.resolved.model.id,
            model_name=self.resolved.model.model_id,
            provider_name=self.resolved.provider.name,
            prompt_preview=self.request.prompt,
            **fields,
        )

    # ── the loop ────────────────────────────────────────────

    async def events(self) -> AsyncIterator[AgentEvent]:
        yield self._event(
            "run_start",
            f"Starting agent with model={self.resolved.label}, "
            f"tools={sorted(self.toolset)}",
        )
        await observability.start_trace(
            self.request.workspace_id,
            run_id=self.run_id,
            prompt=self.request.prompt[:10_000],
            model_name=self.resolved.label,
            model_ref_id=self.resolved.model.id,
            tools_enabled=sorted(self.toolset),
            user_id=self.request.user_id,
        )

        messages = self._messages()
        specs = [tool.spec() for tool in self.toolset.values()]
        try:
            for _ in range(self.request.max_iterations):
                async for event in self._iteration(messages, specs):
                    yield event
                if self.status != "running":
                    break
            else:
                self.status = "error"
                self.error = (
                    f"Reached max_iterations ({self.request.max_iterations}) "
                    "without a final answer"
                )
                yield self._event("error", self.error, error_type="max_iterations")
        except RunCancelled:
            self.status = "cancelled"
            self.error = "Run cancelled"
            yield self._event("error", "Run cancelled", error_type="cancelled")
        except asyncio.CancelledError:
            # The client went away (Starlette cancels the response task).
            self.status = "cancelled"
            self.error = "Client disconnected"
            raise
        finally:
            if self.status == "running":
                self.status = "cancelled"
                self.error = self.error or "Run stopped before finishing"
            self.summary = self._summary()

        yield self._event("run_end", self.summary.model_dump_json())

    async def _iteration(self, messages, specs) -> AsyncIterator[AgentEvent]:
        if self.cancel.is_set():
            raise RunCancelled()
        params: dict[str, Any] = {}
        if specs:
            params["tools"] = specs
            params["tool_choice"] = "auto"

        started = time.perf_counter()
        try:
            result = await self._until_cancelled(
                self.client.chat(self.resolved.model.model_id, messages, **params)
            )
        except LLMError as err:
            latency = (time.perf_counter() - started) * 1000
            self._llm_calls += 1
            await self._log_call(
                latency_ms=latency,
                success=False,
                error_type=err.kind,
                error_message=err.message,
                status_code=err.status,
            )
            self.status = "error"
            self.error = f"{err.provider}: {err.message}"
            yield self._event(
                "error", self.error, error_type=err.kind, latency_ms=latency
            )
            return

        self._llm_calls += 1
        usage = result.usage
        cost = self._step_cost(usage)
        if cost is None:
            self._priced = False
        self._tokens += usage.total_tokens
        self._cost += cost or 0.0
        metrics = {
            "latency_ms": round(result.latency_ms, 2),
            "tokens": usage.total_tokens,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cost_usd": cost or 0.0,
        }
        await self._log_call(
            response_preview=result.content
            or ", ".join(tc.name for tc in result.tool_calls),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            reasoning_tokens=usage.reasoning_tokens,
            cost_usd=cost or 0.0,
            latency_ms=result.latency_ms,
            success=True,
        )

        if not result.tool_calls:
            if result.reasoning:
                yield self._event(
                    "thinking", result.reasoning[:STEP_CONTENT_CHARS], **metrics
                )
                metrics = {}
            self.final_answer = result.content
            self.status = "success"
            yield self._event("final_answer", result.content, **metrics)
            return

        thought = (
            result.reasoning
            or result.content
            or "Calling " + ", ".join(tc.name for tc in result.tool_calls)
        )
        yield self._event("thinking", thought[:STEP_CONTENT_CHARS], **metrics)

        calls = [
            {
                "id": tc.id or f"call_{self._step_index}_{i}",
                "name": tc.name,
                "arguments": tc.arguments or "{}",
            }
            for i, tc in enumerate(result.tool_calls)
        ]
        messages.append(
            {
                "role": "assistant",
                "content": result.content or None,
                "tool_calls": [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {"name": c["name"], "arguments": c["arguments"]},
                    }
                    for c in calls
                ],
            }
        )
        for call in calls:
            if self.cancel.is_set():
                raise RunCancelled()
            name = canonical_name(call["name"])
            yield self._event(
                "tool_call",
                f"Calling tool: {name}",
                tool_name=name,
                tool_input=call["arguments"][:STEP_CONTENT_CHARS],
            )
            tool = self.toolset.get(name)
            started = time.perf_counter()
            if tool is None:
                outcome = ToolResult(
                    f"Error: unknown or disabled tool {call['name']!r}. "
                    f"Available tools: {', '.join(sorted(self.toolset)) or 'none'}",
                    is_error=True,
                )
            else:
                if name not in self._tools_used:
                    self._tools_used.append(name)
                outcome = await self._until_cancelled(
                    run_tool(
                        tool,
                        call["arguments"],
                        ToolContext(workspace_id=self.request.workspace_id),
                    )
                )
            yield self._event(
                "tool_result",
                outcome.content[:STEP_CONTENT_CHARS],
                tool_name=name,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                is_error=outcome.is_error,
            )
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": outcome.content}
            )

    # ── results ─────────────────────────────────────────────

    def _summary(self) -> AgentRunSummary:
        return AgentRunSummary(
            run_id=self.run_id,
            total_steps=len(self.steps),
            total_latency_ms=round((time.perf_counter() - self._started) * 1000, 2),
            total_tokens=self._tokens,
            total_cost_usd=self._cost,
            tools_used=list(self._tools_used),
            model_used=self.resolved.label,
            success=self.status == "success",
            status=self.status,
            llm_calls=self._llm_calls,
            priced=self._priced,
        )

    async def save(self) -> None:
        """Completes the stored trace (call once the run has ended)."""
        summary = self.summary or self._summary()
        ok = await observability.finish_trace(
            self.request.workspace_id,
            self.run_id,
            status=self.status,
            total_steps=summary.total_steps,
            total_latency_ms=summary.total_latency_ms,
            total_tokens=summary.total_tokens,
            total_cost_usd=summary.total_cost_usd,
            tools_used=summary.tools_used,
            final_answer=self.final_answer[:20_000],
            error=self.error,
            steps=[
                json.loads(e.model_dump_json(exclude_none=True)) for e in self.steps
            ],
        )
        if ok:
            logger.info(f"Agent run {self.run_id} finished: {self.status}")
