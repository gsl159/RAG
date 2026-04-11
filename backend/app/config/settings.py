"""
Global configuration — all settings are read from environment variables.
"""
import json
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM
    SILICONFLOW_API_KEY: str = "sk-placeholder"
    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    LLM_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    EMBED_MODEL: str = "BAAI/bge-m3"
    EMBED_DIM: int = 1024

    # PostgreSQL
    DATABASE_URL: str = "postgresql+asyncpg://raguser:ragpass123@postgres:5432/ragdb"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Milvus
    MILVUS_HOST: str = "milvus"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "rag_docs"

    # MinIO
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin123"
    MINIO_BUCKET: str = "documents"
    MINIO_SECURE: bool = False

    # RAG
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    TOP_K: int = 10
    RERANK_TOP_N: int = 5
    QUALITY_THRESHOLD: float = 0.6

    # Hybrid retrieval: score = alpha * vector + (1-alpha) * bm25
    HYBRID_RETRIEVAL_ALPHA: float = 0.7

    # BM25 启动重建：异步则不阻塞 HTTP 就绪；关闭则跳过（依赖后续入库增量更新）
    BM25_REBUILD_ON_STARTUP: bool = True
    BM25_REBUILD_ASYNC: bool = True
    BM25_REBUILD_BATCH_FETCH: int = 5000

    # Timeouts (seconds)
    LLM_TIMEOUT_C2: float = 3.0
    LLM_TIMEOUT_C1: float = 1.5
    LLM_SELF_SCORE_TIMEOUT: float = 2.0
    QUERY_REWRITE_TIMEOUT: float = 3.0
    SINGLEFLIGHT_WAIT_TIMEOUT: float = 2.0

    # Content limits
    CONTEXT_MAX_CHARS: int = 3000
    MAX_QUERY_LENGTH: int = 2000
    # PDF 文本抽取上限（字符），防止超大扫描件拖垮内存
    PDF_MAX_EXTRACT_CHARS: int = 5_000_000

    # Cache TTL
    CACHE_TTL_QUERY: int = 1800
    CACHE_TTL_EMBED: int = 86400
    CACHE_TTL_RAG: int = 3600

    # Auth & Security
    JWT_SECRET: str = "rag-system-jwt-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    RATE_LIMIT_PER_MINUTE: int = 60

    # CORS — 支持环境变量逗号分隔或 JSON 数组，例如:
    # CORS_ORIGINS=http://a.com,http://b.com
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000"]

    # Default admin
    DEFAULT_ADMIN_PASSWORD: str = "admin123"

    # App
    LOG_LEVEL: str = "INFO"
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


def validate_production_settings(s: Settings) -> None:
    """生产环境启动前的安全校验，在 lifespan 中调用。"""
    if s.APP_ENV == "production":
        if s.JWT_SECRET == "rag-system-jwt-secret-change-in-production":
            raise RuntimeError(
                "FATAL: JWT_SECRET 使用了默认值。生产环境必须设置安全的 JWT_SECRET 环境变量。"
            )
        if s.DEFAULT_ADMIN_PASSWORD == "admin123":
            import warnings

            warnings.warn(
                "WARNING: DEFAULT_ADMIN_PASSWORD is still the factory default; set a strong value via environment.",
                stacklevel=2,
            )


settings = get_settings()
