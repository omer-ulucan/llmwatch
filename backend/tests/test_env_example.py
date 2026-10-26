"""Every setting must be documented in .env.example (the reference for users)."""

import re
from pathlib import Path

from llmwatch.config import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_env_example_documents_every_setting():
    documented = set(
        re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M)
    )
    missing = sorted(
        name.upper() for name in Settings.model_fields if name.upper() not in documented
    )
    assert missing == []


def test_env_example_only_names_real_settings():
    known = {name.upper() for name in Settings.model_fields}
    # Read by docker-compose.yml, not by the backend.
    known |= {"LLMWATCH_PORT", "LLMWATCH_EXTRAS"}
    documented = set(
        re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", ENV_EXAMPLE.read_text(), re.M)
    )
    assert sorted(documented - known) == []
