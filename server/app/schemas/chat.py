"""问答/SSE/HITL 相关请求与事件模型。

SSE 事件协议（事件名 -> data JSON）：
- thinking     {reasoning: str}                    思考过程片段（可折叠展示）
- token        {text: str}                         正文逐字输出
- tool_status  {tool: str, message: str}           正在调用哪个工具/检索哪份文件
- citation     {ref: int, file_name, location, source_type}  引用映射
- hitl_pending {thread_id, action, context}        待人工确认
- done         {citations: [...]}                  结束 + 完整引用列表
- error        {message: str}                      错误
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    FILE = "file"
    WEB = "web"


class ChatRequest(BaseModel):
    """发起问答的请求体。"""
    question: str = Field(min_length=1)
    conversation_id: int | None = None   # 空则新建会话
    file_ids: list[int] | None = None    # 空则检索该用户全部文件
    force_web: bool = False              # 调试用：强制联网


class Citation(BaseModel):
    """一条引用：编号 -> 来源。"""
    ref: int
    file_name: str
    location: str = ""                   # page / sheet / slide 位置
    source_type: SourceType = SourceType.FILE
    title: str = ""
    url: str = ""
    file_id: int | None = None           # 文件来源时携带，供前端打开原文定位


class HitlDecision(BaseModel):
    """HITL 人工决策提交。"""
    thread_id: str
    decision: str = Field(..., pattern="^(approve|edit|reject)$")
    edited_prompt: str | None = None     # decision=edit 时携带修改后的内容/参数
    action: str | None = None            # 原始待审批动作，供校验


class ChatDone(BaseModel):
    citations: list[Citation] = []
    answer: str = ""


class SSEEvent(BaseModel):
    event: str
    data: dict[str, Any]
