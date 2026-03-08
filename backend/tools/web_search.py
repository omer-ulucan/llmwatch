"""
Module: web_search.py
Purpose: DuckDuckGo web search tool for the LLMWatch agent.
WHY: Gives the agent access to real-time web information without requiring an API key.
"""

from langchain_core.tools import tool
from config import logger


@tool
def web_search(query: str) -> str:
    """Search the web using DuckDuckGo. Returns top results with titles, snippets, and URLs.
    Use this tool when you need to find current information from the internet."""
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

        if not results:
            return f"No results found for: {query}"

        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            body = r.get("body", "No snippet")
            href = r.get("href", "")
            formatted.append(f"{i}. **{title}**\n   {body}\n   URL: {href}")

        return "\n\n".join(formatted)

    except ImportError:
        return "Error: duckduckgo-search package is not installed."
    except Exception as e:
        logger.error(f"Web search error: {str(e)}")
        return f"Web search failed: {str(e)}"
