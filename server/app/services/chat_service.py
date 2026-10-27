"""问答业务逻辑：驱动 LangGraph 图运行、消费流式队列、处理 HITL 中断与恢复。

对外暴露两个异步生成器（均产出 (event, data)，由路由封装为 SSE）：
- run(question, user, ...)：发起一次问答，直至完成或暂停待人工确认。
- resume(thread_id, decision)：用户提交 approve/edit/reject 后恢复执行。

HITL 暂停点由图节点通过 middlewares/hitl.require_approval 触发（interrupt + checkpointer）。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator

from langgraph.errors import GraphInterrupt
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents import get_graph
from ..agents import streaming
from ..agents.state import ConsultState
from ..core.config import settings
from ..core.logging import get_logger
from ..core.moderation import ModerationError, filter_input
from ..core.ratelimit import llm_limiter
from ..models.conversation import Conversation, Message
from ..models.file import File
from ..schemas.chat import HitlDecision

logger = get_logger(__name__)


def _make_thread_id() -> str:
    return uuid.uuid4().hex


def _config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _interrupt_payload(snapshot: Any) -> dict | None:
    """从 value 模式的图快照中提取 interrupt 信息。"""
    if isinstance(snapshot, dict) and snapshot.get("__interrupt__"):
        intr = snapshot["__interrupt__"][0]
        value = getattr(intr, "value", None) or intr
        if isinstance(value, dict):
            return {
                "action": value.get("action", "unknown"),
                "context": value.get("context", {}),
            }
    return None


async def _run_graph(initial: dict, thread_id: str) -> None:
    """后台任务：运行图，遇 interrupt 则向队列推送 hitl_pending 后结束。"""
    queue = streaming.registry.get(thread_id)
    config = _config(thread_id)
    try:
        # 👇 1. 用 ainvoke 直接跑。遇到中断时它不会报错，而是直接返回
        await get_graph().ainvoke(initial, config=config)

        # 👇 2. 检查是否被中断暂停了
        state = await get_graph().aget_state(config)
        if state.next:
            # 说明被中断了，提取中断信息
            p = None
            for task in state.tasks:
                if hasattr(task, 'interrupts') and task.interrupts:
                    for intr in task.interrupts:
                        value = getattr(intr, "value", None)
                        if isinstance(value, dict):
                            p = {"action": value.get("action", "unknown"), "context": value.get("context", {})}
                            break
                    if p: break

            if not p:
                p = {"action": "web_search", "context": {"question": initial.get("question", "")}}

            hitl_data = {
                "thread_id": thread_id,
                "action": p.get("action", "unknown"),
                "context": p.get("context", {})
            }
            await queue.put(("hitl_pending", hitl_data))

    except GraphInterrupt as e:
        # 兼容某些特殊版本抛出异常的情况
        p = None
        for intr in getattr(e, "interrupts", []) or []:
            value = getattr(intr, "value", None) or intr
            if isinstance(value, dict):
                p = {"action": value.get("action", "unknown"), "context": value.get("context", {})}
                break
        hitl_data = {
            "thread_id": thread_id,
            "action": p.get("action", "unknown") if p else "unknown",
            "context": p.get("context", {}) if p else {}
        }
        await queue.put(("hitl_pending", hitl_data))
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error("chat graph failed: %s", e)
        await queue.put(("error", {"message": f"处理失败: {str(e)}"}))
async def _pump_queue(thread_id: str) -> AsyncIterator[tuple[str, dict]]:
    """消费流式队列并逐个产出 (event, data)，done / hitl_pending 后停止。"""
    queue = streaming.registry.get(thread_id)
    while True:
        try:
            event, data = await asyncio.wait_for(queue.get(), timeout=300)
        except asyncio.TimeoutError:
            logger.warning("chat queue timeout: thread=%s", thread_id)
            yield "error", {"message": "生成超时"}
            break
        yield event, data
        if event in ("done", "hitl_pending", "error"):
            break


async def run(
        db: Session,
        user_id: int,
        question: str,
        conversation_id: int | None,
        file_ids: list[int] | None,
        force_web: bool,
) -> AsyncIterator[tuple[str, dict]]:
    """发起一次问答。产出 SSE 事件流。"""
    thread_id = _make_thread_id()
    streaming.registry.new(thread_id)
    logger.info("chat.run start: user=%s file_ids=%s force_web=%s", user_id, file_ids, force_web)

    # 输入内容安全：敏感词 + Prompt 注入拦截
    try:
        filter_input(question)
    except ModerationError as e:
        yield "error", {"message": str(e)}
        streaming.registry.drop(thread_id)
        return

    # LLM 流控：每用户 RPM 滑动窗口
    if not llm_limiter.allow(user_id):
        yield "error", {"message": "请求过于频繁，请稍后再试"}
        streaming.registry.drop(thread_id)
        return

    if file_ids:
        owned = set(
            db.scalars(select(File.id).where(File.user_id == user_id, File.id.in_(file_ids))).all()
        )
        file_ids = list(owned)

    chat_history: list[dict[str, str]] = []
    if conversation_id:
        conv = db.get(Conversation, conversation_id)
        if conv and conv.user_id == user_id:
            conv.thread_id = thread_id
            db.commit()
            # 多轮对话记忆：滑动窗口取最近 N 轮（一问一答），倒序取后翻正
            rows = db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.id.desc())
                .limit(settings.MAX_HISTORY_TURNS * 2)
            ).all()
            chat_history = [
                {"role": m.role, "content": m.content[:1000]} for m in reversed(rows)
            ]

    # 👇 这里的 initial 字典一定要完整保留
    initial: ConsultState = {
        "question": question,
        "user_id": user_id,
        "file_ids": file_ids,
        "force_web": force_web,
        "conversation_id": conversation_id,
        "__thread_id__": thread_id,
        "chat_history": chat_history,
        "needs_web": False,
        "web_results": [],
        "web_search_skipped": False,
        "citations": {},
        "retrieval_hits": [],
    }

    task = asyncio.create_task(_run_graph(initial, thread_id))
    try:
        async for event, data in _pump_queue(thread_id):

            # 👇👇👇 核心绝杀：在发出前，强行给 data 字典塞入 thread_id！
            if event == "hitl_pending":
                data["thread_id"] = thread_id

            yield event, data
            if event == "done":
                logger.info("chat.run done: thread=%s answer_len=%s", thread_id, len(data.get("answer", "")))
                await _persist_message(db, conversation_id, user_id, question, data)
    finally:
        if not task.done():
            task.cancel()
        streaming.registry.drop(thread_id)
        logger.info("chat.run end: thread=%s", thread_id)


async def resume(thread_id: str, decision: HitlDecision) -> AsyncIterator[tuple[str, dict]]:
    """HITL 恢复：把用户决策写入图并继续执行。"""
    streaming.registry.new(thread_id)
    logger.info("chat.resume: thread=%s decision=%s", thread_id, decision.decision)

    payload = {"decision": decision.decision, "edited": decision.edited_prompt}
    config = _config(thread_id)

    async def _resume_graph():
        queue = streaming.registry.get(thread_id)
        try:
            await get_graph().ainvoke(Command(resume=payload), config=config)

            # 👇 恢复后再次检查是否有第二次中断（如 hitl_final）
            state = await get_graph().aget_state(config)
            if state.next:
                p = None
                for task in state.tasks:
                    if hasattr(task, 'interrupts') and task.interrupts:
                        for intr in task.interrupts:
                            value = getattr(intr, "value", None)
                            if isinstance(value, dict):
                                p = {"action": value.get("action", "unknown"), "context": value.get("context", {})}
                                break
                        if p: break
                if not p:
                    p = {"action": "final_generate_external", "context": {}}

                hitl_data = {
                    "thread_id": thread_id,
                    "action": p.get("action", "unknown"),
                    "context": p.get("context", {})
                }
                await queue.put(("hitl_pending", hitl_data))

        except GraphInterrupt as e:
            p = None
            for intr in getattr(e, "interrupts", []) or []:
                value = getattr(intr, "value", None) or intr
                if isinstance(value, dict):
                    p = {"action": value.get("action", "unknown"), "context": value.get("context", {})}
                    break
            hitl_data = {
                "thread_id": thread_id,
                "action": p.get("action", "unknown") if p else "unknown",
                "context": p.get("context", {}) if p else {}
            }
            await queue.put(("hitl_pending", hitl_data))
        except Exception as e:
            import traceback
            traceback.print_exc()
            await queue.put(("error", {"message": f"恢复失败: {str(e)}"}))

    task = asyncio.create_task(_resume_graph())
    try:
        async for event, data in _pump_queue(thread_id):
            if event == "hitl_pending":
                data["thread_id"] = thread_id
            yield event, data
    finally:
        if not task.done():
            task.cancel()
        streaming.registry.drop(thread_id)
        logger.info("chat.resume end: thread=%s", thread_id)

async def _persist_message(db: Session, conversation_id: int | None, user_id: int, question: str, data: dict) -> None:
    """把用户问题与最终答案（含引用）写入 messages 表。"""
    answer = data.get("answer", "")
    citations = data.get("citations", [])
    if conversation_id is None:
        conv = Conversation(user_id=user_id, title=question[:50], thread_id=None)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        conversation_id = conv.id
    db.add(Message(conversation_id=conversation_id, role="user", content=question))
    db.add(
        Message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            citations_json=json.dumps(citations, ensure_ascii=False),
        )
    )
    db.commit()