"""
Module: db_query.py
Purpose: Tool that lets the agent query the user's own LLM usage logs from DynamoDB.
WHY: Enables self-referential analytics — the agent can answer questions about the user's
own LLM usage patterns, costs, and performance.
"""

from typing import Any, Dict, List
from langchain_core.tools import tool
from config import logger


def _format_logs_summary(logs: List[Dict[str, Any]]) -> str:
    """Format DynamoDB logs into a readable summary string for the agent."""
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

    summary += f"\nRecent Logs (newest first):\n"
    # Show at most 20 individual log entries to keep context manageable
    for line in lines[:20]:
        summary += line + "\n"

    if len(lines) > 20:
        summary += f"  ... and {len(lines) - 20} more entries\n"

    return summary


def make_db_query_tool(company_id: str, dynamo_service: Any = None):
    """
    Factory that creates a db_query tool bound to a specific company_id.
    WHY: The company_id comes from the authenticated user's JWT, so we inject it
    at tool creation time rather than trusting the agent to provide it.
    """
    from services.dynamo_service import get_dynamo_service

    @tool
    def query_llm_logs(question: str) -> str:
        """Query your LLM usage logs and analytics data. Ask questions like:
        - What is my most expensive model?
        - How many requests did I make today?
        - What is my average latency?
        - Show me my recent usage
        The tool fetches your actual usage data and provides a summary for analysis."""
        try:
            svc = dynamo_service or get_dynamo_service()
            logs = svc.get_logs(company_id, limit=100)
            return _format_logs_summary(logs)
        except Exception as e:
            logger.error(f"DB query tool error: {str(e)}")
            return f"Failed to query usage logs: {str(e)}"

    return query_llm_logs
