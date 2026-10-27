"""LangGraph 图节点：retrieve / rerank / judge / hitl_search / search / hitl_final / generate。"""
from __future__ import annotations

import json
import re
from typing import Any

from ..core.config import settings
from ..core.logging import get_logger
from ..core.moderation import filter_output
from ..core.ratelimit import llm_limiter
from ..llm_client import chat, stream_chat
from ..middlewares import hitl
from ..rag.retriever import Retriever, assign_refs
from ..schemas.chat import SourceType
from . import streaming
from .state import ConsultState
from .tools import TOOL_HANDLERS

logger = get_logger(__name__)


async def retrieve(state: ConsultState) -> dict[str, Any]:
    """节点1：RAG 向量召回（按 user 文件范围过滤）。引用编号在 rerank 节点统一分配。"""
    question = state["question"]
    file_ids = state.get("file_ids")
    retriever = Retriever(question, file_ids, user_id=state["user_id"])
    hits = await retriever.retrieve(top_k=settings.RAG_RECALL_TOP_K)
    logger.info("agent.retrieve: recall=%s file_ids=%s", len(hits), file_ids)
    return {"retrieval_hits": hits, "citations": {}}


async def rerank(state: ConsultState) -> dict[str, Any]:
    """节点2：Rerank 精排。对召回的 Top N 用 LLM 挑选最相关片段，截断至 RAG_TOP_K。

    关闭开关或召回量未超限时，直接按距离序截断；LLM 精排失败时回退距离序，
    保证该节点永远可用。引用编号在截断后统一分配。
    """
    hits = list(state.get("retrieval_hits") or [])
    if not hits:
        return {"retrieval_hits": [], "citations": {}}

    if settings.RAG_RERANK_ENABLED and len(hits) > settings.RAG_TOP_K:
        try:
            picked = await _llm_pick(state["question"], hits)
            picked = [i for i in picked if 0 <= i < len(hits)]
            if picked:
                hits = [hits[i] for i in picked]
        except Exception:
            logger.warning("agent.rerank: llm pick failed, fallback to distance order", exc_info=True)

    hits = hits[: settings.RAG_TOP_K]
    hits, citations = assign_refs(hits)
    logger.info("agent.rerank: kept=%s", len(hits))
    return {"retrieval_hits": hits, "citations": citations}


async def _llm_pick(question: str, hits: list[dict[str, Any]]) -> list[int]:
    """让 LLM 从召回片段中挑出最相关的序号（JSON 数组）。"""
    catalog = "\n".join(
        f"{i}. ({h['file_name']} {h['location']}) {h['text'][:200]}" for i, h in enumerate(hits)
    )
    raw = await chat(
        [
            {
                "role": "system",
                "content": (
                    "你是检索结果重排器。根据用户问题，从给定编号的资料片段中选出最相关、"
                    f"最能回答问题的至多 {settings.RAG_TOP_K} 条。"
                    "只输出一个 JSON 数组，元素为片段编号（整数），按相关度从高到低排列，不要输出任何其他内容。"
                ),
            },
            {"role": "user", "content": f"用户问题：{question}\n\n资料片段：\n{catalog}"},
        ],
        temperature=0.0,
    )
    match = re.search(r"\[[\s\S]*\]", raw)
    if not match:
        return []
    data = json.loads(match.group(0))
    return [int(x) for x in data if isinstance(x, (int, float))]


async def judge(state: ConsultState) -> dict[str, Any]:
    """节点3：判断是否需要联网。触发条件见 Retriever.needs_web（写死）。"""
    question = state["question"]
    hits = state.get("retrieval_hits", [])
    retriever = Retriever(question, state.get("file_ids"))
    needs_web = bool(state.get("force_web")) or await retriever.needs_web(hits)
    logger.info("agent.judge: needs_web=%s", needs_web)
    return {"needs_web": needs_web}


async def hitl_search(state: ConsultState) -> dict[str, Any]:
    """节点4：联网搜索发起前的 HITL 强制暂停（需求7①）。"""
    # 直接调用 require_approval，底层会抛出 GraphInterrupt 暂停
    decision = hitl.require_approval("web_search", {"question": state["question"]})
    logger.info("agent.hitl_search decision: %s", decision["decision"])
    if decision["decision"] == hitl.REJECT:
        return {"needs_web": False, "web_search_skipped": True}
    if decision["decision"] == hitl.EDIT and decision.get("edited"):
        return {"question": decision["edited"]}
    return {"needs_web": True}


async def search(state: ConsultState) -> dict[str, Any]:
    """节点5：执行联网搜索，搜索结果分配引用编号并标记来源类型 web。"""
    thread_id = state["__thread_id__"]
    if state.get("web_search_skipped"):
        return {"web_search_skipped": True}
    await streaming.emit(thread_id, "tool_status", {"tool": "web_search", "message": "正在联网搜索外部资料…"})
    results = await TOOL_HANDLERS["web_search"](state["question"])
    logger.info("agent.search: results=%s", len(results))
    citations: dict[int, dict[str, Any]] = dict(state.get("citations") or {})
    next_ref = max(citations.keys(), default=0) + 1
    refs: list[dict[str, Any]] = []
    for r in results:
        ref = next_ref
        next_ref += 1
        r["ref"] = ref
        refs.append(r)
        citations[ref] = {
            "ref": ref,
            "file_name": r["title"],
            "location": "web",
            "source_type": SourceType.WEB.value,
            "title": r["title"],
            "url": r["url"],
            "file_id": None,
        }
    return {"web_results": refs, "citations": citations}


async def hitl_final(state: ConsultState) -> dict[str, Any]:
    """节点6：基于外部信息生成最终答案前，HITL 强制暂停（需求7②）。"""
    if not state.get("web_results"):
        return {"web_results": []}

    decision = hitl.require_approval("final_generate_external", {})
    logger.info("agent.hitl_final decision: %s", decision["decision"])
    if decision["decision"] == hitl.REJECT:
        return {"web_results": []}
    if decision["decision"] == hitl.EDIT and decision.get("edited"):
        return {"question": f"{state['question']}\n（用户补充指令：{decision['edited']}）"}
    return {"needs_web": True}


async def generate(state: ConsultState) -> dict[str, Any]:
    """节点7：流式生成最终答案，产出 thinking / token / citation / done 事件。"""
    thread_id = state["__thread_id__"]
    citations: dict[int, dict[str, Any]] = state.get("citations") or {}
    hits = state.get("retrieval_hits", [])
    web = state.get("web_results", [])

    context_parts: list[str] = []
    for h in hits:
        context_parts.append(
            f"[{h['ref']}] (文件:{h['file_name']}, 位置:{h['location']})\n{h['text']}"
        )
    for w in web:
        context_parts.append(f"[{w['ref']}] (网页:{w['title']} <{w['url']}>)\n{w['snippet']}")

    system = (
        "你是企业信息咨询助手。严格依据提供的带编号资料作答，禁止凭记忆编造外部信息。"
        "每条事实性论断必须在句子末尾标注对应的引用编号，格式为 [编号]，例如“该材料采购周期为7天[1]”。"
        "若某句话没有任何资料支撑，不要编造，应明确说明‘现有资料未覆盖该点’。"
        "对话历史中可能出现指代（如“刚才那个文件”“它的第三点”），请结合历史理解用户当前问题。"
    )
    user = (
        f"用户问题：{state['question']}\n\n"
        f"可用资料（文件与网页，均带引用编号）：\n\n" + "\n\n".join(context_parts)
        if context_parts
        else f"用户问题：{state['question']}\n\n当前无可用检索资料，请如实说明。"
    )
    # 多轮对话记忆：system + 历史（滑动窗口已在入口处截断） + 本轮提问
    history = state.get("chat_history") or []
    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]

    for ref, meta in citations.items():
        await streaming.emit(thread_id, "citation", meta)

    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    # 全局并发信号量：限制同时在飞的 LLM 流式请求数
    async with llm_limiter.semaphore():
        async for ev in stream_chat(messages, thinking=True, user_id=state.get("user_id")):
            if ev.kind == "reasoning":
                reasoning_parts.append(ev.reasoning)
                await streaming.emit(thread_id, "thinking", {"reasoning": ev.reasoning})
            elif ev.kind == "token":
                answer_parts.append(ev.text)
                await streaming.emit(thread_id, "token", {"text": ev.text})
            elif ev.kind == "done":
                break

    # 输出内容安全：敏感词打码后落库与推送
    answer = filter_output("".join(answer_parts))
    logger.info("agent.generate done: answer_len=%s citations=%s", len(answer), len(citations))
    await streaming.emit(
        thread_id,
        "done",
        {"citations": list(citations.values()), "answer": answer},
    )
    return {
        "final_answer": answer,
        "reasoning": "".join(reasoning_parts),
        "messages": messages,
    }
