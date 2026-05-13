"""Document use case — upload, process (full chunking pipeline v2), delete, list."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config.settings import Settings
from app.domain.entities.document import Chunk, ChunkType, Document, DocumentStatus, Section
from app.domain.entities.user import User
from app.domain.ports.cache_port import AbstractCacheService
from app.domain.ports.llm_port import AbstractEmbeddingService
from app.domain.ports.repository_ports import (
    AbstractChunkRepository,
    AbstractDocumentRepository,
    AbstractSectionRepository,
)
from app.domain.ports.search_port import AbstractSearchService
from app.domain.ports.storage_port import AbstractStorageService
from app.domain.ports.task_queue_port import AbstractTaskQueue, TaskItem
from app.domain.ports.vector_port import AbstractVectorRepository


class DocumentUseCase:
    """Document processing use case — v2 with full chunking pipeline.

    Pipeline: parse -> structure_extract -> section_tree -> chunk ->
              relationship_build -> metadata_enrich -> quality_filter ->
              embed_chunks -> embed_sections -> index -> done
    """

    def __init__(
        self,
        document_repo: AbstractDocumentRepository,
        chunk_repo: AbstractChunkRepository,
        section_repo: AbstractSectionRepository | None,
        vector_repo: AbstractVectorRepository,
        search_service: AbstractSearchService,
        storage: AbstractStorageService,
        embed_service: AbstractEmbeddingService,
        cache: AbstractCacheService,
        task_queue: AbstractTaskQueue,
        settings: Settings,
    ) -> None:
        self._document_repo = document_repo
        self._chunk_repo = chunk_repo
        self._section_repo = section_repo
        self._vector_repo = vector_repo
        self._search_service = search_service
        self._storage = storage
        self._embed_service = embed_service
        self._cache = cache
        self._task_queue = task_queue
        self._settings = settings

    async def upload_document(
        self, filename: str, content: bytes, user: User, dept_id: str = "",
    ) -> Document:
        doc_id = str(uuid.uuid4())
        file_type = self._infer_file_type(filename)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        document = Document(
            id=doc_id, filename=filename, file_type=file_type,
            file_size=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
            status=DocumentStatus.PENDING, tenant_id=user.tenant_id,
            dept_id=dept_id or user.dept_id,
            created_at=now, updated_at=now, uploaded_by=user.id,
        )
        document = await self._document_repo.save(document)
        await self._storage.upload(doc_id, content, content_type=file_type)
        task = TaskItem(doc_id=doc_id, file_ext=file_type, content=content)
        await self._task_queue.enqueue(task)
        return document

    async def process_document(self, doc_id: str) -> Document:
        """Full chunking pipeline v2."""
        document = await self._document_repo.find_by_id(doc_id)
        if document is None:
            raise ValueError(f"Document not found: {doc_id}")

        try:
            await self._document_repo.update_status(doc_id, DocumentStatus.PROCESSING)
            try:
                from app.api.routes.ws import broadcast_progress
                await broadcast_progress({"doc_id": doc_id, "status": "processing"})
            except Exception:
                pass

            content = await self._storage.download(doc_id)

            # Clean old artifacts
            for repo in [self._chunk_repo, self._section_repo]:
                if repo:
                    try:
                        await repo.delete_by_doc_id(doc_id)
                    except Exception:
                        pass

            # ── Pipeline v2 ──────────────────────────────────────────
            chunks, sections, doc_type = await self._parse_and_chunk_v2(
                doc_id, content, document.file_type
            )

            # Save sections
            if sections and self._section_repo:
                await self._section_repo.save_batch(sections)

            # Build chunk relationships
            from app.infrastructure.chunking.chunk_relationship_builder import (
                ChunkRelationshipBuilder,
            )
            rel_builder = ChunkRelationshipBuilder()
            relations = rel_builder.build(chunks, sections)
            chunks = rel_builder.apply_to_chunks(chunks, relations)

            # Metadata injection
            from app.infrastructure.chunking.metadata_injector import MetadataInjector
            injector = MetadataInjector()
            doc_info = {
                "doc_name": document.filename,
                "doc_version": str(document.doc_version),
                "source_path": document.filename,
                "file_format": document.file_type,
            }
            enriched_chunks = injector.inject(
                [self._chunk_to_dict(c) for c in chunks],
                doc_info,
                page_map=None,
                strategy_name="semantic",
            )

            # Merge enriched metadata back
            for i, enriched in enumerate(enriched_chunks):
                meta = enriched.get("metadata", {})
                chunks[i] = Chunk(
                    id=chunks[i].id, doc_id=chunks[i].doc_id,
                    content=chunks[i].content, chunk_idx=chunks[i].chunk_idx,
                    section_id=chunks[i].section_id,
                    char_count=chunks[i].char_count,
                    token_count=chunks[i].token_count,
                    parent_id=chunks[i].parent_id,
                    heading=chunks[i].heading,
                    chunk_type=chunks[i].chunk_type, page=chunks[i].page,
                    section_path=chunks[i].section_path,
                    prev_chunk_id=chunks[i].prev_chunk_id,
                    next_chunk_id=chunks[i].next_chunk_id,
                    parent_section_id=chunks[i].parent_section_id,
                    root_section=chunks[i].root_section,
                    source_hash=meta.chunk_hash if hasattr(meta, "chunk_hash") else "",
                    embedding_version="v1",
                    chunk_version=document.doc_version,
                    meta_info=chunks[i].meta_info,
                )

            # Save chunks
            saved_chunks = await self._chunk_repo.save_batch(chunks)

            # Quality filter
            filtered_chunks, filter_rate = await self._apply_quality_filter(saved_chunks)

            # Quality scoring
            quality = await self._compute_quality(filtered_chunks, filter_rate)
            await self._document_repo.update_parse_score(doc_id, quality)

            if filter_rate > 0.30:
                from app.shared.logging import logger
                logger.warning(
                    "Filter rate exceeded: doc_id=%s filter_rate=%.1%%", doc_id, filter_rate * 100)

            # Embed chunks
            texts = [c.content for c in filtered_chunks]
            chunk_dicts = [self._chunk_to_dict(c) for c in filtered_chunks]
            embeddings = await self._embed_service.embed_batch(
                texts, batch_size=self._settings.EMBED_BATCH_SIZE)
            await self._vector_repo.insert(chunk_dicts, embeddings)
            await self._search_service.add_texts(chunk_dicts)

            # Section embeddings
            if sections and self._section_repo:
                await self._embed_sections(sections, saved_chunks)

            await self._cache.increment_doc_version()
            await self._document_repo.update_chunk_count(doc_id, len(filtered_chunks))
            await self._document_repo.update_status(doc_id, DocumentStatus.DONE)

            try:
                from app.api.routes.ws import broadcast_progress
                await broadcast_progress({"doc_id": doc_id, "status": "done"})
            except Exception:
                pass

        except Exception as e:
            await self._document_repo.update_status(doc_id, DocumentStatus.FAILED, error_msg=str(e))
            try:
                from app.api.routes.ws import broadcast_progress
                await broadcast_progress({"doc_id": doc_id, "status": "failed"})
            except Exception:
                pass

        return await self._document_repo.find_by_id(doc_id)

    async def delete_document(self, doc_id: str, user: User) -> None:
        document = await self._document_repo.find_by_id(doc_id)
        if document is None:
            raise ValueError(f"Document not found: {doc_id}")
        try:
            await self._vector_repo.delete_by_doc_id(doc_id)
        except Exception:
            pass
        try:
            chunks = await self._chunk_repo.find_by_doc_id(doc_id)
            chunk_ids = [c.id for c in chunks]
            if chunk_ids:
                await self._search_service.remove_texts(chunk_ids)
        except Exception:
            pass
        for repo in [self._chunk_repo, self._section_repo]:
            if repo:
                try:
                    await repo.delete_by_doc_id(doc_id)
                except Exception:
                    pass
        try:
            await self._storage.delete(doc_id)
        except Exception:
            pass
        await self._document_repo.delete(doc_id)
        await self._cache.increment_doc_version()

    async def list_documents(
        self, tenant_id: str, status: str = "", limit: int = 50, cursor: str = "",
    ) -> tuple[list[Document], str | None]:
        offset = 0
        if cursor:
            try:
                offset = int(cursor)
            except (ValueError, TypeError):
                offset = 0
        docs = await self._document_repo.list_all(tenant_id, limit=limit + 1, offset=offset)
        has_more = len(docs) > limit
        if has_more:
            docs = docs[:limit]
        next_cursor = str(offset + limit) if has_more else None
        return docs, next_cursor

    async def retry_document(self, doc_id: str) -> None:
        doc = await self._document_repo.find_by_id(doc_id)
        if doc is None:
            raise ValueError(f"Document not found: {doc_id}")
        await self._document_repo.update_status(doc_id, DocumentStatus.PENDING)
        content = await self._storage.download(doc_id)
        task = TaskItem(doc_id=doc_id, file_ext=doc.file_type, content=content)
        await self._task_queue.enqueue(task)

    # ------------------------------------------------------------------
    # Pipeline v2: parse + structure + chunk
    # ------------------------------------------------------------------

    async def _parse_and_chunk_v2(
        self, doc_id: str, content: bytes, file_type: str,
    ) -> tuple[list[Chunk], list[Section], str]:
        """Full pipeline: parse -> structure extract -> section tree -> chunk."""
        import os
        import tempfile

        from app.infrastructure.chunking.strategy_resolver import resolve_strategy
        from app.infrastructure.chunking.structure_extractor import StructureExtractor
        from app.infrastructure.chunking.section_tree_builder import SectionTreeBuilder
        from app.infrastructure.document.parsers.base import get_parser_for_type
        from app.infrastructure.document.text_cleaner import TextCleaner
        from app.infrastructure.chunking.language_detector import LanguageDetector

        cleaner = TextCleaner()
        text = ""

        ext = f".{file_type}" if not file_type.startswith(".") else file_type
        parser = get_parser_for_type(ext)

        if parser is not None:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                text = await parser.parse(tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            text = content.decode("utf-8", errors="replace")

        text = cleaner.clean(text)

        # Structure extraction
        extractor = StructureExtractor()
        structure = extractor.extract(text)
        doc_type = StructureExtractor.classify_document_type(structure, ext)

        # Section tree
        tree_builder = SectionTreeBuilder(doc_id)
        sections = tree_builder.build(structure)

        # Language detection
        detector = LanguageDetector()
        lang_profile = detector.detect(text[:5000])

        # Resolve strategy with doc_type
        params, strategy_cls = resolve_strategy(
            ext,
            language_profile=lang_profile,
            semantic_chunking_enabled=self._settings.SEMANTIC_CHUNKING_ENABLED,
            chunk_size=self._settings.CHUNK_SIZE,
            chunk_overlap=self._settings.CHUNK_OVERLAP,
            doc_type=doc_type,
        )

        strategy = strategy_cls(
            chunk_size=params.chunk_size,
            chunk_overlap=params.chunk_overlap,
            min_chunk_size=params.min_chunk_size,
        )

        # For code files, use AST chunker
        if doc_type == "code" or ext in (".py", ".js", ".ts", ".go", ".rs"):
            chunks = await self._chunk_code(text, doc_id, ext, params)
        else:
            chunk_nodes = await strategy.chunk(text, doc_id=doc_id)
            chunks = []
            for node in chunk_nodes:
                # Map chunk to nearest section
                heading_elements = [e for e in structure.elements if e.type == "heading"]
                best_section_id = ""
                best_section_path: list[str] = []
                for heading in heading_elements:
                    if hasattr(node, 'meta') and node.meta.get("char_start", 0) >= heading.start:
                        for s in sections:
                            if s.title == heading.title:
                                best_section_id = s.id
                                best_section_path = s.path
                                break

                source_hash = hashlib.sha256(node.content.encode()).hexdigest()[:16]
                chunks.append(Chunk(
                    id=node.chunk_id, doc_id=doc_id, content=node.content,
                    chunk_idx=node.chunk_idx, section_id=best_section_id,
                    char_count=node.char_count,
                    token_count=getattr(node, 'token_count', 0),
                    parent_id=node.parent_id or "",
                    heading=node.heading or "",
                    chunk_type=self._map_chunk_type(node.chunk_type),
                    page=node.page,
                    section_path=best_section_path or getattr(node, 'section_path', []),
                    source_hash=source_hash,
                    embedding_version="v1",
                    chunk_version=0,
                ))

        return chunks, sections, doc_type

    async def _chunk_code(
        self, code: str, doc_id: str, ext: str, params: Any,
    ) -> list[Chunk]:
        """AST-aware code chunking."""
        from app.infrastructure.chunking.ast_chunker import AstChunker

        chunker = AstChunker()
        lang = AstChunker.detect_language(code, ext)
        code_chunks = chunker.chunk(code, lang)

        chunks: list[Chunk] = []
        for i, cc in enumerate(code_chunks):
            source_hash = hashlib.sha256(cc.content.encode()).hexdigest()[:16]
            ctype = self._map_chunk_type(cc.chunk_type)
            chunks.append(Chunk(
                id=str(uuid.uuid4()), doc_id=doc_id, content=cc.content,
                chunk_idx=i, char_count=len(cc.content),
                token_count=len(cc.content) // 4,
                heading=cc.name,
                chunk_type=ctype, page=1,
                section_path=[cc.class_name] if cc.class_name else [],
                source_hash=source_hash,
                embedding_version="v1",
                meta_info={
                    "language": cc.language,
                    "class_name": cc.class_name,
                    "function_name": cc.name,
                    "start_line": cc.start_line,
                    "end_line": cc.end_line,
                },
            ))
        return chunks

    # ------------------------------------------------------------------
    # Section embedding
    # ------------------------------------------------------------------

    async def _embed_sections(
        self, sections: list[Section], chunks: list[Chunk],
    ) -> None:
        """Generate and store section-level embeddings."""
        if not self._section_repo:
            return

        section_texts: dict[str, str] = {}
        for s in sections:
            section_chunks = [c for c in chunks if c.section_id == s.id]
            if section_chunks:
                combined = "\n\n".join(c.content for c in section_chunks[:5])
                section_texts[s.id] = combined

        if not section_texts:
            return

        ids = list(section_texts.keys())
        texts_list = [section_texts[sid] for sid in ids]

        try:
            embeddings = await self._embed_service.embed_batch(
                texts_list, batch_size=min(8, len(texts_list)))
            for sid, emb in zip(ids, embeddings):
                await self._vector_repo.insert_section_embedding(
                    section_id=sid,
                    text=section_texts[sid],
                    embedding=emb,
                    metadata={
                        "document_id": sections[0].document_id if sections else "",
                        "section_title": next((s.title for s in sections if s.id == sid), ""),
                        "section_path": next((s.path for s in sections if s.id == sid), []),
                    },
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Quality
    # ------------------------------------------------------------------

    async def _apply_quality_filter(
        self, chunks: list[Chunk],
    ) -> tuple[list[Chunk], float]:
        from app.infrastructure.chunking.quality_filter import QualityFilter

        qf = QualityFilter(min_length=self._settings.CHUNK_SIZE // 10)
        chunk_dicts = [{"id": c.id, "char_count": c.char_count, "content": c.content} for c in chunks]
        passed_dicts, rejected_dicts, filter_rate = qf.filter(chunk_dicts)
        passed_ids = {f["id"] for f in passed_dicts}
        filtered = [c for c in chunks if c.id in passed_ids]
        return filtered, filter_rate

    async def _compute_quality(
        self, chunks: list[Chunk], filter_rate: float,
    ) -> float:
        from app.infrastructure.chunking.quality_scorer import QualityScorer

        scorer = QualityScorer()
        baseline = self._settings.CHUNK_SIZE
        if not chunks:
            return 0.0
        avg_chars = sum(c.char_count for c in chunks) / len(chunks)
        filter_score = 1.0 - filter_rate
        length_score = min(1.0, avg_chars / (baseline * 0.8))
        structure_types: dict[str, int] = {}
        for c in chunks:
            t = str(c.chunk_type)
            structure_types[t] = structure_types.get(t, 0) + 1
        narrative_ratio = structure_types.get("text", 0) / len(chunks)
        structure_score = min(1.0, 0.6 + (1.0 - narrative_ratio) * 0.4)
        return round(max(0.0, min(1.0,
            filter_score * 0.40 + length_score * 0.30 + 0.75 * 0.20 + structure_score * 0.10)), 3)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_file_type(filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        mapping = {
            "pdf": "pdf", "docx": "docx", "doc": "doc",
            "txt": "txt", "md": "md", "csv": "csv",
            "xlsx": "xlsx", "pptx": "pptx",
            "html": "html", "htm": "html",
            "json": "json", "xml": "xml",
            "py": "py", "js": "js", "ts": "ts",
            "go": "go", "rs": "rs",
        }
        return mapping.get(ext, ext or "unknown")

    @staticmethod
    def _map_chunk_type(raw: str) -> ChunkType:
        mapping = {
            "text": ChunkType.TEXT, "heading": ChunkType.HEADING,
            "code": ChunkType.CODE, "code_block": ChunkType.CODE,
            "table": ChunkType.TABLE, "list": ChunkType.LIST,
            "image": ChunkType.IMAGE, "procedure": ChunkType.PROCEDURE,
            "api_spec": ChunkType.API_SPEC,
            "class": ChunkType.CODE, "function": ChunkType.CODE,
            "method": ChunkType.CODE, "module": ChunkType.CODE,
            "import_block": ChunkType.CODE, "docstring": ChunkType.TEXT,
        }
        return mapping.get(raw, ChunkType.TEXT)

    @staticmethod
    def _chunk_to_dict(c: Chunk) -> dict:
        return {
            "id": c.id, "doc_id": c.doc_id, "content": c.content,
            "chunk_idx": c.chunk_idx, "section_id": c.section_id,
            "parent_id": c.parent_id, "heading": c.heading,
            "chunk_type": str(c.chunk_type),
            "page": c.page,
            "section_path": c.section_path,
            "prev_chunk_id": c.prev_chunk_id,
            "next_chunk_id": c.next_chunk_id,
            "parent_section_id": c.parent_section_id,
            "root_section": c.root_section,
            "source_hash": c.source_hash,
        }
