"""
Tests for the LLMWatch agent tools.

WHY: Each tool is tested independently with appropriate mocking to ensure
correct behavior without external dependencies (no real web searches,
no real DynamoDB calls, no real URL fetches).
"""

import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

import pytest

# ── Ensure duckduckgo_search is importable for patching ────
# The web_search tool lazily imports DDGS inside its function body.
# If the duckduckgo-search package is not installed (e.g., Python 3.14 CI),
# we inject a stub module into sys.modules so patch() can target it.
_ddg_installed = "duckduckgo_search" in sys.modules
if not _ddg_installed:
    try:
        import duckduckgo_search as _  # noqa: F401

        _ddg_installed = True
    except ImportError:
        _stub = types.ModuleType("duckduckgo_search")
        _stub.DDGS = MagicMock  # type: ignore[attr-defined]
        sys.modules["duckduckgo_search"] = _stub


# ── web_search ─────────────────────────────────────────────


class TestWebSearch:
    """Tests for the DuckDuckGo web search tool."""

    def test_web_search_returns_formatted_results(self):
        """Verify web_search formats results with title, body, and URL."""
        from tools.web_search import web_search

        mock_results = [
            {
                "title": "Result 1",
                "body": "First snippet",
                "href": "https://example.com/1",
            },
            {
                "title": "Result 2",
                "body": "Second snippet",
                "href": "https://example.com/2",
            },
        ]

        with patch("duckduckgo_search.DDGS") as MockDDGS:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.text.return_value = mock_results
            MockDDGS.return_value = mock_instance

            result = web_search.invoke("test query")

        assert "Result 1" in result
        assert "Result 2" in result
        assert "https://example.com/1" in result
        assert "First snippet" in result

    def test_web_search_no_results(self):
        """Verify web_search handles empty results gracefully."""
        from tools.web_search import web_search

        with patch("duckduckgo_search.DDGS") as MockDDGS:
            mock_instance = MagicMock()
            mock_instance.__enter__ = MagicMock(return_value=mock_instance)
            mock_instance.__exit__ = MagicMock(return_value=False)
            mock_instance.text.return_value = []
            MockDDGS.return_value = mock_instance

            result = web_search.invoke("obscure query")

        assert "No results found" in result

    def test_web_search_handles_exception(self):
        """Verify web_search returns error message on failure."""
        from tools.web_search import web_search

        with patch("duckduckgo_search.DDGS") as MockDDGS:
            MockDDGS.side_effect = RuntimeError("Network error")

            result = web_search.invoke("test query")

        assert "failed" in result.lower() or "error" in result.lower()


# ── code_executor ──────────────────────────────────────────


class TestCodeExecutor:
    """Tests for the sandboxed Python code execution tool."""

    def test_execute_python_simple(self):
        """Verify execute_python runs simple code and returns output."""
        from tools.code_executor import execute_python

        result = execute_python.invoke("print('hello world')")
        assert "hello world" in result

    def test_execute_python_math(self):
        """Verify execute_python can do calculations."""
        from tools.code_executor import execute_python

        result = execute_python.invoke("print(2 + 3)")
        assert "5" in result

    def test_execute_python_no_output(self):
        """Verify execute_python reports success when no output."""
        from tools.code_executor import execute_python

        result = execute_python.invoke("x = 42")
        assert "no output" in result.lower()

    def test_execute_python_syntax_error(self):
        """Verify execute_python captures syntax errors."""
        from tools.code_executor import execute_python

        result = execute_python.invoke("def foo(:")
        assert "error" in result.lower()

    def test_execute_python_timeout(self):
        """Verify execute_python handles timeout for infinite loops."""
        from tools.code_executor import execute_python

        with patch("tools.code_executor.EXECUTION_TIMEOUT", 1):
            result = execute_python.invoke("import time; time.sleep(10)")
        assert "timed out" in result.lower() or "error" in result.lower()


# ── db_query ───────────────────────────────────────────────


class TestDbQuery:
    """Tests for the LLM usage log query tool."""

    def test_db_query_returns_summary(self):
        """Verify db_query formats logs into a readable summary."""
        from tools.db_query import make_db_query_tool

        mock_dynamo = MagicMock()
        mock_dynamo.get_logs.return_value = [
            {
                "model_name": "qwen",
                "cost_usd": 0.001,
                "latency_ms": 500,
                "timestamp": "2025-01-01T00:00:00Z",
                "prompt_preview": "Hello world",
                "input_tokens": 10,
                "output_tokens": 50,
            },
            {
                "model_name": "gemini",
                "cost_usd": 0.002,
                "latency_ms": 300,
                "timestamp": "2025-01-01T01:00:00Z",
                "prompt_preview": "Test prompt",
                "input_tokens": 20,
                "output_tokens": 100,
            },
        ]

        tool = make_db_query_tool("test-company", dynamo_service=mock_dynamo)
        result = tool.invoke("show my usage")

        assert "2 requests" in result
        assert "qwen" in result
        assert "gemini" in result
        assert "$" in result

    def test_db_query_no_logs(self):
        """Verify db_query handles no data gracefully."""
        from tools.db_query import make_db_query_tool

        mock_dynamo = MagicMock()
        mock_dynamo.get_logs.return_value = []

        tool = make_db_query_tool("test-company", dynamo_service=mock_dynamo)
        result = tool.invoke("show my usage")

        assert "No LLM usage logs found" in result

    def test_db_query_handles_exception(self):
        """Verify db_query returns error message on failure."""
        from tools.db_query import make_db_query_tool

        mock_dynamo = MagicMock()
        mock_dynamo.get_logs.side_effect = RuntimeError("DynamoDB error")

        tool = make_db_query_tool("test-company", dynamo_service=mock_dynamo)
        result = tool.invoke("show my usage")

        assert "Failed" in result or "error" in result.lower()


# ── doc_analyzer ───────────────────────────────────────────


class TestDocAnalyzer:
    """Tests for the URL fetching and document analysis tool."""

    def test_analyze_document_invalid_url(self):
        """Verify analyze_document rejects non-HTTP URLs."""
        from tools.doc_analyzer import analyze_document

        result = analyze_document.invoke("ftp://example.com/file.txt")
        assert "Invalid URL" in result

    def test_analyze_document_html_extraction(self):
        """Verify analyze_document extracts text from HTML."""
        import httpx

        from security.ssrf import FetchResult
        from tools.doc_analyzer import analyze_document

        html_content = b"<html><head><title>Test</title></head><body><p>Hello World</p><script>var x=1;</script></body></html>"
        fetched = FetchResult(
            url="https://example.com",
            status_code=200,
            headers=httpx.Headers({"Content-Type": "text/html; charset=utf-8"}),
            content=html_content,
        )

        with patch("tools.doc_analyzer.safe_fetch", return_value=fetched):
            result = analyze_document.invoke("https://example.com")

        assert "Hello World" in result
        # Script content should be stripped
        assert "var x=1" not in result

    def test_analyze_document_http_error(self):
        """Verify analyze_document handles HTTP errors."""
        import httpx

        from security.ssrf import FetchResult
        from tools.doc_analyzer import analyze_document

        fetched = FetchResult(
            url="https://example.com/missing",
            status_code=404,
            headers=httpx.Headers({"Content-Type": "text/html"}),
            content=b"Not Found",
        )

        with patch("tools.doc_analyzer.safe_fetch", return_value=fetched):
            result = analyze_document.invoke("https://example.com/missing")

        assert "404" in result

    def test_analyze_document_blocked_url_reports_reason(self):
        """Verify a blocked URL is reported to the model instead of fetched."""
        from tools.doc_analyzer import analyze_document

        result = analyze_document.invoke("http://169.254.169.254/latest/meta-data/")

        assert result.startswith("Request blocked:")

    def test_html_text_extractor_strips_script_and_style(self):
        """Verify the HTML text extractor removes script and style tags."""
        from tools.doc_analyzer import _extract_text_from_html

        html = "<html><style>body { color: red; }</style><body><p>Visible</p><script>alert(1)</script></body></html>"
        text = _extract_text_from_html(html)

        assert "Visible" in text
        assert "color: red" not in text
        assert "alert" not in text


# ── Tool-level regression tests (real loopback server) ──────


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
def test_doc_analyzer_cannot_read_loopback_services(loopback_server, host, monkeypatch):
    """Regression: analyze_document used to fetch any URL, including localhost."""
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)
    from tools.doc_analyzer import analyze_document

    result = analyze_document.invoke(f"http://{host}:{loopback_server}/")

    assert "TOP-SECRET-METADATA" not in result
    assert "blocked" in result.lower()
