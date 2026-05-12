"""
Document parsers — re-exports and auto-registration.
"""

from .base import AbstractDocumentParser, get_parser_for_type, PARSER_REGISTRY
from .pdf_parser import PDFParser
from .docx_parser import DocxParser
from .pptx_parser import PptxParser
from .spreadsheet_parser import SpreadsheetParser
from .html_parser import HTMLParser
from .text_parser import TextParser

__all__ = [
    "AbstractDocumentParser",
    "PDFParser",
    "DocxParser",
    "PptxParser",
    "SpreadsheetParser",
    "HTMLParser",
    "TextParser",
    "get_parser_for_type",
    "PARSER_REGISTRY",
]
