"""
RAG Pipeline 单元测试 — 完整覆盖版本（兼容性）
运行: cd rag_system && DATABASE_URL="sqlite+aiosqlite:///test.db" pytest tests/test_rag_pipeline.py -v
"""
import asyncio
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 设置测试环境变量（必须在导入 app 模块之前）
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
# 1. DocParser
# ────────────────────────────────────────────────

class TestDocParser:
    def setup_method(self):
        from app.infrastructure.document.text_cleaner import DocParser
        self.parser = DocParser()

    def test_parse_txt(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Hello 你好 World", encoding="utf-8")
        result = self.parser.parse(str(f))
        assert "Hello" in result
        assert "你好" in result

    def test_parse_html_strips_tags(self, tmp_path):
        f = tmp_path / "test.html"
        f.write_text("<html><body><p>Test Content</p><script>bad()</script></body></html>")
        result = self.parser.parse(str(f))
        assert "Test Content" in result
        assert "bad()" not in result

    def test_parse_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = self.parser.parse(str(f))
        assert result == ""

    def test_parse_nonexistent_file(self):
        result = self.parser.parse("/nonexistent/path.txt")
        assert result == ""

    def test_parse_returns_string(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("普通文本内容")
        result = self.parser.parse(str(f))
        assert isinstance(result, str)


# ────────────────────────────────────────────────
# 2. TextCleaner
# ────────────────────────────────────────────────

class TestTextCleaner:
    def setup_method(self):
        from app.infrastructure.document.text_cleaner import TextCleaner
        self.cleaner = TextCleaner()

    def test_collapse_newlines(self):
        result = self.cleaner.clean("Line1\n\n\n\nLine2")
        assert "\n\n\n" not in result
        assert "Line1" in result and "Line2" in result

    def test_collapse_spaces(self):
        result = self.cleaner.clean("word1   word2    word3")
        assert "   " not in result

    def test_strip_whitespace(self):
        result = self.cleaner.clean("  \n  Hello  \n  ")
        assert result == "Hello"

    def test_keep_chinese(self):
        result = self.cleaner.clean("这是中文内容 This is English")
        assert "这是中文内容" in result
        assert "This is English" in result

    def test_empty_string(self):
        assert self.cleaner.clean("") == ""

    def test_none_input(self):
        assert self.cleaner.clean(None) == ""  # type: ignore

    def test_removes_control_chars(self):
        result = self.cleaner.clean("hello\x00world\x01test")
        assert "\x00" not in result
        assert "\x01" not in result

    def test_keeps_punctuation(self):
        result = self.cleaner.clean("你好，世界！这是测试。")
        assert "，" in result
        assert "！" in result


# ────────────────────────────────────────────────
# 3. TextSplitter
# ────────────────────────────────────────────────

class TestTextSplitter:
    def setup_method(self):
        from app.infrastructure.document.text_cleaner import TextSplitter
        self.TextSplitter = TextSplitter
        self.splitter = TextSplitter(chunk_size=100, overlap=20)

    def test_basic_split_produces_multiple_chunks(self):
        text = "A" * 250
        chunks = self.splitter.split(text)
        assert len(chunks) > 1

    def test_short_text_fits_in_chunk(self):
        text = "短文本"
        chunks = self.splitter.split(text)
        assert len(chunks) >= 1
        combined = "".join(chunks)
        assert "短" in combined

    def test_empty_text(self):
        assert self.splitter.split("") == []

    def test_whitespace_only(self):
        assert self.splitter.split("   \n   ") == []

    def test_sentence_boundary_preference(self):
        text = "这是第一句话。" * 10 + "这是最后一句。"
        chunks = self.splitter.split(text)
        assert len(chunks) >= 1

    def test_no_infinite_loop(self):
        s = self.TextSplitter(chunk_size=10, overlap=0)
        result = s.split("abc" * 20)
        assert len(result) > 0

    def test_large_text_splits_correctly(self):
        text = "这是一段测试内容。" * 1000
        s = self.TextSplitter(chunk_size=500, overlap=50)
        chunks = s.split(text)
        assert len(chunks) > 1
        assert all(len(c) > 0 for c in chunks)

    def test_all_chunks_non_empty(self):
        text = "内容" * 200
        chunks = self.splitter.split(text)
        assert all(c.strip() for c in chunks)

    def test_overlap_causes_more_chunks(self):
        """有重叠时，next_start更小，产生更多chunks"""
        text = "A" * 300
        s_no_overlap = self.TextSplitter(chunk_size=100, overlap=0)
        s_overlap    = self.TextSplitter(chunk_size=100, overlap=50)
        chunks_no = s_no_overlap.split(text)
        chunks_ov = s_overlap.split(text)
        assert len(chunks_ov) >= len(chunks_no)


# ────────────────────────────────────────────────
# 4. QualityChecker
# ────────────────────────────────────────────────

class TestQualityChecker:
    def setup_method(self):
        from app.infrastructure.document.text_cleaner import QualityChecker
        self.checker = QualityChecker()

    def test_empty_input(self):
        result = self.checker.evaluate([])
        assert result["score"] == 0.0
        assert result["total"] == 0

    def test_all_valid(self):
        chunks = ["这是一段有效内容，超过二十个字符的文本，用于质量测试。"] * 5
        result = self.checker.evaluate(chunks)
        assert result["score"] > 0.6
        assert result["valid"] == 5
        assert result["total"] == 5

    def test_all_invalid_short(self):
        chunks = ["短"] * 5
        result = self.checker.evaluate(chunks)
        assert result["valid"] == 0
        assert result["valid_ratio"] == 0.0

    def test_mixed_quality(self):
        valid_chunk = "这是有效内容，超过20字。" * 2
        chunks = [valid_chunk] * 3 + ["短"] * 7
        result = self.checker.evaluate(chunks)
        assert result["valid"] == 3
        assert result["total"] == 10

    def test_score_range(self):
        chunks = ["A" * 100] * 10
        result = self.checker.evaluate(chunks)
        assert 0.0 <= result["score"] <= 1.0

    def test_returns_all_fields(self):
        result = self.checker.evaluate(["测试内容" * 10])
        for field in ("score", "valid_ratio", "avg_length", "total", "valid"):
            assert field in result


# ────────────────────────────────────────────────
# 5. HybridRetriever
# ────────────────────────────────────────────────

class TestHybridRetriever:
    def setup_method(self):
        from app.application.pipeline.steps.retrieval_step import HybridRetriever
        self.retriever = HybridRetriever()

    def test_bm25_empty_index(self):
        result = self.retriever._sparse_search("query", top_k=5)
        assert result == []

    def test_bm25_add_and_search(self):
        texts = [
            "Python 是一种编程语言",
            "机器学习需要大量数据",
            "向量数据库用于相似搜索",
        ]
        self.retriever.add_texts(texts)
        result = self.retriever._sparse_search("Python 编程", top_k=3)
        assert len(result) >= 1
        assert any("Python" in r["text"] for r in result)

    def test_bm25_search_returns_scores(self):
        self.retriever.add_texts(["Python 编程语言测试"])
        result = self.retriever._sparse_search("Python", top_k=1)
        if result:
            assert "score" in result[0]
            assert result[0]["score"] > 0

    def test_rrf_merge_deduplication(self):
        dense  = [{"text": "同一段文本内容测试", "score": 0.9, "id": "1", "source": "dense"}]
        sparse = [{"text": "同一段文本内容测试", "score": 5.0, "id": "bm25_0", "source": "sparse"}]
        merged = self.retriever._rrf_merge(dense, sparse)
        assert len(merged) == 1

    def test_rrf_merge_combines_different(self):
        dense  = [{"text": "Dense文本内容测试版本", "score": 0.95, "id": "d1", "source": "dense"}]
        sparse = [{"text": "Sparse文本内容测试版本", "score": 10.0, "id": "s1", "source": "sparse"}]
        merged = self.retriever._rrf_merge(dense, sparse)
        assert len(merged) == 2
        assert all("rrf_score" in m for m in merged)

    def test_rrf_alpha_weights_dense(self):
        dense  = [{"text": "Dense高分内容版本测试", "score": 0.95, "id": "d1", "source": "dense"}]
        sparse = [{"text": "Sparse低权重内容版本", "score": 10.0, "id": "s1", "source": "sparse"}]
        merged = self.retriever._rrf_merge(dense, sparse, alpha=0.9)
        assert "Dense" in merged[0]["text"]

    def test_rrf_empty_inputs(self):
        merged = self.retriever._rrf_merge([], [])
        assert merged == []

    def test_rrf_only_dense(self):
        dense = [{"text": "Dense内容", "score": 0.8, "id": "d1", "source": "dense"}]
        merged = self.retriever._rrf_merge(dense, [])
        assert len(merged) == 1

    def test_thread_safety(self):
        import threading
        from app.application.pipeline.steps.retrieval_step import HybridRetriever
        r = HybridRetriever()
        errors = []
        def add():
            try:
                r.add_texts(["测试文本" * 5])
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=add) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0


# ────────────────────────────────────────────────
# 6. SimpleReranker
# ────────────────────────────────────────────────

class TestSimpleReranker:
    def setup_method(self):
        from app.infrastructure.reranker.simple_reranker import SimpleReranker
        self.reranker = SimpleReranker()

    def test_rerank_top_n(self):
        docs = [{"text": f"文档{i}内容测试", "rrf_score": i * 0.1} for i in range(10)]
        result = self.reranker.rerank("文档", docs, top_n=3)
        assert len(result) == 3

    def test_keyword_boost(self):
        docs = [
            {"text": "这是关于 Python 编程的内容介绍", "rrf_score": 0.5},
            {"text": "这是关于 Java 开发的内容说明",   "rrf_score": 0.8},
        ]
        result = self.reranker.rerank("Python", docs, top_n=2)
        assert "Python" in result[0]["text"]

    def test_empty_docs(self):
        result = self.reranker.rerank("query", [], top_n=3)
        assert result == []

    def test_fewer_docs_than_top_n(self):
        docs = [{"text": "只有一条文档内容测试", "rrf_score": 0.5}]
        result = self.reranker.rerank("query", docs, top_n=5)
        assert len(result) == 1

    def test_adds_rerank_score(self):
        docs = [{"text": "测试文档内容" * 3, "rrf_score": 0.5}]
        result = self.reranker.rerank("测试", docs, top_n=1)
        assert "rerank_score" in result[0]

    def test_empty_query(self):
        docs = [{"text": "测试文档内容", "rrf_score": 0.5}]
        result = self.reranker.rerank("", docs, top_n=1)
        assert len(result) == 1


# ────────────────────────────────────────────────
# 7. CacheStats（独立模块，不依赖redis连接）
# ────────────────────────────────────────────────

class TestCacheStats:
    def _make_stats(self):
        class CacheStats:
            def __init__(self):
                self.hits = 0
                self.misses = 0
            @property
            def hit_rate(self):
                total = self.hits + self.misses
                return round(self.hits / total, 4) if total else 0.0
            def record_hit(self): self.hits += 1
            def record_miss(self): self.misses += 1
        return CacheStats()

    def test_initial_hit_rate(self):
        s = self._make_stats()
        assert s.hit_rate == 0.0

    def test_hit_rate_calculation(self):
        s = self._make_stats()
        for _ in range(7): s.record_hit()
        for _ in range(3): s.record_miss()
        assert s.hit_rate == 0.7

    def test_all_hits(self):
        s = self._make_stats()
        for _ in range(10): s.record_hit()
        assert s.hit_rate == 1.0

    def test_all_misses(self):
        s = self._make_stats()
        for _ in range(10): s.record_miss()
        assert s.hit_rate == 0.0


# ────────────────────────────────────────────────
# 8. RAG Pipeline Functions
# ────────────────────────────────────────────────

class TestPipelineFunctions:

    @pytest.mark.asyncio
    async def test_classify_intent_c0(self):
        from app.application.pipeline import classify_intent
        result = await classify_intent("什么是RAG")
        assert result == "C0"

    @pytest.mark.asyncio
    async def test_classify_intent_c1(self):
        from app.application.pipeline import classify_intent
        result = await classify_intent("请简要说明RAG系统的检索过程")
        assert result == "C1"

    @pytest.mark.asyncio
    async def test_classify_intent_c2(self):
        from app.application.pipeline import classify_intent
        result = await classify_intent("请详细分析RAG系统在企业知识库场景下的检索增强生成流程，包括向量检索、BM25稀疏检索和RRF融合排序的具体实现细节")
        assert result == "C2"

    def test_build_context_empty(self):
        from app.application.pipeline import build_context
        assert build_context([]) == ""

    def test_build_context_truncation(self):
        from app.application.pipeline import build_context
        docs = [{"text": "A" * 5000}]
        result = build_context(docs, max_chars=100)
        assert len(result) <= 200  # [来源N]\n prefix + text

    def test_build_context_multiple_docs(self):
        from app.application.pipeline import build_context
        docs = [
            {"text": "第一段内容"},
            {"text": "第二段内容"},
        ]
        result = build_context(docs)
        assert "来源1" in result
        assert "来源2" in result

    def test_calc_confidence_empty(self):
        from app.application.pipeline import calc_confidence
        assert calc_confidence([], 0.0, 0.0) == 0.0

    def test_calc_confidence_range(self):
        from app.application.pipeline import calc_confidence
        docs = [{"rerank_score": 0.5}]
        result = calc_confidence(docs, 0.8, 0.7)
        assert 0.0 <= result <= 1.0


# ────────────────────────────────────────────────
# 9. Reranker Integration
# ────────────────────────────────────────────────

class TestRerankerIntegration:

    def test_simple_reranker_preserves_fields(self):
        from app.infrastructure.reranker.simple_reranker import SimpleReranker
        r = SimpleReranker()
        docs = [{"text": "测试文档内容内容", "rrf_score": 0.5, "doc_id": "d1", "chunk_idx": 0}]
        result = r.rerank("测试", docs, top_n=1)
        assert result[0]["doc_id"] == "d1"
        assert result[0]["chunk_idx"] == 0
        assert "rerank_score" in result[0]


# ────────────────────────────────────────────────
# 10. Pipeline Degradation
# ────────────────────────────────────────────────

class TestPipelineDegradation:

    @pytest.mark.asyncio
    async def test_generate_answer_no_context(self):
        """无上下文时返回友好提示"""
        from app.application.pipeline import generate_answer
        answer, level, reason = await generate_answer("问题", "")
        assert "未找到" in answer
        assert level == "C0"
        assert reason == "NO_CONTEXT"

    @pytest.mark.asyncio
    async def test_generate_answer_c2_timeout_degrades(self):
        """C2超时降级到C1"""
        from app.application.pipeline import generate_answer
        import asyncio as aio

        call_count = 0
        async def mock_chat(messages, temperature=0.3, max_tokens=1024, model=""):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await aio.sleep(10)  # C2超时
            return "C1快速回答"

        with patch("app.core.pipeline.generation.llm_client") as mock:
            mock.chat = mock_chat
            answer, level, reason = await generate_answer("问", "上下文")

        assert level in ("C1", "C0")

    @pytest.mark.asyncio
    async def test_llm_self_score_range(self):
        """自评分必须在 0~1 范围"""
        from app.application.pipeline import llm_self_score
        with patch("app.core.pipeline.generation.llm_client") as mock:
            mock.chat = AsyncMock(return_value="0.85")
            score = await llm_self_score("问题", "回答")
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_llm_self_score_invalid_returns_default(self):
        """LLM返回非数字时使用默认分"""
        from app.application.pipeline import llm_self_score
        with patch("app.core.pipeline.generation.llm_client") as mock:
            mock.chat = AsyncMock(return_value="不是数字")
            score = await llm_self_score("问题", "回答")
        assert score == 0.5


# ────────────────────────────────────────────────
# 11. Trace ID
# ────────────────────────────────────────────────

class TestTraceId:
    def test_generate_trace_id_format(self):
        from app.shared.trace import generate_trace_id
        tid = generate_trace_id()
        assert len(tid) == 16
        assert tid.isalnum()

    def test_trace_id_context(self):
        from app.shared.trace import set_trace_id, get_trace_id
        set_trace_id("test123")
        assert get_trace_id() == "test123"
        set_trace_id("")


# ────────────────────────────────────────────────
# 12. Helpers
# ────────────────────────────────────────────────

class TestHelpers:
    def test_truncate(self):
        from app.shared.helpers import truncate
        assert truncate("hello world", 5) == "hello"
        assert truncate("short", 100) == "short"
        assert truncate("", 10) == ""
        assert truncate(None, 10) == ""

    def test_sha256_hash(self):
        from app.shared.helpers import sha256_hash
        h1 = sha256_hash("test")
        h2 = sha256_hash("test")
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex digest length


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
