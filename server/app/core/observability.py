"""可观测性：Sentry 异常上报与 Prometheus 指标（均为可选，未配置/未安装时静默降级）。"""
from __future__ import annotations

from .config import settings
from .logging import get_logger

logger = get_logger(__name__)

# ---------- Prometheus（可选） ----------
_counter = None
_latency = None

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    _http_requests = Counter(
        "http_requests_total", "HTTP 请求总数", ["method", "path", "status"]
    )
    _llm_tokens = Counter(
        "llm_tokens_total", "LLM Token 消耗", ["kind", "direction"]
    )
    _latency = Histogram(
        "http_request_duration_ms", "HTTP 请求耗时（毫秒）", ["method", "path"]
    )
    _counter = True
except ImportError:  # prometheus-client 未安装
    _http_requests = None
    _llm_tokens = None


def init_sentry() -> None:
    """配置 SENTRY_DSN 且安装了 sentry-sdk 时启用异常上报。"""
    if not settings.SENTRY_DSN:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except ImportError:
        logger.warning("已配置 SENTRY_DSN 但未安装 sentry-sdk，跳过 Sentry 初始化")
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        environment=settings.APP_ENV,
        traces_sample_rate=0.1,
    )
    logger.info("sentry initialized: env=%s", settings.APP_ENV)


def record_http(method: str, path: str, status: int, cost_ms: float) -> None:
    if not (settings.METRICS_ENABLED and _counter):
        return
    _http_requests.labels(method=method, path=path, status=str(status)).inc()
    _latency.labels(method=method, path=path).observe(cost_ms)


def record_llm_tokens(kind: str, prompt_tokens: int, completion_tokens: int) -> None:
    """kind: chat / embedding。"""
    if not (settings.METRICS_ENABLED and _counter):
        return
    _llm_tokens.labels(kind=kind, direction="input").inc(prompt_tokens)
    _llm_tokens.labels(kind=kind, direction="output").inc(completion_tokens)


def render_metrics() -> bytes | None:
    """输出 Prometheus 文本格式；未启用或未安装依赖时返回 None。"""
    if not (settings.METRICS_ENABLED and _counter):
        return None
    return generate_latest()
