"""T3.7: yorliq (shtrix-kod) shablonlari — brauzer localStorage o'rniga serverda (korxona + ixtiyoriy filial)."""
import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.label_template import LabelTemplate
from app.models.user import User, UserRole

router = APIRouter(prefix="/label-templates", tags=["Label templates"])

LABEL_WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.manager, UserRole.warehouse)
MAX_CONFIG_BYTES = 64 * 1024   # config JSON hajmi chegarasi (64 KB)

Kind = Literal["product", "customer"]


class LabelTemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    kind: Kind = "product"
    branch_id: Optional[int] = None
    config: Dict[str, Any]


class LabelTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    branch_id: Optional[int] = None     # model_fields_set da bo'lsa — doira o'zgaradi (None = butun korxona)
    config: Optional[Dict[str, Any]] = None


class LabelTemplateOut(BaseModel):
    id: int
    kind: str
    name: str
    branch_id: Optional[int] = None
    config: Dict[str, Any]

    model_config = {"from_attributes": True}


def _require_company(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


def _check_branch(db: Session, cid: int, branch_id: Optional[int]) -> None:
    """Filial shu korxonaga tegishli bo'lishi shart — aks holda 404 (begona filial nomi sizib chiqmaydi)."""
    if branch_id is None:
        return
    ok = db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == cid).first()
    if not ok:
        raise HTTPException(status_code=404, detail="Filial topilmadi")


def _check_config_size(config: Dict[str, Any]) -> None:
    if len(json.dumps(config, ensure_ascii=False).encode("utf-8")) > MAX_CONFIG_BYTES:
        raise HTTPException(status_code=422, detail="Shablon sozlamalari juda katta (64 KB dan oshmasin)")


def _duplicate(db: Session, cid: int, kind: str, name: str, branch_id: Optional[int],
               exclude_id: Optional[int] = None) -> bool:
    q = db.query(LabelTemplate.id).filter(
        LabelTemplate.company_id == cid,
        LabelTemplate.kind == kind,
        LabelTemplate.name == name,
        func.coalesce(LabelTemplate.branch_id, 0) == (branch_id or 0),
    )
    if exclude_id is not None:
        q = q.filter(LabelTemplate.id != exclude_id)
    return q.first() is not None


def _get_own(db: Session, cid: int, template_id: int) -> LabelTemplate:
    tpl = db.query(LabelTemplate).filter(
        LabelTemplate.id == template_id, LabelTemplate.company_id == cid,
    ).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Shablon topilmadi")
    return tpl


@router.get("", response_model=List[LabelTemplateOut])
def list_label_templates(
    kind: Optional[Kind] = Query(None),
    branch_id: Optional[int] = Query(None, description="Berilsa: butun korxona + shu filial shablonlari"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    cid = _require_company(user)
    q = db.query(LabelTemplate).filter(LabelTemplate.company_id == cid)
    if kind:
        q = q.filter(LabelTemplate.kind == kind)
    if branch_id is not None:
        _check_branch(db, cid, branch_id)
        q = q.filter(or_(LabelTemplate.branch_id.is_(None), LabelTemplate.branch_id == branch_id))
    return q.order_by(LabelTemplate.name, LabelTemplate.id).all()


@router.post("", response_model=LabelTemplateOut, status_code=201)
def create_label_template(
    data: LabelTemplateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*LABEL_WRITE_ROLES)),
):
    cid = _require_company(user)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Shablon nomi bo'sh bo'lmasin")
    _check_branch(db, cid, data.branch_id)
    _check_config_size(data.config)
    if _duplicate(db, cid, data.kind, name, data.branch_id):
        raise HTTPException(status_code=409, detail="Bunday nomli shablon allaqachon bor")
    tpl = LabelTemplate(
        company_id=cid, branch_id=data.branch_id, kind=data.kind, name=name,
        config=data.config, created_by=user.id,
    )
    db.add(tpl)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bunday nomli shablon allaqachon bor")
    db.refresh(tpl)
    return tpl


@router.put("/{template_id}", response_model=LabelTemplateOut)
def update_label_template(
    template_id: int,
    data: LabelTemplateUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*LABEL_WRITE_ROLES)),
):
    cid = _require_company(user)
    tpl = _get_own(db, cid, template_id)
    new_name = data.name.strip() if data.name is not None else tpl.name
    if not new_name:
        raise HTTPException(status_code=422, detail="Shablon nomi bo'sh bo'lmasin")
    new_branch = data.branch_id if "branch_id" in data.model_fields_set else tpl.branch_id
    _check_branch(db, cid, new_branch)
    if data.config is not None:
        _check_config_size(data.config)
    if _duplicate(db, cid, tpl.kind, new_name, new_branch, exclude_id=tpl.id):
        raise HTTPException(status_code=409, detail="Bunday nomli shablon allaqachon bor")
    tpl.name = new_name
    tpl.branch_id = new_branch
    if data.config is not None:
        tpl.config = data.config
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bunday nomli shablon allaqachon bor")
    db.refresh(tpl)
    return tpl


@router.delete("/{template_id}", status_code=204)
def delete_label_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*LABEL_WRITE_ROLES)),
):
    cid = _require_company(user)
    tpl = _get_own(db, cid, template_id)
    db.delete(tpl)
    db.commit()
    return Response(status_code=204)
