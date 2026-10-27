"""豆包模型统一客户端。

规则：所有与豆包模型的交互（流式对话、function calling、思考过程 reasoning_content 透传、向量化）一律经过本文件，
禁止在 services/agents/rag 各处散写 HTTP 请求。

通过火山方舟（Volcengine Ark）的 OpenAI 兼容接口访问，模型名/API Key/Base URL 全部取自环境变量。
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

from openai import AsyncOpenAI

from .core.config import settings
from .core.logging import get_logger

logger = get_logger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.DOUBAO_API_KEY:
            raise RuntimeError("未配置 DOUBAO_API_KEY，请在 .env 中填写")
        _client = AsyncOpenAI(
            api_key=settings.DOUBAO_API_KEY,
            base_url=settings.DOUBAO_BASE_URL,
        )
        logger.info("llm client initialized: base_url=%s", settings.DOUBAO_BASE_URL)
    return _client

_embedding_client: AsyncOpenAI | None = None

def _get_embedding_client() -> AsyncOpenAI:
    global _embedding_client
    if _embedding_client is None:
        import os
        base_url = os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434/v1")
        api_key = os.getenv("EMBEDDING_API_KEY", "ollama")
        _embedding_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info("embedding client initialized: base_url=%s", base_url)
    return _embedding_client
def _record_usage(
    user_id: int | None,
    kind: Literal["chat", "embedding"],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Token 用量落库 + Prometheus 计数（双重 try，失败静默降级，不影响主流程）。"""
    try:
        from .core import observability

        observability.record_llm_tokens(kind, prompt_tokens, completion_tokens)
    except Exception:
        logger.warning("record usage to metrics failed", exc_info=True)
    try:
        from .core.database import SessionLocal
        from .models.llm_usage import LlmUsage

        with SessionLocal() as db:
            db.add(
                LlmUsage(
                    user_id=user_id,
                    kind=kind,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            )
            db.commit()
    except Exception:
        logger.warning("record usage to db failed", exc_info=True)


# ---------- 流式事件 ----------
class StreamEvent:
    """一次流式回调的粒度单元。"""

    __slots__ = ("kind", "text", "reasoning", "tool_calls", "finish")

    def __init__(
        self,
        kind: Literal["reasoning", "token", "tool_calls", "done"],
        text: str = "",
        reasoning: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        finish: str | None = None,
    ):
        self.kind = kind
        self.text = text
        self.reasoning = reasoning
        self.tool_calls = tool_calls
        self.finish = finish


async def stream_chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    thinking: bool = True,
    temperature: float = 0.3,
    user_id: int | None = None,
) -> AsyncIterator[StreamEvent]:
    """流式调用豆包对话/思考模型，逐个产出 StreamEvent。

    - kind="reasoning"：思考过程（reasoning_content）片段，供 SSE 的 thinking 事件透传。
    - kind="token"    ：正文逐字输出。
    - kind="tool_calls"：一次 function calling 请求。
    - kind="done"     ：本轮流结束，携带 finish_reason。

    user_id 用于 Token 用量落库（成本核算），可空。
    """
    client = _get_client()
    model = settings.DOUBAO_THINKING_MODEL if (thinking and settings.DOUBAO_THINKING_MODEL) else settings.DOUBAO_CHAT_MODEL

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
        "stream_options": {"include_usage": True},   # 末帧携带 token 用量
    }
    if tools:
        kwargs["tools"] = tools

    logger.info("llm.stream_chat start: model=%s tools=%s", model, bool(tools))
    stream = await client.chat.completions.create(**kwargs)

    # 工具调用可能分片到达，需要累积
    pending_tool: dict[str, Any] | None = None
    usage: Any = None
    async for chunk in stream:
        if not chunk.choices:
            # include_usage 开启后，最后一个空 choices 的 chunk 携带 usage
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage
            continue
        delta = chunk.choices[0].delta

        # 思考过程透传
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield StreamEvent(kind="reasoning", reasoning=reasoning)
            continue

        # function calling：累积 tool_call 片段
        if delta.tool_calls:
            for tc in delta.tool_calls:
                if pending_tool is None:
                    pending_tool = {
                        "id": tc.id or "",
                        "name": tc.function.name or "",
                        "arguments": "",
                    }
                if tc.function:
                    pending_tool["name"] = pending_tool["name"] or tc.function.name or ""
                    if tc.function.arguments:
                        pending_tool["arguments"] += tc.function.arguments
                if tc.id:
                    pending_tool["id"] = tc.id
            continue

        if delta.content:
            if pending_tool is not None:
                # 工具调用之后不应再有正文，防御性处理
                pending_tool = None
            yield StreamEvent(kind="token", text=delta.content)
            continue

        finish_reason = chunk.choices[0].finish_reason
        if pending_tool is not None and (finish_reason or chunk.choices[0].index == 0):
            yield StreamEvent(kind="tool_calls", tool_calls=[pending_tool])
            pending_tool = None
            if finish_reason:
                yield StreamEvent(kind="done", finish=finish_reason)
            continue

        if finish_reason:
            yield StreamEvent(kind="done", finish=finish_reason)

    # 流结束：记录 Token 用量（成本核算）
    if usage is not None:
        _record_usage(
            user_id, "chat", model,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )


async def chat(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    thinking: bool = False,
    temperature: float = 0.2,
) -> str:
    """非流式调用，返回完整正文（用于不需要逐字输出的环节，如判断/提炼）。"""
    client = _get_client()
    model = settings.DOUBAO_CHAT_MODEL
    logger.info("llm.chat: model=%s tools=%s", model, bool(tools))
    if tools is None:
        resp = await client.chat.completions.create(
            model=model, messages=messages, temperature=temperature
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            _record_usage(
                None, "chat", model,
                getattr(usage, "prompt_tokens", 0) or 0,
                getattr(usage, "completion_tokens", 0) or 0,
            )
        return resp.choices[0].message.content or ""
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "tools": tools, "temperature": temperature}
    resp = await client.chat.completions.create(**kwargs)
    usage = getattr(resp, "usage", None)
    if usage is not None:
        _record_usage(
            None, "chat", model,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
        )
    msg = resp.choices[0].message
    if msg.tool_calls:
        return json.dumps([tc.model_dump() for tc in msg.tool_calls], ensure_ascii=False)
    return msg.content or ""


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """文本向量化（专用本地 Ollama 模型）。"""
    if not settings.DOUBAO_EMBEDDING_MODEL:
        raise RuntimeError("未配置 DOUBAO_EMBEDDING_MODEL")
    # 👇 改用 embedding 客户端
    client = _get_embedding_client()
    logger.info("llm.embed: n=%s", len(texts))
    resp = await client.embeddings.create(model=settings.DOUBAO_EMBEDDING_MODEL, input=texts)
    usage = getattr(resp, "usage", None)
    if usage is not None:
        _record_usage(
            None, "embedding", settings.DOUBAO_EMBEDDING_MODEL,
            getattr(usage, "prompt_tokens", 0) or 0, 0,
        )
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in ordered]