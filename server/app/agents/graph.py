"""LangGraph 图装配：定义节点、条件边与 HITL 暂停点。

图在应用启动时（main.lifespan 完成 checkpointer 初始化后）通过 init_graph()
编译，避免模块导入期即绑定 checkpointer，保证可替换为持久化实现。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from langgraph.graph import END, START, StateGraph

from .checkpointer import get_checkpointer
from .nodes import generate, hitl_final, hitl_search, judge, retrieve, rerank, search
from .state import ConsultState

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


def _route_after_judge(state: ConsultState) -> Literal["hitl_search", "generate"]:
    # needs_web=True -> 走 HITL 联网审批；否则直接生成
    return "hitl_search" if state.get("needs_web") else "generate"


def _route_after_search(state: ConsultState) -> Literal["hitl_final", "generate"]:
    # 有外部结果 -> 生成前再 HITL；无结果则直接生成（仅文件资料）
    return "hitl_final" if state.get("web_results") else "generate"


def build_graph() -> "CompiledStateGraph":
    g = StateGraph(ConsultState)

    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank)
    g.add_node("judge", judge)
    g.add_node("hitl_search", hitl_search)
    g.add_node("search", search)
    g.add_node("hitl_final", hitl_final)
    g.add_node("generate", generate)

    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "judge")
    g.add_conditional_edges(
        "judge", _route_after_judge, {"hitl_search": "hitl_search", "generate": "generate"}
    )
    g.add_edge("hitl_search", "search")
    g.add_conditional_edges(
        "search", _route_after_search, {"hitl_final": "hitl_final", "generate": "generate"}
    )
    g.add_edge("hitl_final", "generate")
    g.add_edge("generate", END)

    return g.compile(checkpointer=get_checkpointer())


_graph: "CompiledStateGraph | None" = None


def init_graph() -> None:
    """在 checkpointer 就绪后编译图（应用启动时调用一次）。"""
    global _graph
    if _graph is None:
        _graph = build_graph()


def get_graph() -> "CompiledStateGraph":
    """取编译后的图；未初始化说明启动流程异常。"""
    if _graph is None:
        raise RuntimeError("graph 未初始化：请先在应用启动时调用 init_graph()")
    return _graph