"""表格/表单预留路由（需求8）：本期仅提供占位接口，不实现完整 UI。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.deps import get_current_user
from ..models.form_template import FormTemplate
from ..models.user import User
from ..services import table_service

router = APIRouter(prefix="/tables", tags=["tables"])


class TableGenRequest(BaseModel):
    format_text: str = Field(min_length=1)
    data_source: list[dict] = Field(default_factory=list)


class TableGenResponse(BaseModel):
    status: str
    table: dict | None = None


@router.post("/generate", response_model=TableGenResponse)
async def generate_table(
    payload: TableGenRequest,
    user: User = Depends(get_current_user),
) -> TableGenResponse:
    """需求8预留：格式说明文本 + 数据来源 -> 结构化表格 JSON。"""
    result = await table_service.generate_table(payload.format_text, payload.data_source)
    return TableGenResponse(**result)


@router.post("/templates", status_code=201)
def save_template(
    body: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """保存一个表单模板到 form_templates 表（扩展点）。"""
    text = body.get("template_text")
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="template_text 必填")
    t = FormTemplate(user_id=user.id, template_text=text)
    db.add(t)
    db.commit()
    return {"id": t.id}


@router.get("/templates")
def list_templates(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(select(FormTemplate).where(FormTemplate.user_id == user.id)).all()
    return {"items": [{"id": r.id, "template_text": r.template_text} for r in rows]}