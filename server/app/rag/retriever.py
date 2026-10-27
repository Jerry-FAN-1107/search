"""RAG 检索器：检索 + 引用编号分配 + 相似度阈值判断。"""
from __future__ import annotations

from ..core.config import settings
from ..core.logging import get_logger
from ..llm_client import chat
from .vectorstore import get_vectorstore

logger = get_logger(__name__)


class Retriever:
    def __init__(self, question: str, file_ids: list[int] | None, user_id: int | None = None) -> None:
        self.question = question
        self.file_ids = file_ids
        self.user_id = user_id

    async def retrieve(self, top_k: int | None = None) -> list[dict]:
        vs = get_vectorstore()
        hits = await vs.query([self.question], user_id=self.user_id, file_ids=self.file_ids, top_k=top_k)
        hits.sort(key=lambda h: h["distance"])
        logger.info("rag.retrieve: question_len=%s hits=%s", len(self.question), len(hits))
        return hits

    async def needs_web(self, hits: list[dict]) -> bool:
        """判断是否需要联网搜索。触发条件写死：
        1) 无命中；或 2) 最佳命中相似度低于阈值；或 3) 模型判定资料不足。"""
        if not hits:
            logger.info("rag.needs_web: no hits -> True")
            return True
        best = hits[0]["distance"]
        if best > settings.RAG_SIMILARITY_THRESHOLD:
            logger.info("rag.needs_web: best_dist=%.3f > %.3f -> True", best, settings.RAG_SIMILARITY_THRESHOLD)
            return True
        try:
            verdict = await chat(
                [
                    {
                        "role": "system",
                        "content": "你只回答是或否。根据给定的检索摘要，判断是否足以回答用户问题。若检索资料缺失关键信息，回答：是；否则回答：否。",
                    },
                    {
                        "role": "user",
                        "content": f"用户问题：{self.question}\n检索资料摘要：{self._summarize(hits)}",
                    },
                ]
            )
            need = verdict.strip().startswith("是")
            logger.info("rag.needs_web: model_verdict=%s", need)
            return need
        except Exception:
            logger.warning("rag.needs_web: model judge failed, fallback False", exc_info=True)
            return False

    @staticmethod
    def _summarize(hits: list[dict]) -> str:
        return "\n---\n".join(h[:400] for h in [x["text"] for x in hits[:3]])


def assign_refs(hits: list[dict]) -> tuple[list[dict], dict[int, dict]]:
    """为检索结果分配引用编号。返回 (带 ref 的 hits, ref->元信息映射)。"""
    mapping: dict[int, dict] = {}
    start = 1
    for i, hit in enumerate(hits, start=start):
        hit["ref"] = i
        mapping[i] = {
            "ref": i,
            "file_name": hit["file_name"],
            "location": hit["location"],
            "source_type": "file",
            "title": hit["file_name"],
            "url": "",
            "file_id": hit.get("file_id"),
        }
    return hits, mapping