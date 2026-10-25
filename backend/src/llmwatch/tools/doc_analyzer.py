"""
Module: doc_analyzer.py
Purpose: URL fetching and document analysis tool for the LLMWatch agent.
WHY: Allows the agent to read and summarize web pages or documents at given URLs.
All fetching goes through security.ssrf.safe_fetch, which blocks internal addresses.
"""

import asyncio
import re
from html.parser import HTMLParser

import httpx
from langchain_core.tools import tool

from llmwatch.config import logger, settings
from llmwatch.security.ssrf import BlockedURLError, parse_allowed_hosts, safe_fetch

# Maximum content size to return (in characters)
MAX_CONTENT_CHARS = 5000
# Request timeout in seconds
REQUEST_TIMEOUT = 15


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML parser that extracts visible text content."""

    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = False
        self._skip_tags = {"script", "style", "head", "meta", "link", "noscript"}

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.result.append(text)

    def get_text(self) -> str:
        return " ".join(self.result)


def _extract_text_from_html(html: str) -> str:
    """Extract visible text content from HTML."""
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html)
        return extractor.get_text()
    except Exception:
        # Fallback: strip tags with regex
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean)
        return clean.strip()


@tool
def analyze_document(url: str) -> str:
    """Fetch and extract text content from a URL. Use this tool to read web pages,
    articles, documentation, or any publicly accessible document.
    Returns the extracted text content for analysis."""
    try:
        if not url.startswith(("http://", "https://")):
            return f"Invalid URL: {url}. URL must start with http:// or https://"

        # WHY: LangChain runs this sync tool in a worker thread with no event loop,
        # so asyncio.run is safe here. The async agent rewrite calls safe_fetch
        # directly.
        result = asyncio.run(
            safe_fetch(
                url,
                allowed_hosts=parse_allowed_hosts(settings.fetch_allowed_hosts),
                max_bytes=500_000,
                timeout=REQUEST_TIMEOUT,
            )
        )

        if result.status_code >= 400:
            return f"HTTP error fetching {url}: {result.status_code}"

        content_type = result.headers.get("content-type", "")
        text = result.text

        # Extract text from HTML if needed
        if "html" in content_type.lower() or text.strip().startswith("<!"):
            text = _extract_text_from_html(text)

        # Truncate to keep within context limits
        if len(text) > MAX_CONTENT_CHARS:
            text = (
                text[:MAX_CONTENT_CHARS]
                + f"\n\n[Content truncated at {MAX_CONTENT_CHARS} characters]"
            )

        if not text.strip():
            return f"No readable text content found at {url}"

        return f"Content from {result.url}:\n\n{text}"

    except BlockedURLError as e:
        # WHY: Tell the model plainly so it doesn't keep retrying variants.
        return f"Request blocked: {e}"
    except (TimeoutError, httpx.TimeoutException):
        return f"Request timed out after {REQUEST_TIMEOUT} seconds for {url}"
    except httpx.HTTPError as e:
        return f"Failed to reach {url}: {e}"
    except Exception as e:
        logger.error(f"Document analysis error: {str(e)}")
        return f"Failed to analyze document at {url}: {str(e)}"
