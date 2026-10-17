"""Marketplace agentlarini korxona admini boshqaradi (/api/marketplace-agents/*).

Modul o'chiq korxonalar uchun butun router yopiq (require_feature).
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
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
from app.models.purchase_order import POStatus
from app.models.supplier import Supplier
from app.models.user import User, UserRole, UserStatus
from app.models.warehouse import Warehouse
from app.routers.mobile.marketplace_agent import _product_out, agent_balance, check_warehouse
from app.schemas.marketplace import AgentStatusIn, ApproveIn, PayoutIn, ProductUpdateIn, ReceiveIn, RejectIn
from app.schemas.purchase_order import POCreate, POItemCreate
from app.services import marketplace_service as mp
from app.services import supplier_ledger
from app.services.branch_provisioning import DEFAULT_CANDIDATE_TYPES, get_default_warehouse
from app.services.purchase_order_service import create_purchase_order
from app.services.wallet_access import get_company_wallet
from app.services.warehouse_access import assert_warehouse_branch_access, resolve_ctx

# T3.17: modul o'chiq korxonalar uchun butun router yopiq
_feature = require_feature("marketplace_agents")

router = APIRouter(
    prefix="/marketplace-agents", tags=["marketplace-agents"], dependencies=[Depends(_feature)],
)

_admin = require_roles(UserRole.admin, UserRole.director, UserRole.manager)
# T3.17: agentga pul to'lash — faqat admin/director
_payout_roles = require_roles(UserRole.admin, UserRole.director)


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
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("list_products error: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
        return {"total": 0, "items": []}


def _pick_warehouse(db: Session, admin: User, warehouse_id: Optional[int],
                    preferred_id: Optional[int]) -> Optional[Warehouse]:
    """Kirim qilinadigan ombor (T3.17).

    Aniq `warehouse_id` — korxonaning faol ombori bo'lishi shart (boshqa korxona — 404), menejer
    uchun o'z filialida (aks holda 403). Berilmasa agent so'ragan `preferred_id`, so'ng
    filial/korxona standart ombori (main/shop, `id` bo'yicha tartiblangan). Topilmasa `None`."""
    cid = admin.company_id
    wid = warehouse_id or preferred_id
    if wid:
        wh = db.query(Warehouse).filter(
            Warehouse.id == wid, Warehouse.company_id == cid, Warehouse.is_active == True,  # noqa: E712
        ).first()
        if wh:
            assert_warehouse_branch_access(db, admin, None, wh.id)  # menejer boshqa filial — 403
            return wh
        if warehouse_id:
            raise HTTPException(status_code=404, detail="Ombor topilmadi")
        # agent so'ragan ombor o'chirilgan/nofaol — standart omborga tushamiz

    ctx = resolve_ctx(db, admin)
    ids = None if ctx.bypass else ctx.scope_ids()
    from app.core.branch_context import effective_branch_id
    br = effective_branch_id(db, admin)
    if br and (ids is None or br in ids):
        wh = get_default_warehouse(db, cid, br)
        if wh:
            return wh
    base = db.query(Warehouse).filter(Warehouse.company_id == cid, Warehouse.is_active == True)  # noqa: E712
    if ids is not None:
        base = base.filter(Warehouse.branch_id.in_(list(ids)))
    return (
        base.filter(Warehouse.is_default == True).order_by(Warehouse.id).first()  # noqa: E712
        or base.filter(Warehouse.type.in_(DEFAULT_CANDIDATE_TYPES)).order_by(Warehouse.id).first()
    )


def _sync_product(db: Session, admin: User, p: MarketplaceProduct):
    """Marketplace tovarini asosiy `Product` jadvaliga sinxronlaydi (shtrix-kod/nom bo'yicha topadi)."""
    from app.models.product import Product, ProductStatus
    chk = db.query(Product).filter(Product.company_id == admin.company_id, Product.is_deleted == False)  # noqa: E712
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
    return prod


def _agent_supplier(db: Session, admin: User, agent: User) -> Supplier:
    """Agent uchun ta'minotchi (telefon bo'yicha topiladi, bo'lmasa yaratiladi)."""
    supplier = db.query(Supplier).filter(
        Supplier.company_id == admin.company_id, Supplier.phone == agent.phone).first()
    if not supplier:
        supplier = Supplier(
            company_id=admin.company_id,
            name=f"Agent: {agent.name}",
            phone=agent.phone,
            notes=f"Marketplace savdo agenti #{agent.id}",
            is_active=True,
        )
        db.add(supplier)
        db.flush()
    return supplier


def _receive_into_warehouse(db: Session, admin: User, p: MarketplaceProduct, agent: User, wh: Warehouse) -> None:
    """Tovarni yagona xarid servisi (`create_purchase_order`, status=received) orqali omborga kirim qiladi:
    PO raqami, qoldiq, Batch va ta'minotchi qarzi (ledger) shu yerda yoziladi. Xatolar yutilmaydi."""
    prod = _sync_product(db, admin, p)
    supplier = _agent_supplier(db, admin, agent)
    po = create_purchase_order(db, POCreate(
        supplier_id=supplier.id, warehouse_id=wh.id, status=POStatus.received, currency="UZS",
        note=f"Marketplace agenti ({agent.name}) tovari: {p.name} (MP #{p.id})",
        items=[POItemCreate(product_id=prod.id, qty_ordered=Decimal(str(p.qty or 0)),
                            unit_cost=Decimal(str(p.price or 0)))],
    ), admin)
    p.purchase_order_id = po.id
    p.warehouse_id = wh.id


def _locked_product(db: Session, admin: User, product_id: int) -> MarketplaceProduct:
    p = db.query(MarketplaceProduct).filter(
        MarketplaceProduct.id == product_id, MarketplaceProduct.company_id == admin.company_id,
    ).with_for_update().first()
    if not p:
        raise HTTPException(status_code=404, detail="Mahsulot topilmadi")
    return p


def _atomic(db: Session, fn) -> None:
    """`fn` ni savepoint ichida bajaradi: xatoda hammasi orqaga qaytadi va HTTP xato ko'tariladi."""
    try:
        with db.begin_nested():
            fn()
    except HTTPException:
        raise
    except Exception as ex:
        logger.exception("Marketplace kirimida xatolik: %s", ex)
        raise HTTPException(status_code=500, detail="Tovarni omborga kirim qilib bo'lmadi")


@router.post("/products/{product_id}/approve")
def approve_product(product_id: int, background_tasks: BackgroundTasks, data: Optional[ApproveIn] = None,
                    db: Session = Depends(get_db), admin: User = Depends(_admin)):
    data = data or ApproveIn()
    p = _locked_product(db, admin, product_id)
    if p.status not in (MarketplaceProductStatus.review, MarketplaceProductStatus.rejected):
        raise HTTPException(status_code=409, detail="Faqat tekshiruvdagi yoki rad etilgan mahsulotni tasdiqlash mumkin")
    agent = db.query(User).filter(User.id == p.agent_id).first()
    if not agent or agent.status != UserStatus.active:
        raise HTTPException(status_code=409, detail="Agent faol emas — avval agentni faollashtiring")

    qty = Decimal(str(p.qty or 0))
    want_receive = bool(data.receive_stock) and qty > 0 and not p.purchase_order_id
    wh = None
    if want_receive or data.warehouse_id:
        wh = _pick_warehouse(db, admin, data.warehouse_id, p.preferred_warehouse_id)
        if want_receive and not wh:
            raise HTTPException(status_code=409, detail="Qabul qilinadigan ombor tanlang")

    def _work():
        if want_receive:
            _receive_into_warehouse(db, admin, p, agent, wh)
        else:
            _sync_product(db, admin, p)

    _atomic(db, _work)

    p.status, p.reject_reason = MarketplaceProductStatus.approved, None
    log_action(db=db, action="MARKETPLACE_PRODUCT_APPROVE", entity_type="marketplace_product",
               entity_id=p.id, user_id=admin.id,
               new_values={"warehouse_id": p.warehouse_id, "purchase_order_id": p.purchase_order_id,
                           "receive_stock": want_receive})

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


@router.post("/products/{product_id}/receive")
def receive_product(product_id: int, data: ReceiveIn, db: Session = Depends(get_db), admin: User = Depends(_admin)):
    """Tasdiqlangan, lekin kirimsiz qolgan (purchase_order_id IS NULL) tovarni keyin omborga kirim qiladi."""
    p = _locked_product(db, admin, product_id)
    if p.status != MarketplaceProductStatus.approved:
        raise HTTPException(status_code=409, detail="Faqat tasdiqlangan mahsulotni kirim qilish mumkin")
    if p.purchase_order_id:
        raise HTTPException(status_code=409, detail="Bu mahsulot allaqachon kirim qilingan")
    if Decimal(str(p.qty or 0)) <= 0:
        raise HTTPException(status_code=409, detail="Mahsulot qoldig'i 0 — kirim qiladigan narsa yo'q")
    agent = db.query(User).filter(User.id == p.agent_id).first()
    if not agent:
        raise HTTPException(status_code=409, detail="Agent topilmadi")
    wh = _pick_warehouse(db, admin, data.warehouse_id, None)
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")

    _atomic(db, lambda: _receive_into_warehouse(db, admin, p, agent, wh))
    log_action(db=db, action="MARKETPLACE_PRODUCT_RECEIVE", entity_type="marketplace_product",
               entity_id=p.id, user_id=admin.id,
               new_values={"warehouse_id": wh.id, "purchase_order_id": p.purchase_order_id})
    db.commit()
    return _product_out(p, mp.category_name_map())


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
    if "preferred_warehouse_id" in changes:
        check_warehouse(db, admin.company_id, changes["preferred_warehouse_id"])
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
def create_payout(agent_id: int, data: PayoutIn, db: Session = Depends(get_db), admin: User = Depends(_payout_roles)):
    u = _agent_or_404(db, admin, agent_id)
    # Bir vaqtda ikki to'lov balansdan oshib ketmasligi uchun agent qatorini qulflaymiz
    db.query(User).filter(User.id == u.id).with_for_update().first()
    bal = agent_balance(db, u.id)["balance"]
    if float(data.amount) > bal + 0.001:
        raise HTTPException(status_code=400, detail=f"To'lov summasi balansdan oshadi (balans: {bal:,.2f})")

    # T3.17: pul faqat shu korxonaning faol (umumiy) kassasidan, filial doirasida chiqadi
    wallet = get_company_wallet(db, data.wallet_id, admin.company_id, for_update=True)
    if wallet is None or getattr(wallet, "is_personal", False):
        raise HTTPException(status_code=404, detail="Kassa (hamyon) topilmadi")
    ctx = resolve_ctx(db, admin)
    scope = None if ctx.bypass else ctx.scope_ids()
    if scope is not None and wallet.branch_id not in scope:
        raise HTTPException(status_code=403, detail="Bu kassa sizning filialingizga tegishli emas")
    if Decimal(str(wallet.balance or 0)) < Decimal(str(data.amount)):
        raise HTTPException(status_code=400, detail="Kassada mablag' yetarli emas")

    t = MarketplaceAgentTransaction(
        agent_id=u.id, company_id=admin.company_id, transaction_type=MarketplaceTransactionType.payout,
        amount=data.amount, note=data.note, wallet_id=wallet.id)
    db.add(t)
    db.flush()
    tx = supplier_ledger.record_cash(
        db, user=admin, direction="out", amount=data.amount, currency="UZS", payment_type=data.payment_type,
        wallet_id=wallet.id, reference_type="marketplace_payout", reference_id=t.id,
        description=f"Marketplace agent to'lovi: {u.name}",
    )
    if wallet.branch_id:
        tx.branch_id = wallet.branch_id  # xarajat kassa filialiga yoziladi
    t.finance_transaction_id = tx.id
    t.branch_id = tx.branch_id
    log_action(db=db, action="MARKETPLACE_PAYOUT", entity_type="marketplace_agent_transaction",
               entity_id=t.id, user_id=admin.id,
               new_values={"agent_id": u.id, "amount": str(data.amount), "wallet_id": wallet.id,
                           "finance_transaction_id": tx.id})
    db.commit()
    return {"id": t.id, "wallet_id": wallet.id, "finance_transaction_id": tx.id, **agent_balance(db, u.id)}


@router.get("/stats/summary")
def stats(db: Session = Depends(get_db), admin: User = Depends(_admin)):
    cid = admin.company_id
    agents = db.query(User.status, func.count(User.id)).filter(
        User.company_id == cid, User.role == UserRole.marketplace_agent).group_by(User.status).all()
    prods = db.query(MarketplaceProduct.status, func.count(MarketplaceProduct.id)).filter(
        MarketplaceProduct.company_id == cid).group_by(MarketplaceProduct.status).all()
    return {"agents": {k.value: v for k, v in agents}, "products": {k.value: v for k, v in prods}}
