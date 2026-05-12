"""
Document processing infrastructure — parsers and text cleaning.
"""

from .text_cleaner import TextCleaner
from .parsers import (
    AbstractDocumentParser,
    PDFParser,
    DocxParser,
    PptxParser,
    SpreadsheetParser,
    HTMLParser,
    TextParser,
    PARSER_REGISTRY,
    get_parser_for_type,
)

__all__ = [
    "TextCleaner",
    "AbstractDocumentParser",
    "PDFParser",
    "DocxParser",
    "PptxParser",
    "SpreadsheetParser",
    "HTMLParser",
    "TextParser",
    "PARSER_REGISTRY",
    "get_parser_for_type",
]
