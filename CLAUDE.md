# CLAUDE.md - Enterprise RAG System

## Common Commands

### Docker (primary workflow)
```bash
docker compose up -d                          # Start all services
docker compose down                           # Stop all services
docker compose ps                             # Check service status
docker compose logs -f backend                # Follow backend logs
docker compose restart backend                # Restart backend
docker compose build --no-cache backend       # Rebuild backend image
docker compose exec postgres psql -U raguser -d ragdb  # PostgreSQL shell
docker compose exec redis redis-cli           # Redis shell
```

### Backend testing
```bash
DATABASE_URL="sqlite+aiosqlite:///test.db" PYTHONPATH=backend pytest tests/ -v
pytest tests/ -v --cov=backend/app --cov-report=html
```

### Frontend testing
```bash
cd frontend && npm run dev      # Dev server on :5173 (proxies /api to :8000)
cd frontend && npm run build    # Production build
cd frontend && npm run test     # Run vitest tests
```

### Database migrations
```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

### Local development
```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL="sqlite+aiosqlite:///dev.db"
export APP_ENV="development"
export SILICONFLOW_API_KEY="sk-xxx"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Architecture: Clean Architecture (Ports & Adapters)

```
api/          → Web adapter: FastAPI routes, middleware, auth deps, error handler
application/  → Use cases: pipeline orchestration, shared steps for sync+stream
domain/       → Pure business logic: entities, services, port protocols (NO I/O)
infrastructure/ → Adapters: PostgreSQL, Redis, Milvus, MinIO, LLM, BM25, chunking
shared/       → Cross-cutting: logging, tracing, pagination, constants, helpers
di/           → Dependency injection container
config/       → Pydantic Settings (all env vars)
```

**Dependency rule**: domain ← application ← infrastructure/api. Domain has zero external imports.

### Layer breakdown

| Layer | Directory | Responsibility |
|-------|-----------|---------------|
| domain/entities | `domain/entities/` | Frozen dataclasses: Document, Chunk, QueryResponse, User, Session |
| domain/services | `domain/services/` | Pure logic: IntentClassifier, ConfidenceCalculator, FlowController |
| domain/ports | `domain/ports/` | Protocol interfaces: AbstractLLMService, AbstractVectorRepository, etc. |
| application/pipeline | `application/pipeline/` | PipelineStep protocol, PipelineContext, Orchestrator |
| application/pipeline/steps | `application/pipeline/steps/` | 10 steps: flow_control, memory, rewrite, intent, agent, retrieval, rerank, context, generation, confidence |
| application/use_cases | `application/use_cases/` | QueryUseCase, StreamingQueryUseCase, DocumentUseCase |
| infrastructure/persistence | `infrastructure/persistence/` | SQLAlchemy models + Postgres repositories |
| infrastructure/cache | `infrastructure/cache/` | Redis 5-layer cache + SingleFlight dedup |
| infrastructure/llm | `infrastructure/llm/` | Multi-provider LLM + embedding clients |
| infrastructure/vector | `infrastructure/vector/` | Milvus + InMemory vector repositories |
| infrastructure/search | `infrastructure/search/` | BM25 (memory + Elasticsearch) |
| infrastructure/chunking | `infrastructure/chunking/` | Semantic, sliding window, fixed size strategies |
| infrastructure/document | `infrastructure/document/` | PDF/DOCX/PPTX/XLSX/HTML/TXT parsers + TextCleaner |
| infrastructure/reranker | `infrastructure/reranker/` | Simple keyword + Cross-encoder BGE rerankers |
| infrastructure/graph | `infrastructure/graph/` | Knowledge graph extraction + BFS multi-hop query |
| infrastructure/task_queue | `infrastructure/task_queue/` | Redis-backed persistent task queue with DLQ |
| infrastructure/storage | `infrastructure/storage/` | MinIO object storage |

### RAG Pipeline Flow (10 shared steps)

1. **FlowControlStep** - Refuse/clarify pre-check
2. **MemoryStep** - Load short-term + long-term conversation memory
3. **RewriteStep** - LLM query rewrite resolving anaphora
4. **IntentStep** - Rule-based C0/C1/C2 complexity + semantic type classification
5. **AgentStep** - LLM agent decision: retrieval/tool/direct/clarify/refuse/multi_step
6. **RetrievalStep** - Embed → dense (Milvus) + sparse (BM25) → RRF fusion → permission filter
7. **RerankStep** - Cross-encoder/simple rerank + GraphRAG context injection
8. **ContextStep** - Build context string from top docs with source numbering
9. **GenerationStep** - LLM generation with C0/C1/C2-tiered timeout degradation
10. **ConfidenceStep** - Weighted confidence: 0.5*rerank + 0.3*embed + 0.2*llm_self_score

### Dependency Injection

`di/container.py` → `DIContainer` wires all ports to adapters with lazy properties.
- Created in `main.py` lifespan, stored on `app.state.container`
- Routes access via `Depends(get_container)`
- Tests inject mock implementations directly (no monkey-patching)

### Auth Model

Dual auth in `api/deps/auth.py`:
- JWT (HS256, jti-based blacklisting in Redis) - web login
- API Key (`rag_` prefix, SHA-256 hashed) - programmatic access
- RBAC: user/admin/super_admin via `require_role()` dependency
- Rate limiting: Redis sliding window per user per minute

### Error Handling

Exception hierarchy in `domain/exceptions.py`:
- `RagError` base → `DomainError` (400) | `InfrastructureError` (502) | `ApiError`
- Global handler in `api/error_handler.py` maps exceptions to JSON responses
- All errors carry `code`, `message`, `status_code`, optional `details`

### Key files to update together

- New pipeline step: `application/pipeline/steps/<step>.py` + register in `di/container.py`
- New config option: `config/settings.py` + `docker-compose.yml` env section
- New API endpoint: `api/routes/<module>.py` + `application/use_cases/<use_case>.py`
- DB schema change: Alembic migration + `infrastructure/persistence/models/<model>.py` + repository
