"""管理路由：用户管理与全库文件管理，仅 role=admin 可访问。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import require_admin
from ..models.user import User
from ..schemas.auth import AdminUserOut
from ..services import file_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)) -> list[AdminUserOut]:
    """列出全部用户。"""
    users = db.scalars(select(User).order_by(User.id)).all()
    return [AdminUserOut.model_validate(u) for u in users]


@router.post("/users/{user_id}/deactivate", status_code=204)
def deactivate_user(user_id: int, db: Session = Depends(get_db)):
    """停用账号（停用后无法登录，已有 token 在过期前仍会被 get_current_user 拦截）。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user.is_active = False
    db.commit()


@router.post("/users/{user_id}/activate", status_code=204)
def activate_user(user_id: int, db: Session = Depends(get_db)):
    """恢复账号。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    user.is_active = True
    db.commit()


@router.delete("/files/{file_id}", status_code=204)
def delete_any_file(file_id: int, db: Session = Depends(get_db)):
    """管理员可删除任意用户的文件（DB + 磁盘 + 向量库同步清理）。"""
    file_service.delete_file(db, file_id, user_id=None)
