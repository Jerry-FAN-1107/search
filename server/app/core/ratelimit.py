"""限流：登录防爆破（内存实现）与 LLM 流控（每用户滑动窗口 + 全局并发信号量）。

单机部署下使用进程内状态即可；多实例部署时应替换为 Redis Token Bucket，
本模块的接口签名（check/record 分离）按可替换性设计。
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict, deque

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)


class LoginRateLimiter:
    """登录防爆破：同一 (IP, 邮箱) 连续失败 N 次后锁定 M 分钟。"""

    def __init__(self) -> None:
        self._fails: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._locked_until: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def check(self, ip: str, email: str) -> int:
        """若被锁定，返回剩余锁定秒数；否则返回 0。"""
        key = (ip, email.lower())
        now = _monotonic()
        with self._lock:
            until = self._locked_until.get(key, 0.0)
            if until > now:
                return int(until - now) + 1
            return 0

    def record_failure(self, ip: str, email: str) -> None:
        """记录一次失败；达到阈值即锁定。"""
        key = (ip, email.lower())
        now = _monotonic()
        window = settings.LOGIN_LOCK_MINUTES * 60
        with self._lock:
            dq = self._fails[key]
            dq.append(now)
            while dq and dq[0] < now - window:
                dq.popleft()
            if len(dq) >= settings.LOGIN_MAX_FAILURES:
                self._locked_until[key] = now + window
                dq.clear()
                logger.warning("login locked: ip=%s email=%s for %dmin", ip, email, settings.LOGIN_LOCK_MINUTES)

    def record_success(self, ip: str, email: str) -> None:
        """登录成功：清除失败计数与锁定。"""
        key = (ip, email.lower())
        with self._lock:
            self._fails.pop(key, None)
            self._locked_until.pop(key, None)


class LlmRateLimiter:
    """LLM 流控：每用户每分钟滑动窗口限流 + 全局并发信号量。"""

    def __init__(self) -> None:
        self._hits: dict[int, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._semaphore: asyncio.Semaphore | None = None

    def allow(self, user_id: int) -> bool:
        """检查该用户当前是否可发起一次 LLM 请求（RPM 窗口）。"""
        now = _monotonic()
        with self._lock:
            dq = self._hits[user_id]
            while dq and dq[0] < now - 60:
                dq.popleft()
            if len(dq) >= settings.LLM_PER_USER_RPM:
                logger.warning("llm rate limited: user=%s rpm>=%d", user_id, settings.LLM_PER_USER_RPM)
                return False
            dq.append(now)
            return True

    def semaphore(self) -> asyncio.Semaphore:
        """全局并发信号量（惰性创建，绑定当前事件循环使用）。"""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.LLM_GLOBAL_CONCURRENCY)
        return self._semaphore


def _monotonic() -> float:
    return time.monotonic()


def _in_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


login_limiter = LoginRateLimiter()
llm_limiter = LlmRateLimiter()
