"""
Settings 模块单元测试
运行: cd rag_system && pytest tests/test_settings.py -v
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("MILVUS_HOST", "localhost")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("SILICONFLOW_API_KEY", "sk-test-key")
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-not-for-production")

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


class TestSettings:
    def test_settings_importable(self):
        from app.config.settings import settings
        assert settings is not None

    def test_settings_has_required_fields(self):
        from app.config.settings import settings
        assert hasattr(settings, "DATABASE_URL")
        assert hasattr(settings, "REDIS_URL")
        assert hasattr(settings, "MILVUS_HOST")
        assert hasattr(settings, "LLM_MODEL")
        assert hasattr(settings, "JWT_SECRET")
        assert hasattr(settings, "APP_ENV")

    def test_settings_defaults(self):
        from app.config.settings import Settings
        s = Settings()
        assert s.CHUNK_SIZE == 500
        assert s.CHUNK_OVERLAP == 50
        assert s.TOP_K == 20           # from .env
        assert s.RERANK_TOP_N == 10       # from .env
        assert s.QUALITY_THRESHOLD == 0.6
        assert s.EMBED_DIM == 1024
        assert s.PDF_MAX_EXTRACT_CHARS > 0

    def test_settings_cache_ttl_positive(self):
        from app.config.settings import settings
        assert settings.CACHE_TTL_QUERY > 0
        assert settings.CACHE_TTL_EMBED > 0
        assert settings.CACHE_TTL_RAG > 0

    def test_settings_hybrid_alpha_range(self):
        from app.config.settings import settings
        assert 0.0 <= settings.HYBRID_RETRIEVAL_ALPHA <= 1.0


class TestValidateProductionSettings:
    def test_production_with_default_jwt_raises(self):
        from app.config.settings import Settings, validate_production_settings
        s = Settings(
            APP_ENV="production",
            JWT_SECRET="",  # Empty JWT_SECRET now raises in all environments
        )
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            validate_production_settings(s)

    def test_production_with_custom_jwt_passes(self):
        from app.config.settings import Settings, validate_production_settings
        s = Settings(
            APP_ENV="production",
            JWT_SECRET="a-secure-random-production-secret-key",
        )
        # Should not raise
        validate_production_settings(s)

    def test_development_with_empty_jwt_raises(self):
        from app.config.settings import Settings, validate_production_settings
        s = Settings(
            APP_ENV="development",
            JWT_SECRET="",  # Empty JWT_SECRET now raises in all environments
        )
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            validate_production_settings(s)

    def test_testing_env_passes(self):
        from app.config.settings import Settings, validate_production_settings
        s = Settings(APP_ENV="testing")
        validate_production_settings(s)
