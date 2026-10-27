"""文件上传相关响应模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FileOut(BaseModel):
    id: int
    file_name: str
    file_type: str
    size_bytes: int
    parse_status: str
    chunk_count: int
    created_at: datetime
    # 上传时命中相似旧文件（相似度 >= 90%）时返回，提示用户可能存在新旧版本
    similar_file_id: int | None = None
    similar_to: str | None = None
    similarity: float | None = None

    model_config = {"from_attributes": True}


class FileListOut(BaseModel):
    items: list[FileOut]
