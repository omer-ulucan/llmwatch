"""
Module: template.py
Purpose: Renders eval prompt templates with `{{ variable }}` placeholders.
WHY: Deliberately tiny and strict. No expressions, filters or code (unlike Jinja), so
an imported suite can't execute anything, and a missing variable is an error rather
than silently rendering as an empty string and skewing results.

Syntax: `{{name}}` or `{{ name }}`; dotted names (`{{ ticket.subject }}`) read nested
values. Non-string values are rendered as JSON.
"""

import json
import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}")


class TemplateError(ValueError):
    """A template references variables the case doesn't provide."""


def variables(template: str) -> list[str]:
    """Top-level variable names used by a template, in first-use order."""
    seen: dict[str, None] = {}
    for match in _PLACEHOLDER.finditer(template or ""):
        seen.setdefault(match.group(1).split(".")[0], None)
    return list(seen)


_MISSING = object()


def _lookup(values: dict[str, Any], dotted: str) -> Any:
    current: Any = values
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def render(template: str, values: dict[str, Any]) -> str:
    """Substitutes every placeholder.

    Raises:
        TemplateError: if any placeholder has no value.
    """
    missing: list[str] = []

    def substitute(match: re.Match) -> str:
        value = _lookup(values, match.group(1))
        if value is _MISSING:
            missing.append(match.group(1))
            return ""
        return _to_text(value)

    rendered = _PLACEHOLDER.sub(substitute, template)
    if missing:
        names = ", ".join(dict.fromkeys(missing))
        raise TemplateError(f"Missing template variable(s): {names}")
    return rendered
