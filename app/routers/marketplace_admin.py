"""Marketplace agentlarini korxona admini boshqaradi (/api/marketplace-agents/*).

Modul o'chiq korxonalar uchun butun router yopiq (require_feature).
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

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
        u_status = u.status.value if hasattr(u.status, "value") else str(u.status or "")
        items.append({"id": u.id, "name": u.name, "phone": u.phone, "status": u_status,
                      "products": cnt, "balance": agent_balance(db, u.id)["balance"],
                      "created_at": u.created_at.isoformat() if u.created_at else None})
    return {"items": items}


@router.put("/{agent_id}/status")
def set_agent_status(agent_id: int, data: AgentStatusIn, db: Session = Depends(get_db),
                     admin: User = Depends(_admin)):
    u = _agent_or_404(db, admin, agent_id)
    old = u.status.value if hasattr(u.status, "value") else str(u.status or "")
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
    new_status = u.status.value if hasattr(u.status, "value") else str(u.status or "")
    return {"id": u.id, "status": new_status}


# ── Moderatsiya va mahsulotlar ─────────────────────────────────────────────

@router.get("/products")
def list_products(status: Optional[str] = None, agent_id: Optional[int] = None,
                  page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
                  db: Session = Depends(get_db), admin: User = Depends(_admin)):
    query = db.query(MarketplaceProduct).filter(MarketplaceProduct.company_id == admin.company_id)
    if status and status.strip():
        try:
            query = query.filter(MarketplaceProduct.status == MarketplaceProductStatus(status.strip()))
        except ValueError:
            raise HTTPException(status_code=400, detail="Noto'g'ri status")
    if agent_id:
        query = query.filter(MarketplaceProduct.agent_id == agent_id)
    total = query.count()
    rows = query.order_by(MarketplaceProduct.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    try:
        names = mp.category_name_map()
    except Exception:
        names = {}
    agent_ids = {p.agent_id for p in rows if p.agent_id}
    agent_names = {u.id: u.name for u in db.query(User).filter(User.id.in_(agent_ids)).all()} if agent_ids else {}
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
    
    # Asosiy mahsulotlar (Product) jadvaliga ham sinxronlash
    try:
        from app.models.product import Product, ProductStatus
        chk = db.query(Product).filter(Product.company_id == admin.company_id)
        if p.barcode:
            chk = chk.filter(Product.barcode == p.barcode)
        else:
            chk = chk.filter(Product.name == p.name)
        prod = chk.first()
        if not prod:
            prod = Product(
                company_id=admin.company_id,
                name=p.name,
                sku=p.sku or f"MP-{p.id}",
                barcode=p.barcode or f"MP{p.id:08d}",
                sale_price=p.price,
                cost_price=p.price,
                status=ProductStatus.active,
                image_url=(p.images[0] if p.images else None),
            )
            db.add(prod)
            db.flush()
    except Exception as ex:
        logger.warning("Product sinxronlashda xatolik: %s", ex)
        prod = None

    # ERP ga avtomatik Prixod (PurchaseOrder / Xarid) shakllantirish (/admin/purchases da ko'rinishi uchun)
    try:
        from app.models.supplier import Supplier
        from app.models.purchase_order import PurchaseOrder, POItem, POStatus
        from app.models.warehouse import Warehouse
        from app.services.inventory_service import receive_stock

        agent_user = db.query(User).filter(User.id == p.agent_id).first()
        if agent_user and prod and float(p.qty or 0) > 0 and not getattr(p, "purchase_order_id", None):
            supplier = db.query(Supplier).filter(
                Supplier.company_id == admin.company_id,
                Supplier.phone == agent_user.phone,
            ).first()
            if not supplier:
                supplier = Supplier(
                    company_id=admin.company_id,
                    name=f"Agent: {agent_user.name}",
                    phone=agent_user.phone,
                    notes=f"Marketplace savdo agenti #{agent_user.id}",
                    is_active=True,
                )
                db.add(supplier)
                db.flush()

            wh = db.query(Warehouse).filter(Warehouse.company_id == admin.company_id, Warehouse.is_active == True).first()
            if wh:
                import random
                po_num = f"PO-AG-{p.id}-{random.randint(100, 999)}"
                cost_dec = Decimal(str(p.price or 0))
                qty_dec = Decimal(str(p.qty or 0))
                total_sum = cost_dec * qty_dec

                po = PurchaseOrder(
                    company_id=admin.company_id,
                    supplier_id=supplier.id,
                    warehouse_id=wh.id,
                    number=po_num,
                    status=POStatus.received,
                    total_amount=total_sum,
                    paid_amount=Decimal(0),
                    supplier_debt=total_sum,
                    note=f"Marketplace agenti ({agent_user.name}) tovari: {p.name} (MP #{p.id})",
                    created_by=admin.id,
                )
                db.add(po)
                db.flush()

                po_item = POItem(
                    po_id=po.id,
                    product_id=prod.id,
                    qty_ordered=qty_dec,
                    qty_received=qty_dec,
                    unit_cost=cost_dec,
                )
                db.add(po_item)

                try:
                    receive_stock(
                        db=db,
                        product_id=prod.id,
                        quantity=qty_dec,
                        user_id=admin.id,
                        reason=f"Agent tovari qabul qilindi (PO #{po_num})",
                        reference_type="purchase_order",
                        reference_id=po.id,
                        warehouse_id=wh.id,
                    )
                except Exception as ex_stock:
                    logger.warning("receive_stock xatoligi: %s", ex_stock)

                supplier.debt_balance = (supplier.debt_balance or Decimal(0)) + total_sum
                p.purchase_order_id = po.id
    except Exception as ex_po:
        logger.warning("Avtomatik prixod yaratishda xatolik: %s", ex_po)

    try:
        mp.notify_agent(
            db=db,
            agent_id=p.agent_id,
            company_id=admin.company_id,
            title="Mahsulotingiz tasdiqlandi! ✅",
            body=f"'{p.name}' mahsulotingiz korxona admini tomonidan tasdiqlandi va Mir-maza ga joylashtirildi.",
            notif_type="product_approved",
            data={"product_id": p.id},
        )
    except Exception as ex:
        logger.warning("notify_agent xatoligi: %s", ex)

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
    try:
        mp.notify_agent(
            db=db,
            agent_id=p.agent_id,
            company_id=admin.company_id,
            title="Mahsulotingiz rad etildi ❌",
            body=f"'{p.name}' mahsulotingiz rad etildi. Sabab: {data.reason.strip()}",
            notif_type="product_rejected",
            data={"product_id": p.id, "reason": data.reason.strip()},
        )
    except Exception as ex:
        logger.warning("notify_agent xatoligi: %s", ex)

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
