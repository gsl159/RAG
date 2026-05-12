# Enterprise RAG System v3.0 — 完整技术文档

> **版本**: 3.0.0 | **架构**: Clean Architecture (Ports & Adapters)  
> **Python**: 3.11+ | **部署**: Docker Compose | **文件数**: 135

---

## 目录

1. 系统架构总览
2. Domain 层（纯业务逻辑）
3. Application 层（用例编排）
4. Infrastructure 层（基础设施适配器）
5. API 层（Web适配器）
6. RAG Pipeline 完整流程
7. 文档处理 Pipeline
8. 缓存体系
9. 安全体系
10. 部署架构
11. API 参考

---

## 1. 系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                     API Layer (FastAPI)                  │
│   routes/  middleware  deps/  error_handler              │
├─────────────────────────────────────────────────────────┤
│                 Application Layer                        │
│   pipeline/steps/   pipeline/orchestrator   use_cases/   │
├─────────────────────────────────────────────────────────┤
│                    Domain Layer                          │
│   entities/   services/   ports/   exceptions.py         │
├─────────────────────────────────────────────────────────┤
│                Infrastructure Layer                      │
│   persistence/ cache/ vector/ llm/ search/ storage/      │
│   chunking/ document/ reranker/ graph/ task_queue/       │
│   observability/ performance/                            │
├─────────────────────────────────────────────────────────┤
│              Cross-Cutting                               │
│   di/container.py   config/settings.py   shared/          │
└─────────────────────────────────────────────────────────┘
```

**依赖方向**: API → Application → Domain ← Infrastructure  
**核心原则**: Domain 层零 I/O 依赖，所有外部交互通过 Port (Protocol) 抽象

### 模块统计

| 层 | 文件数 | 职责 |
|---|--------|------|
| `domain/entities/` | 6 | 不可变领域对象 (frozen dataclass) |
| `domain/services/` | 11 | 纯业务逻辑 (零I/O) |
| `domain/ports/` | 8 | 抽象接口协议 (Protocol) |
| `application/pipeline/` | 12 | 10步骤流水线 + 编排器 |
| `application/use_cases/` | 4 | 查询/流式/文档用例 |
| `infrastructure/` | 67 | 外部系统适配器 |
| `api/` | 17 | HTTP路由 + 中间件 + 鉴权 |
| `shared/` + `config/` + `di/` | 10 | 横切关注点 |
| **总计** | **135** | |

---

## 2. Domain 层 — 纯业务逻辑

### 2.1 实体 (entities/)

所有实体为 **frozen dataclass**，不可变，无 ORM 依赖。

**Document（文档）**
```
字段: id, filename, file_type, file_size, status, tenant_id, dept_id,
      chunk_count, parse_score, doc_version, created_at, updated_at, error_msg
状态机: PENDING → PROCESSING → DONE / FAILED
```

**Chunk（分块）**
```
字段: id, doc_id, content, chunk_idx, char_count, parent_id, heading,
      chunk_type, page, section, meta_info
类型枚举: TEXT | HEADING | CODE | TABLE | LIST | IMAGE
```

**QueryResponse（查询响应）**
```
字段: answer, sources[], context, rewritten_query, intent,
      intent_v2, confidence, cache_hit, latency_ms, retrieval_ms,
      llm_ms, degrade_level, degrade_reason, suggestions[]
```

**User（用户）**
```
字段: id, username, role(USER/ADMIN/SUPER_ADMIN), tenant_id, dept_id,
      is_active, created_at
```

**其他实体**: IntentResult, SourceRef, Session, Message, Evaluation, Feedback, Benchmark

### 2.2 领域服务 (services/)

**IntentClassifier（意图分类器）**
- 策略: 纯规则匹配，零 LLM 调用
- 复杂度: C0(简单,<15字符) / C1(中等,<40字符) / C2(复杂)
- 语义类型: FACT | COMPARISON | REASONING | SUMMARY | DEFINITION | HOW_TO
- 路由映射: C0→direct_answer, C1→rag, C2→multi_step/agentic_rag
- 结构推断: procedural | api_spec | table | code | narrative

**ConfidenceCalculator（置信度）**
- 公式: confidence = 0.5×rerank_avg + 0.3×embedding_sim + 0.2×llm_self_score
- 权重可配置: CONF_WEIGHT_RERANK/EMBED/LLM
- 归一化: rerank>1.0时÷10, 否则×20, 压缩到[0,1]

**FlowController（流量控制）**
- 前置拒绝: 赌博/色情/代码生成/黑客/PII/违法
- 模糊检测: 过短/纯代词/过于宽泛
- 后置增强: 低置信度追问 + 建议生成

**ContextualCompressor（上下文压缩）**
- LLM压缩检索文档，保留查询相关信息
- 输入截断8000字符，输出限制target_tokens(默认2000)

**QualityTracker（质量追踪）**
- 每查询: 检索精度/置信度/延迟分解/用户反馈
- 低质量聚类: 阈值0.3, 最少5样本
- 容量: 10000条记录

**ABTestingFramework（A/B测试）**
- 流量分割: 默认50:50 control:treatment
- 显著性: Z-test, 95%置信度
- 自动提升: 胜出策略自动应用

**EvalRunner（基准评估）**
- 5个默认用例, 关键词匹配+置信度门控
- 回归检测: pass_rate下降>10%触发告警
- 基线持久化: eval_baseline.json

**AdaptiveOptimizer（自适应优化）**
- 目标参数: CONF_WEIGHT_RERANK, TOP_K, CHUNK_SIZE, RERANKER_MODE
- 历史窗口: 100条趋势数据

**PromptTemplate（提示词模板）**
- 6个版本化模板: RAG_GENERATION, QUERY_REWRITE, AGENT_DECISION, SELF_SCORE, HYDE, GRAPH_EXTRACT
- 版本号变更自动触发缓存失效

### 2.3 异常层次 (exceptions.py)

```
RagError (Base)
├── DomainError (400)
│   ├── InvalidQueryError
│   └── ContentQualityError
├── InfrastructureError (502)
│   ├── LLMServiceError
│   ├── EmbeddingServiceError
│   ├── VectorSearchError
│   ├── CacheError
│   ├── DatabaseError
│   └── StorageError
└── ApiError
    ├── AuthenticationError (401)
    ├── AuthorizationError (403)
    ├── RateLimitError (429)
    ├── ValidationError (422)
    ├── NotFoundError (404)
    └── ConflictError (409)
```

### 2.4 端口接口 (ports/)

| 端口 | 核心方法 |
|------|---------|
| AbstractLLMService | chat(), chat_json(), stream(), close() |
| AbstractEmbeddingService | embed_one(), embed_batch(), close() |
| AbstractDocumentRepository | find_by_id(), save(), update_status(), delete(), list_all() |
| AbstractChunkRepository | save_batch(), find_by_doc_id(), delete_by_doc_id() |
| AbstractUserRepository | find_by_username(), save(), list_all() |
| AbstractVectorRepository | search(), insert(), delete_by_doc_id() |
| AbstractCacheService | 5层缓存 + Session + Token黑名单 + SingleFlight |
| AbstractSearchService | search(), add_texts(), remove_texts() |
| AbstractStorageService | upload(), download(), delete(), is_connected() |
| AbstractTaskQueue | enqueue(), dequeue(), DLQ支持 |

---

## 3. Application 层 — 用例编排

### 3.1 Pipeline 核心概念

- **PipelineStep**: Protocol, `async execute(ctx) -> PipelineContext`
- **PipelineContext**: 可变状态袋，贯穿全部10个步骤
- **RAGPipelineOrchestrator**: 顺序执行，支持 early_exit 短路

### 3.2 10个 Pipeline 步骤

```
Step 1: FlowControlStep
  策略: FlowController.pre_check()
  输出: REFUSE→early_exit / CLARIFY→early_exit / PASS→继续

Step 2: MemoryStep
  策略: 短期记忆(Redis List, 20条) + 长期记忆(Redis Hash, LLM压缩摘要)
  话题切换: 嵌入余弦相似度 < 0.35 检测

Step 3: RewriteStep
  策略: LLM改写，解析多轮指代，最多6轮历史
  超时: 5s, 失败回退原始查询

Step 4: IntentStep
  策略: IntentClassifier.classify_intent() 纯规则匹配

Step 5: AgentStep
  策略: 快速规则预分类(问候/数学/日期/拒绝) → LLM决策
  路由: retrieval→继续 / tool_call→执行→返回 / direct_answer→生成→返回
  护栏: 知识查询强制路由到retrieval

Step 6: RetrievalStep
  策略:
    1. L3缓存检查
    2. Embedding (BGE-m3 1024d)
    3. Dense检索 (Milvus HNSW, top_k=10)
    4. Sparse检索 (BM25, top_k=10)
    5. RRF融合 (alpha=0.7, chunk_id作为合并键)
    6. 权限过滤 (scope_doc_ids)
  优化: HyDE / 多查询分解 / Self-RAG循环

Step 7: RerankStep
  策略:
    1. Cross-Encoder或SimpleReranker重排序
    2. 垃圾过滤 (重复字符>40%, 数字比>50%, 8+相同字符)
    3. 父扩展 (替换为父块文本, 最多2个父块)
    4. GraphRAG上下文注入

Step 8: ContextStep
  策略: 编号来源[1][2]..., 截断到CONTEXT_MAX_CHARS(3000)

Step 9: GenerationStep
  策略:
    1. 相关性门控 (max rerank_score<0.02→拒绝)
    2. 系统提示词 + 上下文 + 查询
    3. C2(3s)→C1(1.5s)→C0(fallback) 分级超时降级
    4. 输出消毒 (重复/循环检测)
  优化: Token预算 + 语义缓存

Step 10: ConfidenceStep
  策略:
    1. LLM自评分 (并行, 最佳努力, 2s超时)
    2. ConfidenceCalculator.calculate()
```

### 3.3 用例 (use_cases/)

**QueryUseCase** — 同步RAG查询
```
验证 → L4缓存检查 → PipelineContext → 运行Pipeline → 来源文件名丰富 → 会话持久化 → QueryResponse
```

**StreamingQueryUseCase** — SSE流式查询
```
同QueryUseCase, GenerationStep使用execute_stream()逐token输出
SSE格式: data: {token} → data: [SOURCES] → data: [DONE]
```

**DocumentUseCase** — 文档生命周期
```
upload_document: 扩展名验证 → SHA256去重锁 → MinIO存储 → PG写入 → 入队
process_document: 下载 → 旧chunk清理 → 解析 → 清洗 → 分块 → 嵌入 → Milvus → BM25 → 质量评分 → DONE
delete_document: Milvus → BM25 → PG chunks → MinIO → PG document (级联删除)
list_documents: keyset游标分页, 租户隔离
```

---

## 4. Infrastructure 层 — 基础设施适配器

### 4.1 持久化 (persistence/)

**PostgreSQL (SQLAlchemy Async)**
- 12张表: users, documents, chunks, query_logs, evaluations, feedback, benchmarks, audit_logs, api_keys, doc_permissions, tags, doc_tags
- SQLite: NullPool + check_same_thread=False
- PostgreSQL: pool_size=20, max_overflow=40, pool_pre_ping=True
- 启动重试: 指数退避, 最多3次, 2^attempt秒间隔
- 时区: 所有datetime使用.replace(tzinfo=None)兼容TIMESTAMP WITHOUT TIME ZONE

### 4.2 缓存 (cache/) — Redis 5层

```
L1 查询缓存 (30min)    → 完整查询结果, sha256(query+answer)
L2 嵌入缓存 (24h)      → 文本嵌入向量, sha256(text)
L3 检索缓存 (1h)       → 检索结果, 嵌入哈希分桶(8维×0.25量化)
L3 RAG缓存 (1h)        → 完整pipeline输出
L4 答案缓存 (15min)     → 最终答案, sha256(query+context)
```

**缓存策略**:
- 版本控制: 所有key包含doc_version+embed_version, 文档变更自动失效
- SingleFlight: 并发相同key去重, 共享Future, 2s超时
- TTL抖动: 查询/检索层随机±10%TTL, 防缓存雪崩
- 嵌入哈希分桶: 相似向量命中同一桶, 提高缓存命中率

**电路断路器**:
- 3次连续失败→断路30秒→半开探测→成功恢复
- 断路期间静默返回None (fail-open)
- CRITICAL级别日志告警

### 4.3 向量存储 (vector/)

**MilvusVectorRepository (生产)**
- 集合: rag_docs_v2 (11字段 + FLOAT_VECTOR 1024d)
- 索引: HNSW, COSINE, M=16, efConstruction=256
- 连接: 自动重连, 信号量限流(pool_size=10)
- 安全: UTF-8边界安全截断VARCHAR(8192), DocID正则^[a-zA-Z0-9\-_]+$
- 异步: asyncio.to_thread包装阻塞操作

**InMemoryVectorRepository (测试)**
- 纯Python余弦相似度, 零外部依赖

### 4.4 LLM (llm/)

**多提供者故障转移链**:
```
SiliconFlow(Qwen2.5-7B, 主) → OpenAI(gpt-4o-mini, 备1) → Ollama(qwen2.5:7b, 备2)
```

- 自动降级: 5xx/超时/连接错误 → 3次指数退避重试 → 下一提供者
- 模型路由: C0/C1/C2可配置不同模型
- Embedding: BGE-m3 1024d, batch_size=32, 自动分块
- 流式: 逐token yield, 故障切换重新流式

**提供者适配**:
- SiliconFlowProvider: response_format JSON, 标准重试
- OpenAIProvider: OpenAI兼容API, 标准重试
- OllamaProvider: JSON注入提示词(不支持response_format), 重试2次

### 4.5 搜索 (search/)

**MemoryBM25Search (默认)**
- rank_bm25.BM25Okapi
- jieba分词(中文) + 正则回退(英文)
- threading.Lock线程安全

**ElasticsearchBM25Search (可选)**
- ik_max_word(索引) / ik_smart(搜索)
- bulk API + refresh="wait_for"

### 4.6 文档解析器 (document/parsers/)

| 格式 | 库 | 处理策略 |
|------|-----|---------|
| PDF | pymupdf(fitz) | 逐页文本, OCR回退(eng+chi_sim), 最大5M字符 |
| DOCX | python-docx | 段落+表格, 保留标题层级 |
| PPTX | python-pptx | 幻灯片文本+表格+注释, ===第N页===分隔 |
| XLSX | openpyxl | 只读模式, Markdown表格(|col1|col2|) |
| CSV | csv模块 | 编码检测, Markdown表格输出 |
| HTML | HTMLParser | 跳过script/style/nav/footer/header |
| TXT/MD | 直接读取 | 编码检测(UTF-8→GBK→latin-1) |

### 4.7 文本清洗 (TextCleaner)
- Unicode NFC标准化
- 空白规范化: 合并多空格/换行
- 控制字符移除: 保留CJK/拉丁语扩展/数学符号/全角形式
- 白名单字符模式

### 4.8 分块策略 (chunking/strategies/)

**SemanticChunkingStrategy（语义分块，主力）**
- 结构检测: Markdown标题(#), 中文章节(第X章/一、/二、), 代码块(```), API端点(GET/POST), 表格(|...|), 过程步骤(数字列表)
- 递归分裂: 文档→章节(按标题)→段落(按空行)→句子组
- 父子引用: 子块parent_id跟踪, 支持父扩展检索
- 专用分割器: _split_procedure(按步骤编号), _split_api_endpoints(按HTTP方法), _split_table(保留行), _split_code(按函数边界)
- 语义边界检测: 嵌入余弦相似度下降>0.5标记边界
- 适用格式: pdf, docx, pptx, html, txt, md

**SlidingWindowStrategy（滑动窗口，回退）**
- chunk_size=500, chunk_overlap=100
- 句子边界断开(。！？!?.\n)
- 默认回退策略

**FixedSizeStrategy（固定大小）**
- 精确大小, 无重叠
- 适用格式: xlsx, csv

### 4.9 重排序器 (reranker/)

**SimpleReranker（默认）**
- 关键词覆盖率+RRF分数混合, 权重RRF=0.6/Keyword=0.4
- jieba分词(中文)+正则回退
- 零API调用, <1ms延迟

**CrossEncoderReranker（可选）**
- BGE-reranker-v2-m3 via SiliconFlow API
- batch_size=20, 512字符截断
- 失败自动降级到SimpleReranker
- 共享httpx.AsyncClient

### 4.10 知识图谱 (graph/)

**GraphExtractor（实体抽取）**
- LLM JSON结构输出(entity: name/type/description, relation: source/target/type/weight)
- 超时30s, 输入截断1500字符

**KnowledgeGraph（图存储）**
- 邻接表双向图, threading.Lock线程安全
- BFS多跳查询: max_depth=3, max_nodes=50
- 子图上下文构建: entity_name邻居文本
- jieba查询实体匹配
- Redis序列化持久化(7天TTL)

### 4.11 任务队列 (task_queue/)

**RedisTaskQueue（生产）**
- LPUSH/BRPOP, JSON序列化
- DLQ死信队列: 重试3次后移入
- 处理状态追踪: Redis Hash
- 重放: retry_dlq()

**InMemoryTaskQueue（开发）**
- asyncio.Queue(maxsize=200)
- 内存DLQ, 重启丢失

**文档处理Worker**
- 3个并发协程/进程, 优雅关闭
- 启动扫描: PENDING文档重新入队
- WebSocket进度广播: processing→done/failed

### 4.12 对象存储 (storage/)

**MinioStorage**
- MinIO/S3兼容API, 自动创建bucket
- 指数退避重试(ServerError/ConnectionError/TimeoutError)
- asyncio.to_thread异步包装
- is_connected()健康检查

### 4.13 可观测性 (observability/)

**PrometheusMetrics**
- 计数器: 请求总数, 错误数, LLM token使用量
- 仪表: 每层缓存命中率, 队列深度, 运行时间
- 摘要: P50/P95/P99延迟
- 导出: /api/metrics/prometheus (Prometheus text format)

---

## 5. API 层 — Web适配器

### 5.1 路由表

| 前缀 | 端点 | 方法 | 鉴权 |
|------|------|------|------|
| /api/v1/auth | /login, /logout, /me, /refresh | POST/GET | -/JWT |
| /api/v1/chat | /, /stream, /history, /share/{id}, /suggestions, /confirm | GET/POST | JWT |
| /api/v1/documents | /, /upload, /batch, /import-url, /{id}, /{id}/chunks, /{id}/retry, /{id}/permissions | GET/POST/DELETE | JWT |
| /api/v1/admin | /users, /users/{id}, /change-password, /api-keys | GET/POST/PUT/DELETE | Admin |
| /api/v1/feedback | /, /stats | POST/GET | JWT |
| /api/v1/metrics | /overview, /rag, /cache, /docs, /qps, /llm-status, /prometheus, /health | GET | JWT |
| /api/v1/tags | /, /{id}, /bind, /unbind, /doc/{id} | GET/POST/DELETE | JWT |
| /api/v1/ws | /progress | WS | JWT |
| /health, /api/v1/health | - | GET | - |

### 5.2 中间件

| 中间件 | 功能 |
|--------|------|
| SecurityHeadersMiddleware | CSP, X-Frame-Options, X-XSS-Protection, Referrer-Policy |
| RequestSizeLimitMiddleware | 请求体>10MB返回413 |
| TraceMiddleware | X-Trace-Id注入, 结构化请求日志 |
| CORSMiddleware | 可配置来源, 凭证支持 |

### 5.3 鉴权 (deps/auth.py)

- JWT: HS256, jti黑名单(Redis), 24h过期
- API Key: rag_前缀, SHA-256哈希存储
- RBAC: user/admin/super_admin, require_role()工厂
- 速率限制: Redis滑动窗口60次/分钟, IP登录10次/分钟
- Fail-open: Redis不可用时允许通过, 3次失败后CRITICAL告警

### 5.4 统一响应

```json
// 成功: {"code": 0, "message": "success", "data": {...}, "trace_id": "..."}
// 错误: {"code": "ERROR_CODE", "message": "...", "data": null, "trace_id": "..."}
```

---

## 6. RAG Pipeline 完整流程

```
用户查询
  │
  ├─ FlowControlStep ──── 拒绝/澄清检查
  │   └─ 拒绝模式: 赌博/色情/黑客/PII/代码生成
  │
  ├─ MemoryStep ────────── 会话历史加载
  │   ├─ 短期: Redis List (最近20条)
  │   └─ 长期: Redis Hash (LLM压缩摘要)
  │
  ├─ RewriteStep ───────── LLM查询改写 (指代消解, 最多6轮)
  │
  ├─ IntentStep ────────── 规则意图分类
  │   ├─ C0/C1/C2复杂度
  │   └─ 语义类型 + 路由策略
  │
  ├─ AgentStep ─────────── LLM代理决策
  │   ├─ 快速预分类 (问候/数学/日期/拒绝)
  │   ├─ retrieval → 继续pipeline
  │   ├─ tool_call → 执行工具 → 返回
  │   └─ direct_answer → LLM直答 → 返回
  │
  ├─ RetrievalStep ─────── 混合检索
  │   ├─ L3缓存检查
  │   ├─ Embedding (BGE-m3 1024d)
  │   ├─ Dense检索 (Milvus HNSW top10)
  │   ├─ Sparse检索 (BM25 top10)
  │   ├─ RRF融合 (alpha=0.7)
  │   └─ 权限过滤 + [HyDE/多查询/Self-RAG]
  │
  ├─ RerankStep ────────── 重排序 + 增强
  │   ├─ Cross-Encoder / Simple Reranker
  │   ├─ 垃圾过滤 + 父扩展
  │   └─ GraphRAG上下文注入
  │
  ├─ ContextStep ───────── 上下文构建
  │   └─ 编号来源[1][2]..., 截断3000字符
  │
  ├─ GenerationStep ────── LLM生成
  │   ├─ 相关性门控 (max_score<0.02→拒绝)
  │   ├─ C2→C1→C0分级超时降级 (3s/1.5s)
  │   └─ 输出消毒 + [Token预算/语义缓存]
  │
  ├─ ConfidenceStep ────── 置信度计算
  │   └─ 0.5×rerank + 0.3×embed + 0.2×llm
  │
  └─ 后处理 ────────────── 会话持久化 + L4缓存 + 返回
```

---

## 7. 文档处理 Pipeline

```
上传 → 扩展名验证(frozenset 10种) → SHA256去重锁(Redis 300s)
     → MinIO存储(key=doc_id) → PG写入(status=PENDING) → 入队TaskQueue
                                                                  ↓
Worker消费:
  1. 下载MinIO内容
  2. 删除旧chunk (防重复处理)
  3. 格式解析 (DocumentParser: pymupdf/python-docx/python-pptx/openpyxl/HTMLParser)
  4. 文本清洗 (TextCleaner: NFC+空白规范化+控制字符移除)
  5. 语义分块 (SemanticChunking: 结构检测→递归分裂→父子引用)
  6. 嵌入生成 (EmbeddingService: BGE-m3 1024d, batch_size=32)
  7. Milvus批量插入
  8. BM25索引更新
  9. GraphRAG实体抽取 (LLM: 1500字符截断, 30s超时)
  10. PG分块持久化
  11. 质量评分 (parse_score=avg_chars/200, [0,1])
  12. doc_version递增 (缓存失效)
  13. DONE/FAILED + WebSocket广播
```

---

## 8. 缓存体系

### 架构

```
请求 → L1(查询缓存) → L4(答案缓存) ──── 命中→直接返回
     → 未命中 → L3(检索缓存) → L2(嵌入缓存) → 原始计算
```

### 各层详情

| 层 | Key | TTL | 内容 |
|----|-----|-----|------|
| L1 | sha256(query+answer):doc_version | 30min | 完整查询结果 |
| L2 | sha256(text):embed_version | 24h | 嵌入向量 |
| L3 | sha256(query_vec_bucket):top_k | 1h | 检索结果列表 |
| L3RAG | sha256(query+context):doc_version | 1h | Pipeline输出 |
| L4 | sha256(query+context) | 15min | 最终答案 |

### 电路断路器

```
状态机: CLOSED → (3次失败) → OPEN(30s) → HALF_OPEN → (成功) → CLOSED
OPEN期间: 静默返回None, CRITICAL日志
```

---

## 9. 安全体系

| 层面 | 措施 |
|------|------|
| 传输 | HTTPS (Caddy反向代理) |
| 鉴权 | JWT HS256 (jti黑名单) + API Key SHA-256 |
| 授权 | RBAC三级 (user/admin/super_admin) |
| 限流 | Redis滑动窗口 60次/分钟/用户, IP登录10次/分钟 |
| SQL注入 | SQLAlchemy参数化查询 |
| Vector注入 | Milvus DocID正则 ^[a-zA-Z0-9\-_]+$ |
| SSRF | URL导入: 仅http/https, 阻止私有IP范围(ipaddress库) |
| ZIP炸弹 | 条目≤200, 总大小≤500MB |
| XSS | CSP + X-XSS-Protection响应头 |
| 点击劫持 | X-Frame-Options: DENY |
| 密钥 | 环境变量, Settings.__repr__脱敏7个敏感字段 |
| 密码 | ≥8字符, 大小写+数字+特殊字符 |
| 时序攻击 | 不存在用户也执行bcrypt哈希 |

---

## 10. 部署架构

### Docker Compose 服务拓扑

```
Caddy(HTTPS) → Frontend(Nginx:80, Vue3 SPA)
             → Backend(Gunicorn:8000, UvicornWorker×2)
                   → PostgreSQL:5432
                   → Redis:6379
                   → Milvus:19530
                   → MinIO:9000
                   → SiliconFlow API (外部)
```

### 资源限制

| 服务 | 内存 | CPU |
|------|------|-----|
| milvus | 4G | 2.0 |
| backend | 2G | 2.0 |
| postgres | 1G | - |
| minio | 1G | - |
| etcd | 512M | 0.5 |
| redis | 512M | - |
| frontend | 256M | - |

### Gunicorn配置
- Worker: 2 × UvicornWorker
- Timeout: 120s, Graceful: 30s
- 每worker: 3个文档处理协程

### 快速开始

```bash
cp .env.example .env  # 编辑设置 SILICONFLOW_API_KEY + JWT_SECRET
docker compose up -d   # 启动8个服务
open http://localhost:3000  # admin / admin123
```

---

## 11. API 参考

```bash
# 健康检查
curl http://localhost:8000/health

# 登录获取Token
curl -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 同步问答
curl -X POST http://localhost:3000/api/chat/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"question":"什么是RAG?"}'

# 流式问答 (SSE)
curl -N http://localhost:3000/api/chat/stream?question=什么是RAG \
  -H "Authorization: Bearer <token>"

# 上传文档
curl -X POST http://localhost:3000/api/documents/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@document.pdf"

# 文档列表
curl http://localhost:3000/api/documents/ \
  -H "Authorization: Bearer <token>"

# 监控指标
curl http://localhost:3000/api/metrics/prometheus
```
