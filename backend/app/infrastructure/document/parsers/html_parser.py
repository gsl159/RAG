"""
HTML document parser — stdlib html.parser.

Strips markup, ignores script/style/nav/footer/header content,
preserves paragraph breaks.
"""

from html.parser import HTMLParser as StdlibHTMLParser
from pathlib import Path

from app.shared.logging import logger

from .base import PARSER_REGISTRY

_BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "blockquote", "pre", "section", "article",
}

_SKIP_TAGS = {
    "script", "style", "nav", "footer", "header",
}


class _TextExtractor(StdlibHTMLParser):
    """Strip tags and collect text, skipping non-content regions."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self._last_was_block = False

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag_lower in _BLOCK_TAGS and not self._last_was_block:
            if self.parts and not self.parts[-1].endswith("\n"):
                self.parts.append("\n")
            self._last_was_block = True

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag_lower == "br":
            self.parts.append("\n")
            self._last_was_block = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)
            self._last_was_block = False

    def get_data(self) -> str:
        import re
        text = "".join(self.parts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class HTMLParser:
    """Parse HTML files into plain text, preserving paragraph structure."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".html", ".htm"]

    async def parse(self, filepath: str) -> str:
        try:
            raw = Path(filepath).read_text("utf-8", errors="replace")
        except Exception as exc:
            logger.error("HTML read failed [{}]: {}", filepath, exc)
            return ""

        extractor = _TextExtractor()
        try:
            extractor.feed(raw)
        except Exception as exc:
            logger.warning("HTML parse error [{}]: {}", filepath, exc)

        result = extractor.get_data()
        logger.info(
            "HTML parsed [{}]: {} chars",
            Path(filepath).name,
            len(result),
        )
        return result


# ── Auto-register ─────────────────────────────────────────────────
for _ext in HTMLParser().supported_extensions:
    PARSER_REGISTRY[_ext] = HTMLParser
