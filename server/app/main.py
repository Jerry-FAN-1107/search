"""应用入口：装配路由、中间件、启动时初始化数据库表并配置日志。"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .agents.checkpointer import close_checkpointer, init_checkpointer
from .agents.graph import init_graph
from .core.config import settings
from .core.database import init_db
from .core.logging import get_logger, setup_logging
from .core.observability import init_sentry, record_http
from .routers import admin, auth, chat, files, tables

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/关闭钩子：日志 -> Sentry -> DB -> checkpointer -> 编译 LangGraph 图。"""
    setup_logging()          # 幂等：先配置日志再打启动日志
    logger.info("=== 应用启动：%s (env=%s, debug=%s) ===", settings.APP_NAME, settings.APP_ENV, settings.DEBUG)
    settings.validate_secret_strength()
    init_sentry()
    init_db()
    logger.info("数据库初始化完成（DATABASE_URL 已加载）")
    # 启动对账：清理 DB 已删除文件的孤儿向量 + 重新派发因重启中断的解析任务
    from .core.database import SessionLocal
    from .rag.vectorstore import get_vectorstore
    from .services.file_service import File, recover_interrupted_parses
    from . import models  # noqa: F401  确保 File 模型已注册

    with SessionLocal() as _db:
        _valid_ids = {row[0] for row in _db.query(File.id).all()}
    _removed = get_vectorstore().cleanup_orphans(_valid_ids)
    if _removed:
        logger.info("启动对账：清理孤儿向量 %s 条", _removed)
    _redispatched = recover_interrupted_parses()
    if _redispatched:
        logger.info("启动恢复：重新派发解析任务 %s", _redispatched)
    await init_checkpointer()
    init_graph()
    logger.info("LangGraph 图编译完成（checkpoint 已持久化）")
    yield
    await close_checkpointer()
    logger.info("=== 应用关闭 ===")


app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """请求访问日志：记录方法、路径、状态码、耗时与客户端标识。"""
    start = time.perf_counter()
    response = await call_next(request)
    cost_ms = (time.perf_counter() - start) * 1000
    client = request.client.host if request.client else "-"
    logger.info(
        "http %s %s -> %d | %.1fms | from %s",
        request.method,
        request.url.path,
        response.status_code,
        cost_ms,
        client,
    )
    record_http(request.method, request.url.path, response.status_code, cost_ms)
    return response


app.include_router(auth.router)
app.include_router(files.router)
app.include_router(chat.router)
app.include_router(tables.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.APP_NAME}


@app.get("/metrics")
def metrics():
    """Prometheus 指标端点（未安装 prometheus-client 或未启用时返回 404）。"""
    from fastapi import HTTPException, Response

    from .core.observability import render_metrics

    payload = render_metrics()
    if payload is None:
        raise HTTPException(status_code=404, detail="metrics 未启用")
    return Response(content=payload, media_type="text/plain; version=0.0.4")


def run() -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)


if __name__ == "__main__":
    run()