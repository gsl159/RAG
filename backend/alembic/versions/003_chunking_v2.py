"""Chunking System v2 — sections table + enhanced chunks schema.

Revision ID: 003_chunking_v2
Revises: 002_add_permissions_benchmarks
Create Date: 2025-01-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_chunking_v2"
down_revision: Union[str, None] = "002_add_permissions_benchmarks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- sections table ---
    op.create_table(
        "sections",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("parent_id", sa.String(64), default="", index=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("level", sa.Integer, default=1),
        sa.Column("path", sa.JSON, default=list),
        sa.Column("order_index", sa.Integer, default=0),
        sa.Column("summary", sa.Text, default=""),
        sa.Column("chunk_count", sa.Integer, default=0),
        sa.Column("token_count", sa.Integer, default=0),
        sa.Column("has_embedding", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime),
    )
    op.create_index("idx_sections_doc_order", "sections", ["document_id", "order_index"])
    op.create_index("idx_sections_parent", "sections", ["parent_id"])

    # --- Add new columns to chunks ---
    with op.batch_alter_table("chunks") as batch_op:
        batch_op.add_column(sa.Column("section_id", sa.String(64), default=""))
        batch_op.add_column(sa.Column("token_count", sa.Integer(), default=0))
        batch_op.add_column(sa.Column("prev_chunk_id", sa.String(64), default=""))
        batch_op.add_column(sa.Column("next_chunk_id", sa.String(64), default=""))
        batch_op.add_column(sa.Column("parent_section_id", sa.String(64), default=""))
        batch_op.add_column(sa.Column("root_section", sa.String(512), default=""))
        batch_op.add_column(sa.Column("section_path", sa.JSON, default=list))
        batch_op.add_column(sa.Column("source_hash", sa.String(64), default=""))
        batch_op.add_column(sa.Column("chunk_version", sa.Integer, default=0))
        batch_op.add_column(sa.Column("embedding_version", sa.String(16), default=""))

    op.create_index("idx_chunks_section", "chunks", ["section_id"])
    op.create_index("idx_chunks_prev", "chunks", ["prev_chunk_id"])
    op.create_index("idx_chunks_next", "chunks", ["next_chunk_id"])
    op.create_index("idx_chunks_hash", "chunks", ["source_hash"])


def downgrade() -> None:
    op.drop_index("idx_chunks_hash", table_name="chunks")
    op.drop_index("idx_chunks_next", table_name="chunks")
    op.drop_index("idx_chunks_prev", table_name="chunks")
    op.drop_index("idx_chunks_section", table_name="chunks")

    with op.batch_alter_table("chunks") as batch_op:
        batch_op.drop_column("embedding_version")
        batch_op.drop_column("chunk_version")
        batch_op.drop_column("source_hash")
        batch_op.drop_column("section_path")
        batch_op.drop_column("root_section")
        batch_op.drop_column("parent_section_id")
        batch_op.drop_column("next_chunk_id")
        batch_op.drop_column("prev_chunk_id")
        batch_op.drop_column("token_count")
        batch_op.drop_column("section_id")

    op.drop_index("idx_sections_parent", table_name="sections")
    op.drop_index("idx_sections_doc_order", table_name="sections")
    op.drop_table("sections")
