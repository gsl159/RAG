"""
Plain text parser — direct file read with encoding detection.
"""

from pathlib import Path

from app.shared.logging import logger

from .base import PARSER_REGISTRY


class TextParser:
    """Parse plain text files with automatic encoding detection.

    Tries UTF-8 first, falls back to GBK (common for Chinese documents),
    then latin-1 as a last resort.
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [
            ".txt", ".md", ".json", ".xml",
            ".yaml", ".yml", ".ini", ".cfg", ".log",
        ]

    async def parse(self, filepath: str) -> str:
        content = self._read_with_encoding(filepath)
        if content is None:
            logger.error(
                "Text read failed [{}]: all encodings exhausted",
                filepath,
            )
            return ""
        logger.info(
            "Text parsed [{}]: {} chars",
            Path(filepath).name,
            len(content),
        )
        return content

    @staticmethod
    def _read_with_encoding(path: str) -> str | None:
        """Try UTF-8, GBK, then latin-1.  Returns None if all fail."""
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                return Path(path).read_text(encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception:
                return None
        return None


# ── Auto-register ─────────────────────────────────────────────────
for _ext in TextParser().supported_extensions:
    PARSER_REGISTRY[_ext] = TextParser
