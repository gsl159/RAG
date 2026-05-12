"""
Document parser base — Protocol and registry.
"""

from typing import Protocol, Optional


class AbstractDocumentParser(Protocol):
    """Protocol for document format parsers."""

    async def parse(self, filepath: str) -> str:
        """Parse a document and return its text content."""
        ...

    @property
    def supported_extensions(self) -> list[str]:
        """Return list of supported file extensions."""
        ...


# Registry mapping extensions to parser classes
PARSER_REGISTRY: dict[str, type] = {}


def get_parser_for_type(file_ext: str) -> Optional[AbstractDocumentParser]:
    """Factory: return parser instance for a given file extension.

    Args:
        file_ext: File extension with leading dot, e.g. ".pdf"

    Returns:
        Parser instance or None if no parser is registered for this extension.
    """
    ext = file_ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    cls = PARSER_REGISTRY.get(ext)
    return cls() if cls else None
