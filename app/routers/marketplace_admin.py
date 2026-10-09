"""Marketplace agentlarini korxona admini boshqaradi (/api/marketplace-agents/*).

Modul o'chiq korxonalar uchun butun router yopiq (require_feature).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import get_current_user, require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.marketplace import (
    MarketplaceAgentTransaction, MarketplaceProduct, MarketplaceProductStatus, MarketplaceTransactionType,
)
from app.models.user import User, UserRole, UserStatus
from app.routers.mobile.marketplace_agent import _product_out, agent_balance
from app.schemas.marketplace import AgentStatusIn, PayoutIn, ProductUpdateIn, RejectIn
from app.services import marketplace_service as mp

router = APIRouter(
    prefix="/marketplace-agents", tags=["marketplace-agents"],
    dependencies=[Depends(require_feature("marketplace_agents"))],
)

_admin = require_roles(UserRole.admin, UserRole.director, UserRole.manager)


def _agent_or_404(db: Session, admin: User, agent_id: int) -> User:
    u = db.query(User).filter(
        User.id == agent_id, User.company_id == admin.company_id,
        User.role == UserRole.marketplace_agent).first()
    if not u:
        raise HTTPException(status_code=404, detail="Agent topilmadi")
    return u


def _product_or_404(db: Session, admin: User, product_id: int) -> MarketplaceProduct:
    p = db.query(MarketplaceProduct).filter(
        MarketplaceProduct.id == product_id, MarketplaceProduct.company_id == admin.company_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    return p


# ── Agentlar ───────────────────────────────────────────────────────────────

@router.get("")
def list_agents(status: Optional[str] = None, q: Optional[str] = Query(None, max_length=100),
                db: Session = Depends(get_db), admin: User = Depends(_admin)):
    query = db.query(User).filter(User.company_id == admin.company_id, User.role == UserRole.marketplace_agent)
    if status:
        try:
            query = query.filter(User.status == UserStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Noto'g'ri status")
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(User.name.ilike(like) | User.phone.ilike(like))
    items = []
    for u in query.order_by(User.id.desc()).all():
        cnt = db.query(func.count(MarketplaceProduct.id)).filter(MarketplaceProduct.agent_id == u.id).scalar() or 0
        items.append({"id": u.id, "name": u.name, "phone": u.phone, "status": u.status.value,
                      "products": cnt, "balance": agent_balance(db, u.id)["balance"],
                      "created_at": u.created_at.isoformat() if u.created_at else None})
    return {"items": items}


@router.put("/{agent_id}/status")
def set_agent_status(agent_id: int, data: AgentStatusIn, db: Session = Depends(get_db),
                     admin: User = Depends(_admin)):
    u = _agent_or_404(db, admin, agent_id)
    old = u.status.value
    u.status = UserStatus(data.status)
    # Bloklanganda mahsulotlar marketplace'dan yashiriladi (review ga qaytariladi),
    # qayta faollashtirilganda admin ularni qayta tasdiqlaydi.
    if u.status == UserStatus.blocked:
        db.query(MarketplaceProduct).filter(
            MarketplaceProduct.agent_id == u.id, MarketplaceProduct.status == MarketplaceProductStatus.approved,
        ).update({"status": MarketplaceProductStatus.review}, synchronize_session=False)
    log_action(db=db, action="MARKETPLACE_AGENT_STATUS", entity_type="user", entity_id=u.id, user_id=admin.id,
               old_values={"status": old}, new_values={"status": data.status, "reason": data.reason})
    db.commit()
    return {"id": u.id, "status": u.status.value}


# ── Moderatsiya va mahsulotlar ─────────────────────────────────────────────

@router.get("/products")
def list_products(status: Optional[str] = "review", agent_id: Optional[int] = None,
                  page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
                  db: Session = Depends(get_db), admin: User = Depends(_admin)):
    query = db.query(MarketplaceProduct).filter(MarketplaceProduct.company_id == admin.company_id)
    if status:
        try:
            query = query.filter(MarketplaceProduct.status == MarketplaceProductStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail="Noto'g'ri status")
    if agent_id:
        query = query.filter(MarketplaceProduct.agent_id == agent_id)
    total = query.count()
    rows = query.order_by(MarketplaceProduct.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    names = mp.category_name_map()
    agent_names = {u.id: u.name for u in db.query(User).filter(User.id.in_({p.agent_id for p in rows} or {0})).all()}
    return {"total": total, "items": [{**_product_out(p, names), "agent_id": p.agent_id,
                                       "agent_name": agent_names.get(p.agent_id)} for p in rows]}


@router.post("/products/{product_id}/approve")
def approve_product(product_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), admin: User = Depends(_admin)):
    p = _product_or_404(db, admin, product_id)
    agent = db.query(User).filter(User.id == p.agent_id).first()
    if not agent or agent.status != UserStatus.active:
        raise HTTPException(status_code=409, detail="Agent faol emas — avval agentni faollashtiring")
    p.status, p.reject_reason = MarketplaceProductStatus.approved, None
    log_action(db=db, action="MARKETPLACE_PRODUCT_APPROVE", entity_type="marketplace_product",
               entity_id=p.id, user_id=admin.id)
    db.commit()
    
    cat_names = mp.category_name_map()
    background_tasks.add_task(mp.push_product_to_mirmaza, p, cat_names.get(p.category_id, ""))
    
    return _product_out(p, cat_names)


@router.post("/products/{product_id}/reject")
def reject_product(product_id: int, data: RejectIn, db: Session = Depends(get_db), admin: User = Depends(_admin)):
    p = _product_or_404(db, admin, product_id)
    p.status, p.reject_reason = MarketplaceProductStatus.rejected, data.reason.strip()
    log_action(db=db, action="MARKETPLACE_PRODUCT_REJECT", entity_type="marketplace_product",
               entity_id=p.id, user_id=admin.id, new_values={"reason": p.reject_reason})
    db.commit()
    return _product_out(p, mp.category_name_map())


@router.put("/products/{product_id}")
def edit_product(product_id: int, data: ProductUpdateIn, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
                 admin: User = Depends(_admin)):
    p = _product_or_404(db, admin, product_id)
    changes = data.model_dump(exclude_unset=True, exclude={"submit"})
    if "images" in changes:
        changes["images"] = mp.clamp_images(changes["images"])
    for k, v in changes.items():
        setattr(p, k, v)
    log_action(db=db, action="MARKETPLACE_PRODUCT_ADMIN_EDIT", entity_type="marketplace_product",
               entity_id=p.id, user_id=admin.id, new_values={k: str(v) for k, v in changes.items()})
    db.commit()

    cat_names = mp.category_name_map()
    if p.status == MarketplaceProductStatus.approved:
        background_tasks.add_task(mp.push_product_to_mirmaza, p, cat_names.get(p.category_id, ""))

    return _product_out(p, cat_names)


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), admin: User = Depends(_admin)):
    p = _product_or_404(db, admin, product_id)
    log_action(db=db, action="MARKETPLACE_PRODUCT_ADMIN_DELETE", entity_type="marketplace_product",
               entity_id=p.id, user_id=admin.id, old_values={"name": p.name})
    db.delete(p)
    db.commit()
    return {"ok": True}


# ── Hisob-kitob ────────────────────────────────────────────────────────────

@router.get("/{agent_id}/balance")
def agent_balance_view(agent_id: int, db: Session = Depends(get_db), admin: User = Depends(_admin)):
    u = _agent_or_404(db, admin, agent_id)
    return {"agent_id": u.id, "name": u.name, **agent_balance(db, u.id)}


@router.post("/{agent_id}/payouts", status_code=201)
def create_payout(agent_id: int, data: PayoutIn, db: Session = Depends(get_db), admin: User = Depends(_admin)):
    u = _agent_or_404(db, admin, agent_id)
    # Bir vaqtda ikki to'lov balansdan oshib ketmasligi uchun agent qatorini qulflaymiz
    db.query(User).filter(User.id == u.id).with_for_update().first()
    bal = agent_balance(db, u.id)["balance"]
    if float(data.amount) > bal + 0.001:
        raise HTTPException(status_code=400, detail=f"To'lov summasi balansdan oshadi (balans: {bal:,.2f})")
    t = MarketplaceAgentTransaction(
        agent_id=u.id, company_id=admin.company_id, transaction_type=MarketplaceTransactionType.payout,
        amount=data.amount, note=data.note)
    db.add(t)
    db.flush()
    log_action(db=db, action="MARKETPLACE_PAYOUT", entity_type="marketplace_agent_transaction",
               entity_id=t.id, user_id=admin.id, new_values={"agent_id": u.id, "amount": str(data.amount)})
    db.commit()
    return {"id": t.id, **agent_balance(db, u.id)}


@router.get("/stats/summary")
def stats(db: Session = Depends(get_db), admin: User = Depends(_admin)):
    cid = admin.company_id
    agents = db.query(User.status, func.count(User.id)).filter(
        User.company_id == cid, User.role == UserRole.marketplace_agent).group_by(User.status).all()
    prods = db.query(MarketplaceProduct.status, func.count(MarketplaceProduct.id)).filter(
        MarketplaceProduct.company_id == cid).group_by(MarketplaceProduct.status).all()
    return {"agents": {k.value: v for k, v in agents}, "products": {k.value: v for k, v in prods}}
