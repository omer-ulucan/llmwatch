"""
Module: pricing.py
Purpose: Turns reported token usage into USD using per-model prices.
WHY: Prices are per 1M tokens and editable per model; costs are computed from the
provider's reported usage. Unknown prices yield None (shown as "unpriced"), not $0,
so missing configuration is visible instead of looking like a free model.
"""

from llmwatch.llm.types import Usage


def compute_cost(
    usage: Usage,
    input_price_per_mtok: float | None,
    output_price_per_mtok: float | None,
) -> float | None:
    if input_price_per_mtok is None and output_price_per_mtok is None:
        return None
    # Reasoning tokens are already part of output_tokens (and billed as output).
    return (usage.input_tokens / 1_000_000) * (input_price_per_mtok or 0.0) + (
        usage.output_tokens / 1_000_000
    ) * (output_price_per_mtok or 0.0)
