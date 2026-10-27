# 企业信息咨询大模型应用

一个前后端分离的企业知识库问答系统：多格式文档上传 → RAG 检索与精排 → 判断是否需要联网搜索 → HITL 人工审批 → SSE 流式生成回答（思考过程 + 正文 + 引用角标 + 原文预览）。

- 前端：React 18 + TypeScript + Vite + Tailwind + Zustand + react-pdf
- 后端：FastAPI + SQLAlchemy 2 + LangGraph 0.2.53 + Pydantic v2
- 存储：MySQL 8（业务数据） + ChromaDB（向量） + SQLite（LangGraph checkpoint）
- 模型：豆包（火山方舟 OpenAI 兼容接口） + 本地 Ollama embedding
- 部署：Docker Compose（Nginx + Gunicorn/Uvicorn + MySQL + Ollama）

## 功能特性

### 知识库
- 支持 `docx / pdf / xlsx / pptx`，**批量选择上传**，单文件上限 50MB（`MAX_UPLOAD_MB`）
- **扩展名魔数校验**：OOXML 必须是 zip 包（`PK\x03\x04`）、PDF 必须以 `%PDF` 开头，拦截 RTF 改名 `.docx` 等伪装文件
- **内容去重**（同一用户范围内）：
  - 不同文件名但内容完全一致 → `409` 拒绝
  - 同名但内容不同 → 允许上传
  - 内容相似度 ≥ 90%（SimHash 64 位指纹，汉明距离 ≤ 6）→ 允许上传，但返回提示，前端询问是否删除旧版本
- **异步解析**：上传只落盘并立即返回，解析/向量化在后台执行；状态流转 `pending → parsing → ready/failed`，前端轮询感知
- **启动自愈**：服务重启后自动重新派发中断的解析任务；磁盘文件已丢失的直接标记 `failed`
- **删除闭环**：DB 记录 + 磁盘文件 + Chroma 向量三处同步清理；启动时另做一次孤儿向量对账

### 问答
- RAG 两阶段检索：向量召回 `RAG_RECALL_TOP_K=20` → LLM 精排 → 取 `RAG_TOP_K=6` 喂给模型
- 多轮对话：`chat_history` + 滑动窗口（`MAX_HISTORY_TURNS`），支持指代性追问
- SSE 事件协议：`thinking / token / tool_status / citation / hitl_pending / done / error`
- 引用角标可点击，文件来源打开在线预览并跳转页码
- 支持强制联网搜索（`force_web`）

### HITL 人工审批
- 联网搜索前、最终生成前可中断等待人工决策：`approve / edit / reject`
- 决策提交后解除中断、继续流式输出；点击一次即关闭弹窗，不会重复提交
- LangGraph 状态用 `AsyncSqliteSaver` 持久化到磁盘，**进程重启后可从 checkpoint 恢复**继续审批

### 在线预览
- PDF：`react-pdf` 渲染，支持页码跳转、文本层选择
- docx / xlsx / pptx：后端复用解析器提取文本，前端以文档卡片展示（排版非原样）

### 安全与权限
- JWT 双 Token：Access 2 小时 + Refresh 7 天（`jti` 落库，支持吊销）
- bcrypt 密码哈希；登录防爆破（同 IP+邮箱连续失败 5 次锁定 5 分钟）
- RBAC：`role=admin` 可管理用户与全库文件
- IDOR 防护：文件下载/预览/删除、对话记录均校验资源归属当前 `user_id`
- 向量数据按 `user_id` 隔离，检索强制过滤
- 敏感词过滤 + Prompt 注入启发式拦截；LLM 按用户限流（RPM）+ 全局并发信号量
- 生产环境弱 `JWT_SECRET_KEY` 直接拒绝启动

### 可观测性
- 统一日志：控制台 + 滚动文件（默认 `server/logs/app.log`，10MB × 5 份）
- 请求访问日志（方法/路径/状态码/耗时）、LLM 调用、解析、检索、HITL 节点均有埋点
- Token 用量落库 `llm_usage` 表（按用户/模型统计成本）
- 可选 Sentry 异常上报、Prometheus `/metrics`

## 目录结构

```
.
├── client/                     # 前端
│   └── src/
│       ├── pages/              # Login / Register / Chat
│       ├── components/
│       │   ├── chat/           # 消息、思考面板、工具状态、HITL 卡片、引用角标
│       │   ├── files/          # 文件上传（批量 + 去重提示）
│       │   └── PdfViewer.tsx   # 在线预览（PDF 渲染 / 其他格式文本）
│       ├── hooks/useChat.ts    # SSE 解析与对话状态
│       ├── api/                # axios 封装（401 自动刷新 Token）
│       └── store/              # Zustand 认证状态
├── server/                     # 后端
│   ├── app/
│   │   ├── main.py             # 入口：路由、CORS、日志、lifespan
│   │   ├── routers/            # auth / files / chat / admin / tables
│   │   ├── services/           # 认证、文件、对话、表格业务逻辑
│   │   ├── agents/             # LangGraph 图、节点、checkpointer
│   │   ├── rag/                # 解析、切分、向量库、检索、重排
│   │   ├── models/             # SQLAlchemy 模型
│   │   ├── schemas/            # Pydantic 入参/出参
│   │   └── core/               # 配置、数据库、日志、鉴权依赖、可观测性
│   ├── .env.example
│   └── Dockerfile
├── docker-compose.yml
├── DEPLOY.md                   # Docker 部署指南（含国内镜像加速踩坑记录）
└── README.md
```

## 快速开始（本地开发）

### 1. 后端

```bash
cd server
python -m venv .venv
.venv\Scripts\activate            # Windows；macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

准备 MySQL 库：

```sql
CREATE DATABASE enterprise_consult CHARACTER SET utf8mb4;
```

配置环境变量：

```bash
copy .env.example .env            # macOS/Linux: cp .env.example .env
```

`.env` 至少填写：

- `DATABASE_URL`：MySQL 连接串
- `JWT_SECRET_KEY`：强随机值（`openssl rand -hex 32`）
- `DOUBAO_API_KEY` / `DOUBAO_CHAT_MODEL` / `DOUBAO_THINKING_MODEL` / `DOUBAO_EMBEDDING_MODEL`
- `EMBEDDING_BASE_URL`：本地 Ollama 地址，默认 `http://localhost:11434/v1`

本地 embedding（Ollama）：

```bash
ollama pull <你的 embedding 模型名>
```

启动：

```bash
python -m app.main               # 开发模式（DEBUG=true 时带 --reload 效果）
```

### 2. 前端

```bash
cd client
npm install
npm run dev
```

浏览器打开 http://localhost:5173（Vite 已将 `/api` 代理到后端 `8000`）。

### 3. 首次使用

注册账号 → 知识库上传文件 → 等待列表状态变为 `ready` → 勾选检索范围（不选则全库）→ 提问。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/register` | 注册（返回双 Token） |
| POST | `/auth/login` | 登录（含防爆破） |
| POST | `/auth/refresh` | 用 Refresh Token 换新 Access Token |
| POST | `/auth/logout` | 注销并吊销 Refresh Token |
| POST | `/files/upload` | 上传文件（异步解析；内容重复 409；相似 ≥90% 返回提示） |
| GET | `/files` | 当前用户文件列表与解析状态 |
| GET | `/files/{id}/raw` | 下载原文（PDF 预览用） |
| GET | `/files/{id}/preview` | 文本预览（docx/xlsx/pptx） |
| DELETE | `/files/{id}` | 删除文件（DB + 磁盘 + 向量） |
| POST | `/chat/ask` | 发起问答，返回 SSE 流 |
| POST | `/chat/hitl/{thread_id}` | HITL 决策提交（approve/edit/reject） |
| GET | `/admin/users` | 用户列表（仅管理员） |
| POST | `/admin/users/{id}/activate` \| `/deactivate` | 启用 / 停用账号（仅管理员） |
| DELETE | `/admin/files/{id}` | 删除任意用户文件（仅管理员） |
| POST | `/tables/generate` | 表格生成**预留占位**接口 |
| POST/GET | `/tables/templates` | 表单模板**预留占位**接口 |
| GET | `/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标（需 `METRICS_ENABLED=true`） |

## 环境变量

完整清单与默认值见 [server/.env.example](server/.env.example) 与 [server/app/core/config.py](server/app/core/config.py)。常用分组：

| 分组 | 关键变量 |
|---|---|
| 应用 | `APP_ENV`、`DEBUG`、`HOST`、`PORT`、`CORS_ORIGINS` |
| 数据库 | `DATABASE_URL` |
| 认证 | `JWT_SECRET_KEY`、`ACCESS_TOKEN_EXPIRE_MINUTES`、`REFRESH_TOKEN_EXPIRE_DAYS`、`LOGIN_MAX_FAILURES`、`LOGIN_LOCK_MINUTES` |
| 模型 | `DOUBAO_API_KEY`、`DOUBAO_BASE_URL`、`DOUBAO_CHAT_MODEL`、`DOUBAO_THINKING_MODEL`、`DOUBAO_EMBEDDING_MODEL`、`EMBEDDING_BASE_URL` |
| RAG | `CHROMA_PERSIST_DIR`、`RAG_TOP_K`、`RAG_RECALL_TOP_K`、`RAG_SIMILARITY_THRESHOLD`、`RAG_RERANK_ENABLED` |
| LangGraph | `GRAPH_CHECKPOINT_DB`、`HITL_ENABLED`、`MAX_HISTORY_TURNS` |
| 流控 | `LLM_PER_USER_RPM`、`LLM_GLOBAL_CONCURRENCY` |
| 内容安全 | `CONTENT_MODERATION_ENABLED`、`SENSITIVE_WORDS_FILE`、`PROMPT_INJECTION_GUARD` |
| 文件 | `UPLOAD_DIR`、`MAX_UPLOAD_MB` |
| 可观测性 | `SENTRY_DSN`、`METRICS_ENABLED`、`LOG_LEVEL`、`LOG_DIR` |

> 密钥只存在于后端，前端永远不接触第三方 API Key。

## Docker 一键部署

```bash
# 1. 配置环境变量（必须）
copy server/.env.example server/.env

# 2. 构建并启动
docker compose up -d --build

# 3. 首次拉取 embedding 模型
docker compose exec ollama ollama pull <你的 embedding 模型名>

# 4. 访问
http://localhost:8080          # 可用 CLIENT_PORT 覆盖端口
```

国内网络需先通过镜像加速前缀拉取基础镜像，以及 checkpoint 版本冲突等已知问题，详见 [DEPLOY.md](DEPLOY.md)。

## 关键设计约定

- **模型调用集中**：所有豆包交互（流式、function calling、`reasoning_content`、embedding）统一走 `server/app/llm_client.py`，禁止散落 HTTP 请求。
- **图装配**：`server/app/agents/graph.py`
  `retrieve → rerank → judge →（hitl_search → search）→ hitl_final → generate`
  `judge` / `search` 后为条件边，按检索质量决定是否联网。
- **HITL**：中断逻辑在 `server/app/middlewares/hitl.py`，状态由 `AsyncSqliteSaver` 持久化。
- **SSE 协议**：后端 `server/app/schemas/chat.py`，前端 `client/src/types/chat.ts`，两边需同步修改。
- **建表**：首次启动 `init_db()` 自动建表；新增列走 `server/app/core/database.py` 的 information_schema 朴素补列迁移。生产环境建议迁移到 Alembic。
- **上传检测**：`server/app/services/file_service.py` 中 SHA-256 精确去重 + 纯 Python SimHash 相似度，不引入额外依赖。

## 已知限制与注意事项

- ChromaDB 本地持久化适合单机/中小规模；海量数据与高并发场景建议替换为 Milvus / Qdrant，并改用数据库级去重。
- 历史文件没有内容指纹，重新上传与其完全相同的内容不会触发 409（不回填历史数据）。
- docx/xlsx/pptx 在线预览为文本提取结果，不保留原始排版；PDF 保留原貌。
- 服务重启时若存在进行中的对话流，SSE 连接会断开，但 HITL 等待状态可恢复。
- 在 Trae IDE 内置预览面板中调试 SSE 时可能因面板重载导致请求中止，联调请使用系统浏览器。
- `/tables/*` 为预留占位接口，前端暂无对应页面。
- 上线前需完成生成式 AI 备案、用户隐私协议与数据合规评估。

## 日志

- 统一日志模块 `server/app/core/logging.py`，`setup_logging()` 启动时装配（幂等）。
- 输出控制台 + 滚动文件（默认 `server/logs/app.log`，单文件 10MB、保留 5 份）。
- 可通过 `LOG_LEVEL` / `LOG_DIR` / `LOG_FILE` / `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` 调整。
- 已埋点：请求访问日志、认证成功与失败、LLM 调用与 Token 用量、文件解析/向量化、RAG 检索与联网判定、各 Agent 节点、HITL 暂停与决策。
