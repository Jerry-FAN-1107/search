"""LangGraph checkpointer：AsyncSqliteSaver 持久化实现。

将图的 checkpoint 落盘到 SQLite（GRAPH_CHECKPOINT_DB），服务重启后
HITL 等待状态与对话上下文可恢复（替换原 MemorySaver 内存方案）。

生命周期：由应用启动钩子（main.lifespan）调用 init_checkpointer() 建立
aiosqlite 长连接并完成建表；进程退出时由 close_checkpointer() 释放。
"""
from __future__ import annotations

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

_saver: AsyncSqliteSaver | None = None
_conn: aiosqlite.Connection | None = None


async def init_checkpointer() -> AsyncSqliteSaver:
    """建立 SQLite 连接并初始化 checkpoint 表结构。幂等。"""
    global _saver, _conn
    if _saver is not None:
        return _saver
    _conn = await aiosqlite.connect(settings.GRAPH_CHECKPOINT_DB)
    _saver = AsyncSqliteSaver(_conn)
    await _saver.setup()
    logger.info("checkpointer ready: AsyncSqliteSaver db=%s", settings.GRAPH_CHECKPOINT_DB)
    return _saver


def get_checkpointer() -> AsyncSqliteSaver:
    """取已初始化的 checkpointer；未初始化说明启动流程异常。"""
    if _saver is None:
        raise RuntimeError("checkpointer 未初始化：请先在应用启动时调用 init_checkpointer()")
    return _saver


async def close_checkpointer() -> None:
    """释放 SQLite 连接（应用关闭时调用）。"""
    global _saver, _conn
    if _conn is not None:
        await _conn.close()
    _saver = None
    _conn = None
