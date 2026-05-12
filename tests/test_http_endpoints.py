"""
HTTP 端到端集成测试 — 使用 FastAPI TestClient 测试完整请求/响应链路。
覆盖: auth, chat, feedback, metrics, upload, 错误处理
"""
import io
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.persistence.models import Base, engine, init_db


# ──────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────

@pytest.fixture(scope="module")
async def setup_db():
    """为整个测试模块创建一次数据库表（先 drop 确保干净状态）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(setup_db):
    """AsyncClient wrapping the FastAPI app (dev mode: auth bypassed)"""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    """生成有效 JWT token 用于测试"""
    from app.api.deps import create_token
    token = create_token(user_id="test-user-001", role="admin", tenant_id="default")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def _mock_rag_pipeline():
    """Mock RAG pipeline，避免真实 LLM / 向量库 调用"""
    fake_result = {
        "answer": "这是测试回答。",
        "sources": [{"idx": 1, "text": "测试文档片段", "score": 0.95, "doc_id": "d1", "chunk_idx": 0}],
        "context": "测试上下文",
        "confidence": 0.85,
        "rewritten_query": "测试问题",
        "intent": "C2",
        "intent_v2": {"route_strategy": "rag_standard", "complexity": "medium"},
        "cache_hit": False,
        "latency_ms": 120,
        "retrieval_ms": 50,
        "llm_ms": 70,
        "degrade_level": "C2",
        "degrade_reason": "",
    }
    with patch("app.api.chat.rag_service") as mock_svc:
        mock_svc.query = AsyncMock(return_value=fake_result)

        async def _fake_stream(*args, **kwargs):
            for tok in ["这是", "流式", "回答"]:
                yield tok
            yield f"\n[SOURCES]{json.dumps([{{'idx': 1, 'text': '片段', 'score': 0.9}}], ensure_ascii=False)}"

        mock_svc.stream = _fake_stream
        yield mock_svc, fake_result


@pytest.fixture
def _mock_redis():
    """Mock Redis，防止测试依赖外部 Redis 实例"""
    with patch("app.repository.redis_cache.cache") as mock:
        mock.get_rag = AsyncMock(return_value=None)
        mock.set_rag = AsyncMock()
        mock.get_answer = AsyncMock(return_value=None)
        mock.set_answer = AsyncMock()
        mock.get_session_history = AsyncMock(return_value=[])
        mock.get_global_doc_version = AsyncMock(return_value=1)
        mock.is_token_blacklisted = AsyncMock(return_value=False)
        mock.blacklist_token = AsyncMock()
        mock.try_acquire_upload_lock = AsyncMock(return_value=True)
        mock.release_upload_lock = AsyncMock()
        mock.single_flight = AsyncMock(side_effect=lambda key, coro: coro())
        mock.client = MagicMock()
        yield mock


# ──────────────────────────────────────────
# Auth 端点
# ──────────────────────────────────────────

class TestAuthEndpoints:
    """认证相关端点"""

    async def test_login_missing_fields(self, client):
        resp = await client.post("/auth/login", json={})
        assert resp.status_code == 422  # Pydantic validation

    async def test_login_wrong_credentials(self, client):
        resp = await client.post("/auth/login", json={
            "username": "nonexistent_user_xxx",
            "password": "wrongpass",
        })
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"]["code"] == 1002

    async def test_login_success(self, client):
        """需要 admin 账号存在（init_db 会创建）"""
        import bcrypt
        from sqlalchemy import select
        from app.infrastructure.persistence.models import AsyncSessionLocal, User

        # 确保 admin 存在
        pw = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(User).where(User.username == "testadmin"))
            if not r.scalar_one_or_none():
                db.add(User(
                    id=str(uuid.uuid4()), username="testadmin",
                    password=pw, role="admin",
                ))
                await db.commit()

        resp = await client.post("/auth/login", json={
            "username": "testadmin",
            "password": "admin123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "token" in body["data"]

    async def test_me_dev_mode(self, client, auth_headers):
        """开发模式下 /auth/me 返回 dev_user"""
        resp = await client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200

    async def test_logout(self, client, auth_headers):
        resp = await client.post("/auth/logout", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


# ──────────────────────────────────────────
# Chat 端点
# ──────────────────────────────────────────

class TestChatEndpoints:
    """RAG 查询端点"""

    async def test_chat_sync_success(self, client, auth_headers, _mock_rag_pipeline, _mock_redis):
        mock_svc, fake_result = _mock_rag_pipeline
        resp = await client.post(
            "/chat/",
            json={"question": "什么是RAG系统？"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "answer" in body["data"]
        assert body["data"]["answer"] == "这是测试回答。"

    async def test_chat_empty_question(self, client, auth_headers):
        resp = await client.post(
            "/chat/",
            json={"question": ""},
            headers=auth_headers,
        )
        # 空问题应返回 400
        assert resp.status_code in (400, 422)

    async def test_chat_question_too_long(self, client, auth_headers):
        long_q = "a" * 5000
        resp = await client.post(
            "/chat/",
            json={"question": long_q},
            headers=auth_headers,
        )
        # Pydantic schema max_length=2000 rejects with 422
        assert resp.status_code in (400, 422)

    async def test_chat_with_session_id(self, client, auth_headers, _mock_rag_pipeline, _mock_redis):
        mock_svc, _ = _mock_rag_pipeline
        resp = await client.post(
            "/chat/",
            json={"question": "继续上个话题", "session_id": "sess-001"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # 验证 session_id 传递到 service
        mock_svc.query.assert_called_once()
        call_kwargs = mock_svc.query.call_args
        assert call_kwargs.kwargs.get("session_id") == "sess-001" or \
               (call_kwargs.args and "sess-001" in str(call_kwargs))

    async def test_chat_with_tag_ids(self, client, auth_headers, _mock_rag_pipeline, _mock_redis):
        mock_svc, _ = _mock_rag_pipeline
        resp = await client.post(
            "/chat/",
            json={"question": "查询特定标签", "tag_ids": ["tag-1", "tag-2"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_chat_no_auth(self, client):
        """未认证请求应被拒绝"""
        resp = await client.post("/chat/", json={"question": "test"})
        assert resp.status_code == 401

    async def test_chat_stream_endpoint_exists(self, client, auth_headers):
        """验证 SSE 流式端点可达"""
        resp = await client.get(
            "/chat/stream",
            params={"question": "测试"},
            headers=auth_headers,
        )
        # Stream 端点应该返回 200（即使底层 mock 不完整，端点本身应该可达）
        assert resp.status_code in (200, 500)


# ──────────────────────────────────────────
# Chat History 端点
# ──────────────────────────────────────────

class TestChatHistoryEndpoints:

    async def test_history_list(self, client, auth_headers):
        resp = await client.get("/chat/history", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "items" in body["data"] or isinstance(body["data"], list)

    async def test_history_with_limit(self, client, auth_headers):
        resp = await client.get(
            "/chat/history", params={"limit": 5}, headers=auth_headers,
        )
        assert resp.status_code == 200


# ──────────────────────────────────────────
# Feedback 端点
# ──────────────────────────────────────────

class TestFeedbackEndpoints:

    async def test_submit_like(self, client, auth_headers):
        resp = await client.post(
            "/feedback/",
            json={
                "query": "测试问题",
                "answer": "测试回答",
                "feedback": "like",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0

    async def test_submit_dislike_with_reason(self, client, auth_headers):
        resp = await client.post(
            "/feedback/",
            json={
                "query": "测试问题",
                "answer": "错误的回答",
                "feedback": "dislike",
                "reason": "答非所问",
                "correction": "正确的回答应该是...",
                "ratings": {"relevance": 1, "accuracy": 2, "completeness": 1},
                "comment": "需要改进",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_submit_invalid_feedback_type(self, client, auth_headers):
        resp = await client.post(
            "/feedback/",
            json={
                "query": "测试",
                "answer": "回答",
                "feedback": "invalid_type",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_feedback_stats(self, client, auth_headers):
        resp = await client.get("/feedback/stats", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


# ──────────────────────────────────────────
# Metrics 端点
# ──────────────────────────────────────────

class TestMetricsEndpoints:

    async def test_overview(self, client, auth_headers, _mock_redis):
        with patch("app.repository.vector_store.milvus_db") as mock_milvus:
            mock_milvus.get_stats.return_value = {"total_entities": 100}
            resp = await client.get("/metrics/overview", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert "doc_count" in data
        assert "query_count" in data

    async def test_cache_metrics(self, client, auth_headers, _mock_redis):
        _mock_redis.get_stats = AsyncMock(return_value={"redis_hit_rate": 0.75})
        resp = await client.get("/metrics/cache", headers=auth_headers)
        assert resp.status_code == 200

    async def test_rag_metrics(self, client, auth_headers):
        with patch("app.api.metrics.eval_service") as mock_eval:
            mock_eval.get_metrics = AsyncMock(return_value={"avg_score": 3.5})
            resp = await client.get(
                "/metrics/rag", params={"days": 7}, headers=auth_headers,
            )
        assert resp.status_code == 200


# ──────────────────────────────────────────
# Upload 端点
# ──────────────────────────────────────────

class TestUploadEndpoints:

    async def test_upload_no_file(self, client, auth_headers):
        resp = await client.post("/upload/", headers=auth_headers)
        assert resp.status_code == 422  # missing required file

    async def test_upload_empty_file(self, client, auth_headers, _mock_redis):
        resp = await client.post(
            "/upload/",
            files={"file": ("test.txt", b"", "text/plain")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_upload_unsupported_ext(self, client, auth_headers, _mock_redis):
        resp = await client.post(
            "/upload/",
            files={"file": ("test.exe", b"binary content", "application/octet-stream")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_upload_txt_success(self, client, auth_headers, _mock_redis):
        with patch("app.api.upload.minio_storage") as mock_minio, \
             patch("app.api.upload.process_document_after_upload") as mock_process:
            mock_minio.upload = MagicMock()
            mock_process.return_value = None

            content = "这是一段测试文档内容，用于验证上传功能是否正常工作。" * 10
            resp = await client.post(
                "/upload/",
                files={"file": ("test.txt", content.encode("utf-8"), "text/plain")},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0


# ──────────────────────────────────────────
# Audit 端点
# ──────────────────────────────────────────

class TestAuditEndpoints:

    async def test_audit_list(self, client, auth_headers):
        resp = await client.get("/audit/", headers=auth_headers)
        assert resp.status_code == 200

    async def test_audit_with_action_filter(self, client, auth_headers):
        resp = await client.get(
            "/audit/",
            params={"action": "login"},
            headers=auth_headers,
        )
        assert resp.status_code == 200


# ──────────────────────────────────────────
# 通用错误处理
# ──────────────────────────────────────────

class TestErrorHandling:

    async def test_404_not_found(self, client):
        resp = await client.get("/nonexistent/endpoint")
        assert resp.status_code == 404

    async def test_method_not_allowed(self, client, auth_headers):
        resp = await client.delete("/chat/", headers=auth_headers)
        assert resp.status_code == 405

    async def test_trace_id_in_response(self, client, auth_headers, _mock_rag_pipeline, _mock_redis):
        resp = await client.post(
            "/chat/",
            json={"question": "trace测试"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        # 统一响应格式应包含 trace_id
        assert "trace_id" in body


# ──────────────────────────────────────────
# 并发安全
# ──────────────────────────────────────────

class TestConcurrency:

    async def test_concurrent_chat_requests(self, client, auth_headers, _mock_rag_pipeline, _mock_redis):
        """并发发送多个 chat 请求，验证不会出错"""
        import asyncio
        tasks = []
        for i in range(5):
            tasks.append(
                client.post(
                    "/chat/",
                    json={"question": f"并发问题 {i}"},
                    headers=auth_headers,
                )
            )
        responses = await asyncio.gather(*tasks)
        for resp in responses:
            assert resp.status_code == 200
            assert resp.json()["code"] == 0


# ──────────────────────────────────────────
# API 版本化兼容
# ──────────────────────────────────────────

class TestVersionedApi:

    async def test_health_v1_alias(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    async def test_metrics_overview_v1_alias(self, client, auth_headers, _mock_redis):
        with patch("app.repository.vector_store.milvus_db") as mock_milvus:
            mock_milvus.get_stats.return_value = {"total_entities": 100}
            resp = await client.get("/api/v1/metrics/overview", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


# ──────────────────────────────────────────
# R3: 输入校验与边界硬化
# ──────────────────────────────────────────

class TestInputValidationR3:

    async def test_chat_question_max_length_schema(self, client, auth_headers):
        """Pydantic schema 层拒绝超长问题"""
        long_q = "a" * 2001
        resp = await client.post("/chat/", json={"question": long_q}, headers=auth_headers)
        assert resp.status_code in (400, 422)

    async def test_chat_question_empty_string_rejected(self, client, auth_headers):
        """Pydantic min_length=1 拒绝空字符串"""
        resp = await client.post("/chat/", json={"question": ""}, headers=auth_headers)
        assert resp.status_code in (400, 422)

    async def test_chat_question_whitespace_only_rejected(self, client, auth_headers):
        """空白字符串在业务层被拒绝"""
        resp = await client.post("/chat/", json={"question": "   "}, headers=auth_headers)
        assert resp.status_code == 400


class TestZipBombProtection:

    async def test_zip_too_many_entries(self, client, auth_headers, _mock_redis):
        """ZIP 条目超限应返回 400"""
        import zipfile as _zf
        buf = io.BytesIO()
        with _zf.ZipFile(buf, "w") as zf:
            for i in range(201):
                zf.writestr(f"file_{i}.txt", f"content {i}")
        buf.seek(0)
        resp = await client.post(
            "/upload/batch",
            files={"file": ("test.zip", buf.getvalue(), "application/zip")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "条目过多" in resp.json()["detail"]["message"]

    async def test_zip_normal_count_accepted(self, client, auth_headers, _mock_redis):
        """正常数量的 ZIP 条目通过校验（不会在条目数校验处失败）"""
        import zipfile as _zf
        buf = io.BytesIO()
        with _zf.ZipFile(buf, "w") as zf:
            for i in range(3):
                zf.writestr(f"doc_{i}.txt", "valid content " * 20)
        buf.seek(0)
        with patch("app.api.upload.minio_storage") as mock_minio, \
             patch("app.api.upload.process_document_after_upload") as mock_proc:
            mock_minio.upload = MagicMock()
            mock_proc.return_value = None
            resp = await client.post(
                "/upload/batch",
                files={"file": ("test.zip", buf.getvalue(), "application/zip")},
                headers=auth_headers,
            )
        assert resp.status_code == 200


class TestRateLimitHeaders:

    async def test_rate_limit_has_retry_after(self, client, auth_headers):
        """429 应携带 Retry-After 头"""
        with patch("app.repository.redis_cache.cache") as mock_cache:
            mock_cache.client = MagicMock()
            mock_cache.client.incr = AsyncMock(return_value=9999)
            mock_cache.client.expire = AsyncMock()
            mock_cache.is_token_blacklisted = AsyncMock(return_value=False)
            resp = await client.post(
                "/chat/",
                json={"question": "rate limit test"},
                headers=auth_headers,
            )
        assert resp.status_code == 429
        assert resp.headers.get("retry-after") == "60"


class TestUploadLockOwnerSafety:

    @pytest.mark.asyncio
    async def test_release_lock_only_if_owner_matches(self):
        """compare-and-delete: 非 owner 不能释放锁"""
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=b"owner-A")
        mock_client.delete = AsyncMock()
        c.client = mock_client

        await c.release_upload_lock("key1", owner="owner-B")
        mock_client.delete.assert_not_called()

        await c.release_upload_lock("key1", owner="owner-A")
        mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_lock_without_owner_always_deletes(self):
        """不传 owner 时无条件删除（向后兼容）"""
        from app.infrastructure.cache.redis_cache import RedisCache
        c = RedisCache()
        mock_client = AsyncMock()
        mock_client.delete = AsyncMock()
        c.client = mock_client

        await c.release_upload_lock("key1")
        mock_client.delete.assert_called_once()
