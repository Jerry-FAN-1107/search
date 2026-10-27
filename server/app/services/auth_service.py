"""认证业务逻辑：注册、登录（含防爆破限流）、令牌刷新与注销。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.ratelimit import login_limiter
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from ..models.refresh_token import RefreshToken
from ..models.user import User
from ..schemas.auth import LoginRequest, RegisterRequest, TokenResponse


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    """签发 Access + Refresh Token，Refresh Token 的 jti 落库以支持吊销。"""
    access = create_access_token(user.id)
    refresh, jti, expires = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            expires_at=expires.astimezone(timezone.utc).replace(tzinfo=None),
        )
    )
    db.commit()
    return TokenResponse(access_token=access, refresh_token=refresh)


def register(db: Session, payload: RegisterRequest) -> TokenResponse:
    """注册新用户；邮箱唯一。密码以 bcrypt 单向哈希存储。"""
    exists = db.scalar(select(User).where(User.email == payload.email.lower()))
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被注册")

    user = User(
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_tokens(db, user)


def login(db: Session, payload: LoginRequest, ip: str) -> TokenResponse:
    """登录校验，成功后签发 JWT。

    防爆破：同一 (IP, 邮箱) 连续失败 LOGIN_MAX_FAILURES 次锁定 LOGIN_LOCK_MINUTES 分钟。
    """
    locked_for = login_limiter.check(ip, payload.email)
    if locked_for > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"失败次数过多，已临时锁定，请 {locked_for} 秒后重试",
        )

    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        login_limiter.record_failure(ip, payload.email)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已停用")
    login_limiter.record_success(ip, payload.email)
    return _issue_tokens(db, user)


def refresh(db: Session, refresh_token: str) -> TokenResponse:
    """用 Refresh Token 换取新的 Access Token（Refresh Token 原样保留至过期/注销）。"""
    try:
        payload = decode_refresh_token(refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh Token 无效或已过期"
        )

    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload.get("jti")))
    if (
        row is None
        or row.revoked
        or row.expires_at < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh Token 已失效，请重新登录"
        )

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")
    return TokenResponse(access_token=create_access_token(user.id), refresh_token=refresh_token)


def logout(db: Session, refresh_token: str) -> None:
    """注销：吊销对应的 Refresh Token（幂等，无效 token 直接忽略）。"""
    try:
        payload = decode_refresh_token(refresh_token)
    except Exception:
        return
    row = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload.get("jti")))
    if row is not None and not row.revoked:
        row.revoked = True
        db.commit()
