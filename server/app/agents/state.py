"""LangGraph 图状态（TypedDict）。"""
from __future__ import annotations

from typing import Any, TypedDict


class ConsultState(TypedDict, total=False):
    # 输入
    question: str
    user_id: int
    file_ids: list[int] | None
    force_web: bool
    conversation_id: int | None
    __thread_id__: str   # 流式队列与 HITL 恢复的线程标识

    # 多轮对话记忆（滑动窗口截断后的历史消息：[{role, content}]）
    chat_history: list[dict[str, str]]

    # RAG 检索
    retrieval_hits: list[dict[str, Any]]      # [{text,file_name,location,distance,ref}]
    citations: dict[int, dict[str, Any]]      # ref -> {file_name,location,source_type,...}

    # 联网判断与结果
    needs_web: bool
    web_results: list[dict[str, Any]]         # [{title,url,snippet,ref}]
    web_search_skipped: bool

    # 生成
    final_answer: str
    reasoning: str