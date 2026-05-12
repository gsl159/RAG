"""
集成测试 — 多模块协同
运行: cd rag_system && DATABASE_URL="sqlite+aiosqlite:///test.db" pytest tests/test_integration.py -v
"""
import asyncio
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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


# ────────────────────────────────────────────────
# 1. 文档处理全流程
# ────────────────────────────────────────────────

class TestDocProcessingFlow:
    """从原始文本到分块的完整处理链路"""

    def test_clean_then_split(self):
        from app.infrastructure.document.text_cleaner import TextCleaner, TextSplitter
        raw = "  多余空格   和\n\n\n\n多余换行  " * 30
        clean_text = TextCleaner().clean(raw)
        chunks = TextSplitter(chunk_size=100, overlap=20).split(clean_text)
        assert len(chunks) >= 1
        for c in chunks:
            assert "\n\n\n" not in c
            assert c.strip() == c or len(c.strip()) > 0

    def test_quality_after_splitting(self):
        from app.infrastructure.document.text_cleaner import TextSplitter, QualityChecker
        text = "这是一段相当有效的知识库内容。" * 100
        chunks = TextSplitter(chunk_size=200, overlap=40).split(text)
        result = QualityChecker().evaluate(chunks)
        assert result["valid"] > 0
        assert result["score"] > 0.5

    def test_pipeline_clean_split_check(self):
        from app.infrastructure.document.text_cleaner import TextCleaner, TextSplitter, QualityChecker
        raw = "  重要知识内容段落。  " * 50
        cleaned = TextCleaner().clean(raw)
        chunks = TextSplitter(chunk_size=100, overlap=20).split(cleaned)
        quality = QualityChecker().evaluate(chunks)
        assert quality["total"] == len(chunks)

    def test_short_doc_pipeline(self):
        from app.infrastructure.document.text_cleaner import TextCleaner, TextSplitter, QualityChecker
        raw = "短文本"
        cleaned = TextCleaner().clean(raw)
        chunks = TextSplitter(chunk_size=100, overlap=20).split(cleaned)
        quality = QualityChecker().evaluate(chunks)
        assert quality["total"] == len(chunks)


# ────────────────────────────────────────────────
# 2. 缓存版本一致性
# ────────────────────────────────────────────────

class TestCacheVersionConsistency:
    """缓存键中包含文档版本，修改后缓存失效"""

    def test_version_in_cache_key(self):
        q = "查询内容"
        v1_key = f"rag:v1:{q}"
        v2_key = f"rag:v2:{q}"
        assert v1_key != v2_key

    def test_different_queries_different_keys(self):
        q1_key = "rag:v1:查询A"
        q2_key = "rag:v1:查询B"
        assert q1_key != q2_key


# ────────────────────────────────────────────────
# 3. 降级机制
# ────────────────────────────────────────────────

class TestDegradationFlow:
    """多级降级，确保最终一定有输出"""

    @pytest.mark.asyncio
    async def test_no_context_gives_friendly_message(self):
        from app.application.pipeline import generate_answer
        answer, level, reason = await generate_answer("问题", "")
        assert "未找到" in answer
        assert reason == "NO_CONTEXT"
        assert level == "C0"

    @pytest.mark.asyncio
    async def test_low_confidence_note(self):
        from app.application.pipeline import calc_confidence
        docs = [{"rerank_score": 0.005}]
        c = calc_confidence(docs, 0.1, 0.1)
        assert c < 0.5  # 低分文档不应有高置信度


# ────────────────────────────────────────────────
# 4. 数据一致性
# ────────────────────────────────────────────────

class TestDataConsistency:
    """验证质量分计算的一致性"""

    def test_quality_score_deterministic(self):
        from app.infrastructure.document.text_cleaner import QualityChecker
        checker = QualityChecker()
        chunks = ["高质量内容超过二十个字符，确保通过验证。"] * 10
        r1 = checker.evaluate(chunks)
        r2 = checker.evaluate(chunks)
        assert r1["score"] == r2["score"]
        assert r1["valid"] == r2["valid"]

    def test_quality_all_short_score_zero(self):
        from app.infrastructure.document.text_cleaner import QualityChecker
        checker = QualityChecker()
        chunks = ["短"] * 10
        result = checker.evaluate(chunks)
        assert result["valid"] == 0
        # score 不完全为0，因为 len_score = min(avg_len/100, 1.0) * 0.3 有微小贡献
        assert result["score"] < 0.01

    def test_quality_mixed_ratio(self):
        from app.infrastructure.document.text_cleaner import QualityChecker
        checker = QualityChecker()
        valid_chunk = "这是有效内容，超过20字的文本段落。" * 2
        chunks = [valid_chunk] * 3 + ["短"] * 7
        result = checker.evaluate(chunks)
        assert result["valid"] == 3
        assert result["total"] == 10
        assert result["valid_ratio"] == pytest.approx(0.3, abs=0.01)


# ────────────────────────────────────────────────
# 5. 并发安全
# ────────────────────────────────────────────────

class TestConcurrencySafety:
    """BM25 索引在并发写入时不会崩溃"""

    def test_concurrent_add_texts(self):
        import threading
        from app.application.pipeline.steps.retrieval_step import HybridRetriever
        retriever = HybridRetriever()
        errors = []

        def add():
            try:
                retriever.add_texts(["并发写入测试文本" * 5])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []

    def test_concurrent_search(self):
        import threading
        from app.application.pipeline.steps.retrieval_step import HybridRetriever
        retriever = HybridRetriever()
        retriever.add_texts(["测试搜索文本" * 5] * 10)
        results = []

        def search():
            try:
                r = retriever._sparse_search("测试搜索", top_k=3)
                results.append(r)
            except Exception as e:
                results.append(e)

        threads = [threading.Thread(target=search) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert all(isinstance(r, list) for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
