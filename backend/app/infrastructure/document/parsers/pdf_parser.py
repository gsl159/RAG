"""
PDF document parser — pymupdf (fitz) with OCR fallback for scanned pages.
"""

from pathlib import Path

from app.config.settings import settings
from app.shared.logging import logger

from .base import PARSER_REGISTRY


class PDFParser:
    """Parse PDF files using pymupdf with optional OCR fallback.

    Text is extracted page by page.  For image-only pages (scanned docs)
    OCR is attempted when ``OCR_ENABLED`` is ``True``.  Total output is
    capped at ``PDF_MAX_EXTRACT_CHARS`` to avoid OOM on very large PDFs.
    """

    @property
    def supported_extensions(self) -> list[str]:
        return [".pdf"]

    async def parse(self, filepath: str) -> str:
        import fitz  # pymupdf

        texts: list[str] = []
        total = 0
        cap = settings.PDF_MAX_EXTRACT_CHARS

        try:
            with fitz.open(filepath) as doc:
                for page_num, page in enumerate(doc, 1):
                    page_text = page.get_text("text")

                    if not page_text.strip():
                        if settings.OCR_ENABLED:
                            page_text = self._ocr_page(page)
                        if not page_text or not page_text.strip():
                            logger.debug(
                                "PDF page {} yielded no text (blank or unreadable)",
                                page_num,
                            )
                            continue

                    if total >= cap:
                        break
                    remaining = cap - total
                    if len(page_text) > remaining:
                        if remaining > 50:
                            texts.append(page_text[:remaining])
                        break

                    texts.append(page_text)
                    total += len(page_text)

        except Exception as exc:
            logger.error("PDF parse failed [{}]: {}", filepath, exc)
            return ""

        result = "\n\n".join(texts)
        logger.info(
            "PDF parsed [{}]: {} pages, {} chars",
            Path(filepath).name,
            len(texts),
            len(result),
        )
        return result

    @staticmethod
    def _ocr_page(page) -> str:
        """Run OCR on a single PDF page (requires pytesseract + Tesseract)."""
        try:
            import pytesseract
            from PIL import Image
            import io

            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            return pytesseract.image_to_string(img, lang="chi_sim+eng")
        except ImportError:
            logger.debug("pytesseract not installed -- OCR skipped")
            return ""
        except Exception as exc:
            logger.warning("OCR failed on page: {}", exc)
            return ""


# ── Auto-register ─────────────────────────────────────────────────
for _ext in PDFParser().supported_extensions:
    PARSER_REGISTRY[_ext] = PDFParser
