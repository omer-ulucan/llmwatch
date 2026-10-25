"""
Regression test: Docker build contexts must not include secrets or local junk.

WHY: Both Dockerfiles do `COPY . .`. Without a .dockerignore, a developer's
backend/.env (JWT secret, provider API keys) is baked into the image layers, and
anyone who can pull the image can read it.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _patterns(path: Path) -> list[str]:
    lines = path.read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


@pytest.mark.parametrize("context", ["backend", "frontend"])
def test_dockerignore_exists_and_excludes_env_files(context):
    path = REPO_ROOT / context / ".dockerignore"
    assert path.is_file(), f"{context}/.dockerignore is missing"
    patterns = _patterns(path)
    assert ".env" in patterns
    assert ".env.*" in patterns
    assert ".git" in patterns


def test_backend_context_excludes_local_state():
    patterns = _patterns(REPO_ROOT / "backend" / ".dockerignore")
    for entry in (".venv", "data", "**/__pycache__"):
        assert entry in patterns


def test_frontend_context_excludes_node_modules_and_dist():
    patterns = _patterns(REPO_ROOT / "frontend" / ".dockerignore")
    for entry in ("node_modules", "dist"):
        assert entry in patterns
