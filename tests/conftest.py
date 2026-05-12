"""Shared test fixtures for enterprise RAG system.

Uses dependency injection — no monkey-patching required.
Inject mock implementations directly into domain ports.
"""
import sys
import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Set test environment before any imports
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")
os.environ.setdefault("SILICONFLOW_API_KEY", "sk-test")
os.environ.setdefault("SILICONFLOW_API_BASE", "http://localhost:8080")
os.environ.setdefault("LLM_MODEL", "test-model")
os.environ.setdefault("EMBED_MODEL", "test-embed")


@pytest.fixture
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ---------------------------------------------------------------------------
# Mock infrastructure adapters (inject via DI container)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm_service():
    """Mock LLM service that returns predetermined responses."""
    svc = AsyncMock()
    svc.chat.return_value = "This is a mock answer based on the provided context."
    svc.chat_json.return_value = {
        "action": "retrieval",
        "reason": "Knowledge query requiring document retrieval",
        "tool_name": "",
        "tool_args": {},
    }
    svc.stream.return_value = None  # Set in test if needed
    svc.close.return_value = None
    return svc


@pytest.fixture
def mock_embed_service():
    """Mock embedding service returning zero vectors."""
    svc = AsyncMock()
    svc.embed_one.return_value = [0.1] * 768
    svc.embed_batch.return_value = [[0.1] * 768]
    svc.close.return_value = None
    return svc


@pytest.fixture
def mock_cache_service():
    """Mock cache that returns None (cache miss) by default."""
    svc = AsyncMock()
    svc.connect.return_value = None
    svc.close.return_value = None
    svc.get.return_value = None
    svc.set.return_value = None
    svc.delete.return_value = None
    svc.exists.return_value = False
    svc.get_answer_cache.return_value = None
    svc.set_answer_cache.return_value = None
    svc.get_retrieval_cache.return_value = None
    svc.set_retrieval_cache.return_value = None
    svc.get_embedding_cache.return_value = None
    svc.set_embedding_cache.return_value = None
    svc.get_session_history.return_value = []
    svc.append_session_message.return_value = None
    svc.get_long_term_memory.return_value = ""
    svc.blacklist_token.return_value = None
    svc.is_token_blacklisted.return_value = False
    svc.acquire_upload_lock.return_value = True
    svc.single_flight.return_value = None
    svc.get_doc_version.return_value = 0
    return svc


@pytest.fixture
def mock_vector_repo():
    """Mock vector repository returning fake search results."""
    repo = AsyncMock()
    repo.connect.return_value = None
    repo.close.return_value = None
    repo.search.return_value = [
        {
            "id": "chunk-001",
            "doc_id": "doc-001",
            "text": "RAG stands for Retrieval-Augmented Generation.",
            "score": 0.95,
            "chunk_idx": 0,
            "heading": "Introduction",
            "chunk_type": "text",
        },
        {
            "id": "chunk-002",
            "doc_id": "doc-001",
            "text": "It combines retrieval from a knowledge base with LLM generation.",
            "score": 0.88,
            "chunk_idx": 1,
            "heading": "Introduction",
            "chunk_type": "text",
        },
    ]
    repo.insert.return_value = None
    repo.delete_by_doc_id.return_value = None
    repo.get_collection_stats.return_value = {"entity_count": 100}
    return repo


@pytest.fixture
def mock_search_service():
    """Mock sparse search returning empty results."""
    svc = AsyncMock()
    svc.search.return_value = []
    svc.add_texts.return_value = None
    svc.remove_texts.return_value = None
    svc.clear.return_value = None
    svc.rebuild.return_value = None
    return svc


@pytest.fixture
def mock_graph_store():
    """Mock knowledge graph store."""
    from app.infrastructure.graph.graph_store import KnowledgeGraph
    return KnowledgeGraph()


@pytest.fixture
def mock_document_repo():
    """Mock document repository."""
    repo = AsyncMock()
    repo.find_by_id.return_value = None
    repo.find_by_ids.return_value = []
    repo.save.return_value = None
    repo.update_status.return_value = None
    repo.delete.return_value = None
    repo.list_all.return_value = []
    return repo


@pytest.fixture
def test_settings():
    """Settings instance configured for testing."""
    from app.config.settings import Settings
    return Settings(
        APP_ENV="testing",
        DATABASE_URL="sqlite+aiosqlite:///test.db",
        JWT_SECRET="test-secret",
        SILICONFLOW_API_KEY="sk-test",
        AGENTIC_RAG_ENABLED=True,
        GRAPH_RAG_ENABLED=False,
        RERANKER_MODE="simple",
    )
