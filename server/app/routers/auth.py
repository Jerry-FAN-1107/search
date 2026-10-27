"""认证路由：注册 / 登录 / 令牌刷新 / 注销。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from ..services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return auth_service.register(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ip = request.client.host if request.client else "-"
    return auth_service.login(db, payload, ip)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Access Token 过期后，用 Refresh Token 换新（前端 401 拦截自动调用）。"""
    return auth_service.refresh(db, payload.refresh_token)


@router.post("/logout", status_code=204)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    """注销并吊销 Refresh Token。"""
    auth_service.logout(db, payload.refresh_token)
