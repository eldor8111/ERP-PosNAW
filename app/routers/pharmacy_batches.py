"""D3.3 — Dorixona: partiya holatlari (faol, karantin, brak, qaytarib olingan).

Faqat dorixona moduli yoqilgan korxonada ishlaydi (oddiy do'konda 403).
`Batch.status` NULL yoki 'active' — faol; 'quarantine' | 'defect' | 'recalled' partiyalar sotuvga
ajratilmaydi (`batch_allocator.batch_active_filter`), lekin ta'minotchiga qaytarish mumkin.
Holat o'zgarishi AuditLog ("BATCH_STATUS") ga yoziladi; sabab majburiy.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.routers.pharmacy_reports import _warehouse_scope
from app.utils.report_utils import local_today

router = APIRouter(
    prefix="/pharmacy/batches",
    tags=["Pharmacy batches"],
    dependencies=[Depends(require_feature("pharmacy"))],
)

VIEW_ROLES = (
    UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager,
    UserRole.accountant, UserRole.warehouse,
)
STATUS_ROLES = (
    UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager, UserRole.warehouse,
)

QTY_ROLES = (UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager)   # P.9: qoldiqni tuzatish

STATUSES = ("active", "quarantine", "defect", "recalled")
STATUS_FILTER_PATTERN = "^(active|quarantine|defect|recalled)$"
OTHER_BRANCH = "Bu filial ma'lumotiga ruxsat yo'q"
MAX_ROWS = 2000


class BatchStatusIn(BaseModel):
    status: str
    reason: str


class BatchEditIn(BaseModel):
    """P.5: partiya seriyasi va sanalarini to'g'rilash (dorini tahrirlash oynasidan). Yuborilmagan maydon o'zgarmaydi;
    manufacture_date: null — o'chiriladi."""
    lot_number: Optional[str] = None
    expiry_date: Optional[date] = None
    manufacture_date: Optional[date] = None
    # P.9: partiya qoldig'ini tuzatish (asosiy birlikda, >= 0): ombor qoldig'i ham farqqa o'zgaradi, ADJUST harakati
    quantity: Optional[Decimal] = None


def _company_id(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


def _norm(status: Optional[str]) -> str:
    return status or "active"


@router.get("")
def list_batches(
    product_id: Optional[int] = Query(None),
    warehouse_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, pattern=STATUS_FILTER_PATTERN,
                                  description="active | quarantine | defect | recalled (bo'sh — hammasi)"),
    lot: Optional[str] = Query(None, description="Seriya raqami (qisman moslik)"),
    expiry_from: Optional[date] = Query(None),
    expiry_to: Optional[date] = Query(None),
    include_empty: bool = Query(False, description="Qoldig'i 0 bo'lgan partiyalar ham"),
    limit: int = Query(500, ge=1, le=MAX_ROWS),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VIEW_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
) -> List[Dict[str, Any]]:
    """Partiyalar: seriya, muddat, ombor, qoldiq, holat. Filial doirasi mavjud qoidalar bo'yicha."""
    cid = _company_id(current_user)
    wh_ids = _warehouse_scope(db, current_user, ctx, branch_id, warehouse_id)

    q = (
        db.query(Batch, Product.name, Product.unit, ProductVariant.name, Warehouse.name, Warehouse.branch_id, Branch.name)
        .join(Product, Product.id == Batch.product_id)
        .outerjoin(ProductVariant, ProductVariant.id == Batch.variant_id)
        .outerjoin(Warehouse, Warehouse.id == Batch.warehouse_id)
        .outerjoin(Branch, Branch.id == Warehouse.branch_id)
        .filter(Batch.company_id == cid)
    )
    if wh_ids is not None:
        # Omborsiz eski partiyalar har qanday ombor uchun amal qiladi — ular ham ko'rinadi
        q = q.filter(or_(Batch.warehouse_id.in_(wh_ids), Batch.warehouse_id.is_(None)))
    if not include_empty:
        q = q.filter(Batch.quantity > 0)
    if product_id:
        q = q.filter(Batch.product_id == product_id)
    if status == "active":
        q = q.filter(or_(Batch.status.is_(None), Batch.status == "active"))
    elif status:
        q = q.filter(Batch.status == status)
    if lot and lot.strip():
        q = q.filter(Batch.lot_number.ilike(f"%{lot.strip()}%"))
    if expiry_from:
        q = q.filter(Batch.expiry_date >= datetime.combine(expiry_from, datetime.min.time()))
    if expiry_to:
        # expiry_to kuni ham kiradi
        q = q.filter(Batch.expiry_date < datetime.combine(expiry_to + timedelta(days=1), datetime.min.time()))

    rows = q.order_by(Batch.expiry_date.asc().nulls_last(), Batch.id.asc()).offset(offset).limit(limit).all()
    today = local_today()
    out: List[Dict[str, Any]] = []
    for b, p_name, p_unit, v_name, w_name, w_branch_id, br_name in rows:
        expiry = b.expiry_date.date() if b.expiry_date else None
        out.append({
            "batch_id": b.id,
            "product_id": b.product_id,
            "product_name": p_name,
            "variant_name": v_name,
            "unit": p_unit,
            "lot_number": b.lot_number,
            "expiry_date": expiry.isoformat() if expiry else None,
            "manufacture_date": b.manufacture_date.date().isoformat() if b.manufacture_date else None,   # P.5
            "days_left": (expiry - today).days if expiry else None,
            "warehouse_id": b.warehouse_id,
            "warehouse_name": w_name,
            "branch_id": w_branch_id,
            "branch_name": br_name,
            "quantity": float(b.quantity or 0),
            "initial_quantity": float(b.initial_quantity or 0),
            "unit_cost": float(b.purchase_price or 0),
            "status": _norm(b.status),
            "status_reason": b.status_reason,
            "status_changed_at": b.status_changed_at.isoformat() if b.status_changed_at else None,
            "status_changed_by": b.status_changed_by,
        })
    return out


def _locked_batch(db: Session, batch_id: int, cid: int, ctx: BranchContext):
    """Qulflangan partiya va uning filiali; boshqa korxona -> 404, ruxsatsiz filial -> 403."""
    # Sotuv bilan poygani oldini olish uchun qator qulflanadi; boshqa korxona partiyasi -> 404
    batch = (
        db.query(Batch).filter(Batch.id == batch_id, Batch.company_id == cid)
        .populate_existing().with_for_update().first()
    )
    if not batch:
        raise HTTPException(status_code=404, detail="Partiya topilmadi")
    branch_id = None
    if batch.warehouse_id is not None:
        wh = db.query(Warehouse).filter(Warehouse.id == batch.warehouse_id, Warehouse.company_id == cid).first()
        branch_id = wh.branch_id if wh else None
        allowed = ctx.allowed_branch_ids  # None — cheklanmagan
        if allowed is not None and branch_id not in allowed:
            raise HTTPException(status_code=403, detail=OTHER_BRANCH)
        scope_ids = ctx.scope_ids()
        if scope_ids is not None and branch_id not in scope_ids:
            raise HTTPException(status_code=403, detail=OTHER_BRANCH)
    return batch, branch_id


@router.put("/{batch_id}")
def edit_batch(
    batch_id: int,
    data: BatchEditIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STATUS_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """P.5: partiyaning seriya raqami, yaroqlilik muddati va ishlab chiqarilgan sanasini to'g'rilash; audit log yoziladi."""
    cid = _company_id(current_user)
    batch, branch_id = _locked_batch(db, batch_id, cid, ctx)
    sent = data.model_fields_set
    old = {
        "lot_number": batch.lot_number,
        "expiry_date": batch.expiry_date.date().isoformat() if batch.expiry_date else None,
        "manufacture_date": batch.manufacture_date.date().isoformat() if batch.manufacture_date else None,
    }
    if "lot_number" in sent and (data.lot_number or "").strip():
        lot = data.lot_number.strip()
        if len(lot) > 100:
            raise HTTPException(status_code=400, detail="Seriya raqami 100 belgidan oshmasligi kerak")
        batch.lot_number = lot
    if "expiry_date" in sent:
        if data.expiry_date is None:
            raise HTTPException(status_code=400, detail="Yaroqlilik muddatini kiriting")
        batch.expiry_date = datetime.combine(data.expiry_date, datetime.min.time())
    if "manufacture_date" in sent:
        batch.manufacture_date = (datetime.combine(data.manufacture_date, datetime.min.time())
                                  if data.manufacture_date else None)
    if batch.manufacture_date and batch.expiry_date and batch.manufacture_date >= batch.expiry_date:
        raise HTTPException(status_code=400, detail="Ishlab chiqarilgan sana yaroqlilik muddatidan oldin bo'lishi kerak")
    old["quantity"] = str(batch.quantity or 0)
    if "quantity" in sent and data.quantity is not None:
        # P.9: qoldiqni tuzatish — umumiy /inventory/adjust dagidek faqat admin/direktor/menejer
        if current_user.role not in QTY_ROLES:
            raise HTTPException(status_code=403, detail="Qoldiqni o'zgartirishga ruxsat yo'q")
        new_qty = Decimal(str(data.quantity))
        if not new_qty.is_finite() or new_qty < 0:
            raise HTTPException(status_code=400, detail="Qoldiq manfiy bo'lishi mumkin emas")
        delta = new_qty - Decimal(str(batch.quantity or 0))
        if delta != 0:
            if batch.warehouse_id is None:
                raise HTTPException(status_code=400, detail="Partiya omborga bog'lanmagan — qoldiqni Inventarizatsiya orqali tuzating")
            from app.models.inventory import MovementType, StockMovement
            from app.services.inventory_service import get_or_create_stock
            stock = get_or_create_stock(db, batch.product_id, batch.warehouse_id, batch.variant_id)
            level_before = Decimal(str(stock.quantity or 0))
            level_after = max(Decimal("0"), level_before + delta)
            stock.quantity = level_after
            batch.quantity = new_qty
            if new_qty > Decimal(str(batch.initial_quantity or 0)):
                batch.initial_quantity = new_qty
            db.add(StockMovement(
                product_id=batch.product_id, variant_id=batch.variant_id, warehouse_id=batch.warehouse_id,
                type=MovementType.ADJUST, qty_before=level_before, qty_after=level_after, quantity=abs(delta),
                reference_type="batch_edit", reference_id=batch.id, user_id=current_user.id,
                reason=f"Partiya qoldig'i tuzatildi ({batch.lot_number or batch.id})",
            ))
    new = {
        "lot_number": batch.lot_number,
        "expiry_date": batch.expiry_date.date().isoformat() if batch.expiry_date else None,
        "manufacture_date": batch.manufacture_date.date().isoformat() if batch.manufacture_date else None,
        "quantity": str(batch.quantity or 0),
    }
    if new != old:
        db.add(AuditLog(
            user_id=current_user.id, company_id=cid, branch_id=branch_id,
            action="BATCH_EDIT", entity_type="batch", entity_id=batch.id,
            old_values=old, new_values={**new, "product_id": batch.product_id},
        ))
    db.commit()
    return {"batch_id": batch.id, **new}


@router.post("/{batch_id}/status")
def set_batch_status(
    batch_id: int,
    data: BatchStatusIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STATUS_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Partiya holatini o'zgartiradi (active, quarantine, defect, recalled). Sabab majburiy; audit log yoziladi."""
    cid = _company_id(current_user)
    new_status = (data.status or "").strip().lower()
    if new_status not in STATUSES:
        raise HTTPException(status_code=422, detail="Holat: active, quarantine, defect yoki recalled bo'lishi kerak")
    reason = (data.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Holatni o'zgartirish sababini kiriting")

    batch, branch_id = _locked_batch(db, batch_id, cid, ctx)

    old_status = _norm(batch.status)
    if old_status == new_status:
        raise HTTPException(status_code=400, detail="Partiya allaqachon shu holatda")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    batch.status = new_status
    batch.status_reason = reason[:500]
    batch.status_changed_at = now
    batch.status_changed_by = current_user.id
    db.add(AuditLog(
        user_id=current_user.id, company_id=cid, branch_id=branch_id,
        action="BATCH_STATUS", entity_type="batch", entity_id=batch.id,
        old_values={"status": old_status},
        new_values={"status": new_status, "reason": reason, "quantity": str(batch.quantity or 0),
                    "lot_number": batch.lot_number, "product_id": batch.product_id},
    ))
    db.commit()
    return {
        "batch_id": batch.id,
        "status": new_status,
        "previous_status": old_status,
        "status_reason": batch.status_reason,
        "status_changed_at": now.isoformat(),
    }
