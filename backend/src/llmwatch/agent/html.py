"""
Module: html.py
Purpose: Extracts readable text from HTML for the agent's fetch tool.
"""

import re
from html.parser import HTMLParser


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML parser that extracts visible text content."""

    def __init__(self):
        super().__init__()
        self.result: list[str] = []
        self._skip = 0
        self._skip_tags = {"script", "style", "head", "meta", "link", "noscript"}

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._skip_tags:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._skip_tags and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self.result.append(text)

    def get_text(self) -> str:
        return " ".join(self.result)


def extract_text_from_html(html: str) -> str:
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
