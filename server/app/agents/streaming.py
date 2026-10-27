"""流式事件队列：把生成节点产出的 thinking/token/citation 桥接到 SSE。

LangGraph 生成节点不直接控制 HTTP 响应；它把事件写入以 thread_id 为键的 asyncio.Queue，
由 chat_service 的 SSE 生成器消费并推送。interrupt 期间队列保持，resume 后继续写入。
"""
from __future__ import annotations

import asyncio
from typing import Any


class _Registry:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}

    def new(self, thread_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[thread_id] = q
        return q

    def get(self, thread_id: str) -> asyncio.Queue:
        return self._queues[thread_id]

    def drop(self, thread_id: str) -> None:
        self._queues.pop(thread_id, None)


registry = _Registry()


async def emit(thread_id: str, event: str, data: dict[str, Any]) -> None:
    """生成节点调用：把一条 SSE 事件放入队列。"""
    try:
        await registry.get(thread_id).put((event, data))
    except KeyError:
        # 队列不存在（例如后端重启），静默丢弃
        pass