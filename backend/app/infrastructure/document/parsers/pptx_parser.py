"""
PPTX document parser — python-pptx.
"""

from pathlib import Path

from app.shared.logging import logger

from .base import PARSER_REGISTRY


class PptxParser:
    """Parse .pptx files extracting text from all slide elements.

    Output format::

        === Slide N ===
        text content
        [备注] speaker notes

    Includes text frames, tables, and speaker notes.
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".pptx", ".ppt"]

    async def parse(self, filepath: str) -> str:
        from pptx import Presentation

        slide_parts: list[str] = []

        try:
            prs = Presentation(filepath)
        except Exception as exc:
            logger.error("PPTX open failed [{}]: {}", filepath, exc)
            return ""

        for slide_idx, slide in enumerate(prs.slides, 1):
            slide_texts: list[str] = []

            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        t = para.text.strip()
                        if t:
                            slide_texts.append(t)

                if shape.has_table:
                    for row in shape.table.rows:
                        cells = [
                            cell.text.strip()
                            for cell in row.cells
                            if cell.text.strip()
                        ]
                        if cells:
                            slide_texts.append(" | ".join(cells))

            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    slide_texts.append(f"[notes] {notes}")

            if slide_texts:
                slide_parts.append(
                    f"=== Slide {slide_idx} ===\n" + "\n".join(slide_texts)
                )

        result = "\n\n".join(slide_parts)
        logger.info(
            "PPTX parsed [{}]: {} slides, {} chars",
            Path(filepath).name,
            len(slide_parts),
            len(result),
        )
        return result


# ── Auto-register ─────────────────────────────────────────────────
for _ext in PptxParser().supported_extensions:
    PARSER_REGISTRY[_ext] = PptxParser
