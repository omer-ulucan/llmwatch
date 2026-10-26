"""
Module: messages.py
Purpose: Turns a suite's prompt template and one case's vars into chat messages.
WHY: Shared by the preview endpoint and the runner, so what you preview is exactly
what gets sent (and what the response cache is keyed on).
"""

from typing import Any

from llmwatch.evals.schema import SuiteDefinition
from llmwatch.evals.template import render


def build_messages(
    definition: SuiteDefinition, values: dict[str, Any]
) -> list[dict[str, str]]:
    """Raises TemplateError if a placeholder has no value."""
    messages: list[dict[str, str]] = []
    if definition.system_prompt:
        messages.append(
            {"role": "system", "content": render(definition.system_prompt, values)}
        )
    messages.append({"role": "user", "content": render(definition.prompt, values)})
    return messages
