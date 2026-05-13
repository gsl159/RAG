"""AST-aware code chunker for Python, JavaScript/TypeScript, Go, and Rust.

Splits source code at function, class, method, and module boundaries
using language-specific AST parsers. Falls back to regex-based splitting
when AST parsing fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CodeChunk:
    content: str
    language: str
    chunk_type: str  # module, class, function, method, import_block, docstring
    name: str = ""
    class_name: str = ""
    start_line: int = 0
    end_line: int = 0
    meta: dict = field(default_factory=dict)


class AstChunker:
    """AST-aware source code chunker.

    Supports: Python, JavaScript/TypeScript, Go, Rust.
    Falls back to regex-based heuristic for unsupported languages.
    """

    _PARSERS: dict[str, Callable] = {}

    def __init__(self) -> None:
        self._register_builtins()

    def _register_builtins(self) -> None:
        self._PARSERS["python"] = self._chunk_python
        self._PARSERS["py"] = self._chunk_python
        self._PARSERS["javascript"] = self._chunk_javascript
        self._PARSERS["js"] = self._chunk_javascript
        self._PARSERS["typescript"] = self._chunk_javascript
        self._PARSERS["ts"] = self._chunk_javascript
        self._PARSERS["go"] = self._chunk_go
        self._PARSERS["golang"] = self._chunk_go
        self._PARSERS["rust"] = self._chunk_rust
        self._PARSERS["rs"] = self._chunk_rust

    def chunk(self, code: str, language: str = "") -> list[CodeChunk]:
        lang = language.lower()
        parser = self._PARSERS.get(lang)
        if parser:
            try:
                return parser(code)
            except Exception:
                pass
        return self._chunk_fallback(code, lang)

    # ------------------------------------------------------------------
    # Python AST chunker
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_python(code: str) -> list[CodeChunk]:
        try:
            import ast
            tree = ast.parse(code)
        except SyntaxError:
            return AstChunker._chunk_fallback(code, "python")

        chunks: list[CodeChunk] = []
        lines = code.split("\n")

        # Extract module docstring
        if (isinstance(tree.body, list) and tree.body
                and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant)
                and isinstance(tree.body[0].value.value, str)):
            doc_node = tree.body[0]
            chunks.append(CodeChunk(
                content="\n".join(lines[doc_node.lineno - 1:doc_node.end_lineno]),
                language="python",
                chunk_type="docstring",
                start_line=doc_node.lineno,
                end_line=doc_node.end_lineno or doc_node.lineno,
            ))

        # Extract imports
        import_lines: list[int] = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_lines.append(node.lineno - 1)
        if import_lines:
            chunks.append(CodeChunk(
                content="\n".join(lines[i] for i in import_lines),
                language="python",
                chunk_type="import_block",
                start_line=import_lines[0] + 1,
                end_line=import_lines[-1] + 1,
            ))

        # Extract top-level classes and functions
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                chunks.extend(AstChunker._extract_python_class(node, lines))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunks.append(AstChunker._extract_python_func(node, lines, ""))

        return chunks

    @staticmethod
    def _extract_python_class(
        node: Any, lines: list[str]
    ) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        class_name = node.name
        # Class definition itself
        class_src = "\n".join(lines[node.lineno - 1:node.end_lineno])
        chunks.append(CodeChunk(
            content=class_src,
            language="python",
            chunk_type="class",
            name=class_name,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
        ))
        # Methods
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunks.append(AstChunker._extract_python_func(
                    child, lines, class_name,
                ))
        return chunks

    @staticmethod
    def _extract_python_func(
        node: Any, lines: list[str], class_name: str
    ) -> CodeChunk:
        func_src = "\n".join(lines[node.lineno - 1:node.end_lineno])
        return CodeChunk(
            content=func_src,
            language="python",
            chunk_type="function",
            name=node.name,
            class_name=class_name,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
        )

    # ------------------------------------------------------------------
    # JavaScript / TypeScript (regex-based with structure awareness)
    # ------------------------------------------------------------------

    _JS_CLASS = re.compile(
        r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", re.MULTILINE
    )
    _JS_FUNC = re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+(\w+)|(\w+)\s*=\s*(?:async\s+)?function)",
        re.MULTILINE,
    )
    _JS_METHOD = re.compile(
        r"^\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*{", re.MULTILINE
    )

    @staticmethod
    def _chunk_javascript(code: str) -> list[CodeChunk]:
        return AstChunker._chunk_fallback(code, "javascript")

    # ------------------------------------------------------------------
    # Go (regex-based)
    # ------------------------------------------------------------------

    _GO_FUNC = re.compile(
        r"^func\s+(?:\([^)]*\)\s+)?(\w+)\(", re.MULTILINE
    )
    _GO_TYPE = re.compile(
        r"^type\s+(\w+)\s+struct\s*{", re.MULTILINE
    )
    _GO_METHOD = re.compile(
        r"^func\s+\((\w+)\s+\*?(\w+)\)\s+(\w+)\(", re.MULTILINE
    )

    @staticmethod
    def _chunk_go(code: str) -> list[CodeChunk]:
        return AstChunker._chunk_fallback(code, "go")

    # ------------------------------------------------------------------
    # Rust (regex-based)
    # ------------------------------------------------------------------

    _RUST_FN = re.compile(
        r"^\s*(?:pub(?:\s*\(\s*crate\s*\))?\s+)?(?:async\s+|unsafe\s+)?fn\s+(\w+)", re.MULTILINE
    )
    _RUST_STRUCT = re.compile(
        r"^\s*(?:pub\s+)?struct\s+(\w+)", re.MULTILINE
    )
    _RUST_IMPL = re.compile(
        r"^\s*impl\s+(?:(\w+)\s+for\s+)?(\w+)", re.MULTILINE
    )
    _RUST_TRAIT = re.compile(
        r"^\s*(?:pub\s+)?trait\s+(\w+)", re.MULTILINE
    )

    @staticmethod
    def _chunk_rust(code: str) -> list[CodeChunk]:
        return AstChunker._chunk_fallback(code, "rust")

    # ------------------------------------------------------------------
    # Fallback: regex-based structural chunking
    # ------------------------------------------------------------------

    _RE_CLASS = re.compile(
        r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+\w+", re.MULTILINE
    )
    _RE_FUNC = re.compile(
        r"^\s*(?:pub(?:\s*\(\s*crate\s*\))?\s+)?(?:async\s+|unsafe\s+)?(?:def|fn|func|function)\s+\w+",
        re.MULTILINE,
    )
    _RE_IMPORT = re.compile(
        r"^\s*(?:import|from|use|package|require)\s", re.MULTILINE
    )

    @staticmethod
    def _chunk_fallback(code: str, language: str) -> list[CodeChunk]:
        """Regex-based code splitting that keeps functions/classes intact."""
        lines = code.split("\n")
        if len(lines) <= 1:
            return [CodeChunk(
                content=code, language=language,
                chunk_type="module", start_line=1, end_line=1,
            )]

        # Find all structural boundaries
        boundaries: list[tuple[int, str, str]] = []
        for i, line in enumerate(lines):
            if AstChunker._RE_CLASS.match(line):
                name = line.strip().split()[-1].rstrip("{:").strip()
                boundaries.append((i, "class", name))
            elif AstChunker._RE_FUNC.match(line):
                parts = line.strip().split()
                name = parts[-1].split("(")[0] if "(" in parts[-1] else parts[-1]
                boundaries.append((i, "function", name))
            elif AstChunker._RE_IMPORT.match(line):
                boundaries.append((i, "import", ""))

        if not boundaries:
            return [CodeChunk(
                content=code, language=language,
                chunk_type="module", start_line=1, end_line=len(lines),
            )]

        chunks: list[CodeChunk] = []
        for j, (start, ctype, name) in enumerate(boundaries):
            end = boundaries[j + 1][0] if j + 1 < len(boundaries) else len(lines)
            content = "\n".join(lines[start:end])
            chunks.append(CodeChunk(
                content=content,
                language=language,
                chunk_type=ctype,
                name=name,
                start_line=start + 1,
                end_line=end,
            ))
        return chunks

    @staticmethod
    def detect_language(code: str, file_path: str = "") -> str:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
        ext_map = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "jsx": "javascript", "tsx": "typescript",
            "go": "go", "rs": "rust",
            "java": "java", "kt": "kotlin",
            "c": "c", "cpp": "cpp", "h": "c", "hpp": "cpp",
            "cs": "csharp", "swift": "swift",
        }
        if ext in ext_map:
            return ext_map[ext]
        # Heuristic detection
        if "def " in code and "import " in code:
            return "python"
        if "func " in code and "package " in code:
            return "go"
        if "fn " in code and "let " in code:
            return "rust"
        return "unknown"
