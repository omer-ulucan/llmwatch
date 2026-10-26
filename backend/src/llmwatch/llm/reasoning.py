"""
Module: reasoning.py
Purpose: Turns a "thinking on/off" switch into each provider's own request knobs.
WHY: Providers expose reasoning differently. Sending reasoning parameters to models
that don't support them makes some APIs reject the request, so knobs are only added
for models marked as reasoning-capable in the catalogue (Gemini is always eligible,
its OpenAI-compatible endpoint accepts reasoning_effort on every model).
"""

from typing import Any

from llmwatch.llm.types import Message

_EFFORT_PRESETS = {"openai", "openrouter", "groq", "together", "custom"}


def reasoning_controls(
    preset: str, supports_reasoning: bool, thinking: bool
) -> tuple[list[Message], dict[str, Any]]:
    """
    Returns (system messages to prepend, request params) for this provider.
    """
    if preset == "gemini":
        return [], {"reasoning_effort": "high" if thinking else "low"}
    if not supports_reasoning:
        return [], {}
    if preset == "ollama":
        # WHY: Ollama's reasoning models think by default, which can burn the whole
        # max_tokens budget on hidden reasoning and return an empty answer.
        # reasoning_effort="none" turns it off (verified on Ollama 0.18; "low" and
        # think=false do not).
        return [], ({} if thinking else {"reasoning_effort": "none"})
    if preset == "vllm":
        # WHY: Qwen3-style models honour this soft switch to skip reasoning.
        return ([] if thinking else [{"role": "system", "content": "/no_think"}]), {}
    if preset in _EFFORT_PRESETS and thinking:
        return [], {"reasoning_effort": "high"}
    return [], {}
