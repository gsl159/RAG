"""
Tag management routes -- CRUD for knowledge-base tags and document-tag
bindings.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, func

from app.api.deps import get_container, get_current_user
from app.api.responses import err, ok
from app.config.settings import settings
from app.di.container import DIContainer
from app.infrastructure.persistence.models.base import get_session_factory
from app.infrastructure.persistence.models.tag import DocTag, Tag
from app.shared.logging import logger

router = APIRouter(prefix="/tags", tags=["Tags"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=32)
    color: str = "#4f7ef8"


class TagDocBind(BaseModel):
    doc_id: str
    tag_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_factory():
    """Return a session factory for tag operations."""
    return get_session_factory(settings.storage.database_url)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/")
async def list_tags(
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """List all tags with document counts."""
    try:
        async with _session_factory()() as db:
            result = await db.execute(
                select(
                    Tag.id,
                    Tag.name,
                    Tag.color,
                    Tag.created_at,
                    func.count(DocTag.doc_id).label("doc_count"),
                )
                .outerjoin(DocTag, Tag.id == DocTag.tag_id)
                .group_by(Tag.id, Tag.name, Tag.color, Tag.created_at)
                .order_by(Tag.created_at.desc())
            )
            rows = result.all()
            tags = [
                {
                    "id": r.id,
                    "name": r.name,
                    "color": r.color,
                    "doc_count": r.doc_count,
                    "created_at": r.created_at.isoformat()
                    if r.created_at
                    else None,
                }
                for r in rows
            ]
            return ok(tags)
    except Exception as e:
        logger.error("Failed to list tags: {}", e)
        return err(5001, "Failed to list tags", status_code=500)


@router.post("/")
async def create_tag(
    req: TagCreate,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Create a new tag."""
    try:
        tag_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        async with _session_factory()() as db:
            tag = Tag(
                id=tag_id,
                name=req.name,
                color=req.color,
                tenant_id=user.get("tenant_id", "default"),
                created_at=now,
            )
            db.add(tag)
            await db.commit()
            await db.refresh(tag)
            return ok({"id": tag.id, "name": tag.name, "color": tag.color})
    except Exception as e:
        logger.error("Failed to create tag: {}", e)
        return err(5002, "Failed to create tag", status_code=500)


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Delete a tag and remove all document bindings."""
    try:
        async with _session_factory()() as db:
            await db.execute(delete(DocTag).where(DocTag.tag_id == tag_id))
            await db.execute(delete(Tag).where(Tag.id == tag_id))
            await db.commit()
            return ok({"message": "Tag deleted"})
    except Exception as e:
        logger.error("Failed to delete tag: {}", e)
        return err(5003, "Failed to delete tag", status_code=500)


@router.post("/bind")
async def bind_tag(
    req: TagDocBind,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Bind a tag to a document."""
    try:
        async with _session_factory()() as db:
            binding = DocTag(doc_id=req.doc_id, tag_id=req.tag_id)
            db.add(binding)
            await db.commit()
            return ok({"message": "Tag bound"})
    except Exception as e:
        logger.error("Failed to bind tag: {}", e)
        return err(5004, "Failed to bind tag", status_code=500)


@router.post("/unbind")
async def unbind_tag(
    req: TagDocBind,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Unbind a tag from a document."""
    try:
        async with _session_factory()() as db:
            await db.execute(
                delete(DocTag).where(
                    DocTag.doc_id == req.doc_id,
                    DocTag.tag_id == req.tag_id,
                )
            )
            await db.commit()
            return ok({"message": "Tag unbound"})
    except Exception as e:
        logger.error("Failed to unbind tag: {}", e)
        return err(5005, "Failed to unbind tag", status_code=500)


@router.get("/doc/{doc_id}")
async def get_doc_tags(
    doc_id: str,
    container: DIContainer = Depends(get_container),
    user: dict = Depends(get_current_user),
):
    """Get all tags for a specific document."""
    try:
        async with _session_factory()() as db:
            result = await db.execute(
                select(Tag)
                .join(DocTag, Tag.id == DocTag.tag_id)
                .where(DocTag.doc_id == doc_id)
            )
            rows = result.scalars().all()
            tags = [
                {"id": t.id, "name": t.name, "color": t.color} for t in rows
            ]
            return ok(tags)
    except Exception as e:
        logger.error("Failed to get doc tags: {}", e)
        return err(5006, "Failed to get doc tags", status_code=500)
