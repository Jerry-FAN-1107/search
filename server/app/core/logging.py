"""统一日志配置：控制台 + 滚动文件（RotatingFileHandler）。

- 日志文件位于 LOG_DIR（默认 ./logs），按大小滚动轮转（maxBytes / backupCount），避免无限膨胀；
- LOG_LEVEL 从环境变量读取；
- 所有模块统一 get_logger(__name__) 获取 logger，格式统一（时间/级别/模块/消息）。
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from .config import settings

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging() -> None:
    """配置根 logger：同时输出到控制台与滚动日志文件。幂等。"""
    root = logging.getLogger()
    if root.handlers:  # 已被配置过，避免重复挂 handler
        return

    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root.setLevel(level)

    fmt = logging.Formatter(_FORMAT)

    # 控制台输出
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # 滚动日志文件
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / settings.LOG_FILE,
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """模块统一取 logger。"""
    return logging.getLogger(name)