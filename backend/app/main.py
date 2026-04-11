"""RAG System — FastAPI entry point (enterprise architecture)."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import settings, validate_production_settings
from app.utils.logger import logger
from app.utils.trace import generate_trace_id, set_trace_id
from app.api.deps import ok, ErrorCode
from app.repository.postgres import init_db, engine
from app.repository.redis_cache import cache
from app.repository.vector_store import milvus_db
from app.api import chat, upload, feedback, metrics, auth, audit
from app.api.admin import router as admin_router
from app.api.tags import router as tags_router
from app.api.ws import router as ws_router


async def _bm25_rebuild_task() -> None:
    """后台分批拉取 Chunk 文本并一次性重建 BM25，避免阻塞进程就绪。"""
    try:
        from sqlalchemy import select

        from app.core.retriever import retriever
        from app.repository.postgres import AsyncSessionLocal, Chunk

        batch = settings.BM25_REBUILD_BATCH_FETCH
        all_texts: list[str] = []
        async with AsyncSessionLocal() as db:
            offset = 0
            while True:
                result = await db.execute(select(Chunk.content).limit(batch).offset(offset))
                rows = result.all()
                if not rows:
                    break
                all_texts.extend(row[0] for row in rows if row[0])
                offset += batch
        if all_texts:
            retriever.replace_corpus(all_texts)
            logger.info(f"BM25 index rebuilt with {len(all_texts)} chunks (background)")
        else:
            logger.info("BM25: no chunks found, skipping")
    except Exception as e:
        logger.warning(f"BM25 index rebuild failed (non-fatal): {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"RAG System starting... ENV={settings.APP_ENV}")
    validate_production_settings(settings)
    try:
        await init_db()
        logger.info("PostgreSQL initialized")
    except Exception as e:
        logger.error(f"PostgreSQL init failed: {e}")
    try:
        await cache.connect()
        logger.info("Redis connected")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
    try:
        milvus_db.connect()
        logger.info("Milvus connected")
    except Exception as e:
        logger.error(f"Milvus connection failed: {e}")
    if settings.BM25_REBUILD_ON_STARTUP:
        if settings.BM25_REBUILD_ASYNC:
            asyncio.create_task(_bm25_rebuild_task())
            logger.info("BM25 rebuild scheduled (non-blocking)")
        else:
            await _bm25_rebuild_task()
    else:
        logger.info("BM25 startup rebuild skipped (BM25_REBUILD_ON_STARTUP=false)")
    logger.info("System startup complete")
    yield
    # 优雅关闭资源
    from app.core.generator import llm_client, embed_client
    try:
        await llm_client.close()
        await embed_client.close()
    except Exception as e:
        logger.warning(f"HTTP client cleanup failed: {e}")
    await engine.dispose()
    logger.info("RAG System shut down")


app = FastAPI(
    title="RAG Knowledge System",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """Inject trace_id into every request and propagate via context."""
    trace_id = request.headers.get("X-Trace-Id") or generate_trace_id()
    set_trace_id(trace_id)
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback as _tb
    trace_id = getattr(request.state, "trace_id", "")
    logger.error(f"[{trace_id}] Unhandled exception [{request.method} {request.url}]: {exc}")
    logger.error(_tb.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "code": ErrorCode.SYSTEM_ERROR,
            "message": "Internal server error, please try again later",
            "data": None,
            "trace_id": trace_id,
        },
    )


app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(feedback.router)
app.include_router(metrics.router)
app.include_router(audit.router)
app.include_router(admin_router)
app.include_router(tags_router)
app.include_router(ws_router)


@app.get("/health", tags=["System"])
async def health():
    # PostgreSQL 连通性检查
    pg_ok = False
    try:
        from app.repository.postgres import AsyncSessionLocal
        from sqlalchemy import text
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            pg_ok = True
    except Exception:
        pass

    # Redis 连通性检查
    redis_ok = False
    try:
        if cache.client:
            await cache.client.ping()
            redis_ok = True
    except Exception:
        pass

    milvus_ok = milvus_db.is_connected
    all_ok = pg_ok and redis_ok and milvus_ok

    return ok({
        "status": "ok" if all_ok else "degraded",
        "version": "2.0.0",
        "env": settings.APP_ENV,
        "checks": {
            "postgres": pg_ok,
            "milvus": milvus_ok,
            "redis": redis_ok,
        },
    })


@app.get("/", tags=["System"])
async def root():
    return ok({"message": "RAG Knowledge System is running", "docs": "/docs"})
