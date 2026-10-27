"""问答路由：SSE 流式接口 + HITL 决策提交。

SSE 事件：thinking / token / tool_status / citation / hitl_pending / done / error。
前端依据事件名分流：thinking -> 思考面板；token -> 正文；citation -> 角标映射。
"""
from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.user import User
from ..schemas.chat import ChatRequest, HitlDecision
from ..services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


async def _sse(gen: AsyncIterator[tuple[str, dict]]) -> AsyncIterator[str]:
    """把 (event, data) 生成器编码为 SSE 文本流。"""
    yield "retry: 3000\n\n"
    async for event, data in gen:
        payload = json.dumps(data, ensure_ascii=False)
        print(f"🚀 [SSE 发送] event={event}, payload={payload}")
        yield f"event: {event}\ndata: {payload}\n\n"


@router.post("/ask")
async def ask(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """发起一次问答，返回 SSE 流。"""
    gen = chat_service.run(
        db,
        user_id=user.id,
        question=payload.question,
        conversation_id=payload.conversation_id,
        file_ids=payload.file_ids,
        force_web=payload.force_web,
    )
    return StreamingResponse(
        _sse(gen),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/hitl/{thread_id}")
async def submit_hitl(
    thread_id: str,
    decision: HitlDecision,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """HITL 人工决策提交（approve/edit/reject），恢复图执行并继续返回 SSE。"""
    gen = chat_service.resume(thread_id, decision)
    return StreamingResponse(_sse(gen), media_type="text/event-stream")