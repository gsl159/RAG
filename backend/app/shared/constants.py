"""Immutable application-wide constants."""

from __future__ import annotations


class Constants:
    """Central repository for all numeric and categorical constants.

    All values are immutable at the class level.  Instantiation is not
    expected (the class serves as a namespace).
    """

    # ── Upload limits ─────────────────────────────────────────────
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MiB
    MAX_ZIP_ENTRIES: int = 200
    MAX_ZIP_TOTAL_BYTES: int = 500 * 1024 * 1024  # 500 MiB

    # ── Allowed file extensions ───────────────────────────────────
    ALLOWED_EXTENSIONS: frozenset[str] = frozenset({
        "pdf", "docx", "pptx", "xlsx", "csv",
        "txt", "md", "html", "json", "xml", "zip",
    })

    # ── Chat / Q&A limits ─────────────────────────────────────────
    MAX_QUESTION_LENGTH: int = 2000
    PREVIEW_CHARS: int = 200
    SUGGESTION_TOP_N: int = 5

    # ── Database ──────────────────────────────────────────────────
    SQL_IN_CLAUSE_BATCH: int = 500

    # ── URL import ────────────────────────────────────────────────
    URL_IMPORT_MAX_URLS: int = 10
    URL_FETCH_TIMEOUT: int = 30  # seconds
    URL_MAX_CONTENT_BYTES: int = 10 * 1024 * 1024  # 10 MiB

    # ── BM25 ──────────────────────────────────────────────────────
    BM25_BATCH_SIZE: int = 512
