"""表格生成业务逻辑（需求8预留扩展点）。

本期不实现完整功能，仅提供 schema 注册入口与占位接口，供前端“表单生成”页与 Agent 工具层对接。
"""
from __future__ import annotations

from typing import Any

from ..agents.tools import TOOL_HANDLERS, get_tool_schemas


async def generate_table(format_text: str, data_source: list[dict[str, Any]]) -> dict[str, Any]:
    """调用已注册的 table_generator 工具（占位）。"""
    return await TOOL_HANDLERS["table_generator"](format_text, data_source)


def table_tool_schema() -> dict[str, Any]:
    """返回 table_generator 工具的 schema（已预注册）。"""
    for s in get_tool_schemas():
        if s["function"]["name"] == "table_generator":
            return s
    raise KeyError("table_generator 未注册")