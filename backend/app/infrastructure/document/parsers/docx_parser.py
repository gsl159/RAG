"""
DOCX document parser — python-docx.
"""

from pathlib import Path

from app.shared.logging import logger

from .base import PARSER_REGISTRY


class DocxParser:
    """Parse .docx files extracting paragraphs and table content.

    Heading levels are preserved as ``#``-prefixed headers in the output
    so downstream chunking can detect document structure.
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".docx", ".doc"]

    async def parse(self, filepath: str) -> str:
        from docx import Document as DocxDocument

        parts: list[str] = []

        try:
            doc = DocxDocument(filepath)
        except Exception as exc:
            logger.error("DOCX open failed [{}]: {}", filepath, exc)
            return ""

        # ── Paragraphs with heading level markers ──────────────
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = (
                para.style.name.lower()
                if para.style and para.style.name
                else ""
            )
            if style_name.startswith("heading"):
                try:
                    level = int(
                        style_name.replace("heading", "").strip()
                    )
                except (ValueError, AttributeError):
                    level = 1
                parts.append(f"{'#' * level} {text}")
            elif text:
                parts.append(text)

        # ── Tables ─────────────────────────────────────────────
        for table in doc.tables:
            for row in table.rows:
                cells = [
                    cell.text.strip()
                    for cell in row.cells
                    if cell.text.strip()
                ]
                if cells:
                    parts.append(" | ".join(cells))

        result = "\n".join(parts)
        logger.info(
            "DOCX parsed [{}]: {} parts, {} chars",
            Path(filepath).name,
            len(parts),
            len(result),
        )
        return result


# ── Auto-register ─────────────────────────────────────────────────
for _ext in DocxParser().supported_extensions:
    PARSER_REGISTRY[_ext] = DocxParser
