"""D4.2 — Dorixona: seriya bo'yicha kuzatish va qaytarib olish (recall).

Faqat dorixona moduli yoqilgan korxonada ishlaydi (oddiy do'konda 403).
  GET  /pharmacy/recall            — seriya: ta'minotchi/xarid, hozirgi qoldiq (omborlar), kimga sotilgan, qaytarishlar
  GET  /pharmacy/recall/customers  — seriyani olgan mijozlar ro'yxati (CSV, Excel ochadi)
  POST /pharmacy/recall/block      — shu seriyali BARCHA partiyalar 'recalled' (D3.3), audit log, admin Telegram xabari
Qaytarib olingan partiya sotuvga ajratilmaydi (`batch_allocator.batch_active_filter`), lekin ta'minotchiga
qaytarish mumkin.
"""
import csv
import io
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.admin_tg_bot.notifications import trigger_batch_recalled
from app.core.branch_context import BranchContext, get_branch_context
from app.core.dependencies import require_roles
from app.core.features import require_feature
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.purchase_order import PurchaseOrder
from app.models.sale import Sale, SaleItem, SaleItemBatch, SaleStatus
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.routers.pharmacy_reports import _warehouse_scope
from app.services.supplier_return_service import ACTION as SUPPLIER_RETURN_ACTION
from app.utils.report_utils import local_today

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pharmacy/recall",
    tags=["Pharmacy recall"],
    dependencies=[Depends(require_feature("pharmacy"))],
)

VIEW_ROLES = (
    UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager,
    UserRole.accountant, UserRole.warehouse,
)
BLOCK_ROLES = (
    UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager, UserRole.warehouse,
)

OTHER_BRANCH = "Bu filial ma'lumotiga ruxsat yo'q"
MAX_ROWS = 5000
RECALL_STATUS = "recalled"


class RecallBlockIn(BaseModel):
    lot: str
    product_id: Optional[int] = None
    reason: str


def _company_id(user: User) -> int:
    if not user.company_id:
        raise HTTPException(status_code=400, detail="Korxona aniqlanmadi")
    return user.company_id


def _num(v) -> float:
    return float(v or 0)


def _clean_lot(lot: Optional[str]) -> str:
    lot = (lot or "").strip()
    if not lot:
        raise HTTPException(status_code=400, detail="Seriya raqamini kiriting")
    return lot


def _lot_query(db: Session, cid: int, lot: str, product_id: Optional[int]):
    """Korxona partiyalari: seriya raqami TO'LIQ mos (katta-kichik harfga e'tiborsiz)."""
    q = db.query(Batch).filter(Batch.company_id == cid, func.lower(Batch.lot_number) == lot.lower())
    if product_id:
        q = q.filter(Batch.product_id == product_id)
    return q


def _sales_rows(
    db: Session, cid: int, batch_ids: List[int], ctx: BranchContext, limit: int = MAX_ROWS,
    scoped: bool = True,
) -> List[Dict[str, Any]]:
    """Shu partiyalardan sotilgan qatorlar (SaleItemBatch orqali): mijoz, telefon, sana, miqdor.
    Qaytarish hujjatlari (original_sale_id) chiqarilmaydi; filial doirasi sotuv filiali bo'yicha."""
    if not batch_ids:
        return []
    q = (
        db.query(SaleItemBatch, SaleItem, Sale, Product.name, Customer.name, Customer.phone,
                 Branch.name, User.name)
        .join(SaleItem, SaleItem.id == SaleItemBatch.sale_item_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .outerjoin(Customer, Customer.id == Sale.customer_id)
        .outerjoin(Branch, Branch.id == Sale.branch_id)
        .outerjoin(User, User.id == Sale.cashier_id)
        .filter(
            SaleItemBatch.batch_id.in_(batch_ids),
            Sale.company_id == cid,
            Sale.original_sale_id.is_(None),
            Sale.status != SaleStatus.cancelled,
        )
    )
    scope = ctx.scope_ids() if scoped else None
    if scope is not None:
        q = q.filter(or_(Sale.branch_id.in_(list(scope)), Sale.branch_id.is_(None)))
    rows = q.order_by(Sale.created_at.desc(), Sale.id.desc()).limit(limit).all()
    out: List[Dict[str, Any]] = []
    for sib, item, sale, p_name, c_name, c_phone, br_name, cashier in rows:
        status = sale.status.value if hasattr(sale.status, "value") else sale.status
        out.append({
            "sale_id": sale.id,
            "sale_number": sale.number,
            "sold_at": sale.created_at.isoformat() if sale.created_at else None,
            "status": status,
            "branch_id": sale.branch_id,
            "branch_name": br_name,
            "cashier_name": cashier,
            "customer_id": sale.customer_id,
            "customer_name": c_name,
            "customer_phone": c_phone,
            "batch_id": sib.batch_id,
            "product_id": item.product_id,
            "product_name": p_name,
            "quantity": _num(sib.quantity),
            # Qaytarish partiya bo'yicha emas, sotuv qatori bo'yicha yuritiladi
            "returned_quantity": _num(item.returned_quantity),
            "item_quantity": _num(item.quantity),
        })
    return out


def _supplier_returns(db: Session, cid: int, batch_ids: List[int]) -> List[Dict[str, Any]]:
    """Ta'minotchiga qaytarishlar: AuditLog(RETURN_TO_SUPPLIER).movements[].batches = [[batch_id, qty]]."""
    if not batch_ids:
        return []
    wanted = set(batch_ids)
    suppliers = {s.id: s.name for s in db.query(Supplier.id, Supplier.name).filter(Supplier.company_id == cid).all()}
    if not suppliers:
        return []
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.action == SUPPLIER_RETURN_ACTION, AuditLog.entity_type == "supplier",
                AuditLog.entity_id.in_(list(suppliers)))
        .order_by(AuditLog.id.desc()).limit(MAX_ROWS).all()
    )
    out: List[Dict[str, Any]] = []
    for lg in logs:
        nv = lg.new_values or {}
        for mv in nv.get("movements") or []:
            for pair in mv.get("batches") or []:
                try:
                    b_id, qty = int(pair[0]), float(pair[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if b_id in wanted:
                    out.append({
                        "log_id": lg.id,
                        "returned_at": lg.created_at.isoformat() if lg.created_at else None,
                        "supplier_id": lg.entity_id,
                        "supplier_name": suppliers.get(lg.entity_id),
                        "batch_id": b_id,
                        "quantity": qty,
                        "reverted": bool(nv.get("reverted")),
                    })
    return out


@router.get("")
def recall_lookup(
    lot: str = Query(..., description="Seriya raqami (to'liq mos)"),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VIEW_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
) -> Dict[str, Any]:
    """Seriya kuzatuvi: qaysi ta'minotchi/xarid bilan kelgan, hozir qaysi omborda qancha, kimga sotilgan, qaytarishlar."""
    cid = _company_id(current_user)
    lot = _clean_lot(lot)
    wh_ids = _warehouse_scope(db, current_user, ctx, None, None)

    q = (
        _lot_query(db, cid, lot, product_id)
        .join(Product, Product.id == Batch.product_id)
        .outerjoin(ProductVariant, ProductVariant.id == Batch.variant_id)
        .outerjoin(Warehouse, Warehouse.id == Batch.warehouse_id)
        .outerjoin(Branch, Branch.id == Warehouse.branch_id)
        .outerjoin(PurchaseOrder, PurchaseOrder.id == Batch.po_id)
        .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
    )
    if wh_ids is not None:
        # Omborsiz eski partiyalar har qanday ombor uchun amal qiladi
        q = q.filter(or_(Batch.warehouse_id.in_(wh_ids), Batch.warehouse_id.is_(None)))
    rows = (
        q.with_entities(Batch, Product.name, Product.unit, ProductVariant.name, Warehouse.name,
                        Warehouse.branch_id, Branch.name, PurchaseOrder.number,
                        PurchaseOrder.supplier_invoice_number, PurchaseOrder.supplier_invoice_date,
                        Supplier.id, Supplier.name, Supplier.phone)
        .order_by(Batch.id.asc()).limit(MAX_ROWS).all()
    )

    today = local_today()
    batches: List[Dict[str, Any]] = []
    stock: Dict[Any, Dict[str, Any]] = {}
    for (b, p_name, p_unit, v_name, w_name, w_branch_id, br_name, po_number,
         inv_no, inv_date, sup_id, sup_name, sup_phone) in rows:
        expiry = b.expiry_date.date() if b.expiry_date else None
        qty = _num(b.quantity)
        batches.append({
            "batch_id": b.id,
            "product_id": b.product_id,
            "product_name": p_name,
            "variant_name": v_name,
            "unit": p_unit,
            "lot_number": b.lot_number,
            "expiry_date": expiry.isoformat() if expiry else None,
            "days_left": (expiry - today).days if expiry else None,
            "received_at": b.created_at.isoformat() if b.created_at else None,
            "initial_quantity": _num(b.initial_quantity),
            "quantity": qty,
            "unit_cost": _num(b.purchase_price),
            "warehouse_id": b.warehouse_id,
            "warehouse_name": w_name,
            "branch_id": w_branch_id,
            "branch_name": br_name,
            "po_id": b.po_id,
            "po_number": po_number,
            "supplier_invoice_number": inv_no,
            "supplier_invoice_date": inv_date.isoformat() if inv_date else None,
            "supplier_id": sup_id,
            "supplier_name": sup_name,
            "supplier_phone": sup_phone,
            "status": b.status or "active",
            "status_reason": b.status_reason,
            "status_changed_at": b.status_changed_at.isoformat() if b.status_changed_at else None,
        })
        if qty > 0:
            key = (b.warehouse_id, b.product_id)
            s = stock.setdefault(key, {
                "warehouse_id": b.warehouse_id, "warehouse_name": w_name, "branch_id": w_branch_id,
                "branch_name": br_name, "product_id": b.product_id, "product_name": p_name, "quantity": 0.0,
            })
            s["quantity"] += qty

    batch_ids = [x["batch_id"] for x in batches]
    sales = _sales_rows(db, cid, batch_ids, ctx)
    supplier_returns = _supplier_returns(db, cid, batch_ids)
    customer_keys = {s["customer_id"] for s in sales if s["customer_id"]}

    summary = {
        "received": sum(x["initial_quantity"] for x in batches),
        "remaining": sum(x["quantity"] for x in batches),
        "sold": sum(s["quantity"] for s in sales),
        "returned_by_customers": sum(min(s["returned_quantity"], s["quantity"]) for s in sales),
        "returned_to_supplier": sum(r["quantity"] for r in supplier_returns if not r["reverted"]),
        "sales_count": len({s["sale_id"] for s in sales}),
        "customers_count": len(customer_keys),
        "walk_in_sales": len({s["sale_id"] for s in sales if not s["customer_id"]}),
        "recalled_batches": sum(1 for x in batches if x["status"] == RECALL_STATUS),
    }
    return {
        "lot": lot,
        "product_id": product_id,
        "found": bool(batches),
        "batches": batches,
        "stock": sorted(stock.values(), key=lambda s: (s["branch_name"] or "", s["warehouse_name"] or "")),
        "sales": sales,
        "supplier_returns": supplier_returns,
        "summary": summary,
    }


@router.get("/customers")
def recall_customers(
    lot: str = Query(..., description="Seriya raqami (to'liq mos)"),
    product_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VIEW_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Seriyani olgan mijozlar ro'yxati — CSV (UTF-8 BOM, Excel ochadi): mijoz, telefon, sana, sotuv, miqdor."""
    cid = _company_id(current_user)
    lot = _clean_lot(lot)
    wh_ids = _warehouse_scope(db, current_user, ctx, None, None)
    bq = _lot_query(db, cid, lot, product_id).with_entities(Batch.id)
    if wh_ids is not None:
        bq = bq.filter(or_(Batch.warehouse_id.in_(wh_ids), Batch.warehouse_id.is_(None)))
    batch_ids = [r[0] for r in bq.all()]
    sales = _sales_rows(db, cid, batch_ids, ctx)

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Mijoz", "Telefon", "Sana", "Sotuv", "Filial", "Mahsulot", "Seriya",
                "Miqdor", "Qaytarilgan", "Holat"])
    for s in sales:
        # Excel formula in'ektsiyasidan himoya: matn maydonlari = + - @ bilan boshlansa oldiga ' qo'yiladi
        # (telefon "+998..." o'zgarishsiz qoladi)
        safe = [("'" + c) if c[:1] in ("=", "+", "-", "@") else c
                for c in (s["customer_name"] or "", s["branch_name"] or "", s["product_name"], lot)]
        w.writerow([safe[0], s["customer_phone"] or "", (s["sold_at"] or "")[:19].replace("T", " "),
                    s["sale_number"], safe[1], safe[2], safe[3],
                    f"{s['quantity']:g}", f"{s['returned_quantity']:g}", s["status"]])
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=seriya_mijozlari_{local_today():%Y%m%d}.csv"},
    )


@router.post("/block")
def recall_block(
    data: RecallBlockIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*BLOCK_ROLES)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """Shu seriyali BARCHA filiallardagi partiyalarni 'recalled' holatiga o'tkazadi: sotuvga ajratilmaydi.
    Sabab majburiy; har partiya uchun AuditLog (BATCH_STATUS) + umumiy yozuv (PHARMACY_RECALL);
    admin Telegram botiga xabar yuboriladi. Foydalanuvchi filial doirasi barcha partiyalarni qamrab
    olmasa — 403 (seriya butun korxona bo'yicha bloklanadi)."""
    cid = _company_id(current_user)
    lot = _clean_lot(data.lot)
    reason = (data.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Qaytarib olish sababini kiriting")

    # Sotuv bilan poygani oldini olish uchun qatorlar qulflanadi
    batches = (
        _lot_query(db, cid, lot, data.product_id)
        .order_by(Batch.id.asc()).populate_existing().with_for_update().all()
    )
    if not batches:
        raise HTTPException(status_code=404, detail="Seriya topilmadi")

    wh_branch = {
        w.id: w.branch_id for w in db.query(Warehouse.id, Warehouse.branch_id).filter(
            Warehouse.company_id == cid,
            Warehouse.id.in_([b.warehouse_id for b in batches if b.warehouse_id is not None] or [0]),
        ).all()
    }
    # Faol filial sarlavhasidan qat'i nazar: bloklash barcha filiallarga tegadi -> ruxsat etilgan filiallar to'liq qamrashi shart
    allowed = ctx.allowed_branch_ids  # None — cheklanmagan
    if allowed is not None:
        for b in batches:
            if b.warehouse_id is not None and wh_branch.get(b.warehouse_id) not in allowed:
                raise HTTPException(status_code=403, detail=OTHER_BRANCH)

    todo = [b for b in batches if (b.status or "active") != RECALL_STATUS]
    if not todo:
        raise HTTPException(status_code=400, detail="Seriya allaqachon qaytarib olingan")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    total_qty = Decimal("0")
    for b in todo:
        old_status = b.status or "active"
        total_qty += Decimal(str(b.quantity or 0))
        b.status = RECALL_STATUS
        b.status_reason = reason[:500]
        b.status_changed_at = now
        b.status_changed_by = current_user.id
        db.add(AuditLog(
            user_id=current_user.id, company_id=cid, branch_id=wh_branch.get(b.warehouse_id),
            action="BATCH_STATUS", entity_type="batch", entity_id=b.id,
            old_values={"status": old_status},
            new_values={"status": RECALL_STATUS, "reason": reason, "quantity": str(b.quantity or 0),
                        "lot_number": b.lot_number, "product_id": b.product_id, "recall": True},
        ))

    todo_ids = [b.id for b in todo]
    sales = _sales_rows(db, cid, todo_ids, ctx, scoped=False)  # bloklash butun korxona bo'yicha
    customers_count = len({s["customer_id"] for s in sales if s["customer_id"]})
    sales_count = len({s["sale_id"] for s in sales})
    product_ids = sorted({b.product_id for b in todo})
    names = [r[0] for r in db.query(Product.name).filter(Product.id.in_(product_ids)).order_by(Product.name).all()]
    db.add(AuditLog(
        user_id=current_user.id, company_id=cid,
        action="PHARMACY_RECALL", entity_type="batch_lot", entity_id=None,
        new_values={"lot": lot, "reason": reason, "batch_ids": todo_ids, "product_ids": product_ids,
                    "quantity": str(total_qty), "customers": customers_count, "sales": sales_count},
    ))
    db.commit()

    # Telegram xabari commit'dan keyin; xato bloklashga ta'sir qilmaydi
    try:
        trigger_batch_recalled(
            cid, lot=lot, product_names=names, reason=reason, user_name=current_user.name,
            batches_count=len(todo), remaining_qty=total_qty, customers_count=customers_count,
            sales_count=sales_count,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Qaytarib olish xabari yuborilmadi (korxona %s, seriya %s): %s", cid, lot, e)

    return {
        "lot": lot,
        "status": RECALL_STATUS,
        "blocked_batches": len(todo),
        "batch_ids": todo_ids,
        "already_recalled": len(batches) - len(todo),
        "remaining_quantity": float(total_qty),
        "customers_count": customers_count,
        "sales_count": sales_count,
        "reason": reason[:500],
    }
