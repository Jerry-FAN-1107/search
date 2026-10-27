"""文件业务逻辑：保存文件、写入元数据、触发解析分段并向量入库。"""
from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import SessionLocal
from ..core.logging import get_logger
from ..models.file import File
from ..rag.parser import ALLOWED_EXTENSIONS, parse_document
from ..rag.splitter import chunkize
from ..rag.vectorstore import get_vectorstore

logger = get_logger(__name__)

_EXT_TO_TYPE = {".docx": "docx", ".pdf": "pdf", ".xlsx": "xlsx", ".pptx": "pptx"}

# SimHash 相似度阈值：64 位指纹汉明距离 <= 6 即相似度 >= 90%
_SIMILARITY_THRESHOLD = 0.90

# 文件魔数：OOXML（docx/xlsx/pptx）本质是 zip 包；PDF 以 %PDF 开头
_MAGIC_ZIP = b"PK\x03\x04"
_MAGIC_PDF = b"%PDF"


def _validate(upload: UploadFile) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的文件类型: {ext or '未知'}")
    return ext


def _check_magic(content: bytes, ext: str) -> None:
    """校验文件内容与扩展名是否匹配，拦截伪装扩展名/损坏文件（如 RTF 改名 .docx）。"""
    ok = content.startswith(_MAGIC_PDF) if ext == ".pdf" else content.startswith(_MAGIC_ZIP)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件内容与扩展名 {ext} 不符（疑似伪装扩展名或已损坏），请导出为真正的 {ext[1:]} 格式后重试",
        )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _simhash_tokens(text: str) -> list[str]:
    """分词：英文/数字按词，中文按字 bigram。"""
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    cjk = re.findall(r"[一-鿿]", text)
    if len(cjk) == 1:
        tokens.append(cjk[0])
    else:
        tokens.extend("".join(cjk[i:i + 2]) for i in range(len(cjk) - 1))
    return tokens


def _simhash(text: str) -> int:
    """纯 Python 64 位 SimHash 指纹。"""
    tokens = _simhash_tokens(text)
    if not tokens:
        return 0
    weights = [0] * 64
    for token in tokens:
        h = int.from_bytes(hashlib.md5(token.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            weights[i] += 1 if (h >> i) & 1 else -1
    fingerprint = 0
    for i in range(64):
        if weights[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def _similarity(fp_a: int, fp_b: int) -> float:
    """由汉明距离换算相似度。"""
    distance = bin(fp_a ^ fp_b).count("1")
    return 1 - distance / 64


def _extract_text_for_fingerprint(path: Path, file_type: str) -> str:
    """提取文本用于 SimHash（限制前 5 万字符，失败返回空串，不阻塞上传）。"""
    try:
        units = parse_document(path, file_type)
        return "\n".join(u.text for u in units)[:50000]
    except Exception:
        logger.warning("fingerprint text extract failed: %s", path.name, exc_info=True)
        return ""


async def save_file(db: Session, user_id: int, upload: UploadFile) -> tuple[File, File | None, float]:
    """保存上传文件到磁盘，写入 files 元数据（user_id 来自 JWT，保证归属）。

    上传检测：
    - 同用户下内容 SHA-256 完全一致（不论文件名）-> 抛 409 拒绝上传；
    - 同名但内容不同 -> 允许上传（正常走流程）；
    - 与已有文件内容相似度 >= 90% -> 正常上传，返回 (record, similar_file, similarity) 供前端提示。

    返回: (新记录, 相似旧文件或 None, 相似度)
    """
    ext = _validate(upload)
    file_type = _EXT_TO_TYPE[ext]

    content = await upload.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="文件超过大小上限")

    _check_magic(content, ext)
    content_hash = _sha256(content)

    # 同用户范围内精确查重（跨用户不互相可见）
    existing = list(db.scalars(select(File).where(File.user_id == user_id)))
    dup = next((f for f in existing if f.content_hash == content_hash), None)
    if dup is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"内容完全一致的文件已存在：「{dup.file_name}」，无需重复上传",
        )

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{user_id}_{uuid.uuid4().hex}{ext}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(content)

    # SimHash 相似度检测（文本提取失败时跳过，不阻塞上传）
    similar_file: File | None = None
    best_similarity = 0.0
    simhash_hex: str | None = None
    text = _extract_text_for_fingerprint(stored_path, file_type)
    if text.strip():
        fp = _simhash(text)
        simhash_hex = f"{fp:016x}"
        for old in existing:
            if not old.simhash:
                continue
            sim = _similarity(fp, int(old.simhash, 16))
            if sim >= _SIMILARITY_THRESHOLD and sim > best_similarity:
                best_similarity = sim
                similar_file = old

    record = File(
        user_id=user_id,
        file_name=upload.filename or stored_name,
        stored_path=str(stored_path),
        file_type=file_type,
        size_bytes=len(content),
        parse_status="pending",
        content_hash=content_hash,
        simhash=simhash_hex,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("file saved: id=%s user=%s name=%s type=%s size=%sB",
                record.id, user_id, record.file_name, file_type, len(content))
    if similar_file is not None:
        logger.info("similar file detected: new=%s old=%s similarity=%.2f",
                    record.id, similar_file.id, best_similarity)
    return record, similar_file, best_similarity


async def parse_and_index(record: File) -> int:
    """解析分段 + 向量入库。返回 chunk 数。若失败标记 parse_status=failed。"""
    try:
        units = parse_document(Path(record.stored_path), record.file_type)
        chunks = chunkize(units, file_id=record.id, file_name=record.file_name, file_type=record.file_type)
        for c in chunks:
            c.user_id = record.user_id  # 向量层跨用户隔离
        vs = get_vectorstore()
        await vs.add_chunks(chunks)
        record.parse_status = "ready"
        record.chunk_count = len(chunks)
        logger.info("file parsed & indexed: id=%s chunks=%s", record.id, len(chunks))
        return len(chunks)
    except Exception:
        record.parse_status = "failed"
        logger.exception("file parse failed: id=%s name=%s", record.id, record.file_name)
        raise


async def run_parse_task(file_id: int) -> None:
    """后台解析任务（FastAPI BackgroundTasks 调用）。

    上传接口只负责落盘并立即返回，解析在后台异步执行；
    使用独立 DB 会话，依次流转 parse_status: pending -> parsing -> ready/failed。
    前端通过轮询 GET /files 感知状态变化。
    """
    db = SessionLocal()
    try:
        record = db.get(File, file_id)
        if record is None:
            logger.warning("parse task: file %s not found", file_id)
            return
        record.parse_status = "parsing"
        db.commit()
        try:
            await parse_and_index(record)
        except Exception:
            pass  # parse_and_index 已把状态标记为 failed
        db.commit()
    except Exception:
        logger.exception("parse task crashed: file_id=%s", file_id)
    finally:
        db.close()


def recover_interrupted_parses() -> list[int]:
    """启动恢复：把因进程重启而丢失的解析任务重新派发。

    pending/parsing 且磁盘文件仍在 -> 重新派发（返回 file_id 列表由 lifespan create_task）；
    磁盘文件已丢 -> 直接标记 failed，避免永远 pending。
    """
    import asyncio
    from pathlib import Path as _Path

    redispatched: list[int] = []
    with SessionLocal() as db:
        stuck = (
            db.query(File)
            .filter(File.parse_status.in_(("pending", "parsing")))
            .all()
        )
        for rec in stuck:
            if _Path(rec.stored_path).exists():
                redispatched.append(rec.id)
            else:
                rec.parse_status = "failed"
                logger.warning("recover: file missing on disk -> failed: id=%s", rec.id)
        db.commit()
    for fid in redispatched:
        logger.info("recover: redispatch parse task: file_id=%s", fid)
        asyncio.get_running_loop().create_task(run_parse_task(fid))
    return redispatched


def get_owned_file(db: Session, file_id: int, user_id: int) -> File:
    """取文件并校验归属（防 IDOR：用户只能访问自己的文件）。"""
    record = db.get(File, file_id)
    if record is None or record.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    return record


def delete_file(db: Session, file_id: int, user_id: int | None) -> None:
    """删除文件：DB 记录 + 磁盘文件 + Chroma 向量，三处同步清理。

    user_id=None 表示管理员调用（跳过归属校验）；否则普通用户只能删自己的文件。
    """
    record = db.get(File, file_id)
    if record is None or (user_id is not None and record.user_id != user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    stored_path = record.stored_path
    db.delete(record)
    db.commit()

    try:
        Path(stored_path).unlink(missing_ok=True)
    except Exception:
        logger.warning("remove file from disk failed: %s", stored_path, exc_info=True)

    get_vectorstore().delete_by_file_id(file_id)
    logger.info("file deleted: id=%s path=%s", file_id, stored_path)


def list_files(db: Session, user_id: int) -> list[File]:
    """仅返回当前用户的文件（隔离）。"""
    return list(db.scalars(select(File).where(File.user_id == user_id).order_by(File.created_at.desc())))