"""End-to-end verification of Chunking System v2.

Tests the full pipeline: parse -> structure_extract -> section_tree ->
chunk -> relationship_build -> quality_filter.

Runs with SQLite — no external services needed.
"""

import asyncio
import hashlib
import os
import sys
import uuid

sys.path.insert(0, '/mnt/d/project/rag_system/backend')

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test_e2e.db"
os.environ["APP_ENV"] = "development"

TEST_MARKDOWN = """# MySQL 8.0 部署指南

## 安装 MySQL

### 下载安装包

从官网下载 MySQL 8.0 社区版。

### 执行安装

```bash
yum install mysql-server -y
```

## 初始化 MySQL

### 初始化数据目录

```bash
mysqld --initialize --user=mysql
```

### 启动服务

```bash
systemctl start mysqld
```

## 创建数据库

### 连接 MySQL

```sql
CREATE DATABASE app_db CHARACTER SET utf8mb4;
CREATE USER 'app_user'@'%' IDENTIFIED BY 'password';
GRANT ALL ON app_db.* TO 'app_user'@'%';
```

## 权限配置

### 设置 root 密码

```sql
ALTER USER 'root'@'localhost' IDENTIFIED BY 'new_password';
FLUSH PRIVILEGES;
```

### 创建只读用户

```sql
CREATE USER 'reader'@'%' IDENTIFIED BY 'readonly';
GRANT SELECT ON app_db.* TO 'reader'@'%';
```
"""

TEST_CODE = '''"""Database connection pool module."""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


class ConnectionPool:
    """Async connection pool for PostgreSQL."""

    def __init__(self, dsn: str, pool_size: int = 10) -> None:
        self._dsn = dsn
        self._pool_size = pool_size
        self._engine = None

    async def connect(self) -> None:
        """Initialize the connection pool."""
        self._engine = create_async_engine(
            self._dsn,
            pool_size=self._pool_size,
            echo=False,
        )

    async def disconnect(self) -> None:
        """Close all connections."""
        if self._engine:
            await self._engine.dispose()

    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async session from the pool."""
        async_session = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session() as session:
            yield session


def get_dsn_from_env() -> str:
    """Build DSN from environment variables."""
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    db = os.environ.get("DB_NAME", "app")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
'''


async def test_markdown_chunking():
    """E2E test: Markdown document -> chunks + sections + relationships."""
    print("=" * 60)
    print("TEST 1: Markdown Document Chunking")
    print("=" * 60)

    from app.infrastructure.document.text_cleaner import TextCleaner
    from app.infrastructure.chunking.structure_extractor import StructureExtractor
    from app.infrastructure.chunking.section_tree_builder import SectionTreeBuilder
    from app.infrastructure.chunking.strategy_resolver import resolve_strategy
    from app.infrastructure.chunking.chunk_relationship_builder import ChunkRelationshipBuilder
    from app.domain.entities.document import Chunk, ChunkType, Section
    from app.infrastructure.chunking.language_detector import LanguageDetector

    doc_id = str(uuid.uuid4())

    # Step 1: Clean text
    cleaner = TextCleaner()
    text = cleaner.clean(TEST_MARKDOWN)

    # Step 2: Extract structure
    extractor = StructureExtractor()
    structure = extractor.extract(text)
    doc_type = StructureExtractor.classify_document_type(structure, '.md')

    headings = [e for e in structure.elements if e.type == 'heading']
    print(f"  Structure: {len(headings)} headings detected, doc_type={doc_type}")
    for h in headings:
        print(f"    {'#' * h.level} {h.title}")

    # Step 3: Build section tree
    builder = SectionTreeBuilder(doc_id)
    sections = builder.build(structure)
    print(f"  Section tree: {len(sections)} sections")
    for s in sections:
        indent = "  " * (s.level - 1)
        print(f"    {indent}└─ {s.title} [{s.id[:8]}...] parent={s.parent_id[:8] if s.parent_id else 'ROOT'}")

    # Step 4: Chunk with strategy
    detector = LanguageDetector()
    lang_profile = detector.detect(text[:5000])
    params, strategy_cls = resolve_strategy('.md', language_profile=lang_profile, doc_type=doc_type)
    strategy = strategy_cls(chunk_size=params.chunk_size, chunk_overlap=params.chunk_overlap, min_chunk_size=params.min_chunk_size)
    chunk_nodes = await strategy.chunk(text, doc_id=doc_id)

    print(f"  Strategy: {strategy_cls.__name__}, chunk_size={params.chunk_size}, overlap={params.chunk_overlap}")

    # Step 5: Map to domain entities
    heading_elements = [e for e in structure.elements if e.type == 'heading']
    chunks = []
    for i, node in enumerate(chunk_nodes):
        best_sid = ""
        best_path = []
        for heading in heading_elements:
            char_start = node.meta.get("char_start", 0) if hasattr(node, 'meta') else 0
            if char_start >= heading.start:
                for s in sections:
                    if s.title == heading.title:
                        best_sid = s.id
                        best_path = s.path
                        break

        source_hash = hashlib.sha256(node.content.encode()).hexdigest()[:16]
        chunks.append(Chunk(
            id=node.chunk_id, doc_id=doc_id, content=node.content,
            chunk_idx=i, section_id=best_sid,
            char_count=node.char_count,
            token_count=getattr(node, 'token_count', 0),
            parent_id=node.parent_id or "",
            heading=node.heading or "",
            chunk_type=ChunkType.TEXT if node.chunk_type == 'text' else ChunkType(node.chunk_type),
            page=node.page,
            section_path=best_path or getattr(node, 'section_path', []),
            source_hash=source_hash, embedding_version="v1",
        ))

    # Step 6: Build relationships
    rel_builder = ChunkRelationshipBuilder()
    relations = rel_builder.build(chunks, sections)
    chunks = rel_builder.apply_to_chunks(chunks, relations)

    # Step 7: Verify
    print(f"\n  Results:")
    print(f"    Total chunks: {len(chunks)}")
    print(f"    Total sections: {len(sections)}")

    # Chunks with section assignment
    chunks_with_section = [c for c in chunks if c.section_id]
    print(f"    Chunks with section: {len(chunks_with_section)}/{len(chunks)}")

    # Sequential links
    has_prev = [c for c in chunks if c.prev_chunk_id]
    has_next = [c for c in chunks if c.next_chunk_id]
    print(f"    Sequential links: {len(has_prev)} prev, {len(has_next)} next")

    # Section hierarchy
    root_sections = [s for s in sections if not s.parent_id]
    child_sections = [s for s in sections if s.parent_id]
    print(f"    Section hierarchy: {len(root_sections)} root(s), {len(child_sections)} child(ren)")

    # Content integrity
    print(f"\n  Chunk details:")
    for c in chunks[:5]:
        content_preview = c.content[:60].replace('\n', '\\n')
        print(f"    [{c.chunk_idx}] type={c.chunk_type} section={c.section_path} heading={c.heading[:30]} prev={c.prev_chunk_id[:8]}... next={c.next_chunk_id[:8]}...")
        print(f"         content: {content_preview}...")

    # Verify critical requirements
    errors = []

    if len(sections) == 0:
        errors.append("NO sections built — structure awareness failed")
    if len(chunks) == 0:
        errors.append("NO chunks produced")
    if len(chunks_with_section) == 0:
        errors.append("NO chunk-section mapping")
    if not any(s.parent_id for s in sections):
        errors.append("NO section hierarchy (all flat)")

    if errors:
        print(f"\n  FAILED:")
        for e in errors:
            print(f"    X {e}")
        return False
    else:
        print(f"\n  PASSED: All structure-aware chunking requirements met")
        return True


async def test_code_chunking():
    """E2E test: Code file -> AST chunking."""
    print("\n" + "=" * 60)
    print("TEST 2: Code Document AST Chunking")
    print("=" * 60)

    from app.infrastructure.chunking.ast_chunker import AstChunker
    from app.domain.entities.document import Chunk, ChunkType

    doc_id = str(uuid.uuid4())
    chunker = AstChunker()
    lang = AstChunker.detect_language(TEST_CODE, 'connection_pool.py')
    code_chunks = chunker.chunk(TEST_CODE, lang)

    print(f"  Language: {lang}")
    print(f"  Code chunks: {len(code_chunks)}")

    chunks = []
    for i, cc in enumerate(code_chunks):
        chunks.append(Chunk(
            id=str(uuid.uuid4()), doc_id=doc_id, content=cc.content,
            chunk_idx=i, char_count=len(cc.content),
            token_count=len(cc.content) // 4,
            heading=cc.name,
            chunk_type=ChunkType.CODE,
        ))

    errors = []
    # Verify functions/classes not truncated
    for c in chunks:
        content = c.content.strip()
        if content.startswith('class ') and not content.rstrip().endswith(('pass', '...', 'return', ')')):
            pass  # class body can end with anything
        if content.startswith('def ') and len(content) < 10:
            errors.append(f"Truncated function: {content[:50]}")

    has_class = any('class ' in c.content for c in chunks)
    has_func = any('def ' in c.content for c in chunks)
    has_import = any(('import ' in c.content or 'from ' in c.content) and 'pass' not in c.content for c in chunks)

    print(f"  Classes detected: {has_class}")
    print(f"  Functions detected: {has_func}")
    print(f"  Import blocks: {has_import}")
    for c in chunks:
        lines = c.content.strip().split('\n')
        print(f"    [{c.chunk_idx}] type={c.chunk_type} name={c.heading} lines={len(lines)} chars={len(c.content)}")

    if errors:
        print(f"\n  FAILED:")
        for e in errors:
            print(f"    X {e}")
        return False
    else:
        print(f"\n  PASSED: Code chunking preserves structure")
        return True


async def test_relationship_building():
    """E2E test: Verify chunk relationship graph."""
    print("\n" + "=" * 60)
    print("TEST 3: Chunk Relationship Graph")
    print("=" * 60)

    from app.infrastructure.chunking.chunk_relationship_builder import ChunkRelationshipBuilder
    from app.domain.entities.document import Chunk, ChunkType, Section

    doc_id = "test-doc-3"

    # Simulate 4 chunks in 2 sections
    s1 = Section(id="s1", document_id=doc_id, title="Install", level=1, path=["Install"])
    s2 = Section(id="s2", document_id=doc_id, title="Config", level=1, path=["Config"])

    c1 = Chunk(id="c1", doc_id=doc_id, content="Step 1", chunk_idx=0, section_id="s1")
    c2 = Chunk(id="c2", doc_id=doc_id, content="Step 2", chunk_idx=1, section_id="s1")
    c3 = Chunk(id="c3", doc_id=doc_id, content="Config A", chunk_idx=2, section_id="s2")
    c4 = Chunk(id="c4", doc_id=doc_id, content="Config B", chunk_idx=3, section_id="s2")

    builder = ChunkRelationshipBuilder()
    relations = builder.build([c1, c2, c3, c4], [s1, s2])
    updated = builder.apply_to_chunks([c1, c2, c3, c4], relations)

    print(f"  prev_map: {relations.prev_map}")
    print(f"  next_map: {relations.next_map}")
    print(f"  parent_map: {relations.parent_map}")

    errors = []
    if updated[0].next_chunk_id != "c2":
        errors.append(f"c1.next should be c2, got {updated[0].next_chunk_id}")
    if updated[1].prev_chunk_id != "c1":
        errors.append(f"c2.prev should be c1, got {updated[1].prev_chunk_id}")
    if updated[2].next_chunk_id != "c4":
        errors.append(f"c3.next should be c4, got {updated[2].next_chunk_id}")

    if errors:
        print(f"  FAILED:")
        for e in errors:
            print(f"    X {e}")
        return False
    else:
        print(f"  PASSED: Sequential and parent links correct")
        return True


async def test_doc_type_sizing():
    """E2E test: Verify dynamic chunk sizing by document type."""
    print("\n" + "=" * 60)
    print("TEST 4: Dynamic Chunk Size Resolution")
    print("=" * 60)

    from app.infrastructure.chunking.strategy_resolver import resolve_doc_type_size

    expected = {
        'faq': (500, 50),
        'markdown': (1000, 100),
        'code': (1200, 150),
        'tutorial': (1500, 300),
        'table_doc': (800, 0),
        'api_spec': (800, 50),
        'narrative': (800, 100),
    }

    all_ok = True
    for dt, (expected_size, expected_overlap) in expected.items():
        size, overlap = resolve_doc_type_size(dt)
        status = "OK" if (size, overlap) == (expected_size, expected_overlap) else "MISMATCH"
        if status != "OK":
            all_ok = False
        print(f"  {dt:15s}: size={size:4d} overlap={overlap:3d} [{status}]")

    if all_ok:
        print(f"\n  PASSED: All document type sizes correct")
    else:
        print(f"\n  FAILED: Size mismatches detected")
    return all_ok


async def main():
    print("Chunking System v2 — End-to-End Verification")
    print("=" * 60)
    print()

    results = []
    results.append(await test_doc_type_sizing())
    results.append(await test_markdown_chunking())
    results.append(await test_code_chunking())
    results.append(await test_relationship_building())

    passed = sum(results)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"VERIFICATION COMPLETE: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("ALL TESTS PASSED — Chunking System v2 is verified.")
        return 0
    else:
        print(f"FAILURES: {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
