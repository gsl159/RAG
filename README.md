# RAG Knowledge System — 企业级智能问答平台

<p align="center">
  <strong>基于检索增强生成（RAG）的企业级知识库系统</strong><br/>
  混合检索 · 5 层缓存 · Agentic RAG · 全链路追踪 · Cyberpunk UI
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" alt="Python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Vue-3.4-4FC08D?logo=vue.js" alt="Vue"/>
  <img src="https://img.shields.io/badge/Milvus-2.3.9-00A0DC" alt="Milvus"/>
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql" alt="PostgreSQL"/>
  <img src="https://img.shields.io/badge/Redis-7.2-DC382D?logo=redis" alt="Redis"/>
  <img src="https://img.shields.io/badge/Tests-327+-brightgreen" alt="Tests"/>
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License"/>
</p>

---

## 目录

- [项目简介](#项目简介)
- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [部署方案](#部署方案)
- [本地开发](#本地开发)
- [测试](#测试)
- [配置参考](#配置参考)
- [API 参考](#api-参考)
- [项目结构](#项目结构)
- [RAG Pipeline](#rag-pipeline)
- [安全机制](#安全机制)

---

## 项目简介

本系统是一个**生产级企业级 RAG 智能问答平台**，支持将企业文档（PDF、Word、PPT、Excel、HTML、TXT、Markdown、CSV）上传后自动解析、分块、向量化，通过混合检索和大语言模型为用户提供基于知识库内容的精准问答。

**适用场景**：企业内部知识库 · 技术文档检索 · 客服知识辅助 · 合规政策查询

---

## 核心功能

### 智能问答

| 功能 | 说明 |
|------|------|
| **混合检索** | Dense（Milvus HNSW）+ Sparse（BM25）双路检索，RRF 融合排序 |
| **Agentic RAG** | Agent 自主决策：直答 / 检索 / 工具调用 / 多步推理 / 澄清 / 拒答 |
| **双层意图分类** | C0/C1/C2 复杂度 + FACT/COMPARISON/REASONING 等 6 类语义意图 |
| **智能改写** | 结合对话历史自动改写查询，消解指代、补全上下文 |
| **Cross-Encoder 重排** | BGE-Reranker-v2-m3 精排（可选简单模式） |
| **GraphRAG** | 知识图谱实体抽取 + 图上下文注入 |
| **SSE 流式输出** | 实时打字机效果流式响应 |
| **置信度评分** | 可配置权重：W1×rerank + W2×embed + W3×llm_score |
| **超时降级** | C2(3s) → C1(1.5s) → C0(原始片段) 三级降级 |
| **对话记忆** | 短期记忆（Redis）+ 长期记忆（LLM 摘要压缩）+ 话题切换检测 |
| **追问建议** | 自动生成 follow-up 问题 |

### 文档管理

| 功能 | 说明 |
|------|------|
| **多格式支持** | PDF、DOCX、PPTX、XLSX、CSV、HTML、TXT、Markdown（12 种） |
| **语义分块** | 基于语义相似度的智能分块策略 |
| **ZIP 批量上传** | 支持 ZIP 压缩包（上限 200 文件 / 500MB） |
| **URL 导入** | HTTP/HTTPS 网页抓取（SSRF 防护 + 重定向安全校验） |
| **覆盖上传** | MD5 去重 + 可选覆盖替换 |
| **文件校验** | Magic bytes 真实类型验证 |
| **文档权限** | 租户/部门/用户三级文档访问控制 |
| **标签系统** | 文档标签管理，按标签筛选检索 |
| **异步处理** | 后台任务队列，支持失败重试（指数退避，最多 3 次） |

### 运营管理

| 功能 | 说明 |
|------|------|
| **监控大盘** | 查询量/缓存命中率/延迟分布/QPS/LLM 状态 |
| **用户反馈** | 赞/踩 + 多维度评分 + 文字纠正 |
| **审计日志** | 完整用户操作审计（登录/上传/删除/查询） |
| **用户管理** | 用户 CRUD、RBAC 角色分配、API Key 管理 |
| **Benchmark** | 内置评测框架，支持按类别运行 |
| **对话导出** | 会话导出为 Markdown |
| **QA 分享** | 单条问答生成公开分享链接 |

### 安全机制

| 功能 | 说明 |
|------|------|
| **JWT + 黑名单** | HS256 + jti 唯一标识 + Redis 黑名单吊销（fail-closed） |
| **RBAC** | 三级角色：user / admin / super_admin |
| **API Key** | `rag_` 前缀，SHA-256 哈希存储 |
| **滑窗限流** | Redis 滑动窗口，按用户/分钟 + IP 登录限流 |
| **租户隔离** | 文档级 + 检索级租户过滤 |
| **SSRF 防护** | URL 导入私有 IP 检测 + 逐跳重定向校验 |
| **文件安全** | Magic bytes 校验 + ZIP 炸弹防护 + 文件大小限制 |
| **时序攻击防护** | 登录失败仍执行 bcrypt，固定耗时 |
| **Token 安全** | SSE/WebSocket 仅接受 Authorization Header，禁止 URL 传参 |
| **安全头** | CSP / X-Frame-Options / X-Content-Type-Options / HSTS |

---

## 系统架构

```
客户端浏览器 (Vue 3 SPA)
        │  HTTPS / SSE / WebSocket
        ▼
    Caddy（自动 HTTPS + HTTP/3）
        │
        ▼
┌──────────────────────────────────────────┐
│           FastAPI Backend (Uvicorn)        │
│  ┌──────────┬──────────┬──────────────┐   │
│  │  L1 API  │ Auth · Chat · Upload     │   │
│  │          │ Metrics · Admin · Audit   │   │
│  ├──────────┼──────────────────────────┤   │
│  │ L2 Svc   │ rag_service · doc_svc     │   │
│  │          │ eval_svc · feedback_svc   │   │
│  ├──────────┼──────────────────────────┤   │
│  │ L3 Core  │ intent → rewrite → retrieve│   │
│  │          │ → rerank → generate        │   │
│  │          │ + Agent · Tools · Memory   │   │
│  ├──────────┼──────────────────────────┤   │
│  │ L4 Repo  │ PostgreSQL · Redis        │   │
│  │          │ Milvus · MinIO             │   │
│  └──────────┴──────────────────────────┘   │
└──────────────────────────────────────────┘
```

### 四层架构

```
backend/app/
├── api/          L1 接入层 — 路由、鉴权、限流、参数校验
├── service/      L2 编排层 — 业务流程组合
├── core/         L3 领域层 — RAG Pipeline、检索、生成、Agent
│   └── pipeline/     Agentic RAG v2 模块
├── repository/   L4 数据层 — PostgreSQL · Redis · Milvus · MinIO
├── config/       配置管理（Pydantic BaseSettings，100+ 项）
├── schema/       请求/响应模型
└── utils/        工具函数
```

依赖方向：api → service → core → repository，严格单向。

---

## 技术栈

### 后端

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | 异步 ASGI，SSE/WebSocket |
| ORM | SQLAlchemy 2.0 (async) | asyncpg 驱动 |
| 关系库 | PostgreSQL 16 | 元数据 + 审计 + 用户 |
| 向量库 | Milvus 2.3 | HNSW + COSINE |
| 缓存 | Redis 7.2 | 5 层缓存 + 限流 + 黑名单 |
| 对象存储 | MinIO | S3 兼容 |
| LLM | SiliconFlow（Qwen2.5-7B） | 多 Provider 故障转移 |
| Embedding | BAAI/bge-m3 | 1024 维 |
| BM25 | rank-bm25 | 内存 / Elasticsearch 后端 |
| 认证 | PyJWT + bcrypt | HS256 + jti |
| 文档解析 | PyMuPDF / python-docx / 等 | 纯 Python |
| 日志 | Loguru | trace_id 全链路 |
| 迁移 | Alembic | 增量 Schema 迁移 |
| 测试 | pytest + pytest-asyncio | 327+ 用例 |

### 前端

| 组件 | 技术 | 说明 |
|------|------|------|
| 框架 | Vue 3 (Composition API) | SPA |
| 构建 | Vite 5 | 秒级 HMR |
| 路由 | Vue Router 4 | History 模式 + JWT 预检 |
| HTTP | Axios | 拦截器 + SSE fetch |
| 图表 | ECharts 5 | 监控大盘 |
| Markdown | markdown-it + KaTeX + Mermaid | 代码高亮 + 公式 + 流程图 |
| XSS | DOMPurify | HTML 净化 |
| PWA | vite-plugin-pwa | 离线缓存 |
| 主题 | Cyberpunk | 深色/亮色双主题 |

### 基础设施

| 组件 | 用途 |
|------|------|
| Docker Compose | 8 服务编排 |
| Caddy | 自动 HTTPS 网关（生产） |
| Nginx | 前端静态 + API 反代（Docker 内） |
| Alembic | DB 版本迁移 |

---

## 快速开始

### 环境要求

- Docker ≥ 20.10 + Docker Compose v2
- 内存 ≥ 4GB，磁盘 ≥ 10GB
- LLM API Key：[SiliconFlow](https://siliconflow.cn)（免费注册）

### 3 步启动

```bash
# 1. 克隆仓库
git clone <repo-url> && cd rag_system

# 2. 运行部署脚本
chmod +x deploy.sh && ./deploy.sh
# 按提示编辑 .env 填入 SILICONFLOW_API_KEY 和 JWT_SECRET 后再次运行

# 3. 访问
# 前端：http://localhost:3000
# 默认账号：admin / admin123（生产环境请立即修改）
```

---

## 部署方案

### 开发环境（Docker Compose）

```bash
cp .env.example .env
# 编辑 .env 填入必填项
docker compose up -d

# 查看状态
docker compose ps
docker compose logs -f backend

# 健康检查
curl http://localhost:8000/health
```

### 生产环境（Caddy HTTPS）

```bash
chmod +x deploy-prod.sh && ./deploy-prod.sh
vim .env  # 设置 DOMAIN、JWT_SECRET、SILICONFLOW_API_KEY

# 生产配置叠加启动
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 内网穿透（无需公网 IP）

```bash
# Cloudflare Tunnel
cloudflared tunnel --url http://localhost:3000
# 分享输出的 https://xxx.trycloudflare.com 即可

# 其他方案：ngrok http 3000  /  frp  /  Tailscale
```

### 数据持久化

| Volume | 内容 |
|--------|------|
| `postgres_data` | 数据库 |
| `milvus_data` | 向量索引 |
| `redis_data` | 缓存 |
| `minio_data` | 原始文档 |
| `etcd_data` | Milvus 元数据 |

---

## 本地开发

### 后端

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="sqlite+aiosqlite:///dev.db"
export JWT_SECRET="dev-secret-key-change-me"
export SILICONFLOW_API_KEY="sk-your-key"
export APP_ENV="development"

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# API 文档：http://localhost:8000/docs
```

### 前端

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173（自动代理 /api → :8000）
npm run build     # 生产构建
```

### 数据库迁移

```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

---

## 测试

### 后端（327+ 用例）

```bash
# 全部测试（SQLite 内存库，无需外部服务）
DATABASE_URL="sqlite+aiosqlite:///test.db" PYTHONPATH=backend pytest tests/ -v

# 按模块测试
pytest tests/test_rag_pipeline.py -v       # RAG Pipeline
pytest tests/test_api.py -v                # API 层
pytest tests/test_http_endpoints.py -v     # HTTP 集成
pytest tests/test_pipeline_v2.py -v        # Agentic RAG v2
pytest tests/test_cache.py -v              # 缓存层
pytest tests/test_v3_features.py -v        # GraphRAG / 工具调用

# 覆盖率
pytest tests/ -v --cov=backend/app --cov-report=html
```

### 前端

```bash
cd frontend
npm run test          # vitest
npm run test:watch    # 监听模式
```

### 测试约定

- 所有测试使用 SQLite 内存库，无需外部依赖
- `conftest.py` 提供公共 mock fixtures（`mock_llm_client`、`mock_redis_cache`、`mock_milvus`）
- `asyncio_mode = auto`，无需显式 `@pytest.mark.asyncio`
- Mock 方式：`unittest.mock.patch` 替换模块级单例（如 `patch("app.core.generator.llm_client")`）

---

## 配置参考

所有配置通过环境变量注入（支持 `.env` 文件）。配置定义见 `backend/app/config/settings.py`。

### 必填项

| 变量 | 说明 |
|------|------|
| `JWT_SECRET` | **必填**，JWT 签名密钥（空值拒绝启动） |
| `SILICONFLOW_API_KEY` | **生产必填**，LLM API Key |

### LLM 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SILICONFLOW_API_KEY` | `sk-placeholder` | SiliconFlow API Key |
| `SILICONFLOW_BASE_URL` | `https://api.siliconflow.cn/v1` | API 地址 |
| `LLM_MODEL` | `Qwen/Qwen2.5-7B-Instruct` | 默认模型 |
| `LLM_MODEL_C0` / `C1` / `C2` | 空 | 按复杂度分级模型 |
| `EMBED_MODEL` | `BAAI/bge-m3` | Embedding 模型 |
| `EMBED_DIM` | `1024` | 向量维度 |
| `OPENAI_API_KEY` | 空 | OpenAI 故障转移 |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI 模型 |
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | 本地 Ollama |

### 数据库与存储

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://raguser:ragpass123@postgres:5432/ragdb` | PG 连接 |
| `PG_POOL_SIZE` | `30` | 连接池 |
| `REDIS_URL` | `redis://redis:6379/0` | Redis 连接 |
| `MILVUS_HOST` | `milvus` | Milvus 地址 |
| `MILVUS_PORT` | `19530` | Milvus 端口 |
| `MINIO_ENDPOINT` | `minio:9000` | MinIO 地址 |

### RAG 参数

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CHUNK_SIZE` | `500` | 分块大小（字符） |
| `TOP_K` | `10` | 检索 Top-K |
| `RERANK_TOP_N` | `5` | 重排保留数 |
| `HYBRID_RETRIEVAL_ALPHA` | `0.7` | 混合检索向量权重 |
| `CONTEXT_MAX_CHARS` | `3000` | 上下文长度上限 |
| `RERANKER_MODE` | `simple` | simple / cross_encoder |
| `GRAPH_RAG_ENABLED` | `true` | GraphRAG |
| `AGENTIC_RAG_ENABLED` | `true` | Agentic RAG |
| `SEMANTIC_CHUNKING_ENABLED` | `true` | 语义分块 |
| `CONF_WEIGHT_RERANK` | `0.5` | 置信度·重排权重 |
| `CONF_WEIGHT_EMBED` | `0.3` | 置信度·相似度权重 |
| `CONF_WEIGHT_LLM` | `0.2` | 置信度·LLM 自评权重 |
| `RERANK_RRF_BLEND` | `0.7` | 重排·RRF 融合权重 |
| `RERANK_COVERAGE_BLEND` | `0.3` | 重排·关键词覆盖权重 |

### 安全配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `JWT_SECRET` | 空 | **必填**，JWT 密钥 |
| `JWT_ALGORITHM` | `HS256` | JWT 算法 |
| `JWT_EXPIRE_HOURS` | `24` | Token 有效期 |
| `JWT_BLACKLIST_FAIL_OPEN` | `false` | Redis 故障时拒绝所有 Token |
| `RATE_LIMIT_PER_MINUTE` | `60` | 每分钟请求上限 |
| `CORS_ORIGINS` | `localhost:5173,localhost:3000` | CORS 白名单 |

### 缓存 TTL

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CACHE_TTL_QUERY` | `1800` | L1 查询（30min） |
| `CACHE_TTL_EMBED` | `86400` | L2 Embedding（24h） |
| `CACHE_TTL_RETRIEVAL` | `3600` | L3 检索（1h） |
| `CACHE_TTL_RAG` | `3600` | L3 RAG（1h） |
| `CACHE_TTL_ANSWER` | `900` | L4 答案（15min） |

### 应用配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_ENV` | `development` | development / production |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `APP_PORT` | `8000` | 监听端口 |
| `WORKERS` | `2` | Uvicorn worker 数 |

---

## API 参考

### 统一响应格式

```json
{
  "code": 0,
  "message": "ok",
  "data": {},
  "trace_id": "abc123"
}
```

### 错误码

| 错误码 | 含义 | HTTP |
|--------|------|------|
| `0` | 成功 | 200 |
| `1001` | 参数错误 | 400 |
| `1002` | 未认证 | 401 |
| `1003` | 权限不足 | 403 |
| `1004` | 请求过于频繁 | 429 |
| `3001` | 检索失败 | 500 |
| `4001` | LLM 超时 | 500 |
| `5000` | 系统异常 | 500 |

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 登录，返回 JWT |
| POST | `/auth/logout` | 登出，Token 加入黑名单 |
| GET | `/auth/me` | 当前用户信息 |

### 查询

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/chat/` | 同步 RAG 查询 |
| GET | `/chat/stream` | SSE 流式查询 |
| POST | `/chat/confirm` | 确认采纳答案 |
| GET | `/chat/history` | 查询历史 |
| GET | `/chat/suggestions` | 热门问题 |
| POST | `/chat/share/{id}` | 创建分享链接 |
| GET | `/chat/share/{token}` | 查看分享 |

### 文档管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/upload/` | 上传文档 |
| POST | `/upload/batch` | ZIP 批量上传 |
| POST | `/upload/from-url` | URL 导入 |
| GET | `/upload/docs` | 文档列表（游标分页） |
| GET | `/upload/docs/{id}` | 文档详情 |
| DELETE | `/upload/docs/{id}` | 删除文档 |
| POST | `/upload/docs/{id}/retry` | 重试失败文档 |
| GET | `/upload/docs/{id}/chunks` | 分块列表 |
| GET/POST/DELETE | `/upload/docs/{id}/permissions` | 文档权限管理 |

### 监控 & 审计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/metrics/overview` | 系统总览 |
| GET | `/metrics/rag` | RAG 性能 |
| GET | `/metrics/cache` | 缓存命中率 |
| GET | `/metrics/qps` | 实时 QPS |
| GET | `/metrics/llm-status` | LLM 状态 |
| GET/POST/DELETE | `/metrics/benchmark` | 基准测试 |
| GET | `/audit/` | 审计日志（Admin） |

### 管理 & 标签

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PUT | `/admin/users` | 用户管理 |
| GET/POST/DELETE | `/admin/apikeys` | API Key 管理 |
| POST | `/admin/change-password` | 修改密码 |
| GET/POST/DELETE | `/tags/` | 标签 CRUD |
| POST | `/tags/bind` / `/tags/unbind` | 文档标签绑定 |

> 所有 API 同时支持根路由（`/chat/*`）和版本化路由（`/api/v1/chat/*`）。新客户端建议使用 `/api/v1/*`。

---

## 项目结构

```
rag_system/
├── README.md
├── ENGINEERING_SPEC.md           # 工程规格书
├── API_CONTRACT.md               # API 契约
├── docker-compose.yml            # Docker 编排
├── docker-compose.prod.yml       # 生产叠加（Caddy HTTPS）
├── deploy.sh / deploy-prod.sh    # 部署脚本
├── pytest.ini
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini               # 数据库迁移
│   ├── alembic/versions/         # 迁移版本
│   └── app/
│       ├── main.py               # FastAPI 入口
│       ├── api/                  # L1 接入层 (10 模块)
│       ├── service/              # L2 编排层
│       ├── core/pipeline/        # L3 领域层 (13 模块)
│       ├── repository/           # L4 数据层
│       ├── config/settings.py    # 100+ 配置项
│       ├── schema/               # 请求/响应模型
│       └── utils/                # 工具
│
├── frontend/
│   ├── src/
│   │   ├── main.js / App.vue     # Vue 入口
│   │   ├── router.js             # 路由 + JWT 守卫
│   │   ├── api/index.js          # Axios + SSE
│   │   ├── pages/                # 7 个页面
│   │   └── components/           # 公共组件
│   ├── vite.config.js
│   └── nginx.conf
│
├── tests/                        # 后端测试 (327+)
│   ├── conftest.py               # 公共 fixtures
│   └── test_*.py
│
└── infra/init.sql                # 补充索引
```

---

## RAG Pipeline

### 查询流程

```
用户提问 → 鉴权限流 → Agent 决策 → 意图分类 + 改写 + Embedding（并行）
→ 混合检索（Dense + Sparse → RRF 融合）→ 重排 + GraphRAG（并行）
→ 上下文构建 → LLM 生成（超时降级）→ 置信度评分 → 写缓存 → 返回
```

### Agent 决策路由

| 策略 | 触发条件 | 说明 |
|------|---------|------|
| `retrieval` | 需要知识库 | 走标准 RAG 检索 |
| `direct_answer` | 常识问题 | LLM 直接回答 |
| `calculator` | 数学表达式 | AST 白名单安全计算 |
| `date_parser` | 日期查询 | 日期解析 |
| `structured_query` | 元数据查询 | 文档统计查询 |
| `multi_step` | 复杂推理 | 多步检索推理组合 |
| `clarify` | 模糊问题 | 追问澄清 |
| `refuse` | 违规/超范围 | 拒绝回答 |

### 5 层缓存

```
L1 Query Cache (30min) → L2 Embedding Cache (24h)
→ L3 Retrieval Cache (1h) → L3 RAG Cache (1h)
→ L4 Answer Cache (15min)
```
所有缓存 Key 包含 `doc_version`，文档更新自动失效。`SingleFlight` 防止并发重复查询。

### 超时降级

```
C2 复杂查询 (3.0s) → C1 中等查询 (1.5s) → C0 直接返回片段
```

### LLM 故障转移

```
SiliconFlow (Qwen2.5-7B) → OpenAI (gpt-4o-mini) → Ollama (本地) → 自定义
```

---

## 安全机制

**认证体系**：JWT HS256 + jti 黑名单（fail-closed）+ API Key（SHA-256 哈希）

**授权**：RBAC 三级角色，文档级租户/部门/用户权限过滤

**传输安全**：
- Token 仅通过 Authorization Header（SSE/WebSocket 拒绝 URL 传参）
- 生产环境 Caddy 自动 HTTPS + HTTP/3
- FORWARDED_ALLOW_IPS 锁定为 127.0.0.1

**攻击防护**：
- Redis 滑窗限流 + IP 登录限流
- bcrypt 固定耗时对比（防时序攻击）
- URL 导入 SSRF 检测 + 逐跳重定向校验
- ZIP 炸弹条目数/解压大小双重防护
- 文件 Magic bytes 类型验证
- 数学表达式 AST 白名单（防代码注入）
- 前端 DOMPurify HTML 净化
- CSP / X-Frame-Options / HSTS 安全头

**运维安全**：
- JWT_SECRET 空值拒绝启动（所有环境）
- 敏感配置 `__repr__` 脱敏
- 生产环境 API Key / MinIO 密码默认值校验

---

## License

MIT
