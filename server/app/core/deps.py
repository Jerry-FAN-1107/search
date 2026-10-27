"""FastAPI 依赖注入：数据库会话 + 当前登录用户（JWT 校验）。"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.logging import get_logger
from ..core.security import decode_access_token
from ..models.user import User

logger = get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <token> 中校验 JWT 并返回当前用户。

    所有受保护的业务接口（文件上传、问答等）都必须依赖此函数。
    """
    if credentials is None:
        logger.warning("auth: missing bearer token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception:
        logger.warning("auth: invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        logger.warning("auth: token missing subject")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌缺少用户标识")

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        logger.warning("auth: user missing or inactive user_id=%s", user_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已停用")
    logger.debug("auth ok: user_id=%s", user.id)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """RBAC：仅 role=admin 可访问（管理接口）。"""
    if getattr(user, "role", "user") != "admin":
        logger.warning("rbac: non-admin access denied user_id=%s", user.id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user