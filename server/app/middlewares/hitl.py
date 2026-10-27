"""HITL（Human-in-the-Loop）审批中间件。

职责：把“人工审批暂停点”集中收敛到本模块，供 agents 图节点调用，
禁止在各工具函数里散写 interrupt / resume 逻辑。

基于 LangGraph 的 interrupt + checkpointer：
- 节点调用 require_approval(...) 时，若 HITL 开启，则 interrupt 暂停并保存图状态；
- 前端展示待确认卡片，用户做出 approve / edit / reject 决策后，通过 resume 恢复；
- resume 返回的是决策结果（含用户可能编辑过的内容），由各节点据此继续。
"""
from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)

APPROVE = "approve"
EDIT = "edit"
REJECT = "reject"
ALLOWED = {APPROVE, EDIT, REJECT}


def require_approval(action: str, context: dict[str, Any]) -> dict[str, Any]:
    """请求一次人工审批。"""
    if not settings.HITL_ENABLED:
        logger.info("hitl disabled -> auto approve action=%s", action)
        return {"decision": APPROVE, "edited": None}

    logger.info("hitl.require_approval pause: action=%s", action)
    decision = interrupt(
        {
            "type": "hitl_approval",
            "action": action,
            "context": context,
        }
    )
    result = normalize_decision(decision, action)
    logger.info("hitl decision: action=%s decision=%s", action, result["decision"])
    return result


def normalize_decision(decision: Any, action: str) -> dict[str, Any]:
    """把用户提交的任意格式决策归一化为标准结构。"""
    if isinstance(decision, str):
        d = decision.lower()
        if d not in ALLOWED:
            d = REJECT
        return {"decision": d, "edited": None}
    if isinstance(decision, dict):
        d = str(decision.get("decision", REJECT)).lower()
        if d not in ALLOWED:
            d = REJECT
        return {"decision": d, "edited": decision.get("edited")}
    return {"decision": REJECT, "edited": None}