"""全局配置：所有关键配置项一律从环境变量读取。"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# 不允许在生产环境使用的弱密钥样本
_WEAK_SECRETS = {"please-change-me", "secret", "changeme", "jwt-secret", "123456", ""}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "enterprise-consult-agent"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 数据库（MySQL）
    DATABASE_URL: str = (
        "mysql+pymysql://root:password@127.0.0.1:3306/enterprise_consult?charset=utf8mb4"
    )

    # 认证
    JWT_SECRET_KEY: str = "please-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120     # Access Token 2 小时内过期
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7         # Refresh Token 有效期（可吊销）

    # 登录防爆破：同一 IP+邮箱 连续失败 N 次锁定 M 分钟
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_LOCK_MINUTES: int = 5

    # 豆包模型
    DOUBAO_CHAT_MODEL: str = ""
    DOUBAO_THINKING_MODEL: str = ""
    DOUBAO_EMBEDDING_MODEL: str = ""
    DOUBAO_API_KEY: str = ""
    DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    DOUBAO_ENDPOINT_ID: str | None = None

    # 向量库
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    RAG_TOP_K: int = 6                    # 最终喂给大模型的资料条数
    RAG_RECALL_TOP_K: int = 20            # 向量召回条数（供 Rerank 精排）
    RAG_SIMILARITY_THRESHOLD: float = 0.65
    RAG_RERANK_ENABLED: bool = True       # 是否对召回结果做 LLM 精排

    # HITL / LangGraph
    GRAPH_CHECKPOINT_DB: str = "./graph_state.db"
    HITL_ENABLED: bool = True

    # 多轮对话：滑动窗口保留最近 N 轮（一问一答为一轮）
    MAX_HISTORY_TURNS: int = 6

    # LLM 流控：每用户每分钟请求上限 + 全局并发信号量
    LLM_PER_USER_RPM: int = 20
    LLM_GLOBAL_CONCURRENCY: int = 8

    # 内容安全
    CONTENT_MODERATION_ENABLED: bool = True      # 敏感词过滤总开关
    SENSITIVE_WORDS_FILE: str = "./sensitive_words.txt"
    PROMPT_INJECTION_GUARD: bool = True          # Prompt 注入启发式拦截

    # 文件
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 50

    # 联网搜索（预留）
    SEARCH_API_KEY: str | None = None
    SEARCH_BASE_URL: str | None = None

    # 可观测性
    SENTRY_DSN: str | None = None          # 配置后启用 Sentry 异常上报
    METRICS_ENABLED: bool = False          # 启用 /metrics（需安装 prometheus-client）

    # 日志
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    LOG_FILE: str = "app.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024   # 单日志文件滚动上限（字节）
    LOG_BACKUP_COUNT: int = 5               # 保留的滚动文件份数

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    def validate_secret_strength(self) -> None:
        """启动时校验 JWT 密钥强度：生产环境弱密钥直接拒绝启动，开发环境告警。"""
        weak = (
            self.JWT_SECRET_KEY in _WEAK_SECRETS
            or len(self.JWT_SECRET_KEY) < 32
        )
        if weak and self.APP_ENV == "production":
            raise RuntimeError(
                "JWT_SECRET_KEY 强度不足或为默认值，生产环境拒绝启动。"
                "请通过环境变量注入强随机密钥（建议 >= 32 字节，可用 openssl rand -hex 32 生成）。"
            )
        if weak:
            import logging

            logging.getLogger(__name__).warning(
                "JWT_SECRET_KEY 强度不足或为默认值，仅限开发环境使用；上线前必须通过环境变量注入强随机密钥。"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
