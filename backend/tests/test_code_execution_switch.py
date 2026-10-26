"""
Regression tests: Python code execution must be opt-in.

WHY: tools/code_executor.py runs model-written code as a subprocess of the backend,
with the same filesystem and network access. It is not a sandbox. It must stay off
unless an operator explicitly sets ENABLE_CODE_EXECUTION=true.
"""

import pytest
from pydantic import ValidationError


@pytest.fixture
def code_execution(monkeypatch):
    from llmwatch.config import settings

    def _set(enabled: bool):
        monkeypatch.setattr(settings, "enable_code_execution", enabled)

    return _set


def test_code_execution_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_CODE_EXECUTION", raising=False)
    from llmwatch.config import Settings

    assert Settings().enable_code_execution is False


def test_code_tool_not_built_when_disabled(code_execution):
    code_execution(False)
    from llmwatch.services.agent_service import build_tools

    tools = build_tools("company-123", ["web_search", "code_execute"])

    assert [t.name for t in tools] == ["web_search"]


def test_code_tool_refuses_to_run_when_disabled(code_execution, tmp_path):
    code_execution(False)
    from llmwatch.tools.code_executor import execute_python

    marker = tmp_path / "ran"
    result = execute_python.invoke(f"open({str(marker)!r}, 'w').write('x')")

    assert "disabled" in result.lower()
    assert not marker.exists()


def test_agent_request_rejects_code_execute_when_disabled(code_execution):
    code_execution(False)
    from llmwatch.models.schemas import AgentRunRequest

    with pytest.raises(ValidationError, match="code_execute"):
        AgentRunRequest(prompt="hi", model="gemini", tools=["code_execute"])


def test_agent_request_default_tools_exclude_disabled_code_execute(code_execution):
    code_execution(False)
    from llmwatch.models.schemas import AgentRunRequest

    req = AgentRunRequest(prompt="hi", model="gemini")

    assert "code_execute" not in req.tools
    assert "web_search" in req.tools


def test_agent_request_accepts_code_execute_when_enabled(code_execution):
    code_execution(True)
    from llmwatch.models.schemas import AgentRunRequest

    req = AgentRunRequest(prompt="hi", model="gemini", tools=["code_execute"])

    assert req.tools == ["code_execute"]


def test_available_tools_reflects_switch(code_execution):
    from llmwatch.services.agent_service import available_tools

    code_execution(False)
    assert "code_execute" not in available_tools()
    code_execution(True)
    assert "code_execute" in available_tools()


class TestHardeningWhenEnabled:
    """When an operator does enable it, the child gets as little as possible."""

    @pytest.fixture(autouse=True)
    def _enable(self, code_execution):
        code_execution(True)

    def test_child_runs_in_isolated_mode(self):
        from llmwatch.tools.code_executor import execute_python

        result = execute_python.invoke("import sys; print(sys.flags.isolated)")
        assert result.strip() == "1"

    def test_child_environment_has_no_backend_secrets(self, monkeypatch):
        monkeypatch.setenv("SUPER_SECRET_TOKEN", "s3cr3t")
        from llmwatch.tools.code_executor import execute_python

        result = execute_python.invoke("import os; print(sorted(os.environ))")
        assert "SUPER_SECRET_TOKEN" not in result
        assert "JWT_SECRET_KEY" not in result

    def test_child_runs_in_a_throwaway_working_directory(self):
        import os

        from llmwatch.tools.code_executor import execute_python

        result = execute_python.invoke("import os; print(os.getcwd())")
        assert result.strip() != os.getcwd()
        assert not os.path.exists(result.strip())  # cleaned up afterwards

    def test_child_has_resource_limits(self):
        import resource

        from llmwatch.tools.code_executor import MAX_MEMORY_BYTES, execute_python

        result = execute_python.invoke(
            "import resource; print(resource.getrlimit(resource.RLIMIT_AS)[1])"
        )
        hard_as = int(result.strip())
        # Some platforms refuse RLIMIT_AS; then the inherited limit is unlimited.
        if hard_as != resource.RLIM_INFINITY:
            assert hard_as == MAX_MEMORY_BYTES

    def test_timeout_kills_the_child(self, monkeypatch):
        import llmwatch.tools.code_executor as ce

        monkeypatch.setattr(ce, "EXECUTION_TIMEOUT", 1)
        result = ce.execute_python.invoke("while True: pass")
        assert "timed out" in result.lower()


def test_tools_endpoint_lists_only_enabled_tools(code_execution):
    from fastapi.testclient import TestClient

    from llmwatch.auth.dependencies import get_current_user
    from llmwatch.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "u1",
        "company_id": "c1",
    }
    try:
        client = TestClient(app)
        # The code tool is listed under its canonical name, "python".
        code_execution(False)
        assert "python" not in client.get("/agent/tools").json()["tools"]
        code_execution(True)
        assert "python" in client.get("/agent/tools").json()["tools"]
    finally:
        app.dependency_overrides.clear()
