"""
Spreadsheet parser — Excel (openpyxl) and CSV.

Output is rendered as Markdown-style tables::

    | col1 | col2 | col3 |
    |------|------|------|
    | val1 | val2 | val3 |
"""

import csv
from pathlib import Path

from app.shared.logging import logger

from .base import PARSER_REGISTRY

_MAX_ROWS = 5000


class SpreadsheetParser:
    """Parse Excel (.xlsx) and CSV files into markdown table format.

    For CSV files encoding is auto-detected (UTF-8, GBK, latin-1).
    For XLSX only the first sheet is parsed by default (use ``sheet_name``
    parameter for specific sheets).
    """

    def __init__(self, sheet_name: str | None = None):
        self.sheet_name = sheet_name

    @property
    def supported_extensions(self) -> list[str]:
        return [".xlsx", ".csv"]

    async def parse(self, filepath: str) -> str:
        suffix = Path(filepath).suffix.lower()
        try:
            if suffix == ".csv":
                return self._parse_csv(filepath)
            return self._parse_xlsx(filepath)
        except Exception as exc:
            logger.error("Spreadsheet parse failed [{}]: {}", filepath, exc)
            return ""

    # ── CSV ──────────────────────────────────────────────────────

    def _parse_csv(self, path: str) -> str:
        encoding = self._detect_encoding(path)
        parts: list[str] = []

        with open(path, "r", encoding=encoding, errors="replace") as f:
            reader = csv.reader(f)
            rows: list[list[str]] = []
            for row in reader:
                cleaned = [cell.strip() for cell in row]
                rows.append(cleaned)
                if len(rows) >= _MAX_ROWS:
                    break

        if not rows:
            return ""

        parts.append(self._rows_to_markdown(rows))

        result = "\n".join(parts)
        logger.info(
            "CSV parsed [{}]: {} rows, {} chars",
            Path(path).name,
            len(rows),
            len(result),
        )
        return result

    # ── XLSX ─────────────────────────────────────────────────────

    def _parse_xlsx(self, path: str) -> str:
        from openpyxl import load_workbook

        parts: list[str] = []

        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:
            logger.error("XLSX open failed [{}]: {}", path, exc)
            return ""

        sheet_names = (
            [self.sheet_name]
            if self.sheet_name
            else wb.sheetnames
        )

        for sheet_name in sheet_names:
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]

            rows: list[list[str]] = []
            for row in ws.iter_rows(values_only=True):
                cleaned = [
                    str(cell).strip()
                    for cell in row
                    if cell is not None and str(cell).strip()
                ]
                if cleaned:
                    rows.append(cleaned)
                if len(rows) >= _MAX_ROWS:
                    break

            if not rows:
                continue

            parts.append(f"=== {sheet_name} ===")
            parts.append(self._rows_to_markdown(rows))

        wb.close()

        result = "\n".join(parts)
        logger.info(
            "XLSX parsed [{}]: {} sheets, {} chars",
            Path(path).name,
            len(sheet_names),
            len(result),
        )
        return result

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _rows_to_markdown(rows: list[list[str]]) -> str:
        """Convert a list of row-lists to a markdown table string."""
        if not rows:
            return ""
        header = rows[0]
        ncols = max(len(r) for r in rows) if rows else len(header)

        padded = [r + [""] * (ncols - len(r)) for r in rows]

        lines: list[str] = []
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join("---" for _ in range(ncols)) + " |")
        for row in padded[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    @staticmethod
    def _detect_encoding(path: str) -> str:
        """Detect file encoding: try UTF-8, then GBK, fallback to latin-1."""
        for enc in ("utf-8", "gbk", "latin-1"):
            try:
                with open(path, "r", encoding=enc) as f:
                    f.read(1024)
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue
        return "latin-1"


# ── Auto-register ─────────────────────────────────────────────────
for _ext in SpreadsheetParser().supported_extensions:
    PARSER_REGISTRY[_ext] = SpreadsheetParser
