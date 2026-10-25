"""
Module: presets.py
Purpose: Known OpenAI-compatible providers and their default settings.
WHY: Picking "Groq" or "Ollama" should fill in the right base URL and tell the UI
whether a key is needed, instead of every user looking these up.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    base_url: str
    requires_api_key: bool
    # Runs on your own hardware (shown with a "local" badge in model pickers).
    local: bool = False
    stream_usage: bool = True
    docs_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


PRESETS: dict[str, Preset] = {
    p.id: p
    for p in [
        Preset(
            "openai",
            "OpenAI",
            "https://api.openai.com/v1",
            True,
            docs_url="https://platform.openai.com/docs/api-reference",
        ),
        Preset(
            "gemini",
            "Google Gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            True,
            docs_url="https://ai.google.dev/gemini-api/docs/openai",
        ),
        Preset(
            "openrouter",
            "OpenRouter",
            "https://openrouter.ai/api/v1",
            True,
            docs_url="https://openrouter.ai/docs",
        ),
        Preset(
            "groq",
            "Groq",
            "https://api.groq.com/openai/v1",
            True,
            docs_url="https://console.groq.com/docs/openai",
        ),
        Preset(
            "together",
            "Together AI",
            "https://api.together.xyz/v1",
            True,
            docs_url="https://docs.together.ai/docs/openai-api-compatibility",
        ),
        Preset(
            "ollama",
            "Ollama",
            "http://localhost:11434/v1",
            False,
            local=True,
            docs_url="https://github.com/ollama/ollama/blob/main/docs/openai.md",
        ),
        Preset(
            "vllm",
            "vLLM",
            "http://localhost:8000/v1",
            False,
            local=True,
            docs_url="https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html",
        ),
        Preset(
            "lmstudio",
            "LM Studio",
            "http://localhost:1234/v1",
            False,
            local=True,
            docs_url="https://lmstudio.ai/docs/app/api/endpoints/openai",
        ),
        Preset("custom", "Custom (OpenAI-compatible)", "", False),
    ]
}


def get_preset(preset_id: str) -> Preset:
    return PRESETS.get(preset_id, PRESETS["custom"])
