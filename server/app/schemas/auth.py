"""认证相关请求/响应模型。"""
from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("密码需同时包含字母与数字")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """刷新/注销令牌请求体。"""
    refresh_token: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_active: bool

    model_config = {"from_attributes": True}


class AdminUserOut(BaseModel):
    """管理员视角的用户列表项。"""
    id: int
    email: EmailStr
    role: str
    is_active: bool

    model_config = {"from_attributes": True}