"""
Module: registry.py
Purpose: Single source of truth for which agent tools exist and which are enabled.
WHY: Kept free of LangChain imports so request schemas can validate tool names
without loading the whole agent stack.
"""

from config import settings

ALL_TOOLS = ("web_search", "code_execute", "db_query", "doc_analyze")


def available_tools() -> list[str]:
    """Tools this server allows, in display order."""
    return [
        t for t in ALL_TOOLS if t != "code_execute" or settings.enable_code_execution
    ]
