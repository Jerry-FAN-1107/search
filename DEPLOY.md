# 部署指南（Docker 一键部署）

## 前置要求

- Docker Desktop（Windows）或 Docker Engine（Linux），含 Docker Compose V2
- 可访问互联网的机器（首次需拉取基础镜像与依赖）

## 1. 国内网络拉取基础镜像（关键步骤）

Docker Hub 直连在国内通常被墙。**不要**直接 `docker compose up`（会卡死在拉镜像）。先用加速器前缀拉取并 tag 回原名：

```bash
docker pull docker.m.daocloud.io/library/python:3.12-slim
docker pull docker.m.daocloud.io/library/node:20-alpine
docker pull docker.m.daocloud.io/library/nginx:alpine
docker pull docker.m.daocloud.io/library/mysql:8.0
docker pull docker.m.daocloud.io/ollama/ollama:latest

docker tag docker.m.daocloud.io/library/python:3.12-slim python:3.12-slim
docker tag docker.m.daocloud.io/library/node:20-alpine node:20-alpine
docker tag docker.m.daocloud.io/library/nginx:alpine nginx:alpine
docker tag docker.m.daocloud.io/library/mysql:8.0 mysql:8.0
docker tag docker.m.daocloud.io/ollama/ollama:latest ollama/ollama:latest
```

> 若 `daocloud` 失效，可换 `docker.1ms.run` 等加速器前缀，命令格式相同。

## 2. 配置环境变量

复制模板并填写密钥（**不要提交到 Git**）：

```bash
cp server/.env.example server/.env
```

必填项：

| 变量 | 说明 |
|---|---|
| `JWT_SECRET_KEY` | 强随机数（可用 `python -c "import secrets; print(secrets.token_hex(32))"` 生成） |
| `DOUBAO_API_KEY` | DeepSeek/豆包 API Key |
| `MYSQL_ROOT_PASSWORD` | 生产环境改为强密码 |
| `MYSQL_PASSWORD` | 同上 |

## 3. 一键启动

```bash
docker compose up -d
```

首次构建约 10 分钟（pip 走清华源，npm 正常）。

## 4. 拉取 Embedding 模型（仅首次）

```bash
docker compose exec ollama ollama pull embeddinggemma
```

> 若 `server/.env` 中改了 `EMBEDDING_BASE_URL`/`DOUBAO_EMBEDDING_MODEL`，请对应调整模型名。

## 5. 验证

| 检查 | 命令 | 预期 |
|---|---|---|
| 前端页面 | `curl http://localhost:8080/` | 200 |
| 后端健康 | `curl http://localhost:8080/api/health` | 200 |
| 服务状态 | `docker compose ps` | 4 个 Up |

浏览器打开 `http://localhost:8080`，注册账号即可使用（容器 MySQL 为独立数据库，与本地开发数据隔离）。

## 常见问题

### 端口被占用

本机 80 端口被 IIS/其他服务占用时，启动前改环境变量：

```powershell
$env:CLIENT_PORT=8080; docker compose up -d
```

### LangGraph checkpoint 版本冲突

`langgraph 0.2.53` 与 `langgraph-checkpoint-sqlite 3.1.2` 在 pip 元数据上冲突（要求 checkpoint 2.x vs 4.x），但**运行时兼容**。`server/Dockerfile` 已用 `--no-deps` 覆盖安装复刻本机验证过的组合，无需手动处理。

### 服务重启后 HITL 对话状态

`graph_state.db` 挂在卷 `server_state` 上，重启不丢。

## 停止与清理

```bash
docker compose down          # 停止（保留数据卷）
docker compose down -v       # 停止并清空数据（MySQL/向量/上传文件全删，谨慎）
```
