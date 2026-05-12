"""
Global configuration -- all settings are read from environment variables.

Field groups
------------
Use the ``.llm``, ``.storage``, ``.cache``, ``.rag``, ``.auth``,
``.reranker``, and ``.agent`` properties to access logically-grouped
subsets of the configuration.  The flat field names (e.g.
``SILICONFLOW_API_KEY``) remain available on the ``Settings`` object
directly and are populated from environment variables, preserving full
backward compatibility.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Logical configuration groups (plain BaseModel -- no env-var auto-load)
# ---------------------------------------------------------------------------


class LLMSettings(BaseModel):
    """LLM provider, model routing and timeouts."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    api_key: str
    base_url: str
    model: str
    embed_model: str
    embed_dim: int
    fallback_providers: str
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    ollama_base_url: str
    ollama_model: str
    model_c0: str
    model_c1: str
    model_c2: str
    timeout_c2: float
    timeout_c1: float
    self_score_timeout: float
    query_rewrite_timeout: float
    singleflight_wait_timeout: float
    agent_decision_timeout: float
    generation_temperature: float


class StorageSettings(BaseModel):
    """PostgreSQL, Redis, Milvus, MinIO connection settings."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    database_url: str
    pg_pool_size: int
    pg_max_overflow: int
    pg_pool_recycle: int
    redis_url: str
    redis_pool_max: int
    redis_sentinel_urls: str
    redis_sentinel_master: str
    milvus_host: str
    milvus_port: int
    milvus_collection: str
    milvus_pool_size: int
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool


class CacheSettings(BaseModel):
    """TTL values for each cache layer."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    ttl_query: int
    ttl_embed: int
    ttl_rag: int
    ttl_retrieval: int
    ttl_answer: int
    ttl_session: int


class RAGSettings(BaseModel):
    """Retrieval, chunking, BM25, reranking, and confidence settings."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    chunk_size: int
    chunk_overlap: int
    embed_batch_size: int
    top_k: int
    rerank_top_n: int
    quality_threshold: float
    context_max_chars: int
    max_query_length: int
    pdf_max_extract_chars: int
    conf_weight_rerank: float
    conf_weight_embed: float
    conf_weight_llm: float
    rerank_rrf_blend: float
    rerank_coverage_blend: float
    hybrid_retrieval_alpha: float
    bm25_rebuild_on_startup: bool
    bm25_rebuild_async: bool
    bm25_rebuild_batch_fetch: int
    bm25_backend: str
    es_url: str
    es_index: str
    parent_expansion_enabled: bool


class AuthSettings(BaseModel):
    """JWT, CORS, rate-limiting, and default admin credentials."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    jwt_secret: str
    jwt_algorithm: str
    jwt_expire_hours: int
    jwt_blacklist_fail_open: bool
    rate_limit_per_minute: int
    cors_origins: list[Any]
    default_admin_password: str


class RerankerSettings(BaseModel):
    """Cross-encoder / simple reranker configuration."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    mode: str
    model: str
    timeout: float


class AgentSettings(BaseModel):
    """Agentic RAG, graph RAG, semantic chunking, and task queue."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    agentic_rag_enabled: bool
    topic_switch_threshold: float
    conversation_compress_enabled: bool
    task_queue_workers: int
    task_max_retries: int
    ocr_enabled: bool
    graph_rag_enabled: bool
    graph_extract_timeout: float
    semantic_chunking_enabled: bool


# ---------------------------------------------------------------------------
# Main Settings (reads from environment / .env)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Application-wide configuration backed by environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # -- Sensitive fields (masked in __repr__ / __str__) ------------
    _SENSITIVE_FIELDS: set[str] = {
        "SILICONFLOW_API_KEY",
        "JWT_SECRET",
        "DEFAULT_ADMIN_PASSWORD",
        "MINIO_SECRET_KEY",
        "MINIO_ACCESS_KEY",
        "DATABASE_URL",
        "REDIS_URL",
    }

    def __repr__(self) -> str:
        safe = {
            k: ("***" if k in self._SENSITIVE_FIELDS else v)
            for k, v in self.model_dump().items()
        }
        return f"Settings({safe})"

    def __str__(self) -> str:
        return self.__repr__()

    # ── LLM: primary provider ─────────────────────────────────────
    SILICONFLOW_API_KEY: str = "sk-placeholder"
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    EMBED_MODEL: str = "BAAI/bge-m3"
    EMBED_DIM: int = 1024

    # ── LLM: fallback providers ───────────────────────────────────
    LLM_FALLBACK_PROVIDERS: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # ── LLM: tiered model routing ─────────────────────────────────
    LLM_MODEL_C0: str = ""
    LLM_MODEL_C1: str = ""
    LLM_MODEL_C2: str = ""

    # ── LLM: timeouts / temperature ───────────────────────────────
    LLM_TIMEOUT_C2: float = 15.0
    LLM_TIMEOUT_C1: float = 10.0
    LLM_SELF_SCORE_TIMEOUT: float = 5.0
    QUERY_REWRITE_TIMEOUT: float = 5.0
    SINGLEFLIGHT_WAIT_TIMEOUT: float = 2.0
    AGENT_DECISION_TIMEOUT: float = 5.0
    RAG_GENERATION_TEMPERATURE: float = 0.1

    # ── Storage: PostgreSQL ───────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://raguser:ragpass123@postgres:5432/ragdb"
    PG_POOL_SIZE: int = 30
    PG_MAX_OVERFLOW: int = 50
    PG_POOL_RECYCLE: int = 1800

    # ── Storage: Redis ────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_POOL_MAX: int = 50
    REDIS_SENTINEL_URLS: str = ""
    REDIS_SENTINEL_MASTER: str = "mymaster"

    # ── Storage: Milvus ───────────────────────────────────────────
    MILVUS_HOST: str = "milvus"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "rag_docs_v2"
    MILVUS_POOL_SIZE: int = 10

    # ── Storage: MinIO ────────────────────────────────────────────
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "documents"
    MINIO_SECURE: bool = False

    # ── RAG: chunking / retrieval ─────────────────────────────────
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    EMBED_BATCH_SIZE: int = 32
    TOP_K: int = 10
    RERANK_TOP_N: int = 5
    QUALITY_THRESHOLD: float = 0.6

    # ── RAG: confidence weights ───────────────────────────────────
    CONF_WEIGHT_RERANK: float = 0.5
    CONF_WEIGHT_EMBED: float = 0.3
    CONF_WEIGHT_LLM: float = 0.2

    # ── RAG: reranker blend ───────────────────────────────────────
    RERANK_RRF_BLEND: float = 0.7
    RERANK_COVERAGE_BLEND: float = 0.3

    # ── RAG: hybrid retrieval ─────────────────────────────────────
    HYBRID_RETRIEVAL_ALPHA: float = 0.7

    # ── RAG: BM25 ─────────────────────────────────────────────────
    BM25_REBUILD_ON_STARTUP: bool = True
    BM25_REBUILD_ASYNC: bool = True
    BM25_REBUILD_BATCH_FETCH: int = 5000
    BM25_BACKEND: str = "memory"
    ES_URL: str = "http://localhost:9200"
    ES_INDEX: str = "rag_bm25"

    # ── RAG: HyDE & Self-RAG ────────────────────────────────────
    HYDE_ENABLED: bool = False
    HYDE_MAX_RETRIEVAL_LOOPS: int = 2
    SELF_RAG_THRESHOLD: float = 0.3

    # ── RAG: content limits ───────────────────────────────────────
    CONTEXT_MAX_CHARS: int = 3000
    MAX_QUERY_LENGTH: int = 2000
    PDF_MAX_EXTRACT_CHARS: int = 5_000_000

    # ── RAG: doc processing ───────────────────────────────────────
    PARENT_EXPANSION_ENABLED: bool = True

    # ── Cache TTL ─────────────────────────────────────────────────
    CACHE_TTL_QUERY: int = 1800
    CACHE_TTL_EMBED: int = 86400
    CACHE_TTL_RAG: int = 3600
    CACHE_TTL_RETRIEVAL: int = 3600
    CACHE_TTL_ANSWER: int = 900
    CACHE_TTL_SESSION: int = 86400

    # ── Auth / Security ───────────────────────────────────────────
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    JWT_BLACKLIST_FAIL_OPEN: bool = False
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: list[Any] = ["http://localhost:5173", "http://localhost:3000"]
    DEFAULT_ADMIN_PASSWORD: str = "admin123"

    # ── Reranker ──────────────────────────────────────────────────
    RERANKER_MODE: str = "simple"
    RERANKER_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RERANKER_TIMEOUT: float = 5.0

    # ── Agentic RAG ───────────────────────────────────────────────
    AGENTIC_RAG_ENABLED: bool = True
    TOPIC_SWITCH_THRESHOLD: float = 0.35
    CONVERSATION_COMPRESS_ENABLED: bool = True
    TASK_QUEUE_WORKERS: int = 3
    TASK_MAX_RETRIES: int = 3
    OCR_ENABLED: bool = False

    # ── GraphRAG ──────────────────────────────────────────────────
    GRAPH_RAG_ENABLED: bool = True
    GRAPH_EXTRACT_TIMEOUT: float = 5.0

    # ── Semantic Chunking ─────────────────────────────────────────
    SEMANTIC_CHUNKING_ENABLED: bool = True

    # ── Observability ─────────────────────────────────────────────
    OTLP_ENDPOINT: str = ""  # OpenTelemetry collector (e.g. http://jaeger:4318/v1/traces)

    # ── Application ───────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ── Validators ────────────────────────────────────────────────

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> Any:
        """Parse CORS_ORIGINS from a comma-separated string or JSON array."""
        if v is None:
            return v
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                try:
                    return json.loads(s)
                except json.JSONDecodeError:
                    pass
            return [x.strip() for x in s.split(",") if x.strip()]
        return v

    # ── Grouped accessors ─────────────────────────────────────────

    @property
    def llm(self) -> LLMSettings:
        return LLMSettings(
            api_key=self.SILICONFLOW_API_KEY,
            base_url=self.SILICONFLOW_BASE_URL,
            model=self.LLM_MODEL,
            embed_model=self.EMBED_MODEL,
            embed_dim=self.EMBED_DIM,
            fallback_providers=self.LLM_FALLBACK_PROVIDERS,
            openai_api_key=self.OPENAI_API_KEY,
            openai_base_url=self.OPENAI_BASE_URL,
            openai_model=self.OPENAI_MODEL,
            ollama_base_url=self.OLLAMA_BASE_URL,
            ollama_model=self.OLLAMA_MODEL,
            model_c0=self.LLM_MODEL_C0,
            model_c1=self.LLM_MODEL_C1,
            model_c2=self.LLM_MODEL_C2,
            timeout_c2=self.LLM_TIMEOUT_C2,
            timeout_c1=self.LLM_TIMEOUT_C1,
            self_score_timeout=self.LLM_SELF_SCORE_TIMEOUT,
            query_rewrite_timeout=self.QUERY_REWRITE_TIMEOUT,
            singleflight_wait_timeout=self.SINGLEFLIGHT_WAIT_TIMEOUT,
            agent_decision_timeout=self.AGENT_DECISION_TIMEOUT,
            generation_temperature=self.RAG_GENERATION_TEMPERATURE,
        )

    @property
    def storage(self) -> StorageSettings:
        return StorageSettings(
            database_url=self.DATABASE_URL,
            pg_pool_size=self.PG_POOL_SIZE,
            pg_max_overflow=self.PG_MAX_OVERFLOW,
            pg_pool_recycle=self.PG_POOL_RECYCLE,
            redis_url=self.REDIS_URL,
            redis_pool_max=self.REDIS_POOL_MAX,
            redis_sentinel_urls=self.REDIS_SENTINEL_URLS,
            redis_sentinel_master=self.REDIS_SENTINEL_MASTER,
            milvus_host=self.MILVUS_HOST,
            milvus_port=self.MILVUS_PORT,
            milvus_collection=self.MILVUS_COLLECTION,
            milvus_pool_size=self.MILVUS_POOL_SIZE,
            minio_endpoint=self.MINIO_ENDPOINT,
            minio_access_key=self.MINIO_ACCESS_KEY,
            minio_secret_key=self.MINIO_SECRET_KEY,
            minio_bucket=self.MINIO_BUCKET,
            minio_secure=self.MINIO_SECURE,
        )

    @property
    def cache(self) -> CacheSettings:
        return CacheSettings(
            ttl_query=self.CACHE_TTL_QUERY,
            ttl_embed=self.CACHE_TTL_EMBED,
            ttl_rag=self.CACHE_TTL_RAG,
            ttl_retrieval=self.CACHE_TTL_RETRIEVAL,
            ttl_answer=self.CACHE_TTL_ANSWER,
            ttl_session=self.CACHE_TTL_SESSION,
        )

    @property
    def rag(self) -> RAGSettings:
        return RAGSettings(
            chunk_size=self.CHUNK_SIZE,
            chunk_overlap=self.CHUNK_OVERLAP,
            embed_batch_size=self.EMBED_BATCH_SIZE,
            top_k=self.TOP_K,
            rerank_top_n=self.RERANK_TOP_N,
            quality_threshold=self.QUALITY_THRESHOLD,
            context_max_chars=self.CONTEXT_MAX_CHARS,
            max_query_length=self.MAX_QUERY_LENGTH,
            pdf_max_extract_chars=self.PDF_MAX_EXTRACT_CHARS,
            conf_weight_rerank=self.CONF_WEIGHT_RERANK,
            conf_weight_embed=self.CONF_WEIGHT_EMBED,
            conf_weight_llm=self.CONF_WEIGHT_LLM,
            rerank_rrf_blend=self.RERANK_RRF_BLEND,
            rerank_coverage_blend=self.RERANK_COVERAGE_BLEND,
            hybrid_retrieval_alpha=self.HYBRID_RETRIEVAL_ALPHA,
            bm25_rebuild_on_startup=self.BM25_REBUILD_ON_STARTUP,
            bm25_rebuild_async=self.BM25_REBUILD_ASYNC,
            bm25_rebuild_batch_fetch=self.BM25_REBUILD_BATCH_FETCH,
            bm25_backend=self.BM25_BACKEND,
            es_url=self.ES_URL,
            es_index=self.ES_INDEX,
            parent_expansion_enabled=self.PARENT_EXPANSION_ENABLED,
        )

    @property
    def auth(self) -> AuthSettings:
        return AuthSettings(
            jwt_secret=self.JWT_SECRET,
            jwt_algorithm=self.JWT_ALGORITHM,
            jwt_expire_hours=self.JWT_EXPIRE_HOURS,
            jwt_blacklist_fail_open=self.JWT_BLACKLIST_FAIL_OPEN,
            rate_limit_per_minute=self.RATE_LIMIT_PER_MINUTE,
            cors_origins=self.CORS_ORIGINS,
            default_admin_password=self.DEFAULT_ADMIN_PASSWORD,
        )

    @property
    def reranker(self) -> RerankerSettings:
        return RerankerSettings(
            mode=self.RERANKER_MODE,
            model=self.RERANKER_MODEL,
            timeout=self.RERANKER_TIMEOUT,
        )

    @property
    def agent(self) -> AgentSettings:
        return AgentSettings(
            agentic_rag_enabled=self.AGENTIC_RAG_ENABLED,
            topic_switch_threshold=self.TOPIC_SWITCH_THRESHOLD,
            conversation_compress_enabled=self.CONVERSATION_COMPRESS_ENABLED,
            task_queue_workers=self.TASK_QUEUE_WORKERS,
            task_max_retries=self.TASK_MAX_RETRIES,
            ocr_enabled=self.OCR_ENABLED,
            graph_rag_enabled=self.GRAPH_RAG_ENABLED,
            graph_extract_timeout=self.GRAPH_EXTRACT_TIMEOUT,
            semantic_chunking_enabled=self.SEMANTIC_CHUNKING_ENABLED,
        )


# ---------------------------------------------------------------------------
# Module-level singleton & startup safety
# ---------------------------------------------------------------------------


@lru_cache
def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    return Settings()


def validate_production_settings(s: Settings) -> None:
    """Verify critical settings before serving in production.

    Call from the FastAPI lifespan handler so the application fails
    early if required secrets are missing or still set to defaults.
    """
    import warnings

    if not s.JWT_SECRET:
        raise RuntimeError(
            "FATAL: JWT_SECRET is not set. "
            "Provide a strong secret via the JWT_SECRET environment variable."
        )

    if s.APP_ENV != "production":
        return

    if s.SILICONFLOW_API_KEY == "sk-placeholder":
        raise RuntimeError(
            "FATAL: SILICONFLOW_API_KEY uses the placeholder value. "
            "A valid API key is required in production."
        )

    if s.MINIO_SECRET_KEY == "minioadmin123":
        warnings.warn(
            "WARNING: MINIO_SECRET_KEY is still the factory default; "
            "set a strong value via environment.",
            stacklevel=2,
        )

    if s.DEFAULT_ADMIN_PASSWORD == "admin123":
        warnings.warn(
            "WARNING: DEFAULT_ADMIN_PASSWORD is still the factory default; "
            "set a strong value via environment.",
            stacklevel=2,
        )

    if s.JWT_BLACKLIST_FAIL_OPEN:
        warnings.warn(
            "WARNING: JWT_BLACKLIST_FAIL_OPEN=true in production. "
            "If Redis is unavailable, revoked tokens may still pass auth.",
            stacklevel=2,
        )


settings = get_settings()
