"""
Module: db_query.py
Purpose: Tool that lets the agent query the user's own LLM usage logs.
WHY: Enables self-referential analytics — the agent can answer questions about the user's
own LLM usage patterns, costs, and performance.
"""

import asyncio
from typing import Any, Dict, List

from langchain_core.tools import tool

from llmwatch.config import logger

QUERY_TIMEOUT_S = 10


def _format_logs_summary(logs: List[Dict[str, Any]]) -> str:
    """Format usage logs into a readable summary string for the agent."""
    if not logs:
        return "No LLM usage logs found for this account."

    total_cost = 0.0
    total_latency = 0.0
    total_requests = len(logs)
    model_counts: Dict[str, int] = {}
    model_costs: Dict[str, float] = {}

    lines = []
    for log in logs:
        model = str(log.get("model_name", "unknown"))
        cost = float(log.get("cost_usd", 0))
        latency = float(log.get("latency_ms", 0))
        timestamp = log.get("timestamp", "unknown")
        prompt = log.get("prompt_preview", "")
        tokens_in = int(log.get("input_tokens", 0))
        tokens_out = int(log.get("output_tokens", 0))

        total_cost += cost
        total_latency += latency
        model_counts[model] = model_counts.get(model, 0) + 1
        model_costs[model] = model_costs.get(model, 0.0) + cost

        lines.append(
            f"  - [{timestamp}] model={model}, cost=${cost:.6f}, "
            f"latency={latency:.0f}ms, tokens={tokens_in}+{tokens_out}, "
            f'prompt="{prompt}"'
        )

    avg_latency = total_latency / total_requests if total_requests > 0 else 0

    summary = f"""=== LLM Usage Summary ({total_requests} requests) ===
Total Cost: ${total_cost:.6f}
Average Latency: {avg_latency:.0f}ms
Model Breakdown:
"""
    for model, count in model_counts.items():
        summary += (
            f"  {model}: {count} requests, ${model_costs[model]:.6f} total cost\n"
        )

    summary += "\nRecent Logs (newest first):\n"
    # Show at most 20 individual log entries to keep context manageable
    for line in lines[:20]:
        summary += line + "\n"

    if len(lines) > 20:
        summary += f"  ... and {len(lines) - 20} more entries\n"

    return summary


def make_db_query_tool(company_id: str, loop: asyncio.AbstractEventLoop | None = None):
    """
    Factory that creates a db_query tool bound to a specific workspace.
    WHY: The workspace comes from the authenticated user, so we inject it at tool
    creation time rather than trusting the agent to provide it.

    The LangChain agent calls tools from a worker thread, but the database engine
    belongs to the server's event loop, so the query is handed back to that loop.
    """
    from llmwatch.services.observability import log_to_dict, recent_logs_for

    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

    async def _fetch() -> list[dict[str, Any]]:
        return [log_to_dict(log) for log in await recent_logs_for(company_id, 100)]

    @tool
    def query_llm_logs(question: str) -> str:
        """Query your LLM usage logs and analytics data. Ask questions like:
        - What is my most expensive model?
        - How many requests did I make today?
        - What is my average latency?
        - Show me my recent usage
        The tool fetches your actual usage data and provides a summary for analysis."""
        try:
            if loop is not None and loop.is_running():
                logs = asyncio.run_coroutine_threadsafe(_fetch(), loop).result(
                    timeout=QUERY_TIMEOUT_S
                )
            else:
                logs = asyncio.run(_fetch())
            return _format_logs_summary(logs)
        except Exception as e:
            logger.error(f"DB query tool error: {str(e)}")
            return f"Failed to query usage logs: {str(e)}"

    return query_llm_logs
