"""密码哈希（bcrypt）与 JWT 签发/校验。禁止明文或可逆加密存储密码。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import settings


# ---------- 密码 ----------
def hash_password(plain: str) -> str:
    """bcrypt 单向哈希（自动生成 salt）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文与哈希是否匹配。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- JWT ----------
def create_access_token(subject: str | int, extra: dict | None = None) -> str:
    """签发 JWT，subject 为 user_id。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """校验并解码 JWT；无效/过期抛 jwt.PyJWTError。"""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ---------- Refresh Token ----------
def create_refresh_token(subject: str | int) -> tuple[str, str, datetime]:
    """签发 Refresh Token。返回 (token, jti, 过期时间)。

    jti 会落库（refresh_tokens 表），用于吊销与有效性校验。
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(subject),
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": expires,
    }
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires


def decode_refresh_token(token: str) -> dict:
    """校验 Refresh Token；类型不符/无效/过期抛异常。"""
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("not a refresh token")
    return payload
