"""
/upload 路由 — 文档上传管理，含审计、覆盖上传、ZIP批量、URL抓取
"""
import hashlib
import io
import os
import uuid
import zipfile
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, ok
from app.constants import (
    ALLOWED_DOCUMENT_EXTENSIONS,
    CHUNK_LIST_MAX_LIMIT,
    MAX_UPLOAD_FILE_BYTES,
    MAX_URL_FETCH_HTML_BYTES,
    MAX_ZIP_ARCHIVE_BYTES,
    URL_IMPORT_MAX_URLS,
    ZIP_EXTENSION,
)
from app.repository.object_store import minio_storage
from app.repository.postgres import AuditLog, Chunk, Document, DocTag, Tag, get_db
from app.repository.redis_cache import cache
from app.schema.upload import UrlImportRequest
from app.service.upload_tasks import (
    milvus_delete_best_effort,
    minio_delete_best_effort,
    process_document_after_upload,
)
from app.utils.file_validation import validate_upload_content_matches_ext
from app.utils.logger import logger
from app.utils.trace import generate_trace_id

router = APIRouter(prefix="/upload", tags=["文档管理"])


@router.post("/")
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    overwrite: bool = Query(False, description="覆盖同名/同MD5文档"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    trace_id = generate_trace_id()
    if not file.filename:
        raise HTTPException(400, detail={"code": 1001, "message": "文件名不能为空"})
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise HTTPException(400, detail={"code": 1001, "message": f"不支持 '{ext}' 格式"})

    content = await file.read()
    if not content:
        raise HTTPException(400, detail={"code": 1001, "message": "文件为空"})
    if len(content) > MAX_UPLOAD_FILE_BYTES:
        raise HTTPException(400, detail={"code": 1001, "message": "文件超过50MB"})

    mime_err = validate_upload_content_matches_ext(ext, content)
    if mime_err:
        raise HTTPException(400, detail={"code": 1001, "message": mime_err})

    file_hash = hashlib.sha256(content).hexdigest()
    lock_key = f"sha256:{file_hash}"
    if not await cache.try_acquire_upload_lock(lock_key):
        raise HTTPException(
            409,
            detail={"code": 1001, "message": "相同内容正在上传或处理中，请稍后再试"},
        )
    try:
        dup = await db.execute(select(Document).where(Document.file_path.contains(file_hash)))
        existing = dup.scalar_one_or_none()

        if existing and not overwrite:
            raise HTTPException(
                409, detail={"code": 1001, "message": "相同文件已存在（MD5重复），可使用覆盖上传"}
            )

        if existing and overwrite:
            milvus_delete_best_effort(existing.id, context="overwrite_upload")
            await db.execute(sql_delete(Chunk).where(Chunk.doc_id == existing.id))
            old_version = existing.doc_version or 1
            await db.execute(
                update(Document)
                .where(Document.id == existing.id)
                .values(
                    filename=file.filename,
                    status="pending",
                    error_msg=None,
                    chunk_count=0,
                    parse_score=0.0,
                    file_size=len(content),
                    doc_version=old_version + 1,
                )
            )
            db.add(
                AuditLog(
                    trace_id=trace_id,
                    user_id=user.get("sub"),
                    action="overwrite_upload",
                    resource=file.filename,
                    ip=request.client.host if request.client else None,
                )
            )
            await db.commit()
            background_tasks.add_task(process_document_after_upload, existing.id, ext, content)
            return ok(
                {
                    "doc_id": existing.id,
                    "filename": file.filename,
                    "status": "processing",
                    "version": old_version + 1,
                    "overwritten": True,
                },
                trace_id=trace_id,
            )

        doc_id = str(uuid.uuid4())
        obj_key = f"{file_hash}{ext}"
        try:
            minio_storage.upload(obj_key, content, file.content_type or "application/octet-stream")
        except Exception as e:
            logger.error(f"MinIO upload failed trace_id={trace_id}: {e}")
            raise HTTPException(500, detail={"code": 5000, "message": "文件存储失败"}) from e

        doc = Document(
            id=doc_id,
            filename=file.filename,
            file_path=obj_key,
            file_type=ext,
            file_size=len(content),
            status="pending",
            tenant_id=user.get("tenant_id", "default"),
        )
        db.add(doc)
        db.add(
            AuditLog(
                trace_id=trace_id,
                user_id=user.get("sub"),
                action="upload",
                resource=file.filename,
                ip=request.client.host if request.client else None,
            )
        )
        await db.commit()

        background_tasks.add_task(process_document_after_upload, doc_id, ext, content)
        return ok({"doc_id": doc_id, "filename": file.filename, "status": "processing"}, trace_id=trace_id)
    finally:
        await cache.release_upload_lock(lock_key)


@router.get("/docs")
async def list_docs(
    skip: int = 0,
    limit: int = 30,
    tag: Optional[str] = Query(None, description="按标签筛选"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    limit = min(limit, 100)
    tenant_id = user.get("tenant_id", "default")
    q = select(Document).where(Document.tenant_id == tenant_id)
    if tag:
        q = (
            q.join(DocTag, DocTag.doc_id == Document.id)
            .join(Tag, Tag.id == DocTag.tag_id)
            .where(Tag.name == tag)
        )
    q = q.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    docs = result.scalars().all()
    return ok(
        [
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "status": d.status,
                "parse_score": round(float(d.parse_score or 0), 3),
                "chunk_count": d.chunk_count,
                "doc_version": d.doc_version,
                "error_msg": d.error_msg,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    )


@router.get("/docs/{doc_id}")
async def get_doc(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, detail={"code": 1001, "message": "文档不存在"})
    return ok(
        {
            "id": doc.id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "status": doc.status,
            "parse_score": round(float(doc.parse_score or 0), 3),
            "chunk_count": doc.chunk_count,
            "error_msg": doc.error_msg,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }
    )


@router.post("/docs/{doc_id}/retry")
async def retry_doc(
    doc_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """重新处理失败的文档"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, detail={"code": 1001, "message": "文档不存在"})
    if doc.status not in ("failed",):
        raise HTTPException(
            400,
            detail={
                "code": 1001,
                "message": f"当前状态 '{doc.status}' 不允许重试，仅 failed 状态可重试",
            },
        )

    trace_id = generate_trace_id()

    try:
        content = minio_storage.download_bytes(doc.file_path)
    except Exception as e:
        logger.error(f"MinIO download failed doc_id={doc_id}: {e}")
        raise HTTPException(
            500, detail={"code": 5000, "message": "从存储下载文件失败，请重新上传"}
        ) from e

    milvus_delete_best_effort(doc_id, context="retry_doc")
    await db.execute(sql_delete(Chunk).where(Chunk.doc_id == doc_id))

    await db.execute(
        update(Document)
        .where(Document.id == doc_id)
        .values(status="pending", error_msg=None, chunk_count=0, parse_score=0.0)
    )
    db.add(
        AuditLog(
            trace_id=trace_id,
            user_id=user.get("sub"),
            action="retry_doc",
            resource=doc.filename,
            ip=request.client.host if request.client else None,
        )
    )
    await db.commit()

    ext = doc.file_type
    background_tasks.add_task(process_document_after_upload, doc_id, ext, content)
    return ok({"doc_id": doc_id, "status": "processing", "message": "重试已启动"}, trace_id=trace_id)


@router.get("/docs/{doc_id}/chunks")
async def list_chunks(
    doc_id: str,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """查看文档的所有分块内容"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, detail={"code": 1001, "message": "文档不存在"})

    limit = min(limit, CHUNK_LIST_MAX_LIMIT)
    chunk_result = await db.execute(
        select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.chunk_idx).offset(skip).limit(limit)
    )
    chunks = chunk_result.scalars().all()
    return ok(
        {
            "doc_id": doc_id,
            "filename": doc.filename,
            "total": doc.chunk_count or 0,
            "chunks": [
                {
                    "id": c.id,
                    "chunk_idx": c.chunk_idx,
                    "content": c.content,
                    "char_count": c.char_count,
                }
                for c in chunks
            ],
        }
    )


@router.delete("/docs/{doc_id}")
async def delete_doc(
    doc_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, detail={"code": 1001, "message": "文档不存在"})

    minio_delete_best_effort(minio_storage, doc.file_path, context="delete_doc")
    milvus_delete_best_effort(doc_id, context="delete_doc")

    db.add(
        AuditLog(
            user_id=user.get("sub"),
            action="delete_doc",
            resource=doc.filename,
            ip=request.client.host if request.client else None,
        )
    )
    await db.delete(doc)
    await db.commit()
    await cache.increment_doc_version()
    return ok({"doc_id": doc_id, "message": "删除成功"})


@router.post("/batch")
async def batch_upload_zip(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """上传 ZIP 包，自动解压并逐个入库"""
    trace_id = generate_trace_id()
    if not file.filename or not file.filename.lower().endswith(ZIP_EXTENSION):
        raise HTTPException(400, detail={"code": 1001, "message": "请上传 .zip 文件"})

    content = await file.read()
    if len(content) > MAX_ZIP_ARCHIVE_BYTES:
        raise HTTPException(400, detail={"code": 1001, "message": "ZIP 文件超过200MB"})

    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(400, detail={"code": 1001, "message": "无效的 ZIP 文件"})

    results = []
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
            results.append(
                {"filename": os.path.basename(name), "status": "skipped", "reason": f"不支持 {ext}"}
            )
            continue
        try:
            file_data = zf.read(name)
            if not file_data or len(file_data) > MAX_UPLOAD_FILE_BYTES:
                results.append(
                    {
                        "filename": os.path.basename(name),
                        "status": "skipped",
                        "reason": "文件为空或超50MB",
                    }
                )
                continue
            sniff = validate_upload_content_matches_ext(ext, file_data)
            if sniff:
                results.append(
                    {"filename": os.path.basename(name), "status": "skipped", "reason": sniff}
                )
                continue
            file_hash = hashlib.sha256(file_data).hexdigest()
            obj_key = f"{file_hash}{ext}"
            try:
                minio_storage.upload(obj_key, file_data, "application/octet-stream")
            except Exception as e:
                logger.warning(f"ZIP entry MinIO upload failed name={name}: {e}")
                results.append(
                    {"filename": os.path.basename(name), "status": "error", "reason": "存储失败"}
                )
                continue
            doc_id = str(uuid.uuid4())
            doc = Document(
                id=doc_id,
                filename=os.path.basename(name),
                file_path=obj_key,
                file_type=ext,
                file_size=len(file_data),
                status="pending",
                tenant_id=user.get("tenant_id", "default"),
            )
            db.add(doc)
            background_tasks.add_task(process_document_after_upload, doc_id, ext, file_data)
            results.append({"filename": os.path.basename(name), "status": "queued", "doc_id": doc_id})
        except Exception as e:
            results.append(
                {"filename": os.path.basename(name), "status": "error", "reason": str(e)[:100]}
            )

    db.add(
        AuditLog(
            trace_id=trace_id,
            user_id=user.get("sub"),
            action="batch_upload",
            resource=file.filename,
            ip=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return ok({"total": len(results), "files": results}, trace_id=trace_id)


def _is_safe_url(url: str) -> bool:
    """检查 URL 是否指向外部地址（防 SSRF）"""
    import ipaddress
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return False

    blocked_hosts = {"localhost", "0.0.0.0", "metadata.google.internal"}
    if hostname.lower() in blocked_hosts:
        return False

    try:
        addrs = socket.getaddrinfo(hostname, None)
        for _family, _t, _p, _c, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False
    except (OSError, ValueError):
        return False
    return True


@router.post("/from-url")
async def import_from_url(
    req: UrlImportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """输入网页 URL 自动爬取入库"""
    import httpx
    from urllib.parse import urlparse

    trace_id = generate_trace_id()
    if not req.urls or len(req.urls) > URL_IMPORT_MAX_URLS:
        raise HTTPException(
            400,
            detail={"code": 1001, "message": f"URL 数量应在 1~{URL_IMPORT_MAX_URLS} 之间"},
        )

    results = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, max_redirects=5) as client:
        for url in req.urls:
            url = url.strip()
            if not url.startswith(("http://", "https://")):
                results.append({"url": url, "status": "skipped", "reason": "无效 URL"})
                continue
            if not _is_safe_url(url):
                results.append({"url": url, "status": "skipped", "reason": "不允许访问内部地址"})
                continue
            try:
                resp = await client.get(url, headers={"User-Agent": "RAG-Bot/1.0"})
                resp.raise_for_status()
                html_bytes = resp.content
                if len(html_bytes) > MAX_URL_FETCH_HTML_BYTES:
                    results.append({"url": url, "status": "skipped", "reason": "页面超10MB"})
                    continue
                parsed = urlparse(url)
                fname = (parsed.netloc + parsed.path).replace("/", "_")[:120] + ".html"
                file_hash = hashlib.sha256(html_bytes).hexdigest()
                obj_key = f"{file_hash}.html"
                minio_storage.upload(obj_key, html_bytes, "text/html")
                doc_id = str(uuid.uuid4())
                doc = Document(
                    id=doc_id,
                    filename=fname,
                    file_path=obj_key,
                    file_type=".html",
                    file_size=len(html_bytes),
                    status="pending",
                    tenant_id=user.get("tenant_id", "default"),
                )
                db.add(doc)
                background_tasks.add_task(process_document_after_upload, doc_id, ".html", html_bytes)
                results.append(
                    {"url": url, "status": "queued", "doc_id": doc_id, "filename": fname}
                )
            except Exception as e:
                logger.warning(f"URL import failed url={url[:80]}: {e}")
                results.append({"url": url, "status": "error", "reason": str(e)[:120]})

    db.add(
        AuditLog(
            trace_id=trace_id,
            user_id=user.get("sub"),
            action="url_import",
            resource=str(len(req.urls)) + " urls",
            ip=request.client.host if request.client else None,
        )
    )
    await db.commit()
    return ok({"total": len(results), "files": results}, trace_id=trace_id)
