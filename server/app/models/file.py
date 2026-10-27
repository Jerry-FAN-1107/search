"""files 表：上传文件的元数据，外键关联 users.id，保证文件归属与隔离。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.database import Base


class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 存于服务端的相对路径（UPLOAD_DIR 之下）
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)  # docx/pdf/xlsx/pptx
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 解析状态：pending/parsing/ready/failed
    parse_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 内容指纹：SHA-256（精确去重）+ SimHash 64 位十六进制（相似度检测）
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    simhash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="files")  # noqa: F821

    def __repr__(self) -> str:
        return f"<File id={self.id} name={self.file_name} user={self.user_id}>"
