"""
Module: tools.py (agent)
Purpose: The agent's tools, described as OpenAI function-calling schemas.
WHY: Native async tools replace the LangChain @tool wrappers: the model sees a JSON
schema per tool, arguments arrive as JSON, and each tool returns text (truncated) plus
an error flag. Tools never raise into the agent loop; failures become results the
model can read and react to.

Tools:
  web_search   DuckDuckGo search (no API key)
  fetch_url    read a web page; SSRF-guarded (security.ssrf)
  query_usage  the workspace's own LLM usage over a time window
  python       run Python; only built when ENABLE_CODE_EXECUTION=true

Older tool names from the LangChain agent are accepted as aliases.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from llmwatch.agent.html import extract_text_from_html
from llmwatch.config import logger, settings

MAX_RESULT_CHARS = 8000
TOOL_TIMEOUT_S = 30.0

TOOL_NAMES = ("web_search", "fetch_url", "query_usage", "python")
ALIASES = {
    "code_execute": "python",
    "db_query": "query_usage",
    "doc_analyze": "fetch_url",
    # Names the old LangChain tools reported to the model.
    "execute_python": "python",
    "query_llm_logs": "query_usage",
    "analyze_document": "fetch_url",
}


@dataclass
class ToolResult:
    content: str
    is_error: bool = False


@dataclass
class ToolContext:
    """What a tool may know about the caller; the model never controls this."""

    workspace_id: str


Runner = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    run: Runner = field(repr=False)

    def spec(self) -> dict[str, Any]:
        """OpenAI `tools` entry."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def canonical_name(name: str) -> str:
    return ALIASES.get(name, name)


def available_tool_names() -> list[str]:
    """Tools this server allows, in display order."""
    return [
        name
        for name in TOOL_NAMES
        if name != "python" or settings.enable_code_execution
    ]


def _truncate(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} more characters]"


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


# ── web_search ──────────────────────────────────────────────


def _ddgs_text(query: str, max_results: int) -> list[dict[str, Any]]:
    from ddgs import DDGS

    return list(DDGS().text(query, max_results=max_results))


async def _web_search(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult("Error: `query` is required", is_error=True)
    max_results = min(max(int(args.get("max_results") or 5), 1), 10)
    results = await asyncio.to_thread(_ddgs_text, query, max_results)
    if not results:
        return ToolResult(f"No results found for: {query}")
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r.get('title', 'No title')}\n"
            f"   {r.get('body', '')}\n"
            f"   URL: {r.get('href', '')}"
        )
    return ToolResult(_truncate("\n\n".join(lines)))


WEB_SEARCH = Tool(
    name="web_search",
    description=(
        "Search the web with DuckDuckGo. Returns titles, snippets and URLs. Use it "
        "for current information; follow up with fetch_url to read a page."
    ),
    parameters=_schema(
        {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "description": "Number of results (default 5)",
            },
        },
        ["query"],
    ),
    run=_web_search,
)


# ── fetch_url ───────────────────────────────────────────────


async def _fetch_url(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    import httpx

    from llmwatch.security import ssrf

    url = str(args.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return ToolResult(
            f"Invalid URL: {url!r}. It must start with http:// or https://",
            is_error=True,
        )
    try:
        result = await ssrf.safe_fetch(
            url,
            allowed_hosts=ssrf.parse_allowed_hosts(settings.fetch_allowed_hosts),
            timeout=15.0,
        )
    except ssrf.BlockedURLError as exc:
        return ToolResult(f"Request blocked: {exc}", is_error=True)
    except (TimeoutError, httpx.TimeoutException):
        return ToolResult(f"Request timed out for {url}", is_error=True)
    except httpx.HTTPError as exc:
        return ToolResult(f"Failed to reach {url}: {exc}", is_error=True)

    if result.status_code >= 400:
        return ToolResult(f"HTTP {result.status_code} fetching {url}", is_error=True)
    text = result.text
    content_type = result.headers.get("content-type", "").lower()
    if "html" in content_type or text.lstrip().startswith("<"):
        text = extract_text_from_html(text)
    if not text.strip():
        return ToolResult(f"No readable text at {result.url}")
    return ToolResult(_truncate(f"Content from {result.url}:\n\n{text}"))


FETCH_URL = Tool(
    name="fetch_url",
    description=(
        "Fetch a public web page or document and return its text. Internal and "
        "private network addresses are blocked."
    ),
    parameters=_schema(
        {"url": {"type": "string", "description": "Absolute http(s) URL"}},
        ["url"],
    ),
    run=_fetch_url,
)


# ── query_usage ─────────────────────────────────────────────


async def _query_usage(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    from llmwatch.db.engine import get_sessionmaker
    from llmwatch.services import analytics

    try:
        hours = float(args.get("hours") or 24)
        window = analytics.resolve_window(hours=hours)
    except (TypeError, ValueError) as exc:
        return ToolResult(f"Error: invalid hours: {exc}", is_error=True)
    except Exception as exc:  # ValidationException from resolve_window
        return ToolResult(f"Error: {exc}", is_error=True)
    filters = analytics.LogFilters(
        model=args.get("model") or None, provider=args.get("provider") or None
    )
    # WHY: The workspace comes from the authenticated caller (ctx), never from the
    # model's arguments.
    async with get_sessionmaker()() as session:
        summary = await analytics.summary(session, ctx.workspace_id, window, filters)

    compact = {
        "window_hours": hours,
        "requests": summary["total_requests"],
        "errors": summary["total_errors"],
        "error_rate_pct": summary["error_rate_pct"],
        "cost_usd": round(summary["total_cost_usd"], 6),
        "avg_latency_ms": summary["avg_latency_ms"],
        "p95_latency_ms": summary["p95_latency_ms"],
        "input_tokens": summary["input_tokens"],
        "output_tokens": summary["output_tokens"],
        "by_model": {
            name: {
                "requests": m["requests"],
                "cost_usd": round(m["cost"], 6),
                "errors": m["errors"],
                "avg_latency_ms": m["avg_latency_ms"],
            }
            for name, m in summary["model_breakdown"].items()
        },
        "change_vs_previous_window_pct": summary["deltas_pct"],
    }
    return ToolResult(_truncate(json.dumps(compact, indent=2)))


QUERY_USAGE = Tool(
    name="query_usage",
    description=(
        "Summarise this workspace's own LLM usage (requests, cost, latency, errors, "
        "per-model breakdown) over the last N hours, optionally for one model or "
        "provider."
    ),
    parameters=_schema(
        {
            "hours": {
                "type": "number",
                "minimum": 0.1,
                "maximum": 8784,
                "description": "Look-back window in hours (default 24)",
            },
            "model": {"type": "string", "description": "Only this model id"},
            "provider": {"type": "string", "description": "Only this provider name"},
        },
        [],
    ),
    run=_query_usage,
)


# ── python ──────────────────────────────────────────────────


async def _python(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    from llmwatch.agent import python_exec

    # WHY: Checked again at call time (defense in depth).
    if not settings.enable_code_execution:
        return ToolResult(python_exec.DISABLED_MESSAGE, is_error=True)
    code = str(args.get("code") or "")
    if not code.strip():
        return ToolResult("Error: `code` is required", is_error=True)
    output = await asyncio.to_thread(python_exec.run_python, code)
    is_error = output.startswith(
        ("Error:", "Code execution error", "Code execution failed")
    )
    return ToolResult(_truncate(output), is_error=is_error)


PYTHON = Tool(
    name="python",
    description=(
        "Run a Python script and return what it prints. Use print() for output. "
        "Runs with a short timeout and limited memory."
    ),
    parameters=_schema(
        {"code": {"type": "string", "description": "Python source to run"}},
        ["code"],
    ),
    run=_python,
)


ALL_TOOLS: dict[str, Tool] = {
    t.name: t for t in (WEB_SEARCH, FETCH_URL, QUERY_USAGE, PYTHON)
}


def build_toolset(requested: list[str]) -> dict[str, Tool]:
    """The enabled tools for a run, by canonical name (aliases accepted, disabled
    and unknown names dropped)."""
    allowed = set(available_tool_names())
    toolset: dict[str, Tool] = {}
    for name in requested:
        canonical = canonical_name(name)
        if canonical in allowed and canonical in ALL_TOOLS:
            toolset[canonical] = ALL_TOOLS[canonical]
    return toolset


async def run_tool(
    tool: Tool, raw_arguments: str, ctx: ToolContext, timeout: float = TOOL_TIMEOUT_S
) -> ToolResult:
    """Parses the model's JSON arguments and runs the tool; never raises."""
    try:
        args = json.loads(raw_arguments) if raw_arguments.strip() else {}
    except json.JSONDecodeError as exc:
        return ToolResult(f"Error: arguments are not valid JSON ({exc})", is_error=True)
    if not isinstance(args, dict):
        return ToolResult("Error: arguments must be a JSON object", is_error=True)
    missing = [k for k in tool.parameters.get("required", []) if k not in args]
    if missing:
        return ToolResult(
            f"Error: missing argument(s): {', '.join(missing)}", is_error=True
        )
    try:
        return await asyncio.wait_for(tool.run(args, ctx), timeout=timeout)
    except TimeoutError:
        return ToolResult(
            f"Error: {tool.name} timed out after {timeout:.0f}s", is_error=True
        )
    except Exception as exc:
        logger.warning(f"Tool {tool.name} failed: {exc}")
        return ToolResult(f"Error: {tool.name} failed: {exc}", is_error=True)
