"""initial schema — 基线迁移，对齐当前 ORM 模型

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 用户表
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(128), unique=True, nullable=False),
        sa.Column("password", sa.String(256), nullable=False),
        sa.Column("role", sa.String(32), server_default="user"),
        sa.Column("tenant_id", sa.String(64), server_default="default"),
        sa.Column("dept_id", sa.String(64)),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_user_username", "users", ["username"])
    op.create_index("idx_user_created_id", "users", ["created_at", "id"])

    # 文档表
    op.create_table(
        "documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("file_path", sa.String(512)),
        sa.Column("file_type", sa.String(16)),
        sa.Column("file_size", sa.BigInteger(), server_default="0"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("parse_score", sa.Float(), server_default="0.0"),
        sa.Column("chunk_count", sa.Integer(), server_default="0"),
        sa.Column("doc_version", sa.Integer(), server_default="1"),
        sa.Column("tenant_id", sa.String(64), server_default="default"),
        sa.Column("dept_id", sa.String(64)),
        sa.Column("error_msg", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("idx_docs_status", "documents", ["status"])
    op.create_index("idx_docs_created", "documents", ["created_at"])
    op.create_index("idx_docs_tenant", "documents", ["tenant_id"])

    # 切片表
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("doc_id", sa.String(64), sa.ForeignKey("documents.id", ondelete="CASCADE")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_idx", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), server_default="0"),
        sa.Column("meta_info", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_chunks_doc_id", "chunks", ["doc_id"])

    # 查询日志
    op.create_table(
        "query_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(32), index=True),
        sa.Column("session_id", sa.String(64)),
        sa.Column("user_id", sa.String(64)),
        sa.Column("tenant_id", sa.String(64), server_default="default"),
        sa.Column("original_query", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text()),
        sa.Column("intent", sa.String(4)),
        sa.Column("answer", sa.Text()),
        sa.Column("context", sa.Text()),
        sa.Column("sources", sa.JSON()),
        sa.Column("confidence", sa.Float(), server_default="0.0"),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("retrieval_ms", sa.Integer()),
        sa.Column("llm_ms", sa.Integer()),
        sa.Column("cache_hit", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("token_count", sa.Integer(), server_default="0"),
        sa.Column("degrade_level", sa.String(4)),
        sa.Column("degrade_reason", sa.String(64)),
        sa.Column("share_token", sa.String(64), unique=True),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_qlog_created", "query_logs", ["created_at"])
    op.create_index("idx_qlog_trace", "query_logs", ["trace_id"])
    op.create_index("idx_qlog_tenant", "query_logs", ["tenant_id"])

    # 评估表
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("log_id", sa.Integer(), sa.ForeignKey("query_logs.id", ondelete="SET NULL")),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("relevance", sa.Float(), server_default="0.0"),
        sa.Column("faithfulness", sa.Float(), server_default="0.0"),
        sa.Column("completeness", sa.Float(), server_default="0.0"),
        sa.Column("overall", sa.Float(), server_default="0.0"),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_eval_created", "evaluations", ["created_at"])

    # 反馈表
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("log_id", sa.Integer(), sa.ForeignKey("query_logs.id", ondelete="SET NULL")),
        sa.Column("trace_id", sa.String(32)),
        sa.Column("session_id", sa.String(64)),
        sa.Column("user_id", sa.String(64)),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text()),
        sa.Column("feedback", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(32)),
        sa.Column("correction", sa.Text()),
        sa.Column("ratings", sa.JSON()),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_fb_type", "feedback", ["feedback"])

    # 审计日志
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(32)),
        sa.Column("user_id", sa.String(64)),
        sa.Column("username", sa.String(128)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(256)),
        sa.Column("detail", sa.JSON()),
        sa.Column("ip", sa.String(64)),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_audit_created", "audit_logs", ["created_at"])
    op.create_index("idx_audit_user", "audit_logs", ["user_id"])

    # API Key
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(64), server_default="default"),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("key_hash", sa.String(256), nullable=False),
        sa.Column("prefix", sa.String(12), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime()),
    )
    op.create_index("idx_apikey_user", "api_keys", ["user_id"])

    # 标签
    op.create_table(
        "tags",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), server_default="default"),
        sa.Column("color", sa.String(16), server_default="'#4f7ef8'"),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_tag_tenant", "tags", ["tenant_id"])

    # 文档-标签关联
    op.create_table(
        "doc_tags",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doc_id", sa.String(64), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.String(64), sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("idx_doctag_doc", "doc_tags", ["doc_id"])
    op.create_index("idx_doctag_tag", "doc_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_table("doc_tags")
    op.drop_table("tags")
    op.drop_table("api_keys")
    op.drop_table("audit_logs")
    op.drop_table("feedback")
    op.drop_table("evaluations")
    op.drop_table("query_logs")
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("users")
