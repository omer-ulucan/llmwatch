"""
Module: agent_service.py
Purpose: Orchestrates ReAct agent execution using LangChain's AgentExecutor with tool calling.
WHY: This is the core agent orchestration layer. It reuses the existing LLM strategies
(Qwen via vLLM, Gemini via Google API) and wraps them with LangChain's ReAct agent framework
to enable multi-step tool-augmented reasoning.
"""

import uuid
import asyncio
from typing import Any, AsyncGenerator, Dict, List

# WHY: langchain.agents.AgentExecutor and create_react_agent may fail to import on
# some Python versions (e.g. 3.14) due to internal langchain compatibility issues.
# We defer the import error to runtime (when the agent endpoint is actually called)
# so the rest of the application can still start and serve non-agent endpoints.
try:
    from langchain.agents import AgentExecutor, create_react_agent

    _AGENT_AVAILABLE = True
except ImportError:
    AgentExecutor = None  # type: ignore[assignment, misc]
    create_react_agent = None  # type: ignore[assignment]
    _AGENT_AVAILABLE = False

from langchain_core.prompts import PromptTemplate
from langchain_core.tools import BaseTool

from config import logger
from services.llm_service import LLMService, get_llm_service
from services.tracing_service import AgentEvent, TracingCallbackHandler
from tools.web_search import web_search
from tools.code_executor import execute_python
from tools.db_query import make_db_query_tool
from tools.doc_analyzer import analyze_document


# WHY: Custom ReAct prompt template instead of pulling from langchain hub.
# This avoids a network dependency and gives us control over the exact format.
# The template follows the standard ReAct pattern: Thought → Action → Observation loop.
REACT_PROMPT = PromptTemplate.from_template(
    """Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
)


def build_tools(company_id: str, enabled_tools: List[str]) -> List[BaseTool]:
    """
    Factory that instantiates the requested tools with proper context injection.

    WHY: db_query needs the company_id from the authenticated user's JWT injected
    at creation time (not at call time) to enforce multi-tenant isolation.
    The agent never sees or controls which company's data it queries.

    Args:
        company_id: The authenticated user's company identifier.
        enabled_tools: List of tool names the user wants the agent to use.

    Returns:
        List of LangChain BaseTool instances ready for agent use.
    """
    available = {
        "web_search": web_search,
        "code_execute": execute_python,
        "db_query": make_db_query_tool(company_id),
        "doc_analyze": analyze_document,
    }
    return [available[t] for t in enabled_tools if t in available]


class AgentService:
    """
    Manages ReAct agent execution with real-time tracing via callback handlers.

    WHY: Separating the agent orchestration from the router keeps the HTTP layer thin.
    The service handles LLM selection, tool binding, agent creation, execution,
    and event streaming — the router just wires it to the HTTP endpoint.
    """

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    def _get_langchain_llm(self, model: str) -> Any:
        """
        Extract the underlying LangChain LLM client from the existing strategy.

        WHY: The LLMService uses a Strategy pattern with QwenStrategy and GeminiStrategy.
        Each strategy holds a LangChain ChatModel instance (.client). We reuse these
        directly with AgentExecutor instead of creating new instances, ensuring consistent
        configuration (API keys, base URLs, model names).
        """
        strategy = self.llm_service.strategies.get(model)
        if not strategy:
            raise ValueError(f"Unsupported model for agent: {model}")
        return strategy.client

    async def run_agent(
        self,
        prompt: str,
        model: str,
        company_id: str,
        tools: List[str],
        max_iterations: int = 10,
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Runs a ReAct agent and yields AgentEvent objects for SSE streaming.

        WHY: Using an async generator lets FastAPI's StreamingResponse consume events
        one at a time as the agent executes. The TracingCallbackHandler bridges
        LangChain's sync callbacks into our async event stream via asyncio.Queue.

        Args:
            prompt: The user's question/instruction for the agent.
            model: Which LLM to use ("qwen" or "gemini").
            company_id: The user's company ID for tool context.
            tools: List of tool names to enable.
            max_iterations: Maximum ReAct loop iterations (safety limit).

        Yields:
            AgentEvent objects for each step of the agent execution.
        """
        run_id = str(uuid.uuid4())

        # Guard: fail fast if langchain agent is not available on this Python version
        if not _AGENT_AVAILABLE:
            raise RuntimeError(
                "Agent functionality is not available: langchain.agents could not be imported. "
                "This is a known issue on Python 3.14. Use Python 3.11–3.13."
            )

        llm = self._get_langchain_llm(model)
        tool_instances = build_tools(company_id, tools)

        # Create the tracing callback handler
        handler = TracingCallbackHandler(run_id=run_id, model_name=model)

        # Create the ReAct agent
        agent = create_react_agent(llm=llm, tools=tool_instances, prompt=REACT_PROMPT)
        executor = AgentExecutor(
            agent=agent,
            tools=tool_instances,
            max_iterations=max_iterations,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
            callbacks=[handler],
        )

        # Emit run_start event
        start_event = AgentEvent(
            run_id=run_id,
            step_index=0,
            event_type="run_start",
            content=f"Starting agent with model={model}, tools={tools}",
        )
        yield start_event

        # WHY: We run the agent in a background thread because AgentExecutor.invoke()
        # is synchronous (it calls sync callbacks). Running it in a thread lets us
        # consume events from the async queue without blocking the event loop.
        success = True

        async def _run_executor() -> None:
            nonlocal success
            try:
                # Run sync agent in thread pool to avoid blocking the event loop
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: executor.invoke(
                        {"input": prompt},
                        config={"callbacks": [handler]},
                    ),
                )
            except Exception as e:
                success = False
                logger.error(f"Agent execution error: {str(e)}")
                error_event = AgentEvent(
                    run_id=run_id,
                    step_index=handler.step_index,
                    event_type="error",
                    content=f"Agent execution failed: {str(e)[:500]}",
                )
                handler._emit(error_event)
            finally:
                handler.signal_done()

        # Start the agent execution as a background task
        agent_task = asyncio.create_task(_run_executor())

        # Consume events from the queue as they arrive
        try:
            while True:
                event = await handler.event_queue.get()
                if event is None:
                    # None is the sentinel value indicating the agent is done
                    break
                yield event
        except asyncio.CancelledError:
            agent_task.cancel()
            raise

        # Wait for the agent task to fully complete
        await agent_task

        # Emit run_end summary event
        summary = handler.build_summary(success)
        end_event = AgentEvent(
            run_id=run_id,
            step_index=handler.step_index,
            event_type="run_end",
            content=summary.model_dump_json(),
        )
        yield end_event

        # Store the handler's trace data and summary on the event for the router to access
        # WHY: We attach metadata to the final event so the router can save it
        # to DynamoDB without needing to reach back into the service internals.
        end_event._trace_data = handler.build_trace_data(prompt, tools, success)  # type: ignore[attr-defined]


# ── Singleton + Factory ────────────────────────────────────

agent_service = AgentService(get_llm_service())


def get_agent_service() -> AgentService:
    """Lazy factory for AgentService. Enables easy mocking in tests."""
    return agent_service
