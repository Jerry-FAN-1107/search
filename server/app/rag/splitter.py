"""分段策略：按格式区分切分规则，产出带统一元数据的 Chunk。

元数据字段（需求3）：file_id, file_name, page_or_sheet_or_slide, chunk_index
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .parser import ParsedUnit


@dataclass
class Chunk:
    text: str
    file_id: int
    file_name: str
    location: str              # page=x / sheet=name / slide=x
    chunk_index: int = 0
    user_id: int | None = None  # 归属用户：向量层跨用户隔离的依据
    metadata: dict = field(default_factory=dict)


def chunkize(
    units: list[ParsedUnit],
    *,
    file_id: int,
    file_name: str,
    file_type: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """按格式调用对应的分段策略。"""
    if file_type == "xlsx":
        chunks = _chunk_excel(units, file_id=file_id, file_name=file_name)
    elif file_type == "pptx":
        chunks = _chunk_pptx(units, file_id=file_id, file_name=file_name)
    else:
        chunks = _chunk_semantic(
            units, file_id=file_id, file_name=file_name, chunk_size=chunk_size, overlap=overlap
        )
    for i, c in enumerate(chunks):
        c.chunk_index = i
        c.metadata = {
            "file_id": file_id,
            "file_name": file_name,
            "page_or_sheet_or_slide": c.location,
            "chunk_index": i,
        }
    return chunks


def _chunk_semantic(
    units: list[ParsedUnit], *, file_id: int, file_name: str, chunk_size: int, overlap: int
) -> list[Chunk]:
    """PDF/Word：以标题为强边界，段落聚合；超长时按字符窗口重叠切分。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    groups: list[str] = []
    buf: list[str] = []
    for u in units:
        is_heading = u.location.startswith("heading")
        if is_heading and buf:
            groups.append("\n".join(buf))
            buf = [u.text]
        else:
            buf.append(u.text)
    if buf:
        groups.append("\n".join(buf))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "；", " "],
    )
    chunks: list[Chunk] = []
    for g in groups:
        parts = splitter.split_text(g)
        for part in parts:
            if part.strip():
                loc = next((u.location for u in units if u.text in part), units[0].location)
                chunks.append(Chunk(text=part, file_id=file_id, file_name=file_name, location=loc))
    return chunks


def _chunk_excel(units: list[ParsedUnit], *, file_id: int, file_name: str) -> list[Chunk]:
    """Excel：sheet -> 行组切分（每个 sheet 内按固定行数分块）。"""
    chunks: list[Chunk] = []
    ROWS_PER_GROUP = 30
    for u in units:
        lines = u.text.split("\n")
        for start in range(0, len(lines), ROWS_PER_GROUP):
            group = "\n".join(lines[start : start + ROWS_PER_GROUP])
            if group.strip():
                chunks.append(
                    Chunk(text=group, file_id=file_id, file_name=file_name, location=u.location)
                )
    return chunks


def _chunk_pptx(units: list[ParsedUnit], *, file_id: int, file_name: str) -> list[Chunk]:
    """PPT：按 slide 切分，每个 slide 为一个 chunk（长 slide 按字符切）。"""
    chunks: list[Chunk] = []
    for u in units:
        if len(u.text) <= 600:
            chunks.append(Chunk(text=u.text, file_id=file_id, file_name=file_name, location=u.location))
        else:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

            splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
            for part in splitter.split_text(u.text):
                if part.strip():
                    chunks.append(
                        Chunk(text=part, file_id=file_id, file_name=file_name, location=u.location)
                    )
    return chunks