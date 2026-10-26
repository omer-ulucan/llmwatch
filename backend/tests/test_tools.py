"""
Tests for the pieces behind the agent's tools: the Python executor, HTML text
extraction, and the loopback SSRF regression run against the real fetch_url tool.

Tool behaviour as the agent sees it (specs, arguments, search, fetch, usage queries)
is covered in test_agent_tools.py.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

from llmwatch.agent.html import extract_text_from_html
from llmwatch.agent.python_exec import run_python
from llmwatch.agent.tools import FETCH_URL, ToolContext, run_tool

# ── Python executor ────────────────────────────────────────


class TestCodeExecutor:
    """Tests for the opt-in Python code execution (run with it enabled)."""

    @pytest.fixture(autouse=True)
    def _enable_code_execution(self, monkeypatch):
        from llmwatch.config import settings

        monkeypatch.setattr(settings, "enable_code_execution", True)

    def test_execute_python_simple(self):
        assert "hello world" in run_python("print('hello world')")

    def test_execute_python_math(self):
        assert "5" in run_python("print(2 + 3)")

    def test_execute_python_no_output(self):
        assert "no output" in run_python("x = 42").lower()

    def test_execute_python_syntax_error(self):
        assert "error" in run_python("def foo(:").lower()

    def test_execute_python_timeout(self):
        with patch("llmwatch.agent.python_exec.EXECUTION_TIMEOUT", 1):
            result = run_python("import time; time.sleep(10)")
        assert "timed out" in result.lower() or "error" in result.lower()


# ── HTML extraction ────────────────────────────────────────


def test_html_text_extractor_strips_script_and_style():
    html = (
        "<html><style>body { color: red; }</style><body><p>Visible</p>"
        "<script>alert(1)</script></body></html>"
    )
    text = extract_text_from_html(html)
    assert "Visible" in text
    assert "color: red" not in text
    assert "alert" not in text


def test_html_text_extractor_handles_nested_skipped_tags():
    html = "<head><title>T</title><script>x()</script></head><p>Body</p>"
    assert extract_text_from_html(html) == "Body"


# ── Loopback SSRF regression (real server, real fetch tool) ─


class _SecretHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib naming
        body = b"TOP-SECRET-METADATA"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def loopback_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SecretHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
async def test_fetch_tool_cannot_read_loopback_services(
    loopback_server, host, monkeypatch
):
    """Regression: the URL fetch tool used to fetch any URL, including localhost."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)

    result = await run_tool(
        FETCH_URL,
        f'{{"url": "http://{host}:{loopback_server}/"}}',
        ToolContext(workspace_id="ws"),
    )

    assert "TOP-SECRET-METADATA" not in result.content
    assert result.is_error
    assert "blocked" in result.content.lower()
