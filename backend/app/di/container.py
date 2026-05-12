"""
Dependency Injection Container — wires all ports (abstract interfaces) to
concrete adapters (infrastructure implementations).

All services are lazily initialised on first access and cached as
instance-level singletons within the container.  The container is
created once during application startup (see ``main.py`` lifespan) and
stored on ``app.state.container``.

Usage
-----
.. code-block:: python

    from app.api.deps.container import get_container

    @router.post("/chat")
    async def chat(container=Depends(get_container)):
        result = await container.query_use_case.execute(...)
"""

from __future__ import annotations

import httpx

from app.config.settings import Settings

# -- Domain ports (abstract interfaces) --
from app.domain.ports.llm_port import AbstractLLMService, AbstractEmbeddingService
from app.domain.ports.cache_port import AbstractCacheService
from app.domain.ports.vector_port import AbstractVectorRepository
from app.domain.ports.search_port import AbstractSearchService
from app.domain.ports.storage_port import AbstractStorageService
from app.domain.ports.repository_ports import (
    AbstractDocumentRepository,
    AbstractChunkRepository,
    AbstractUserRepository,
)
from app.domain.ports.task_queue_port import AbstractTaskQueue

# -- Domain services (pure business logic, stateless) --
from app.domain.services.intent_classifier import IntentClassifier
from app.domain.services.confidence_calculator import ConfidenceCalculator
from app.domain.services.flow_controller import FlowController
from app.domain.services.tool_registry import get_default_registry

# -- Infrastructure: LLM --
from app.infrastructure.llm.client import LLMClient
from app.infrastructure.llm.embedding import EmbeddingClient

# -- Infrastructure: Cache --
from app.infrastructure.cache.redis_cache import RedisCache
from app.infrastructure.cache.null_cache import NullCache

# -- Infrastructure: Vector --
from app.infrastructure.vector.milvus_repository import MilvusVectorRepository
from app.infrastructure.vector.memory_repository import InMemoryVectorRepository

# -- Infrastructure: Search / Storage / Persistence / Task Queue / Graph --
from app.infrastructure.search.factory import create_search_service
from app.infrastructure.storage.minio_storage import MinioStorage
from app.infrastructure.persistence.document_repository import (
    PostgresDocumentRepository,
)
from app.infrastructure.persistence.user_repository import PostgresUserRepository
from app.infrastructure.persistence.chunk_repository import PostgresChunkRepository
from app.infrastructure.reranker.factory import create_reranker
from app.infrastructure.task_queue.redis_queue import RedisTaskQueue
from app.infrastructure.task_queue.memory_queue import InMemoryTaskQueue
from app.infrastructure.graph.graph_store import KnowledgeGraph

# -- Pipeline steps --
from app.application.pipeline.steps.flow_control_step import FlowControlStep
from app.application.pipeline.steps.memory_step import MemoryStep
from app.application.pipeline.steps.rewrite_step import RewriteStep
from app.application.pipeline.steps.intent_step import IntentStep
from app.application.pipeline.steps.agent_step import AgentStep
from app.application.pipeline.steps.retrieval_step import RetrievalStep
from app.application.pipeline.steps.rerank_step import RerankStep
from app.application.pipeline.steps.context_step import ContextStep
from app.application.pipeline.steps.generation_step import GenerationStep
from app.application.pipeline.steps.confidence_step import ConfidenceStep
from app.application.pipeline.orchestrator import RAGPipelineOrchestrator

# -- Use cases --
from app.application.use_cases.query_use_case import QueryUseCase
from app.application.use_cases.streaming_use_case import StreamingQueryUseCase
from app.application.use_cases.document_use_case import DocumentUseCase


class DIContainer:
    """Dependency Injection Container — wires all ports to adapters.

    Every public property returns a fully-wired, lazy-initialised instance.
    The container itself is created once at startup and stored on
    ``app.state.container``.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

        # HTTP client (shared across LLM, embedding, and storage clients)
        self._http_client: httpx.AsyncClient | None = None

        # Infrastructure singletons (lazy)
        self._llm_service: AbstractLLMService | None = None
        self._embed_service: AbstractEmbeddingService | None = None
        self._cache_service: AbstractCacheService | None = None
        self._vector_repo: AbstractVectorRepository | None = None
        self._search_service: AbstractSearchService | None = None
        self._storage_service: AbstractStorageService | None = None
        self._doc_repo: AbstractDocumentRepository | None = None
        self._chunk_repo: AbstractChunkRepository | None = None
        self._user_repo: AbstractUserRepository | None = None
        self._task_queue: AbstractTaskQueue | None = None
        self._graph_store: KnowledgeGraph | None = None
        self._reranker = None

        # Domain services (stateless, instantiated once)
        self._intent_classifier: IntentClassifier | None = None
        self._confidence_calculator: ConfidenceCalculator | None = None
        self._flow_controller: FlowController | None = None

        # Pipeline (shared between sync and streaming)
        self._cached_pipeline_steps: list | None = None
        self._generation_step: GenerationStep | None = None

        # Use cases
        self._query_use_case: QueryUseCase | None = None
        self._stream_use_case: StreamingQueryUseCase | None = None
        self._doc_use_case: DocumentUseCase | None = None

    # ------------------------------------------------------------------
    # Shared HTTP client
    # ------------------------------------------------------------------

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0),
                limits=httpx.Limits(
                    max_keepalive_connections=20, max_connections=100
                ),
            )
        return self._http_client

    # ------------------------------------------------------------------
    # Infrastructure: LLM
    # ------------------------------------------------------------------

    @property
    def llm_service(self) -> AbstractLLMService:
        if self._llm_service is None:
            self._llm_service = LLMClient()
        return self._llm_service

    @property
    def embed_service(self) -> AbstractEmbeddingService:
        if self._embed_service is None:
            self._embed_service = EmbeddingClient()
        return self._embed_service

    # ------------------------------------------------------------------
    # Infrastructure: Cache
    # ------------------------------------------------------------------

    @property
    def cache_service(self) -> AbstractCacheService:
        if self._cache_service is None:
            # RedisCache reads the Redis URL from the global settings singleton
            if self._settings.storage.redis_url:
                self._cache_service = RedisCache()
            else:
                self._cache_service = NullCache()
        return self._cache_service

    # ------------------------------------------------------------------
    # Infrastructure: Vector DB
    # ------------------------------------------------------------------

    @property
    def vector_repo(self) -> AbstractVectorRepository:
        if self._vector_repo is None:
            milvus_host = self._settings.storage.milvus_host
            if milvus_host and milvus_host != "disabled":
                self._vector_repo = MilvusVectorRepository()
            else:
                self._vector_repo = InMemoryVectorRepository()
        return self._vector_repo

    # ------------------------------------------------------------------
    # Infrastructure: Full-text / sparse search
    # ------------------------------------------------------------------

    @property
    def search_service(self) -> AbstractSearchService:
        if self._search_service is None:
            self._search_service = create_search_service(self._settings.rag)
        return self._search_service

    # ------------------------------------------------------------------
    # Infrastructure: Object storage (MinIO / S3)
    # ------------------------------------------------------------------

    @property
    def storage_service(self) -> AbstractStorageService:
        if self._storage_service is None:
            s = self._settings.storage
            self._storage_service = MinioStorage(
                endpoint=s.minio_endpoint,
                access_key=s.minio_access_key,
                secret_key=s.minio_secret_key,
                bucket=s.minio_bucket,
                secure=s.minio_secure,
            )
        return self._storage_service

    # ------------------------------------------------------------------
    # Infrastructure: Persistence (PostgreSQL repositories)
    # ------------------------------------------------------------------

    @property
    def doc_repo(self) -> AbstractDocumentRepository:
        if self._doc_repo is None:
            session_factory = self._session_factory
            self._doc_repo = PostgresDocumentRepository(session_factory)
        return self._doc_repo

    @property
    def chunk_repo(self) -> AbstractChunkRepository:
        if self._chunk_repo is None:
            session_factory = self._session_factory
            self._chunk_repo = PostgresChunkRepository(session_factory)
        return self._chunk_repo

    @property
    def user_repo(self) -> AbstractUserRepository:
        if self._user_repo is None:
            session_factory = self._session_factory
            self._user_repo = PostgresUserRepository(session_factory)
        return self._user_repo

    # ------------------------------------------------------------------
    # Infrastructure: Task queue
    # ------------------------------------------------------------------

    @property
    def task_queue(self) -> AbstractTaskQueue:
        if self._task_queue is None:
            if self._settings.storage.redis_url:
                # Share the Redis client from the cache service if available,
                # otherwise create a standalone client.
                from redis.asyncio import Redis as AsyncRedis
                redis_client = AsyncRedis.from_url(
                    self._settings.storage.redis_url
                )
                self._task_queue = RedisTaskQueue(redis_client)
            else:
                self._task_queue = InMemoryTaskQueue()
        return self._task_queue

    # ------------------------------------------------------------------
    # Infrastructure: Knowledge graph
    # ------------------------------------------------------------------

    @property
    def graph_store(self) -> KnowledgeGraph:
        if self._graph_store is None:
            self._graph_store = KnowledgeGraph()
        return self._graph_store

    # ------------------------------------------------------------------
    # Infrastructure: Reranker
    # ------------------------------------------------------------------

    @property
    def reranker(self):
        if self._reranker is None:
            self._reranker = create_reranker(self._settings.reranker)
        return self._reranker

    # ------------------------------------------------------------------
    # Domain services (stateless, pure logic)
    # ------------------------------------------------------------------

    @property
    def intent_classifier(self) -> IntentClassifier:
        if self._intent_classifier is None:
            self._intent_classifier = IntentClassifier()
        return self._intent_classifier

    @property
    def confidence_calculator(self) -> ConfidenceCalculator:
        if self._confidence_calculator is None:
            self._confidence_calculator = ConfidenceCalculator()
        return self._confidence_calculator

    @property
    def flow_controller(self) -> FlowController:
        if self._flow_controller is None:
            self._flow_controller = FlowController()
        return self._flow_controller

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _session_factory(self):
        from app.infrastructure.persistence.models.base import (
            get_session_factory,
        )

        return get_session_factory(self._settings.storage.database_url)

    @property
    def _pipeline_steps(self) -> list:
        """Build the pipeline step chain with all dependencies injected.

        Steps are cached after first construction so that the same
        ``GenerationStep`` instance is shared between the sync and
        streaming use cases.
        """
        if self._cached_pipeline_steps is not None:
            return self._cached_pipeline_steps

        gen_step = GenerationStep(self.llm_service, self._settings, cache=self.cache_service)
        self._generation_step = gen_step

        steps = [
            FlowControlStep(self.flow_controller),
            MemoryStep(self.cache_service),
            RewriteStep(self.llm_service, self._settings),
            IntentStep(self.intent_classifier),
            AgentStep(self.llm_service, get_default_registry(), self._settings),
            RetrievalStep(
                self.embed_service,
                self.vector_repo,
                self.search_service,
                self.cache_service,
                self._settings,
            ),
            RerankStep(self.reranker, self.graph_store, self._settings),
            ContextStep(self._settings),
            gen_step,
            ConfidenceStep(self.confidence_calculator, self.llm_service),
        ]
        self._cached_pipeline_steps = steps
        return steps

    # ------------------------------------------------------------------
    # Use cases
    # ------------------------------------------------------------------

    @property
    def query_use_case(self) -> QueryUseCase:
        if self._query_use_case is None:
            orchestrator = RAGPipelineOrchestrator(self._pipeline_steps)
            self._query_use_case = QueryUseCase(
                orchestrator, self.cache_service, self.doc_repo, self._settings
            )
        return self._query_use_case

    @property
    def stream_use_case(self) -> StreamingQueryUseCase:
        if self._stream_use_case is None:
            # Force pipeline steps to be built first so _generation_step is set
            _ = self._pipeline_steps
            orchestrator = RAGPipelineOrchestrator(self._pipeline_steps)
            self._stream_use_case = StreamingQueryUseCase(
                orchestrator=orchestrator,
                generation_step=self._generation_step,
                cache=self.cache_service,
                document_repo=self.doc_repo,
                settings=self._settings,
            )
        return self._stream_use_case

    @property
    def doc_use_case(self) -> DocumentUseCase:
        if self._doc_use_case is None:
            self._doc_use_case = DocumentUseCase(
                document_repo=self.doc_repo,
                chunk_repo=self.chunk_repo,
                vector_repo=self.vector_repo,
                search_service=self.search_service,
                storage=self.storage_service,
                embed_service=self.embed_service,
                cache=self.cache_service,
                task_queue=self.task_queue,
                settings=self._settings,
            )
        return self._doc_use_case

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def init_async(self) -> None:
        """Initialise async-capable services (connect to external backends).

        Call once from the FastAPI lifespan startup handler.
        """
        await self.cache_service.connect()
        await self.vector_repo.connect()

    async def close_async(self) -> None:
        """Gracefully shut down all connections.

        Call once from the FastAPI lifespan shutdown handler.
        """
        if self._http_client is not None:
            await self._http_client.aclose()
        await self.llm_service.close()
        await self.embed_service.close()
        await self.cache_service.close()
        await self.vector_repo.close()
