"""Agent 工具注册表：统一声明工具 schema 与可调用处理器。

规则：Agent 要使用的任何工具（联网搜索、表格生成、写操作守卫）都先在此注册 schema，
禁止在 nodes/其他模块里散写工具定义。当前：
- web_search      已实现，供 search 节点调用；
- table_generator 已注册 schema，本期预留扩展点（需求8），handler 为占位；
- export_table    写操作守卫示例：任何“保存/导出”类写操作必须经 HITL 审批。
"""
from __future__ import annotations

from typing import Any, Callable

import httpx

from ..core.config import settings
from ..middlewares import hitl


# ---------- 联网搜索 ----------
async def _web_search(query: str, *, num: int = 5) -> list[dict[str, str]]:
    """调用联网搜索，返回 [{title,url,snippet}]。未配置 API 时返回空并打点。"""
    if not settings.SEARCH_API_KEY or not settings.SEARCH_BASE_URL:
        # 未配置搜索 API：返回空结果，Agent 侧将回退到“仅文件资料”。
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                settings.SEARCH_BASE_URL,
                headers={
                    "X-API-KEY": settings.SEARCH_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": num},
            )
            resp.raise_for_status()
            data = resp.json()
        organic = data.get("organic", data.get("results", []))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("link", r.get("url", "")),
                "snippet": r.get("snippet", ""),
            }
            for r in organic[:num]
        ]
    except Exception:
        return []


# ---------- 表格生成（预留） ----------
async def _table_generator_stub(
    format_text: str, data_source: list[dict[str, Any]]
) -> dict[str, Any]:
    """需求8预留：格式说明文本 + 数据来源 -> 结构化表格 JSON。

    本期不实现完整逻辑，仅返回占位结构。后续接入时在此填充 LLM 调用（经 llm_client）。
    """
    # 写操作守卫：导出/保存表格属于“写操作”，强制走 HITL
    decision = hitl.require_approval(
        "export_table", {"format_text": format_text, "rows_hint": len(data_source)}
    )
    if decision["decision"] == hitl.REJECT:
        return {"status": "rejected", "table": None}
    return {"status": "ok", "table": {"columns": [], "rows": []}}


# ---------- 工具注册表 ----------
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索外部信息，返回带 title/url/snippet 的结果。仅在现有资料不足以回答时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "table_generator",
            "description": "根据格式说明文本与数据来源生成结构化表格 JSON。",
            "parameters": {
                "type": "object",
                "properties": {
                    "format_text": {"type": "string", "description": "表格格式说明"},
                    "data_source": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["format_text"],
            },
        },
    },
]

# 名称 -> 可调用处理器（供节点使用）
TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "web_search": _web_search,
    "table_generator": _table_generator_stub,
}


def get_tool_schemas() -> list[dict[str, Any]]:
    return TOOL_SCHEMAS