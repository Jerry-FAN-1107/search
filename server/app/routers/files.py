"""文件路由：上传（异步解析）/ 列表 / 原文下载 / 删除。

user_id 一律取自 JWT（get_current_user），保证文件归属隔离（防 IDOR）。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.user import User
from ..schemas.file import FileListOut, FileOut
from ..services import file_service

router = APIRouter(prefix="/files", tags=["files"])

_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@router.post("/upload", response_model=FileOut, status_code=201)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileOut:
    """上传文件：落盘后立即返回（parse_status=pending），解析向量化在后台异步执行。

    前端轮询 GET /files 观察 parse_status 流转：pending -> parsing -> ready/failed。
    内容完全一致（SHA-256）时抛 409；相似度 >= 90% 时响应携带 similar_* 字段提示。
    """
    record, similar_file, similarity = await file_service.save_file(db, user.id, file)
    background_tasks.add_task(file_service.run_parse_task, record.id)
    out = FileOut.model_validate(record)
    if similar_file is not None:
        out.similar_file_id = similar_file.id
        out.similar_to = similar_file.file_name
        out.similarity = round(similarity, 4)
    return out


@router.get("", response_model=FileListOut)
def list_files(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileListOut:
    """列出当前用户自己的文件。"""
    records = file_service.list_files(db, user.id)
    return FileListOut(items=[FileOut.model_validate(r) for r in records])


@router.get("/{file_id}/raw")
def download_raw(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    """下载原文（供前端 PDF.js 预览）。仅文件所有者可访问。"""
    record = file_service.get_owned_file(db, file_id, user.id)
    path = Path(record.stored_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件已从磁盘移除")
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES.get(record.file_type, "application/octet-stream"),
        filename=record.file_name,
    )


@router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除文件：DB + 磁盘 + 向量库同步清理。仅文件所有者可操作。"""
    file_service.delete_file(db, file_id, user.id)


@router.get("/{file_id}/preview")
def preview_file(
    file_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """文本预览（供非 PDF 格式在线查看）：提取解析文本返回，限 2 万字符。仅文件所有者可访问。"""
    from ..rag.parser import parse_document

    record = file_service.get_owned_file(db, file_id, user.id)
    path = Path(record.stored_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件已从磁盘移除")
    try:
        units = parse_document(path, record.file_type)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件内容解析失败，无法预览")
    text = "\n\n".join(u.text for u in units)
    return {"file_name": record.file_name, "text": text[:20000]}
