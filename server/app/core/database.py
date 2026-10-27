"""SQLAlchemy 引擎与会话：统一在此管理 MySQL 连接。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,          # 连接前 ping，避免 MySQL 连接失效
    pool_recycle=3600,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """创建所有表（首次运行）。生产环境建议改用 Alembic 迁移。"""
    # 延迟导入，避免循环依赖
    from .. import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_user_role_column()
    _ensure_file_fingerprint_columns()


def _ensure_file_fingerprint_columns() -> None:
    """朴素迁移：老库 files 表缺少 content_hash/simhash 列时补充（仅 MySQL）。"""
    if engine.dialect.name != "mysql":
        return
    try:
        with engine.begin() as conn:
            schema = conn.execute(text("SELECT DATABASE()")).scalar()
            for col, ddl in (
                ("content_hash", "ALTER TABLE files ADD COLUMN content_hash VARCHAR(64) NULL, ADD INDEX ix_files_content_hash (content_hash)"),
                ("simhash", "ALTER TABLE files ADD COLUMN simhash VARCHAR(16) NULL"),
            ):
                cnt = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = :s AND TABLE_NAME = 'files' AND COLUMN_NAME = :c"
                    ),
                    {"s": schema, "c": col},
                ).scalar()
                if not cnt:
                    conn.execute(text(ddl))
                    logger.info("migration: files.%s column added", col)
    except Exception:
        logger.warning("migration: ensure files fingerprint columns failed", exc_info=True)


def _ensure_user_role_column() -> None:
    """朴素迁移：老库 users 表缺少 role 列时补充（仅 MySQL）。

    create_all 不会为已存在的表补列，这里通过 information_schema 判断后 ALTER。
    """
    if engine.dialect.name != "mysql":
        return
    try:
        with engine.begin() as conn:
            schema = conn.execute(text("SELECT DATABASE()")).scalar()
            cnt = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = :s AND TABLE_NAME = 'users' AND COLUMN_NAME = 'role'"
                ),
                {"s": schema},
            ).scalar()
            if not cnt:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'")
                )
                logger.info("migration: users.role column added")
    except Exception:
        logger.warning("migration: ensure users.role failed", exc_info=True)
