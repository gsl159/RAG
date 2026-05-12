"""Document use case -- upload, process, delete, and list documents."""

import uuid
from datetime import datetime, timezone
from typing import Any

from app.config.settings import Settings
from app.domain.entities.document import Chunk, Document, DocumentStatus
from app.domain.entities.user import User
from app.domain.ports.cache_port import AbstractCacheService
from app.domain.ports.llm_port import AbstractEmbeddingService
from app.domain.ports.repository_ports import (
    AbstractChunkRepository,
    AbstractDocumentRepository,
)
from app.domain.ports.search_port import AbstractSearchService
from app.domain.ports.storage_port import AbstractStorageService
from app.domain.ports.task_queue_port import AbstractTaskQueue, TaskItem
from app.domain.ports.vector_port import AbstractVectorRepository


class DocumentUseCase:
    """Document processing use case.

    Handles the full lifecycle: upload raw content, enqueue async processing,
    delete documents and their derived artifacts, and list with cursor-based
    pagination.
    """

    def __init__(
        self,
        document_repo: AbstractDocumentRepository,
        chunk_repo: AbstractChunkRepository,
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
        self._vector_repo = vector_repo
        self._search_service = search_service
        self._storage = storage
        self._embed_service = embed_service
        self._cache = cache
        self._task_queue = task_queue
        self._settings = settings

    async def upload_document(
        self,
        filename: str,
        content: bytes,
        user: User,
        dept_id: str = "",
    ) -> Document:
        """Upload a document, persist to storage, and enqueue async processing.

        Args:
            filename: Original filename (used to detect file type).
            content: Raw binary content.
            user: The uploading user.
            dept_id: Optional department scope.

        Returns:
            The created ``Document`` entity with ``PENDING`` status.
        """
        doc_id = str(uuid.uuid4())
        file_type = self._infer_file_type(filename)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        import hashlib
        document = Document(
            id=doc_id,
            filename=filename,
            file_type=file_type,
            file_size=len(content),
            content_hash=hashlib.sha256(content).hexdigest(),
            status=DocumentStatus.PENDING,
            tenant_id=user.tenant_id,
            dept_id=dept_id or user.dept_id,
            created_at=now,
            updated_at=now,
            uploaded_by=user.id,
        )

        document = await self._document_repo.save(document)
        await self._storage.upload(doc_id, content, content_type=file_type)

        task = TaskItem(doc_id=doc_id, file_ext=file_type, content=content)
        await self._task_queue.enqueue(task)

        return document

    async def process_document(self, doc_id: str) -> Document:
        """Process a PENDING document synchronously.

        Steps: parse -> chunk -> embed -> index in vector store -> index in
        search service -> increment doc version.

        Args:
            doc_id: The document ID to process.

        Returns:
            The updated ``Document`` with ``DONE`` or ``FAILED`` status.
        """
        document = await self._document_repo.find_by_id(doc_id)
        if document is None:
            raise ValueError(f"Document not found: {doc_id}")

        try:
            await self._document_repo.update_status(
                doc_id, DocumentStatus.PROCESSING
            )
            # Broadcast processing status via WebSocket
            try:
                from app.api.routes.ws import broadcast_progress
                await broadcast_progress({"doc_id": doc_id, "status": "processing"})
            except Exception:
                pass

            content = await self._storage.download(doc_id)
            # Remove old chunks before re-processing
            try:
                await self._chunk_repo.delete_by_doc_id(doc_id)
            except Exception:
                pass
            chunks = await self._parse_and_chunk(
                doc_id, content, document.file_type
            )
            saved_chunks = await self._chunk_repo.save_batch(chunks)

            # Run QualityFilter on saved chunks
            from app.infrastructure.chunking.quality_filter import QualityFilter
            from app.infrastructure.chunking.models import LanguageProfile
            from app.infrastructure.chunking.strategy_resolver import resolve_strategy

            # Detect language for quality filter
            try:
                from app.infrastructure.chunking.language_detector import LanguageDetector
                detector = LanguageDetector()
                sample_text = " ".join(c.content[:200] for c in saved_chunks[:10])
                lang_profile = detector.detect(sample_text)
            except Exception:
                lang_profile = LanguageProfile(primary_language="mixed", zh_ratio=0.5, en_ratio=0.5)

            # Apply quality filter
            qf = QualityFilter(min_length=self._settings.CHUNK_SIZE // 10)
            passed_dicts, rejected_dicts, filter_rate = qf.filter(
                [{"id": c.id, "char_count": c.char_count, "content": c.content} for c in saved_chunks]
            )
            passed_ids = {f["id"] for f in passed_dicts}
            filtered_chunks = [c for c in saved_chunks if c.id in passed_ids]

            # Compute quality score using filtered chunks
            from app.infrastructure.chunking.quality_scorer import QualityScorer
            scorer = QualityScorer()
            baseline = self._settings.CHUNK_SIZE
            avg_chars = sum(c.char_count for c in filtered_chunks) / max(len(filtered_chunks), 1)
            # Filter score
            filter_score = 1.0 - filter_rate
            # Length score: dynamic baseline
            length_score = min(1.0, avg_chars / (baseline * 0.8)) if filtered_chunks else 0.0
            # Content score (approximate)
            content_score = 0.75  # default, refined by scorer if available
            # Structure score
            structure_types = {}
            for c in filtered_chunks:
                t = getattr(c, 'chunk_type', 'text')
                structure_types[str(t)] = structure_types.get(str(t), 0) + 1
            narrative_ratio = structure_types.get('text', 0) / max(len(filtered_chunks), 1)
            structure_score = min(1.0, 0.6 + (1.0 - narrative_ratio) * 0.4)
            # Composite
            quality = round(max(0.0, min(1.0,
                filter_score * 0.40 + length_score * 0.30 + content_score * 0.20 + structure_score * 0.10
            )), 3)
            await self._document_repo.update_parse_score(doc_id, quality)

            # Log filter warning
            if filter_rate > 0.30:
                from app.shared.logging import logger
                logger.warning(
                    "Filter rate exceeded: doc_id={} filter_rate={:.1%} rejected={}/{}",
                    doc_id, filter_rate, len(rejected_dicts), len(saved_chunks),
                )

            # Use filtered chunks for embedding
            texts = [c.content for c in filtered_chunks]
            saved_chunks = filtered_chunks  # Use filtered for subsequent steps
            chunk_dicts = [
                {
                    "id": c.id,
                    "doc_id": c.doc_id,
                    "content": c.content,
                    "chunk_idx": c.chunk_idx,
                    "parent_id": c.parent_id,
                    "heading": c.heading,
                    "chunk_type": c.chunk_type,
                    "page": c.page,
                    "section": c.section,
                }
                for c in saved_chunks
            ]

            embeddings = await self._embed_service.embed_batch(
                texts, batch_size=self._settings.EMBED_BATCH_SIZE
            )
            await self._vector_repo.insert(chunk_dicts, embeddings)
            await self._search_service.add_texts(chunk_dicts)
            await self._cache.increment_doc_version()
            await self._document_repo.update_chunk_count(doc_id, len(saved_chunks))
            # Compute quality score based on chunk statistics
            if saved_chunks:
                avg_chars = sum(c.char_count for c in saved_chunks) / len(saved_chunks)
                quality = min(1.0, max(0.0, avg_chars / 200.0))
                await self._document_repo.update_parse_score(doc_id, round(quality, 3))
            await self._document_repo.update_status(doc_id, DocumentStatus.DONE)
            try:
                from app.api.routes.ws import broadcast_progress
                await broadcast_progress({"doc_id": doc_id, "status": "done"})
            except Exception:
                pass

        except Exception as e:
            await self._document_repo.update_status(
                doc_id, DocumentStatus.FAILED, error_msg=str(e)
            )
            try:
                from app.api.routes.ws import broadcast_progress
                await broadcast_progress({"doc_id": doc_id, "status": "failed"})
            except Exception:
                pass

        return await self._document_repo.find_by_id(doc_id)

    async def delete_document(self, doc_id: str, user: User) -> None:
        """Delete a document and all its derived artifacts.

        Args:
            doc_id: The document ID to delete.
            user: The requesting user (for authorisation checks).
        """
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

        try:
            await self._chunk_repo.delete_by_doc_id(doc_id)
        except Exception:
            pass

        try:
            await self._storage.delete(doc_id)
        except Exception:
            pass

        await self._document_repo.delete(doc_id)
        await self._cache.increment_doc_version()

    async def list_documents(
        self,
        tenant_id: str,
        status: str = "",
        limit: int = 50,
        cursor: str = "",
    ) -> tuple[list[Document], str | None]:
        """List documents for a tenant with cursor-based pagination.

        Args:
            tenant_id: The tenant scope.
            status: Optional status filter.
            limit: Maximum results per page (default 50).
            cursor: Opaque cursor string for continuation.

        Returns:
            A tuple of ``(documents, next_cursor)``.
        """
        offset = 0
        if cursor:
            try:
                offset = int(cursor)
            except (ValueError, TypeError):
                offset = 0

        docs = await self._document_repo.list_all(
            tenant_id, limit=limit + 1, offset=offset
        )

        has_more = len(docs) > limit
        if has_more:
            docs = docs[:limit]

        next_cursor = str(offset + limit) if has_more else None
        return docs, next_cursor

    # ------------------------------------------------------------------
    # Internal helpers
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
        }
        return mapping.get(ext, ext or "unknown")

    async def _parse_and_chunk(
        self,
        doc_id: str,
        content: bytes,
        file_type: str,
    ) -> list[Chunk]:
        """Parse raw content into chunks."""
        import tempfile
        from app.infrastructure.chunking.strategy_resolver import resolve_strategy
        from app.infrastructure.document.parsers.base import get_parser_for_type
        from app.infrastructure.document.text_cleaner import TextCleaner

        cleaner = TextCleaner()
        text = ""

        # Try using format-specific parser first
        ext = f".{file_type}" if not file_type.startswith(".") else file_type
        parser = get_parser_for_type(ext)

        if parser is not None:
            # Binary format (pdf, docx, pptx, xlsx, html)
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                text = await parser.parse(tmp_path)
            finally:
                import os
                os.unlink(tmp_path)
        else:
            # Plain text format (txt, md, csv, json, xml)
            text = content.decode("utf-8", errors="replace")

        text = cleaner.clean(text)
        params, strategy_cls = resolve_strategy(ext, semantic_chunking_enabled=self._settings.SEMANTIC_CHUNKING_ENABLED)
        strategy = strategy_cls(chunk_size=params.chunk_size, chunk_overlap=params.chunk_overlap, min_chunk_size=params.min_chunk_size)
        chunk_nodes = await strategy.chunk(text, doc_id=doc_id)

        chunks: list[Chunk] = []
        for node in chunk_nodes:
            chunk = Chunk(
                id=node.chunk_id,
                doc_id=doc_id,
                content=node.content,
                chunk_idx=node.chunk_idx,
                char_count=node.char_count,
                parent_id=node.parent_id or "",
                heading=node.heading or "",
                chunk_type=node.chunk_type,
                page=node.page,
                section=node.section,
            )
            chunks.append(chunk)

        return chunks
    async def retry_document(self, doc_id: str) -> None:
        """Re-enqueue a failed document for processing."""
        doc = await self._document_repo.find_by_id(doc_id)
        if doc is None:
            raise ValueError(f"Document not found: {doc_id}")
        await self._document_repo.update_status(doc_id, DocumentStatus.PENDING)
        # Re-download from storage and re-enqueue
        content = await self._storage.download(doc_id)
        task = TaskItem(doc_id=doc_id, file_ext=doc.file_type, content=content)
        await self._task_queue.enqueue(task)

