"""
RAG System v3 -- FastAPI application entry point with Dependency Injection.

Architecture
------------
- **DI Container** (``app.di.container.DIContainer``) wires all ports to
  concrete adapters.  No module-level singletons.
- **Routes** live under ``app.api.routes.*``.  Each controller is a thin
  HTTP adapter that delegates to use cases from the container.
- **Middleware** (trace, CORS) and a global exception handler that maps
  ``RagError`` subclasses to standardised JSON error responses.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import (
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    TraceMiddleware,
    TracingMiddleware,
)
from app.api.responses import ok
from app.api.routes import (
    admin_router,
    auth_router,
    chat_router,
    documents_router,
    feedback_router,
    metrics_router,
    tags_router,
    ws_router,
)
from app.config.settings import settings, validate_production_settings
from app.di.container import DIContainer
# Import all models so that ``Base.metadata`` discovers every table
# before ``init_database()`` is called in the lifespan.
import app.infrastructure.persistence.models  # NOQA: F401

from app.infrastructure.persistence.models.base import init_database
from app.domain.ports.task_queue_port import TaskItem
from app.shared.logging import logger, setup_logger


# ---------------------------------------------------------------------------
# Lifespan -- startup / shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialise and tear down the DI container."""
    # --- Startup ---
    setup_logger(settings.LOG_LEVEL, settings.APP_ENV)

    # Setup OpenTelemetry tracing (optional, based on OTLP_ENDPOINT env)
    otlp_endpoint = getattr(settings, "OTLP_ENDPOINT", "") or ""
    if otlp_endpoint:
        from app.infrastructure.observability.tracing import (
            instrument_app,
            setup_tracing,
        )

        setup_tracing("rag-system", otlp_endpoint)
        instrument_app(app)

    logger.info("=" * 60)
    logger.info("RAG System v3 starting ... ENV={}", settings.APP_ENV)

    validate_production_settings(settings)

    # Auto-create database tables (no-op if already exist)
    try:
        await init_database(settings.DATABASE_URL)
        logger.info("Database tables verified / created")
    except Exception as e:
        logger.error("Database initialisation failed: {}", e)

    # Ensure default admin user exists on first startup
    try:
        from app.infrastructure.persistence.models.user import User as UserModel
        from app.api.deps.auth import get_password_hash
        from app.infrastructure.persistence.models.base import get_session_factory
        from sqlalchemy import select
        import uuid

        session_factory = get_session_factory(settings.DATABASE_URL)
        async with session_factory() as session:
            result = await session.execute(
                select(UserModel).where(UserModel.username == "admin")
            )
            admin = result.scalar_one_or_none()
            if admin is None:
                admin_user = UserModel(
                    id=str(uuid.uuid4()),
                    username="admin",
                    password_hash=get_password_hash(settings.DEFAULT_ADMIN_PASSWORD),
                    role="super_admin",
                    tenant_id="default",
                    is_active=True,
                )
                session.add(admin_user)
                await session.commit()
                logger.info("Default admin user created (username=admin)")
            else:
                logger.info("Admin user already exists, skipping creation")
    except Exception as e:
        logger.warning("Failed to ensure default admin user: {}", e)

    container = DIContainer(settings)
    try:
        await container.init_async()
        logger.info("DI container initialised -- all services connected")
    except Exception as e:
        logger.error("Container initialisation failed: {}", e)

    app.state.container = container

    # Start background document processing worker
    import asyncio as _asyncio
    worker_count = settings.TASK_QUEUE_WORKERS
    worker_tasks = []
    worker_stop = _asyncio.Event()

    async def _doc_worker(worker_id: int):
        logger.info("Document worker {} started", worker_id)
        while not worker_stop.is_set():
            try:
                task = await container.task_queue.dequeue(timeout=5.0)
                if task is None:
                    continue
                logger.info("Worker {} processing doc_id={}", worker_id, task.doc_id)
                await container.doc_use_case.process_document(task.doc_id)
            except _asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker {} error: {}", worker_id, e)
                await _asyncio.sleep(1)
        logger.info("Document worker {} stopped", worker_id)

    for i in range(worker_count):
        t = _asyncio.create_task(_doc_worker(i))
        worker_tasks.append(t)

    # Scan for existing pending documents that need processing
    try:
        pending_docs = await container.doc_repo.list_all("default", limit=100)
        for doc in pending_docs:
            if str(doc.status) == "pending":
                logger.info("Re-queuing pending document: doc_id={} name={}", doc.id, doc.filename)
                task_item = TaskItem(doc_id=doc.id, file_ext=doc.file_type, content=b"")
                await container.task_queue.enqueue(task_item)
    except Exception as e:
        logger.warning("Failed to scan pending documents: {}", e)

    logger.info("RAG System v3 started successfully ({} doc workers)", worker_count)

    yield

    # --- Shutdown ---
    worker_stop.set()
    for t in worker_tasks:
        t.cancel()
    # Wait for workers to finish
    await _asyncio.gather(*worker_tasks, return_exceptions=True)
    logger.info("All document workers stopped")

    # --- Shutdown ---
    try:
        await container.close_async()
        logger.info("DI container shut down -- all connections closed")
    except Exception as e:
        logger.warning("Container shutdown error: {}", e)
    logger.info("RAG System v3 shut down")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Enterprise RAG System",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# -- Middleware stack (outermost first) --

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TracingMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(TraceMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Global exception handler --

from app.api.error_handler import global_error_handler

app.add_exception_handler(Exception, global_error_handler)

# -- Routes -- all under /api/v1 prefix --

API_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(chat_router, prefix=API_PREFIX)
app.include_router(documents_router, prefix=API_PREFIX)
app.include_router(admin_router, prefix=API_PREFIX)
app.include_router(feedback_router, prefix=API_PREFIX)
app.include_router(metrics_router, prefix=API_PREFIX)
app.include_router(tags_router, prefix=API_PREFIX)
app.include_router(ws_router, prefix=API_PREFIX)


# ---------------------------------------------------------------------------
# System endpoints (no prefix)
# ---------------------------------------------------------------------------




@app.get("/api/v1/health")
async def api_health():
    """Health check under the API prefix for nginx proxy compatibility."""
    return await health()


@app.get("/health")
async def health():
    """Combined health check -- verifies connectivity to all backends."""
    container: DIContainer | None = getattr(app.state, "container", None)

    checks = {
        "postgres": False,
        "redis": False,
        "milvus": False,
        "minio": False,
    }

    if container:
        try:
            _ = await container.doc_repo.count_by_tenant("default")
            checks["postgres"] = True
        except Exception:
            pass

        try:
            _ = await container.cache_service.get("health_check")
            checks["redis"] = True
        except Exception:
            pass

        try:
            _ = await container.vector_repo.get_collection_stats()
            checks["milvus"] = True
        except Exception:
            pass

        try:
            checks["minio"] = await container.storage_service.is_connected()
        except Exception:
            pass

    all_ok = all(checks.values())

    return ok(
        {
            "status": "ok" if all_ok else "degraded",
            "version": "3.0.0",
            "env": settings.APP_ENV,
            "checks": checks,
        }
    )


@app.get("/")
async def root():
    """Root endpoint -- API information."""
    return ok(
        {
            "message": "Enterprise RAG System is running",
            "version": "3.0.0",
            "docs": "/docs",
        }
    )
