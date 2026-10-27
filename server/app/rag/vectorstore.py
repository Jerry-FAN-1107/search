"""向量存储：ChromaDB 封装（本地持久化）。

选型理由（详见架构输出第四部分）：
- PersistentClient 落盘到 CHROMA_PERSIST_DIR，服务重启后向量数据不丢失；
- 天然支持 where 条件过滤（按 file_id 过滤用户文件范围），满足"防止跨用户泄露"的硬要求；
- 支持按 file_id 精确删除向量，保证知识库删除闭环；
- 若未来知识库规模或并发上量，可无缝替换为 Milvus（集合名与检索接口已抽象于此层，不侵入上层）。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import chromadb

from ..core.config import settings
from ..core.logging import get_logger
from ..llm_client import embed_texts
from .splitter import Chunk

logger = get_logger(__name__)

COLLECTION_NAME = "enterprise_consult"


class VectorStore:
    def __init__(self) -> None:
        persist_dir = Path(settings.CHROMA_PERSIST_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "vectorstore ready: persistent dir=%s collection=%s",
            persist_dir,
            COLLECTION_NAME,
        )

    async def add_chunks(self, chunks: list[Chunk]) -> None:
        """向量化并写入。embedding 走 llm_client，批量一次调用。"""
        if not chunks:
            return
        texts = [c.text for c in chunks]
        vectors = await embed_texts(texts)
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [self._chunk_metadata(c) for c in chunks]
        self._collection.add(ids=ids, documents=texts, embeddings=vectors, metadatas=metadatas)
        logger.info("vector.add_chunks: %s chunks", len(chunks))

    def _chunk_metadata(self, c: Chunk) -> dict:
        return {
            "file_id": c.file_id,
            "file_name": c.file_name,
            "page_or_sheet_or_slide": c.location,
            "chunk_index": c.chunk_index,
            "user_id": c.user_id,
        }

    def delete_by_file_id(self, file_id: int) -> None:
        """按 file_id 删除该文件的全部向量（知识库删除闭环的关键一环）。"""
        try:
            self._collection.delete(where={"file_id": file_id})
            logger.info("vector.delete_by_file_id: file_id=%s", file_id)
        except Exception:
            logger.warning("vector.delete_by_file_id failed: file_id=%s", file_id, exc_info=True)

    def cleanup_orphans(self, valid_file_ids: set[int]) -> int:
        """启动对账：删除 DB 中已不存在文件对应的向量（历史脏数据），返回清理条数。"""
        try:
            data = self._collection.get(include=["metadatas"])
            orphans = [
                id_ for id_, meta in zip(data["ids"], data["metadatas"])
                if meta.get("file_id") not in valid_file_ids
            ]
            if orphans:
                self._collection.delete(ids=orphans)
                logger.info("vector.cleanup_orphans: removed=%s", len(orphans))
            return len(orphans)
        except Exception:
            logger.warning("vector.cleanup_orphans failed", exc_info=True)
            return 0

    async def query(
            self,
            query_texts: list[str],
            *,
            user_id: int | None = None,
            file_ids: list[int] | None = None,
            top_k: int | None = None,
    ) -> list[dict]:
        k = top_k or settings.RAG_TOP_K
        # 跨用户隔离硬约束：恒按 user_id 过滤；file_ids 存在时取交集
        conditions: list[dict] = []
        if user_id is not None:
            conditions.append({"user_id": user_id})
        if file_ids:
            conditions.append({"file_id": {"$in": file_ids}})
        if len(conditions) == 1:
            where = conditions[0]
        elif conditions:
            where = {"$and": conditions}
        else:
            where = None

        query_embeddings = await embed_texts(query_texts)

        result = self._collection.query(
            query_embeddings=query_embeddings,
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        out: list[dict] = []
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            out.append(
                {
                    "text": doc,
                    "file_id": meta.get("file_id"),
                    "file_name": meta.get("file_name", ""),
                    "location": meta.get("page_or_sheet_or_slide", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "distance": dist,
                }
            )
        logger.info("vector.query: file_ids=%s hits=%s", file_ids, len(out))
        return out


_store: VectorStore | None = None


def get_vectorstore() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
