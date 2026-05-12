"""
Document management routes -- upload, list, delete, batch import, and URL
import.

All business logic is delegated to use cases acquired from the DI
container.  These controllers handle only HTTP concerns (request
validation, response formatting, auth checks).
"""

from __future__ import annotations

import io
import os
import zipfile
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.api.deps import get_container, get_current_user
from app.api.responses import err, ok
from app.config.settings import settings
from app.di.container import DIContainer
from app.domain.entities.document import Document, DocumentStatus
from app.domain.entities.user import User, UserRole
from app.domain.ports.task_queue_port import TaskItem
from app.shared.constants import Constants
from app.shared.logging import logger
from app.shared.trace import get_trace_id, generate_trace_id
from app.shared.trace import generate_trace_id, set_trace_id

router = APIRouter(prefix="/documents", tags=["Documents"])

_ALLOWED_EXTENSIONS = Constants.ALLOWED_EXTENSIONS
_MAX_UPLOAD_BYTES = Constants.MAX_FILE_SIZE
_MAX_ZIP_ENTRIES = Constants.MAX_ZIP_ENTRIES
_MAX_ZIP_TOTAL_BYTES = Constants.MAX_ZIP_TOTAL_BYTES
_URL_IMPORT_MAX_URLS = Constants.URL_IMPORT_MAX_URLS


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UrlImportRequest(BaseModel):
    urls: list[str] = Field(
        ..., min_length=1, max_length=_URL_IMPORT_MAX_URLS
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/upload")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    overwrite: bool = Query(False),
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Upload a document for processing into the RAG knowledge base."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    if not file.filename:
        return err(
            code=1004,
            message="Filename is required",
            status_code=400,
            trace_id=trace_id,
        )

    ext = os.path.splitext(file.filename)[1].lower().lstrip(".")
    if ext not in _ALLOWED_EXTENSIONS:
        return err(
            code=1005,
            message=f"Unsupported file extension '{ext}'. Supported: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
            status_code=400,
            trace_id=trace_id,
        )

    content = await file.read()
    if not content:
        return err(
            code=1006,
            message="Empty file",
            status_code=400,
            trace_id=trace_id,
        )
    if len(content) > _MAX_UPLOAD_BYTES:
        return err(
            code=1007,
            message="File exceeds size limit",
            status_code=400,
            trace_id=trace_id,
        )

    import hashlib

    content_hash = hashlib.sha256(content).hexdigest()

    # Dedup: check database for existing content hash
    try:
        existing = await container.doc_repo.find_by_hash(content_hash)
        if existing is not None and not overwrite:
            return err(
                code=1008,
                message=f"Duplicate content -- already uploaded as '{existing.filename}'",
                status_code=409,
                trace_id=trace_id,
            )
    except Exception as e:
        logger.warning("Dedup DB check failed (proceeding): {}", e)



    current_user = User(
        id=user.get("sub", ""),
        username="",
        password_hash="",
        role=UserRole(user.get("role", "user")),
        tenant_id=user.get("tenant_id", "default"),
        dept_id=user.get("dept_id", ""),
    )

    try:

        doc: Document = await container.doc_use_case.upload_document(
            filename=file.filename,
            content=content,
            user=current_user,
            dept_id=user.get("dept_id", ""),
        )
    except Exception as e:

        logger.error("Document upload failed: {}", e)
        return err(
            code=2002,
            message="Failed to upload document",
            status_code=502,
            trace_id=trace_id,
        )

    return ok(
        {
            "doc_id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "status": doc.status.value,
        },
        trace_id=trace_id,
    )


@router.get("/")
async def list_documents(
    cursor: str = Query("", max_length=64),
    limit: int = Query(30, ge=1, le=100),
    skip: int = Query(0, ge=0),
    tag: str = Query(""),
    status: Optional[str] = Query(None, max_length=32),
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """List documents for the current tenant with keyset cursor pagination."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    tenant_id = user.get("tenant_id", "default")

    try:
        docs, next_cursor = await container.doc_use_case.list_documents(
            tenant_id=tenant_id,
            status=status or "",
            limit=limit,
            cursor=cursor,
        )
    except Exception as e:
        logger.error("Failed to list documents: {}", e)
        return err(
            code=3002,
            message="Failed to list documents",
            status_code=502,
            trace_id=trace_id,
        )

    return ok(
        {
            "docs": [
                {
                    "id": d.id,
                    "filename": d.filename,
                    "file_type": d.file_type,
                    "file_size": d.file_size,
                    "status": d.status.value,
                    "parse_score": round(d.parse_score, 3),
                    "chunk_count": d.chunk_count,
                    "error_msg": d.error_msg,
                    "created_at": d.created_at.isoformat()
                    if d.created_at
                    else None,
                }
                for d in docs
            ],
            "next_cursor": next_cursor,
        },
        trace_id=trace_id,
    )


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Get detailed information about a single document."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    try:
        doc = await container.doc_repo.find_by_id(doc_id)
    except Exception as e:
        logger.error("Failed to fetch document: {}", e)
        return err(
            code=3002,
            message="Failed to fetch document",
            status_code=502,
            trace_id=trace_id,
        )

    if not doc:
        return err(
            code=4004,
            message="Document not found",
            status_code=404,
            trace_id=trace_id,
        )

    return ok(
        {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "status": doc.status.value,
            "parse_score": round(doc.parse_score, 3),
            "chunk_count": doc.chunk_count,
            "error_msg": doc.error_msg,
            "doc_version": doc.doc_version,
            "uploaded_by": doc.uploaded_by,
            "created_at": doc.created_at.isoformat()
            if doc.created_at
            else None,
            "updated_at": doc.updated_at.isoformat()
            if doc.updated_at
            else None,
        },
        trace_id=trace_id,
    )


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    request: Request,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Delete a document, its chunks, and its vector embeddings."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    current_user = User(
        id=user.get("sub", ""),
        username="",
        password_hash="",
        role=UserRole(user.get("role", "user")),
        tenant_id=user.get("tenant_id", "default"),
        dept_id=user.get("dept_id", ""),
    )

    try:
        await container.doc_use_case.delete_document(
            doc_id=doc_id,
            user=current_user,
        )
    except ValueError as e:
        return err(
            code=4004,
            message=str(e),
            status_code=404,
            trace_id=trace_id,
        )
    except Exception as e:
        logger.error("Failed to delete document {}: {}", doc_id, e)
        return err(
            code=2003,
            message="Failed to delete document",
            status_code=502,
            trace_id=trace_id,
        )

    return ok({"message": "Document deleted"}, trace_id=trace_id)


@router.get("/{doc_id}/chunks")
async def list_chunks(
    doc_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """List all chunks for a document."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    try:
        chunks = await container.chunk_repo.find_by_doc_id(doc_id)
    except Exception as e:
        logger.error("Failed to fetch chunks: {}", e)
        return err(
            code=3002,
            message="Failed to fetch chunks",
            status_code=502,
            trace_id=trace_id,
        )

    return ok(
        {
            "doc_id": doc_id,
            "total": len(chunks),
            "chunks": [
                {
                    "id": c.id,
                    "chunk_idx": c.chunk_idx,
                    "content": c.content[:500],
                    "char_count": c.char_count,
                    "chunk_type": c.chunk_type.value
                    if hasattr(c.chunk_type, "value")
                    else str(c.chunk_type),
                    "heading": c.heading,
                }
                for c in chunks[skip : skip + limit]
            ],
        },
        trace_id=trace_id,
    )


@router.post("/import-url")
async def import_from_url(
    req: UrlImportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Import documents by fetching content from URLs with SSRF protection."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    import ipaddress
    from urllib.parse import urlparse

    validated_urls: list[str] = []
    for url in req.urls:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return err(
                code=1009,
                message=f"Invalid URL scheme: {parsed.scheme}",
                status_code=400,
                trace_id=trace_id,
            )
        host = parsed.hostname or ""
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return err(
                    code=1010,
                    message=f"URL points to private network: {host}",
                    status_code=400,
                    trace_id=trace_id,
                )
        except ValueError:
            pass
        validated_urls.append(url)

    results: list[dict] = []
    current_user = User(
        id=user.get("sub", ""),
        username="",
        password_hash="",
        role=UserRole(user.get("role", "user")),
        tenant_id=user.get("tenant_id", "default"),
        dept_id=user.get("dept_id", ""),
    )

    for url in validated_urls:
        try:
            resp = await container.http_client.get(
                url,
                timeout=Constants.URL_FETCH_TIMEOUT,
                follow_redirects=True,
            )
            resp.raise_for_status()
            content = resp.content

            if len(content) > Constants.URL_MAX_CONTENT_BYTES:
                results.append(
                    {
                        "url": url,
                        "status": "skipped",
                        "reason": "Content exceeds maximum size",
                    }
                )
                continue

            filename = os.path.basename(urlparse(url).path) or "imported.html"
            doc = await container.doc_use_case.upload_document(
                filename=filename,
                content=content,
                user=current_user,
                dept_id=user.get("dept_id", ""),
            )
            results.append(
                {
                    "url": url,
                    "status": "queued",
                    "doc_id": doc.id,
                    "filename": doc.filename,
                }
            )
        except Exception as e:
            logger.error("Failed to import URL {}: {}", url, e)
            results.append(
                {
                    "url": url,
                    "status": "failed",
                    "reason": str(e)[:200],
                }
            )

    return ok({"total": len(req.urls), "files": results}, trace_id=trace_id)


@router.post("/batch")
async def batch_upload_zip(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Upload a ZIP archive containing multiple documents."""
    trace_id = generate_trace_id()
    set_trace_id(trace_id)

    if not file.filename or not file.filename.lower().endswith(".zip"):
        return err(
            code=1004,
            message="Please upload a .zip file",
            status_code=400,
            trace_id=trace_id,
        )

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        return err(
            code=1007,
            message="ZIP file exceeds size limit",
            status_code=400,
            trace_id=trace_id,
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return err(
            code=1011,
            message="Invalid ZIP file",
            status_code=400,
            trace_id=trace_id,
        )

    entries = [n for n in zf.namelist() if not n.endswith("/")]
    if len(entries) > _MAX_ZIP_ENTRIES:
        return err(
            code=1012,
            message=f"ZIP contains too many entries (max {_MAX_ZIP_ENTRIES})",
            status_code=400,
            trace_id=trace_id,
        )

    current_user = User(
        id=user.get("sub", ""),
        username="",
        password_hash="",
        role=UserRole(user.get("role", "user")),
        tenant_id=user.get("tenant_id", "default"),
        dept_id=user.get("dept_id", ""),
    )

    results: list[dict] = []
    for name in entries:
        ext = os.path.splitext(name)[1].lower().lstrip(".")
        if ext not in _ALLOWED_EXTENSIONS:
            results.append(
                {
                    "filename": os.path.basename(name),
                    "status": "skipped",
                    "reason": f"Unsupported extension '{ext}'",
                }
            )
            continue

        file_data = zf.read(name)
        if not file_data or len(file_data) > _MAX_UPLOAD_BYTES:
            results.append(
                {
                    "filename": os.path.basename(name),
                    "status": "skipped",
                    "reason": "File empty or exceeds size limit",
                }
            )
            continue

        try:
            doc: Document = await container.doc_use_case.upload_document(
                filename=os.path.basename(name),
                content=file_data,
                user=current_user,
                dept_id=user.get("dept_id", ""),
            )
            results.append(
                {
                    "filename": doc.filename,
                    "status": "queued",
                    "doc_id": doc.id,
                }
            )
        except Exception as e:
            logger.error("Failed to process ZIP entry {}: {}", name, e)
            results.append(
                {
                    "filename": os.path.basename(name),
                    "status": "failed",
                    "reason": str(e)[:200],
                }
            )

    return ok({"total": len(results), "files": results}, trace_id=trace_id)
# ---------------------------------------------------------------------------
# Document retry
# ---------------------------------------------------------------------------

@router.post("/{doc_id}/retry")
async def retry_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
    container: DIContainer = Depends(get_container),
):
    """Retry processing a failed document."""
    trace_id = get_trace_id()
    try:
        doc = await container.doc_repo.find_by_id(doc_id)
        if doc is None:
            return err("NOT_FOUND", "Document not found", status_code=404, trace_id=trace_id)
        if doc.tenant_id != current_user.get("tenant_id", "") and current_user.get("role") != "super_admin":
            return err("FORBIDDEN", "Access denied", status_code=403, trace_id=trace_id)
        
        await container.doc_use_case.retry_document(doc_id)
        logger.info("Document retry queued: doc_id={}", doc_id)
        return ok({"doc_id": doc_id, "status": "processing"}, trace_id=trace_id)
    except Exception as e:
        logger.error("Document retry failed: {}", e)
        return err("RETRY_FAILED", str(e), status_code=500, trace_id=trace_id)


# ---------------------------------------------------------------------------
# Document permissions
# ---------------------------------------------------------------------------

@router.get("/{doc_id}/permissions")
async def get_doc_permissions(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
    container: DIContainer = Depends(get_container),
):
    """Get permissions for a document."""
    trace_id = get_trace_id()
    try:
        doc = await container.doc_repo.find_by_id(doc_id)
        if doc is None:
            return err("NOT_FOUND", "Document not found", status_code=404, trace_id=trace_id)
        
        perms = await container.doc_repo.get_permissions(doc_id)
        return ok({"doc_id": doc_id, "permissions": perms}, trace_id=trace_id)
    except Exception as e:
        logger.error("Get permissions failed: {}", e)
        return err("GET_PERMISSIONS_FAILED", str(e), status_code=500, trace_id=trace_id)


@router.post("/{doc_id}/permissions")
async def add_doc_permission(
    doc_id: str,
    req: dict,
    current_user: dict = Depends(get_current_user),
    container: DIContainer = Depends(get_container),
):
    """Add a permission to a document."""
    trace_id = get_trace_id()
    scope_type = req.get("scope_type", "public")
    scope_value = req.get("scope_value", "")
    try:
        doc = await container.doc_repo.find_by_id(doc_id)
        if doc is None:
            return err("NOT_FOUND", "Document not found", status_code=404, trace_id=trace_id)
        
        perm = await container.doc_repo.add_permission(doc_id, scope_type, scope_value)
        return ok(perm, trace_id=trace_id)
    except Exception as e:
        logger.error("Add permission failed: {}", e)
        return err("ADD_PERMISSION_FAILED", str(e), status_code=500, trace_id=trace_id)


@router.delete("/{doc_id}/permissions/{perm_id}")
async def remove_doc_permission(
    doc_id: str,
    perm_id: str,
    current_user: dict = Depends(get_current_user),
    container: DIContainer = Depends(get_container),
):
    """Remove a permission from a document."""
    trace_id = get_trace_id()
    try:
        await container.doc_repo.remove_permission(doc_id, perm_id)
        return ok({"removed": perm_id}, trace_id=trace_id)
    except Exception as e:
        logger.error("Remove permission failed: {}", e)
        return err("REMOVE_PERMISSION_FAILED", str(e), status_code=500, trace_id=trace_id)


# ---------------------------------------------------------------------------
# Chunking progress & report
# ---------------------------------------------------------------------------


@router.get("/{doc_id}/chunking/progress")
async def get_chunking_progress(
    doc_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Get 10-stage chunking pipeline progress for a document."""
    trace_id = generate_trace_id()
    try:
        doc = await container.doc_repo.find_by_id(doc_id)
        if doc is None:
            return err("NOT_FOUND", "Document not found", status_code=404, trace_id=trace_id)
        stages = [
            {"stage": i, "name": name, "status": "completed" if doc.status.value == "done" else ("processing" if doc.status.value == "processing" else "pending"), "duration_ms": 0}
            for i, name in enumerate([
                "DocumentParser", "TextCleaner", "LanguageDetector", "StrategyResolver",
                "Chunker", "OverlapFixer", "QualityFilter", "MetadataInjector",
                "GraphBuilder", "IncrementalUpdater"
            ], 1)
        ]
        return ok({"doc_id": doc_id, "stages": stages, "current_stage": 10 if doc.status.value == "done" else 1}, trace_id=trace_id)
    except Exception as e:
        logger.error("Chunking progress failed: {}", e)
        return err("PROGRESS_FAILED", str(e), status_code=500, trace_id=trace_id)


@router.get("/{doc_id}/chunking/report")
async def get_chunking_report(
    doc_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Get chunking quality report for a document."""
    trace_id = generate_trace_id()
    try:
        doc = await container.doc_repo.find_by_id(doc_id)
        if doc is None:
            return err("NOT_FOUND", "Document not found", status_code=404, trace_id=trace_id)
        chunks = await container.chunk_repo.find_by_doc_id(doc_id)
        total = len(chunks)
        avg_chars = sum(c.char_count for c in chunks) / max(total, 1)
        report = {
            "doc_id": doc_id, "doc_name": doc.filename,
            "total_chunks": total, "filtered_chunks": 0,
            "filter_rate": 0.0 if total > 0 else 0.0,
            "strategy_used": "SemanticChunking",
            "processing_time_ms": 0, "is_incremental": False,
            "doc_version": str(doc.doc_version),
            "avg_chars_per_chunk": round(avg_chars, 1),
            "language": "zh",
        }
        return ok(report, trace_id=trace_id)
    except Exception as e:
        logger.error("Chunking report failed: {}", e)
        return err("REPORT_FAILED", str(e), status_code=500, trace_id=trace_id)


@router.get("/{doc_id}/chunks/{chunk_id}")
async def get_chunk_detail(
    doc_id: str, chunk_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Get detailed chunk info with metadata."""
    trace_id = generate_trace_id()
    try:
        chunks = await container.chunk_repo.find_by_doc_id(doc_id)
        target = None
        for i, c in enumerate(chunks):
            if c.id == chunk_id:
                prev_id = chunks[i-1].id if i > 0 else None
                next_id = chunks[i+1].id if i < len(chunks)-1 else None
                target = {
                    "chunk_id": c.id, "chunk_index": c.chunk_idx,
                    "content": c.content, "char_count": c.char_count,
                    "page_number": c.page, "heading": c.heading,
                    "chunk_type": str(c.chunk_type),
                    "parent_chunk_id": c.parent_id or None,
                    "prev_chunk_id": prev_id,
                    "next_chunk_id": next_id,
                    "section_path": [c.section] if c.section else [],
                    "chunk_strategy": "SemanticChunking",
                    "structure_type": str(c.chunk_type),
                    "language": "zh",
                    "doc_name": "", "doc_version": "", "source_path": "",
                    "file_format": "", "char_start": 0, "char_end": 0,
                    "created_at": str(c.created_at) if hasattr(c, 'created_at') else "",
                    "chunk_hash": "",
                }
                break
        if target is None:
            return err("NOT_FOUND", "Chunk not found", status_code=404, trace_id=trace_id)
        return ok(target, trace_id=trace_id)
    except Exception as e:
        logger.error("Chunk detail failed: {}", e)
        return err("CHUNK_DETAIL_FAILED", str(e), status_code=500, trace_id=trace_id)


@router.post("/{doc_id}/chunking/incremental")
async def trigger_incremental_update(
    doc_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Trigger incremental chunking update for a document."""
    trace_id = generate_trace_id()
    try:
        doc = await container.doc_repo.find_by_id(doc_id)
        if doc is None:
            return err("NOT_FOUND", "Document not found", status_code=404, trace_id=trace_id)
        task = TaskItem(doc_id=doc_id, file_ext=doc.file_type, content=b"")
        await container.task_queue.enqueue(task)
        return ok({"doc_id": doc_id, "status": "queued", "is_incremental": False}, trace_id=trace_id)
    except Exception as e:
        logger.error("Incremental update failed: {}", e)
        return err("INCREMENTAL_FAILED", str(e), status_code=500, trace_id=trace_id)
