"""add doc_permissions and benchmarks tables

Revision ID: 002_add_permissions_benchmarks
Revises: 001_initial
Create Date: 2024-01-15 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_add_permissions_benchmarks"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "doc_permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doc_id", sa.String(64), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False, server_default="public"),
        sa.Column("scope_value", sa.String(64), nullable=False, server_default="*"),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_docperm_doc", "doc_permissions", ["doc_id"])
    op.create_index("idx_docperm_scope", "doc_permissions", ["scope_type", "scope_value"])

    op.create_table(
        "benchmarks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), server_default="general"),
        sa.Column("difficulty", sa.String(16), server_default="medium"),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_benchmark_cat", "benchmarks", ["category"])


def downgrade() -> None:
    op.drop_table("benchmarks")
    op.drop_table("doc_permissions")
