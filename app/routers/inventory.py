from datetime import datetime as dt
from decimal import Decimal, ROUND_DOWN
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import case, func, or_
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session, contains_eager, joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.audit import log_action_for
from app.core.branch_context import BranchContext, apply_branch_scope, apply_warehouse_scope, get_branch_context
from app.core.dependencies import get_current_user, require_roles
from app.database import get_db
from app.models.inventory import StockLevel, StockMovement, MovementType
from app.models.product import Product
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.schemas.inventory import (
    StockAdjustRequest,
    StockLevelOut,
    StockMovementOut,
    StockReceiveRequest,
    ChiqimBatchRequest,
    ExpiringBatchOut,
    ChiqimDocumentOut,
    ChiqimDetailOut,
    SupplierReturnRequest, StockMovementUpdate, WriteOffExpiredRequest,
    CustomerReturnRequest,
    StockSettingIn, StockSettingBulkIn, StockSettingOut, ReplenishmentItem, ReplenishmentTransferIn,
)
from app.services.inventory_service import (
    get_or_create_stock,
    adjust_stock,
    receive_stock,
    create_chiqim_batch,
    delete_chiqim_batch,
    resolve_chiqim_warehouse,
    active_chiqim_movements,
)
from app.services.expiry import expired_batches_query
from app.services import stock_report
from app.utils import stock_utils
from app.models.warehouse_stock_setting import WarehouseStockSetting
from app.services.warehouse_access import assert_warehouse_branch_access, list_company_warehouses
from app.services.wallet_access import get_company_wallet, find_company_wallet
from app.services.tenant_guards import (
    get_company_warehouse,
    get_company_customer,
    get_company_product,
    get_company_products,
    get_company_variant,
    get_company_wallet as get_open_company_wallet,
    find_default_wallet,
)

router = APIRouter(prefix="/inventory", tags=["Inventory"])

WAREHOUSE_ROLES = (UserRole.admin, UserRole.director, UserRole.warehouse, UserRole.manager)


def _warehouse_branch(db: Session, warehouse_id: Optional[int]) -> Optional[int]:
    """Audit filiali: ombor filiali (ombor ko'rsatilmasa None — foydalanuvchi filiali ishlatiladi)."""
    if not warehouse_id:
        return None
    wh = db.get(Warehouse, warehouse_id)
    return wh.branch_id if wh is not None else None

# Hujjatga bog'langan harakatlar — PUT /{id}/movements orqali tahrirlanmaydi
LOCKED_MOVEMENT_REFS = (
    "return_from_customer", "return_to_supplier", "return_revert", "sale", "sale_refund",
    "stock_transfer", "transfer_in", "transfer_out", "transfer_rejected", "purchase_order",
    "purchase_order_delete", "production_order", "chiqim", "chiqim_revert", "revision",
    "batch_write_off", "auto_batch_write_off", "product_import",
)


def _report_scope(db: Session, user: User, ctx: BranchContext,
                  branch_id: Optional[int], warehouse_id: Optional[int] = None) -> Optional[List[int]]:
    """T2.3: ombor doirasi. `warehouse_id` — korxona/filial/ruxsat bo'yicha qat'iy tekshiriladi (404/400/403);
    ruxsatsiz `branch_id` esa eski xatti-harakat bo'yicha e'tiborsiz qoldiriladi (xodim o'z filialida qoladi)."""
    if not warehouse_id and branch_id and ctx.allowed_branch_ids is not None \
            and branch_id not in ctx.allowed_branch_ids:
        branch_id = None
    return stock_report.resolve_wh_scope(db, user, user.company_id, branch_id, warehouse_id, ctx)


@router.get("/stock", response_model=List[StockLevelOut])
def get_stock_levels(
        low_stock_only: bool = Query(False, description="Faqat kam qoldiqli mahsulotlar (mahsulot darajasida)"),
        search: Optional[str] = Query(None),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari (ruxsat doirasida)"),
        warehouse_id: Optional[int] = Query(None, description="Faqat shu ombor"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    cid = current_user.company_id
    # T1.3: filialga biriktirilgan xodim faqat o'z filiali omborlari qoldig'ini ko'radi
    # (admin/director va filialsiz manager — header/`branch_id` bo'lmasa hammasini)
    wh_ids = _report_scope(db, current_user, ctx, branch_id, warehouse_id)
    if wh_ids is not None and not wh_ids:
        return []
    q = (
        db.query(StockLevel)
        .join(Product, Product.id == StockLevel.product_id)
        # T2.3: faqat faol omborlar (NULL va nofaol ombor qoldig'i hisobotga kirmaydi)
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .filter(Product.is_deleted == False, Warehouse.is_active.isnot(False))
        .options(joinedload(StockLevel.product), contains_eager(StockLevel.warehouse))
    )
    q = q.filter(Product.company_id == cid)
    if wh_ids is not None:
        q = q.filter(StockLevel.warehouse_id.in_(wh_ids))

    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.barcode.ilike(f"%{search}%"))
        )
    # Filtr bazada — aks holda limit birinchi N qatorni kesib, kam qoldiqlilar tushib qolardi.
    # T4.4: ombor sozlamasi (min_qty) bo'lsa shu ombor qoldig'i bo'yicha, bo'lmasa sozlamasiz omborlar
    # yig'indisi bo'yicha (variantlar yig'indisi; sozlama yo'q bo'lsa avvalgi mahsulot darajasidagi natija)
    if low_stock_only:
        joins, low_cond = stock_utils.low_stock_rows_filter(db, cid, wh_ids)
        for target, on in joins:
            q = q.outerjoin(target, on)
        q = q.filter(low_cond)

    stocks = q.order_by(StockLevel.id).offset(skip).limit(limit).all()
    info = stock_utils.row_stock_info(db, cid, wh_ids, stocks)

    return [
        StockLevelOut(
            product_id=s.product_id,
            variant_id=s.variant_id,
            warehouse_id=s.warehouse_id,
            warehouse_name=s.warehouse.name if s.warehouse else None,
            product_name=s.product.name,
            product_sku=s.product.sku,
            product_barcode=s.product.barcode,
            quantity=s.quantity,
            # T4.4: samarali min/max (ombor sozlamasi yoki mahsulot) va shunga mos kam qoldiq bayrog'i
            min_stock=info[s.id]["min"],
            max_stock=info[s.id]["max"],
            is_low_stock=info[s.id]["is_low"],
            updated_at=s.updated_at,
        )
        for s in stocks
    ]


@router.get("/low-stock-count")
def get_low_stock_count(
        branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari (ruxsat doirasida)"),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Kam qoldiqli MAHSULOTLAR soni (yagona ta'rif: stock_report.low_stock_count)."""
    wh_ids = _report_scope(db, current_user, ctx, branch_id)
    return {"count": stock_utils.low_stock_count(db, current_user.company_id, wh_ids)}


@router.get("/low-stock")
def get_low_stock(
        branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari (ruxsat doirasida)"),
        warehouse_id: Optional[int] = Query(None, description="Faqat shu ombor"),
        skip: int = Query(0, ge=0),
        limit: int = Query(200, ge=1, le=1000),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Kam qoldiqli mahsulotlar (eng kritik birinchi), har biri uchun omborlar bo'yicha qoldiq."""
    wh_ids = _report_scope(db, current_user, ctx, branch_id, warehouse_id)
    return stock_utils.low_stock_products(db, current_user.company_id, wh_ids, limit=limit, skip=skip)


# ─── T4.4: ombor bo'yicha min/max qoldiq va to'ldirish ───────────────────────

STOCK_SETTING_WRITE_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)
_SETTING_FIELDS = ("min_qty", "max_qty", "reorder_qty", "source_warehouse_id")
MAX_QTY_LIMIT = Decimal("999999999.999")


def _setting_wh(db: Session, user: User, ctx: BranchContext, warehouse_id: int) -> Warehouse:
    """Ombor korxonaniki (404) va non-admin xodim uchun o'z filialida (403) bo'lishi shart."""
    return assert_warehouse_branch_access(db, user, ctx, warehouse_id)


def _check_setting_values(wh_id: int, mn, mx, rq, src_id) -> None:
    """Qiymat tekshiruvlari (400)."""
    for label, v in (("Min", mn), ("Max", mx), ("To'ldirish miqdori", rq)):
        if v is None:
            continue
        if v < 0:
            raise HTTPException(status_code=400, detail=f"{label} qoldiq manfiy bo'lishi mumkin emas")
        if v > MAX_QTY_LIMIT:
            raise HTTPException(status_code=400, detail=f"{label} qoldiq qiymati juda katta")
    if mn is not None and mx is not None and mx < mn:
        raise HTTPException(status_code=400, detail="Max qoldiq min qoldiqdan kichik bo'lishi mumkin emas")
    if src_id is not None and src_id == wh_id:
        raise HTTPException(status_code=400, detail="Manba ombor shu ombor bilan bir xil bo'lmasligi kerak")


def _save_setting(db: Session, user: User, wh: Warehouse, product_id: int, body: StockSettingIn,
                  fields: set, product: Optional[Product] = None) -> Optional[WarehouseStockSetting]:
    """Bitta (ombor, mahsulot) sozlamasini saqlaydi (flush; commit chaqiruvchida).
    Hamma maydon NULL bo'lib qolsa qator o'chiriladi (None qaytadi)."""
    cid = user.company_id
    if product is None:
        product = get_company_product(db, cid, product_id)
    row = db.query(WarehouseStockSetting).filter(
        WarehouseStockSetting.warehouse_id == wh.id, WarehouseStockSetting.product_id == product_id,
    ).first()
    cur = {f: getattr(row, f, None) if row is not None else None for f in _SETTING_FIELDS}
    new = dict(cur)
    for f in _SETTING_FIELDS:
        if f in fields:
            new[f] = getattr(body, f)
    _check_setting_values(wh.id, new["min_qty"], new["max_qty"], new["reorder_qty"], new["source_warehouse_id"])
    if new["source_warehouse_id"] is not None:
        src = db.query(Warehouse.id).filter(
            Warehouse.id == new["source_warehouse_id"], Warehouse.company_id == cid).first()
        if not src:
            raise HTTPException(status_code=404, detail="Manba ombor topilmadi")
    if all(new[f] is None for f in _SETTING_FIELDS):
        if row is not None:
            db.delete(row)
            db.flush()
        return None
    old_vals = {f: (str(v) if v is not None else None) for f, v in cur.items()}
    if row is None:
        row = WarehouseStockSetting(company_id=cid, warehouse_id=wh.id, product_id=product_id)
        db.add(row)
    for f in _SETTING_FIELDS:
        setattr(row, f, new[f])
    row.updated_by = user.id
    db.flush()
    log_action_for(db, user, "STOCK_SETTING_SAVE", "warehouse_stock_setting", row.id,
                   old_values=old_vals, new_values={f: (str(v) if v is not None else None) for f, v in new.items()},
                   branch_id=wh.branch_id)
    return row


def _setting_out(row: Optional[WarehouseStockSetting], p: Product, qty) -> dict:
    f = lambda v: None if v is None else float(v)  # noqa: E731
    return {
        "product_id": p.id, "product_name": p.name, "product_sku": p.sku,
        "company_min_stock": f(p.min_stock), "company_max_stock": f(p.max_stock),
        "min_qty": f(row.min_qty) if row else None, "max_qty": f(row.max_qty) if row else None,
        "reorder_qty": f(row.reorder_qty) if row else None,
        "source_warehouse_id": row.source_warehouse_id if row else None,
        "current_qty": float(qty or 0),
    }


@router.get("/stock-settings", response_model=List[StockSettingOut])
def list_stock_settings(
        warehouse_id: int = Query(..., description="Ombor"),
        search: Optional[str] = Query(None),
        only_configured: bool = Query(False, description="Faqat ombor sozlamasi bor mahsulotlar"),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Ombor bo'yicha min/max jadvali: mahsulot, korxona chegarasi, ombor sozlamasi va joriy qoldiq."""
    cid = current_user.company_id
    wh = _setting_wh(db, current_user, ctx, warehouse_id)
    qty_sq = (
        db.query(StockLevel.product_id.label("product_id"), func.coalesce(func.sum(StockLevel.quantity), 0).label("qty"))
        .filter(StockLevel.warehouse_id == wh.id).group_by(StockLevel.product_id).subquery()
    )
    q = (
        db.query(Product, WarehouseStockSetting, qty_sq.c.qty)
        .outerjoin(WarehouseStockSetting, (WarehouseStockSetting.product_id == Product.id)
                   & (WarehouseStockSetting.warehouse_id == wh.id))
        .outerjoin(qty_sq, qty_sq.c.product_id == Product.id)
        .filter(Product.company_id == cid, Product.is_deleted == False,  # noqa: E712
                func.coalesce(Product.product_type, "simple") != stock_utils.VIRTUAL_PRODUCT_TYPE)
    )
    if only_configured:
        q = q.filter(WarehouseStockSetting.id.isnot(None))
    if search:
        q = q.filter(or_(Product.name.ilike(f"%{search}%"), Product.sku.ilike(f"%{search}%"),
                         Product.barcode.ilike(f"%{search}%")))
    rows = q.order_by(Product.name, Product.id).offset(skip).limit(limit).all()
    return [_setting_out(r, p, qty) for p, r, qty in rows]


@router.put("/stock-settings/bulk")
def bulk_save_stock_settings(
        body: StockSettingBulkIn,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*STOCK_SETTING_WRITE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Ommaviy saqlash (ko'pi bilan 1000 qator; har qator alohida savepoint). Javob: `{saved, errors}`."""
    wh = _setting_wh(db, current_user, ctx, body.warehouse_id)
    saved = 0
    errors = []
    for it in body.items:
        try:
            with db.begin_nested():
                _save_setting(db, current_user, wh, it.product_id, it, set(it.model_fields_set) & set(_SETTING_FIELDS))
            saved += 1
        except HTTPException as e:
            errors.append({"product_id": it.product_id, "status": e.status_code, "error": e.detail})
    db.commit()
    return {"saved": saved, "errors": errors}


@router.put("/stock-settings/{warehouse_id}/{product_id}", response_model=StockSettingOut)
def save_stock_setting(
        warehouse_id: int,
        product_id: int,
        body: StockSettingIn,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*STOCK_SETTING_WRITE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Ombor x mahsulot chegarasini o'rnatish (berilgan maydonlar yangilanadi, `null` — olib tashlaydi)."""
    wh = _setting_wh(db, current_user, ctx, warehouse_id)
    product = get_company_product(db, current_user.company_id, product_id)
    row = _save_setting(db, current_user, wh, product_id, body,
                        set(body.model_fields_set) & set(_SETTING_FIELDS), product)
    db.commit()
    qty = db.query(func.coalesce(func.sum(StockLevel.quantity), 0)).filter(
        StockLevel.warehouse_id == wh.id, StockLevel.product_id == product_id).scalar()
    return _setting_out(row, product, qty)


@router.delete("/stock-settings/{warehouse_id}/{product_id}")
def delete_stock_setting(
        warehouse_id: int,
        product_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*STOCK_SETTING_WRITE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Ombor sozlamasini o'chirish — hisob-kitob korxona chegarasiga (`Product.min_stock`) qaytadi."""
    wh = _setting_wh(db, current_user, ctx, warehouse_id)
    get_company_product(db, current_user.company_id, product_id)
    row = db.query(WarehouseStockSetting).filter(
        WarehouseStockSetting.warehouse_id == wh.id, WarehouseStockSetting.product_id == product_id,
    ).first()
    if row is not None:
        log_action_for(db, current_user, "STOCK_SETTING_DELETE", "warehouse_stock_setting", row.id,
                       old_values={f: (str(getattr(row, f)) if getattr(row, f) is not None else None)
                                   for f in _SETTING_FIELDS},
                       branch_id=wh.branch_id)
        db.delete(row)
        db.commit()
    return {"deleted": row is not None}


@router.get("/replenishment", response_model=List[ReplenishmentItem])
def get_replenishment(
        warehouse_id: Optional[int] = Query(None, description="To'ldiriladigan ombor"),
        branch_id: Optional[int] = Query(None, description="To'ldiriladigan filial omborlari"),
        source_warehouse_id: Optional[int] = Query(None, description="Manba ombor (qatorda ko'rsatilmagan bo'lsa)"),
        use_product_max: bool = Query(False, description="Ombor max_qty yo'q bo'lsa Product.max_stock ishlatilsin"),
        limit: int = Query(1000, ge=1, le=5000),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Markazdan to'ldirish tavsiyasi: har (ombor, mahsulot) uchun qoldiq, min, max, yetishmovchilik,
    manbadan beriladigan miqdor (manba o'z minimumidan pastga tushmaydi) va `purchase_needed`."""
    cid = current_user.company_id
    wh_ids = _report_scope(db, current_user, ctx, branch_id, warehouse_id)
    if source_warehouse_id is not None:
        get_company_warehouse(db, current_user, source_warehouse_id, enforce_branch=False)
    return stock_utils.replenishment(db, cid, wh_ids, source_warehouse_id=source_warehouse_id,
                                     use_product_max=use_product_max, limit=limit)


@router.post("/replenishment/transfers")
def create_replenishment_transfers(
        body: ReplenishmentTransferIn,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*STOCK_SETTING_WRITE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """To'ldirish tavsiyasidan `pending` transfer qoralamasi (ikki bosqichli; qoldiqqa tegmaydi)."""
    from app.services.transfer_service import create_draft_transfer
    if body.source_warehouse_id == body.destination_warehouse_id:
        raise HTTPException(status_code=400, detail="Manba va maqsad ombor bir xil bo'lmasligi kerak")
    merged = {}
    for it in body.items:
        if it.qty is None or it.qty <= 0:
            raise HTTPException(status_code=400, detail="Miqdor musbat bo'lishi kerak")
        merged[it.product_id] = merged.get(it.product_id, Decimal(0)) + it.qty
    transfer = create_draft_transfer(
        db, current_user, ctx, body.source_warehouse_id, body.destination_warehouse_id,
        [(pid, q) for pid, q in merged.items()],
    )
    db.commit()
    return {"id": transfer.id, "number": transfer.number, "status": transfer.status.value,
            "from_warehouse_id": transfer.from_warehouse_id, "to_warehouse_id": transfer.to_warehouse_id,
            "items_count": len(merged)}


# Filtrdagi umumiy nomlar → bazada yoziladigan reference_type qiymatlari
MOVEMENT_REF_ALIASES = {
    "return_from_customer": ["return_from_customer", "customer_return", "sale_refund"],
    "transfer": ["transfer", "stock_transfer", "transfer_in", "transfer_out"],
    "inventory_count": ["inventory_count", "revision"],
}


# reference_type -> qaysi jadvaldan nom olinadi (T3.8)
_CONTRA_PURCHASE = ("purchase_order",)
_CONTRA_SALE = ("sale", "return_from_customer", "customer_return", "sale_refund")
_CONTRA_SUPPLIER = ("return_to_supplier",)


def _load_contragents(db: Session, movements) -> dict:
    """`{(reference_type, reference_id): nom}` — harakatlar ro'yxatidagi kontragentlar uchun
    guruhlangan yuklash (har harakatga alohida so'rov o'rniga reference_type bo'yicha bitta IN so'rov).
    Topilmagan kalit lug'atda yo'q (`_contragent_of` fallback beradi)."""
    from sqlalchemy import bindparam
    ids: dict = {"po": set(), "sale": set(), "sup": set()}
    for m in movements:
        if not m.reference_id:
            continue
        rt = m.reference_type or ""
        if rt in _CONTRA_PURCHASE:
            ids["po"].add(m.reference_id)
        elif rt in _CONTRA_SALE:
            ids["sale"].add(m.reference_id)
        elif rt in _CONTRA_SUPPLIER:
            ids["sup"].add(m.reference_id)

    po_names: dict = {}
    sale_names: dict = {}
    sup_names: dict = {}
    try:
        if ids["po"]:
            stmt = sa_text(
                "SELECT po.id, s.name FROM purchase_orders po JOIN suppliers s ON po.supplier_id=s.id "
                "WHERE po.id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            po_names = {r[0]: r[1] for r in db.execute(stmt, {"ids": sorted(ids["po"])}).fetchall()}
        if ids["sale"]:
            stmt = sa_text(
                "SELECT sa.id, c.name FROM sales sa LEFT JOIN customers c ON sa.customer_id=c.id "
                "WHERE sa.id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            sale_names = {r[0]: r[1] for r in db.execute(stmt, {"ids": sorted(ids["sale"])}).fetchall()}
        if ids["sup"]:
            stmt = sa_text("SELECT id, name FROM suppliers WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True))
            sup_names = {r[0]: r[1] for r in db.execute(stmt, {"ids": sorted(ids["sup"])}).fetchall()}
    except Exception:
        pass  # kontragent nomi ixtiyoriy — xato bo'lsa ro'yxat baribir qaytadi

    result: dict = {}
    for m in movements:
        if not m.reference_id:
            continue
        rt = m.reference_type or ""
        if rt in _CONTRA_PURCHASE:
            result[(rt, m.reference_id)] = po_names.get(m.reference_id)
        elif rt == "sale":
            # sotuv topilmasa "Noma'lum mijoz"; topilsa-yu mijozsiz bo'lsa — None (avvalgidek)
            result[(rt, m.reference_id)] = sale_names[m.reference_id] if m.reference_id in sale_names else "Noma'lum mijoz"
        elif rt in _CONTRA_SALE:
            result[(rt, m.reference_id)] = sale_names.get(m.reference_id)
        elif rt in _CONTRA_SUPPLIER:
            result[(rt, m.reference_id)] = sup_names.get(m.reference_id)
    return result


def _contragent_of(contragents: dict, m) -> Optional[str]:
    if not m.reference_id:
        return None
    return contragents.get((m.reference_type or "", m.reference_id))


@router.get("/movements", response_model=List[StockMovementOut])
def get_movements(
        product_id: Optional[int] = Query(None),
        # T3.3: ko'p qiymatli (?type=IN&type=TRANSFER_IN); bitta ?type=IN oldingidek ishlaydi
        type: Optional[List[MovementType]] = Query(None),
        reference_type: Optional[str] = Query(None),
        search: Optional[str] = Query(None, description="Mahsulot nomi yoki SKU"),
        date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
        date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
        warehouse_id: Optional[int] = Query(None, description="Ombor bo'yicha"),
        branch_id: Optional[int] = Query(None, description="Filial bo'yicha (filial omborlari harakatlari)"),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES, UserRole.accountant)),
        ctx: BranchContext = Depends(get_branch_context),
):
    from app.core.branch_context import BRANCH_FORBIDDEN, apply_warehouse_scope
    from app.models.branch import Branch
    from app.utils.report_utils import _date_range, branch_warehouse_ids

    q = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .options(
            joinedload(StockMovement.product), joinedload(StockMovement.user),
            joinedload(StockMovement.warehouse),
        )
        .order_by(StockMovement.created_at.desc())
    )
    q = q.filter(Product.company_id == current_user.company_id)

    # T1.7: ombor / filial filtri. Filialga biriktirilgan (non-admin) xodim faqat o'z filiali
    # omborlarini ko'radi; boshqa filial yoki uning ombori so'ralsa 403.
    if warehouse_id:
        wh = db.query(Warehouse).filter(
            Warehouse.id == warehouse_id, Warehouse.company_id == current_user.company_id,
        ).first()
        if not wh:
            raise HTTPException(status_code=404, detail="Ombor topilmadi")
        if ctx.allowed_branch_ids is not None and wh.branch_id not in ctx.allowed_branch_ids:
            raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        q = q.filter(StockMovement.warehouse_id == warehouse_id)
    if branch_id:
        if ctx.allowed_branch_ids is not None and branch_id not in ctx.allowed_branch_ids:
            raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)
        if not db.query(Branch.id).filter(Branch.id == branch_id, Branch.company_id == current_user.company_id).first():
            raise HTTPException(status_code=404, detail="Filial topilmadi")
        q = q.filter(StockMovement.warehouse_id.in_(branch_warehouse_ids(db, current_user.company_id, branch_id) or []))
    if not warehouse_id and not branch_id:
        # Joriy filial konteksti (X-Branch-Id yoki biriktirilgan filial) bo'yicha
        q = apply_warehouse_scope(q, ctx, StockMovement.warehouse_id)

    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    if type:
        q = q.filter(StockMovement.type.in_(type))
    if reference_type:
        if reference_type == "adjustment":
            # Qo'lda tuzatish (adjust_stock) reference_type siz yoziladi
            q = q.filter(
                (StockMovement.reference_type == "adjustment")
                | ((StockMovement.reference_type.is_(None)) & (StockMovement.type == MovementType.ADJUST))
            )
        else:
            q = q.filter(StockMovement.reference_type.in_(MOVEMENT_REF_ALIASES.get(reference_type, [reference_type])))
    if search:
        q = q.filter(
            (Product.name.ilike(f"%{search}%")) |
            (Product.sku.ilike(f"%{search}%"))
        )
    def _parse_day(value: Optional[str]):
        try:
            return dt.strptime(value, "%Y-%m-%d").date() if value else None
        except ValueError:
            return None

    df, dto = _parse_day(date_from), _parse_day(date_to)
    if df or dto:
        # Hisobotlar bilan bir xil kun chegarasi (Toshkent vaqti)
        start, end = _date_range(df, dto)
        q = q.filter(StockMovement.created_at >= start, StockMovement.created_at < end)

    movements = q.offset(skip).limit(limit).all()

    # ── Kontragent nomlarini yig'ish (T3.8: reference_type bo'yicha guruhlab, jami ≤ 3 ta IN so'rov) ──
    contragents = _load_contragents(db, movements)

    return [
        StockMovementOut(
            id=m.id,
            product_id=m.product_id,
            variant_id=m.variant_id,
            product_name=m.product.name,
            product_sku=m.product.sku,
            product_unit=getattr(m.product, "unit", None),
            type=m.type,
            qty_before=m.qty_before,
            qty_after=m.qty_after,
            quantity=m.quantity,
            reference_type=m.reference_type,
            reference_id=m.reference_id,
            reason=m.reason,
            contragent_name=_contragent_of(contragents, m),
            user_name=m.user.name if m.user else None,
            warehouse_id=m.warehouse_id,
            warehouse_name=m.warehouse.name if m.warehouse else None,
            created_at=m.created_at,
        )
        for m in movements
    ]


@router.get("/movements/{movement_id}", response_model=StockMovementOut)
def get_movement(
        movement_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    """Bitta StockMovement ma'lumotini olish"""
    m = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .options(joinedload(StockMovement.product), joinedload(StockMovement.user))
        .filter(StockMovement.id == movement_id, Product.company_id == current_user.company_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Harakat topilmadi")
    return StockMovementOut(
        id=m.id,
        product_id=m.product_id,
        variant_id=m.variant_id,
        product_name=m.product.name,
        product_sku=m.product.sku,
        product_unit=getattr(m.product, "unit", None),
        type=m.type,
        qty_before=m.qty_before,
        qty_after=m.qty_after,
        quantity=m.quantity,
        reference_type=m.reference_type,
        reference_id=m.reference_id,
        reason=m.reason,
        contragent_name=None,
        user_name=m.user.name if m.user else None,
        warehouse_id=m.warehouse_id,
        warehouse_name=m.warehouse.name if m.warehouse else None,
        created_at=m.created_at,
    )


@router.delete("/movements/{movement_id}")
def delete_return_movement(
        movement_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    """
    Qaytaruvni bekor qilish:
    - return_from_customer → stok kamayadi, mijoz qarzi + kassa orqaga qaytadi
    - sale_refund          → stok kamayadi (avvalgi sotuv logikasi)
    - return_to_supplier   → stok qaytadi, tranzaksiyalar bekor qilinadi
    """
    from app.models.moliya import Transaction, Wallet
    from app.models.supplier import Supplier
    from app.models.customer import Customer

    m = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .options(joinedload(StockMovement.product))
        .filter(StockMovement.id == movement_id, Product.company_id == current_user.company_id)
        .first()
    )
    if not m:
        raise HTTPException(status_code=404, detail="Harakat topilmadi")

    rt = m.reference_type or ""
    qty = Decimal(str(m.quantity))

    # T1.19: asl harakat o'chirilmaydi, shuning uchun takroriy bekor qilish qoldiqni ikki marta kamaytirmasin
    if rt in ("return_from_customer", "sale_refund"):
        already = db.query(StockMovement.id).filter(
            StockMovement.reference_type == "return_revert",
            StockMovement.reference_id == m.id,
        ).first()
        if already:
            raise HTTPException(status_code=400, detail="Qaytaruv allaqachon bekor qilingan")

    # ── 1. MIJOZDAN QAYTARISH BEKOR (return_from_customer) ─────────────────
    # Avval barcha tekshiruvlar, keyin mutatsiya: xatoda hech narsa o'zgarmaydi.
    if rt == "return_from_customer":
        from app.models.batch import Batch
        from app.models.moliya import KassaMovement, KassaSession

        cid = current_user.company_id

        # 1a. Qoldiq — aynan shu ombor va variant qatori (qulf bilan)
        if m.warehouse_id:
            stock = get_or_create_stock(db, m.product_id, m.warehouse_id, m.variant_id)
            if Decimal(str(stock.quantity or 0)) < qty:
                raise HTTPException(
                    status_code=400,
                    detail="Qoldiq yetarli emas: tovar allaqachon sotilgan, qaytarishni bekor qilib bo'lmaydi",
                )
        else:
            # Omborsiz eski harakat — avvalgi xatti-harakat (qoldiq yetsa kamaytiriladi)
            stock = db.query(StockLevel).filter(StockLevel.product_id == m.product_id).first()
            if not (stock and stock.quantity >= qty):
                stock = None

        # 1b. Partiya (RETURN-C<id>) — qisman sotilgan bo'lsa bekor qilib bo'lmaydi
        batch = db.query(Batch).filter(
            Batch.lot_number == f"RETURN-C{m.id}",
            Batch.company_id == cid,
        ).first()
        if batch and Decimal(str(batch.quantity or 0)) < Decimal(str(batch.initial_quantity or 0)):
            raise HTTPException(status_code=400, detail="Qaytarilgan partiya qisman sotilgan, bekor qilib bo'lmaydi")

        # 1c. Tranzaksiyalar — faqat o'z korxonasi; kassasi topilmasa/begona bo'lsa 409
        txs = db.query(Transaction).filter(
            Transaction.reference_type == "return_from_customer",
            Transaction.reference_id == m.id,
            Transaction.company_id == cid,
        ).all()
        tx_wallets = {}
        for tx in txs:
            if tx.wallet_id:
                wallet = find_company_wallet(db, tx.wallet_id, cid)
                if not wallet:
                    raise HTTPException(
                        status_code=409,
                        detail="Qaytarish kassasi topilmadi yoki boshqa korxonaga tegishli — bekor qilib bo'lmaydi",
                    )
                tx_wallets[tx.id] = wallet

        # 1d. Mijoz (reference_id = customer_id) — faqat o'z korxonasi (404), qulf bilan
        customer = None
        if m.reference_id:
            customer = get_company_customer(db, cid, m.reference_id, for_update=True)

        # Tiklanadigan qarz: avval Transaction.meta["debt_reduced_uzs"];
        # meta bo'lmagan eski yozuvlar uchun reason matnidagi "summa:" zaxira
        debt_restore = Decimal("0")
        has_meta = False
        for tx in txs:
            meta = tx.meta if isinstance(tx.meta, dict) else None
            if meta and "debt_reduced_uzs" in meta:
                has_meta = True
                debt_restore += Decimal(str(meta.get("debt_reduced_uzs") or 0))
        if not has_meta and customer:
            reason_txt = m.reason or ""
            if "qarzga" in reason_txt.lower() or "debt" in reason_txt.lower():
                import re
                match = re.search(r'summa:(\d+\.?\d*)', reason_txt)
                debt_restore = Decimal(match.group(1)) if match else Decimal("0")

        kassa_movs = db.query(KassaMovement).filter(
            KassaMovement.reference_type == "return_from_customer",
            KassaMovement.reference_id == m.id,
            KassaMovement.company_id == cid,
            KassaMovement.direction == "out",
        ).all()

        # ── Mutatsiya ──
        # Qoldiq (to'g'ri ombor va variant)
        if stock is not None:
            qty_before = stock.quantity
            stock.quantity -= qty
            db.add(StockMovement(
                product_id=m.product_id,
                variant_id=m.variant_id,
                warehouse_id=m.warehouse_id,
                type=MovementType.OUT,
                qty_before=qty_before,
                qty_after=stock.quantity,
                quantity=qty,
                reference_type="return_revert",
                reference_id=m.id,
                user_id=current_user.id,
                reason=f"Mijozdan qaytarish bekor qilindi (asl ID: {m.id})",
            ))
        if batch:
            batch.quantity = Decimal("0")

        # Kassa balansi: yangi yozuvlarda faqat to'langan ulush (meta), eskilarda tx.amount
        for tx in txs:
            wallet = tx_wallets.get(tx.id)
            if wallet:
                meta = tx.meta if isinstance(tx.meta, dict) else None
                if meta and ("paid_cash" in meta or "paid_card" in meta):
                    restore = Decimal(str(meta.get("paid_cash") or 0)) + Decimal(str(meta.get("paid_card") or 0))
                else:
                    restore = Decimal(str(tx.amount))
                # Chiqim tranzaksiya edi (kassadan pul chiqdi), endi orqaga qaytaramiz
                if tx.type == "expense":
                    wallet.balance = Decimal(str(wallet.balance or 0)) + restore
                else:
                    wallet.balance = Decimal(str(wallet.balance or 0)) - restore
            db.delete(tx)

        # Teskari kassa harakati (asl yozuv o'chirilmaydi) — hozirgi ochiq sessiyaga
        session_cache = {}
        for km in kassa_movs:
            if km.wallet_id not in session_cache:
                ks = db.query(KassaSession).filter(
                    KassaSession.wallet_id == km.wallet_id, KassaSession.status == "open"
                ).first()
                session_cache[km.wallet_id] = ks.id if ks else None
            db.add(KassaMovement(
                wallet_id=km.wallet_id,
                company_id=cid,
                session_id=session_cache[km.wallet_id],
                direction="in",
                payment_type=km.payment_type,
                amount=km.amount,
                currency=km.currency or "UZS",
                reference_type="return_from_customer_revert",
                reference_id=m.id,
                description=f"Mijozdan qaytarish bekor qilindi (asl ID: {m.id})",
                created_by=current_user.id,
            ))

        # Mijoz qarzi tiklanadi (debt_balance va UZS chelagi bir xil miqdorga)
        if customer and debt_restore > 0:
            if not customer.debt_balances:
                if float(customer.debt_balance or 0) > 0:
                    customer.debt_balances = {"UZS": float(customer.debt_balance)}
                else:
                    customer.debt_balances = {}
            curr_uzs = Decimal(str(customer.debt_balances.get("UZS", 0) or 0))
            customer.debt_balances["UZS"] = float(curr_uzs + debt_restore)
            customer.debt_balance = float(Decimal(str(customer.debt_balance or 0)) + debt_restore)
            flag_modified(customer, "debt_balances")

    # ── 2. SOTUV REFUNDI BEKOR (sale_refund – eski logika) ─────────────────
    elif rt == "sale_refund":
        # Aynan shu ombor va variant qatori; qoldiq yetmasa 400 (jim o'tkazilmaydi)
        stock = get_or_create_stock(db, m.product_id, m.warehouse_id, m.variant_id)
        if Decimal(str(stock.quantity or 0)) < qty:
            raise HTTPException(
                status_code=400,
                detail="Qoldiq yetarli emas: tovar allaqachon sotilgan, qaytarishni bekor qilib bo'lmaydi",
            )
        qty_before = stock.quantity
        stock.quantity -= qty
        revert_mov = StockMovement(
            product_id=m.product_id,
            variant_id=m.variant_id,
            warehouse_id=m.warehouse_id,
            type=MovementType.OUT,
            qty_before=qty_before,
            qty_after=stock.quantity,
            quantity=qty,
            reference_type="return_revert",
            reference_id=m.id,
            user_id=current_user.id,
            reason=f"Qaytaruv bekor qilindi (asl harakat ID: {m.id})",
        )
        db.add(revert_mov)

    # ── 3. TA'MINOTCHIGA QAYTARISH BEKOR ───────────────────────────────────
    # Butun qaytarish hujjati bekor qilinadi: qoldiq to'g'ri omborga, partiyalar, ta'minotchi
    # qarzi (aynan qaytarishdagi summa) va shu hujjatning qaytim to'lovi tiklanadi.
    # Avval: qarzga miqdor (dona) qo'shilardi, stok NULL-omborga tushardi va ta'minotchining
    # barcha qaytarish tranzaksiyalari o'chirilardi.
    elif rt == "return_to_supplier":
        from app.services.supplier_return_service import revert_supplier_return
        result = revert_supplier_return(db, m, current_user)
        db.commit()
        if result["legacy"]:
            return {"message": "Qaytaruv bekor qilindi: qoldiq tiklandi. Bu eski qaytarish — ta'minotchi "
                               "qarzi va kassani kerak bo'lsa qo'lda tuzating", "count": result["count"]}
        return {"message": f"Qaytaruv bekor qilindi ({result['count']} ta pozitsiya)", "count": result["count"]}
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Bu turdagi harakatni ({rt}) bekor qilish qo'llab-quvvatlanmaydi"
        )

    # T1.19: harakat o'chirilmaydi — "bekor qilingan" deb belgilanadi (teskari `return_revert` harakati yozilgan)
    m.reason = ((m.reason or "") + " [bekor qilingan]").strip()
    log_action_for(
        db, current_user, "RETURN_REVERT", "stock_movement", m.id,
        old_values={"reference_type": rt, "product_id": m.product_id, "quantity": float(qty)},
        new_values={"voided": True},
        branch_id=_warehouse_branch(db, m.warehouse_id),
    )
    db.commit()
    return {"message": "Qaytaruv muvaffaqiyatli bekor qilindi"}


@router.put("/{movement_id}/movements", response_model=StockMovementOut)
def update_movement(
        movement_id: int,
        movement_data: StockMovementUpdate,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director))
):
    """Faqat izoh (`reason`) tahrirlanadi, faqat admin/director. Hujjatga bog'langan
    harakatlar (sotuv, qaytarish, ko'chirish...) tahrirlanmaydi — reference_* orqali
    harakatni soxtalashtirish yopilgan."""
    movement = (
        db.query(StockMovement).join(Product, Product.id == StockMovement.product_id).filter(StockMovement.id == movement_id, Product.company_id == current_user.company_id).first()
    )
    if not movement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ombor harakati topilmadi"
        )
    if (movement.reference_type or "") in LOCKED_MOVEMENT_REFS:
        raise HTTPException(status_code=400, detail="Hujjatga bog'langan harakatni tahrirlab bo'lmaydi")
    if movement_data.reason is not None:
        movement.reason = movement_data.reason

    db.commit()
    db.refresh(movement)

    # Javob get_movement bilan bir xil shaklda (ORM obyekti StockMovementOut ga to'g'ridan-to'g'ri mos emas)
    product = movement.product
    return StockMovementOut(
        id=movement.id,
        product_id=movement.product_id,
        variant_id=movement.variant_id,
        product_name=product.name if product else "",
        product_sku=product.sku if product else None,
        product_unit=getattr(product, "unit", None),
        type=movement.type,
        qty_before=movement.qty_before,
        qty_after=movement.qty_after,
        quantity=movement.quantity,
        reference_type=movement.reference_type,
        reference_id=movement.reference_id,
        reason=movement.reason,
        contragent_name=None,
        user_name=movement.user.name if movement.user else None,
        created_at=movement.created_at,
    )
@router.post("/receive")
def receive_goods(
        data: StockReceiveRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
        ctx: BranchContext = Depends(get_branch_context),
):
    """Qo'lda kirim (xarid buyurtmasisiz). Tovar tanlangan omborga tushadi, partiya (FIFO tannarx)
    yaratiladi va mahsulot tannarxi yangilanadi. Ta'minotchi qarzi o'zgarmaydi — qarzli xarid
    uchun "Xarid buyurtmasi" ishlatiladi."""
    from app.models.batch import Batch
    from app.models.supplier import Supplier
    from app.services import supplier_ledger as ledger
    from app.services.document_numbers import tashkent_today
    from app.services.pharmacy import pharmacy_context

    cid = current_user.company_id
    wh_q = db.query(Warehouse).filter(Warehouse.company_id == cid, Warehouse.is_active == True)
    if data.warehouse_id:
        warehouse = wh_q.filter(Warehouse.id == data.warehouse_id).first()
        if not warehouse:
            raise HTTPException(status_code=404, detail="Ombor topilmadi")
        # T1.3: filialga biriktirilgan xodim boshqa filial omboriga kirim qila olmaydi (403)
        assert_warehouse_branch_access(db, current_user, ctx, warehouse.id)
    else:
        # T1.5: ombor berilmasa — joriy filialning default ombori (main/shop); korxonaning eng kichik
        # id li omboriga emas. Filial aniq emas va 2+ filial bo'lsa 400 "Omborni tanlang".
        from app.services.warehouse_resolver import resolve_warehouse
        try:
            _wid = resolve_warehouse(db, cid, branch_id=ctx.branch_id, purpose="receive", user=current_user)
        except HTTPException as e:
            if e.status_code == 400:
                raise HTTPException(status_code=400, detail="Omborni tanlang")
            raise
        warehouse = wh_q.filter(Warehouse.id == _wid).first()
    supplier = None
    if data.supplier_id:
        supplier = db.query(Supplier).filter(Supplier.id == data.supplier_id, Supplier.company_id == cid).first()
        if not supplier:
            raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")

    # D1.3: dorixona rejimida partiya qoidalari (P.15: seriya va yaroqlilik muddati ixtiyoriy; faqat modul yoqilgan korxonada)
    pharm_on, _pharm_settings = pharmacy_context(db, cid)
    _rcv_warnings: list = []
    if pharm_on:
        today = tashkent_today()
        from app.services.purchase_order_service import _check_pharmacy_lots
        from app.models.marking_code import MarkingCode
        from app.routers.pharmacy_marking import canonical_code
        _seen_codes: set = set()
        for n, item in enumerate(data.items, 1):
            pname = db.query(Product.name).filter(
                Product.id == item.product_id, Product.company_id == cid, Product.is_deleted == False,
            ).scalar()
            if pname is None:
                raise HTTPException(status_code=404, detail=f"Mahsulot topilmadi: {item.product_id}")
            label = f"{n}-qator '{pname}'"
            # P.5: seriya ixtiyoriy (bo'sh bo'lsa partiya "manual" nomini oladi); P.15: yaroqlilik muddati ham ixtiyoriy,
            # muddati o'tgani — ogohlantirish (_check_pharmacy_lots)
            # CD.1: ishlab chiqarilgan sana bo'lsa — D1.3 (xarid qabuli) dagi qoida: qolgan muddat foizi < min_shelf_life_pct
            # bo'lsa ogohlantirish (rad etmaydi); sana muddatdan keyin bo'lsa 400
            _check_pharmacy_lots(
                label, [(item.lot_number, item.expiry_date, item.manufacture_date, item.quantity)],
                _pharm_settings, today, _rcv_warnings,
            )
            # CD.1/D3.2: markirovka kodi allaqachon ro'yxatda bo'lsa — qo'lda kirimda 400 (yozishdan oldin)
            if item.marking_codes and db.query(Product.requires_marking).filter(Product.id == item.product_id).scalar():
                for raw in item.marking_codes:
                    if not (raw or "").strip():
                        continue
                    canon, _p = canonical_code(raw)
                    if canon in _seen_codes:
                        raise HTTPException(status_code=400, detail=f"{label}: kod takrorlangan — {canon}")
                    _seen_codes.add(canon)
                    if canon and db.query(MarkingCode.id).filter(
                        MarkingCode.company_id == cid, MarkingCode.code == canon,
                    ).first() is not None:
                        raise HTTPException(status_code=400, detail=f"{label}: kod allaqachon ro'yxatda — {canon}")

    movements = []
    for _n, item in enumerate(data.items, 1):
        product = db.query(Product).filter(
            Product.id == item.product_id, Product.company_id == cid, Product.is_deleted == False,
        ).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Mahsulot topilmadi: {item.product_id}")
        price = item.cost_price if item.cost_price is not None else item.purchase_price
        reason = " | ".join(x for x in [
            f"Ta'minotchi: {supplier.name}" if supplier else None, item.reason, data.note,
        ] if x)
        m = receive_stock(
            db=db, product_id=product.id, quantity=item.quantity, user_id=current_user.id,
            reason=reason or None, reference_type="manual_receive",
            warehouse_id=warehouse.id, variant_id=item.variant_id,
        )
        cur = (product.cost_currency or "UZS").strip().upper() or "UZS"
        rate = ledger.currency_rate(db, cid, cur)
        if price is not None and price > 0:
            unit_uzs = Decimal(str(price))
            product.cost_price = unit_uzs if cur == "UZS" else round(unit_uzs / rate, 4)
        else:
            unit_uzs = Decimal(str(product.cost_price or 0)) * rate
        new_batch = Batch(
            product_id=product.id, variant_id=item.variant_id, warehouse_id=warehouse.id,
            lot_number=(item.lot_number or "").strip() or (f"manual-{supplier.id}" if supplier else "manual"),
            expiry_date=dt.combine(item.expiry_date, dt.min.time()) if item.expiry_date else None,
            manufacture_date=dt.combine(item.manufacture_date, dt.min.time()) if (pharm_on and item.manufacture_date) else None,
            initial_quantity=item.quantity, quantity=item.quantity, purchase_price=unit_uzs,
            company_id=cid,
        )
        db.add(new_batch)
        if pharm_on and product.requires_marking and item.marking_codes:
            # CD.1/D3.2: kodlar shu partiyaga in_stock bo'lib yoziladi (received_po_id bo'sh), kirim bilan bir tranzaksiyada
            from types import SimpleNamespace
            from app.routers.pharmacy_marking import register_receipt_codes
            db.flush()
            register_receipt_codes(
                db, po=SimpleNamespace(id=None, company_id=cid, warehouse_id=warehouse.id), product=product,
                codes=item.marking_codes, batches=[new_batch], label=f"{_n}-qator '{product.name}'",
                warnings=_rcv_warnings, expected_qty=item.quantity, warehouse_id=warehouse.id,
            )
        movements.append({"product_id": product.id, "variant_id": item.variant_id,
                          "qty_added": str(item.quantity), "new_qty": str(m.qty_after)})

    log_action_for(
        db, current_user, "STOCK_RECEIVE", "warehouse", warehouse.id,
        new_values={"supplier_id": supplier.id if supplier else None, "items": movements},
        branch_id=warehouse.branch_id,
    )
    db.commit()
    result = {"message": f"{len(movements)} ta mahsulot qabul qilindi", "details": movements,
              "warehouse_id": warehouse.id}
    if pharm_on:
        result["warnings"] = _rcv_warnings  # D1.3/CD.1: qolgan muddat foizi, markirovka kodlari ogohlantirishlari
    return result


@router.post("/return-from-customer")
def return_from_customer(
        data: CustomerReturnRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    """
    Mijozdan mustaqil qaytarish operatsiyasi.
    - Sotuvlar tarixiga ta'sir qilmaydi
    - Operatsiyalar → Qaytarishlar da ko'rinadi
    - O'chirilganda stok + qarz/kassa orqaga qaytadi

    Ombor, mijoz, mahsulot, variant va kassa korxonaga tekshiriladi; qoldiq aynan
    variant qatoriga, partiya (RETURN-C<harakat id>) bilan yoziladi; naqd/karta uchun
    KassaMovement (X-hisobot) yoziladi. Hammasi bitta tranzaksiya — xatoda commit yo'q.
    """
    from app.models.batch import Batch
    from app.models.moliya import Transaction, KassaMovement, KassaSession
    from app.services.sale_helpers import resolve_branch_id

    cid = current_user.company_id
    TIYIN = Decimal("0.01")

    # 1. Ombor — korxona, faollik, filial (admin/director istalgan ombor)
    warehouse = get_company_warehouse(db, current_user, data.warehouse_id)

    # 2. Mijoz — korxona bo'yicha, qulf bilan
    customer = None
    if data.customer_id:
        customer = get_company_customer(db, cid, data.customer_id, for_update=True)

    # 3. Mahsulotlar — bitta so'rovda, korxona bo'yicha; variant mahsulotga tegishliligi
    products = get_company_products(db, cid, [i.product_id for i in data.items])
    for item in data.items:
        product = products[item.product_id]
        if getattr(product, "product_type", "stock") == "sell":
            raise HTTPException(
                status_code=400,
                detail=f"Virtual mahsulotni ({product.name}) qaytarib bo'lmaydi. Asosiy mahsulotini tanlang.",
            )
        if item.variant_id:
            get_company_variant(db, product.id, item.variant_id)

    # 4. Filial — ombor filialidan (foydalanuvchi filialidan emas)
    tx_branch_id = resolve_branch_id(db, current_user, warehouse.id, prefer_warehouse=True)
    if not tx_branch_id:
        raise HTTPException(status_code=400, detail="Filial aniqlanmadi")

    # 5. Summa va to'lov — mutatsiyadan OLDIN tekshiriladi
    line_totals = [
        (Decimal(str(i.quantity)) * Decimal(str(i.unit_price))).quantize(TIYIN) for i in data.items
    ]
    total_amount = sum(line_totals, Decimal("0"))
    paid_cash = Decimal("0")
    paid_card = Decimal("0")
    debt_reduction = Decimal("0")
    wallet = None

    if data.payment_type == "debt":
        if not customer:
            raise HTTPException(status_code=400, detail="Qarzga qaytarish uchun mijoz tanlang")
        debt_reduction = total_amount
    else:
        paid_cash = Decimal(str(data.paid_cash or 0))
        paid_card = Decimal(str(data.paid_card or 0))
        if paid_cash == 0 and paid_card == 0:
            if data.payment_type == "cash":
                paid_cash = total_amount
            elif data.payment_type == "card":
                paid_card = total_amount
        paid_total = paid_cash + paid_card
        if paid_total > total_amount:
            raise HTTPException(
                status_code=400,
                detail="Qaytarilgan summa umumiy summadan ko'p bo'lishi mumkin emas",
            )
        remainder = total_amount - paid_total
        if remainder > 0:
            # Qolgan summa mijoz qarzidan ayiriladi
            if not customer:
                raise HTTPException(status_code=400, detail="Qolgan summani qarzdan ayirish uchun mijoz tanlang")
            debt_reduction = remainder
        if paid_total > 0:
            # Kassa: berilgan bo'lsa korxona bo'yicha (faol, ochiq), aks holda default kassa
            if data.wallet_id:
                wallet = get_open_company_wallet(db, cid, data.wallet_id, for_update=True, require_open=True)
            else:
                wallet = find_default_wallet(db, current_user)
            if not wallet:
                raise HTTPException(status_code=400, detail="Kassa tanlang")
            if Decimal(str(wallet.balance or 0)) < paid_total:
                raise HTTPException(
                    status_code=400,
                    detail=f"Kassada yetarli mablag' yo'q. Balans: {wallet.balance}",
                )
    paid_total = paid_cash + paid_card

    # Mijoz qarzi (UZS chelagi) qaytarish summasidan kam bo'lsa 400 (jim kesilmaydi)
    curr_uzs_debt = Decimal("0")
    if debt_reduction > 0:
        # Eski mijozlar uchun: debt_balances null bo'lsa, debt_balance dan ko'chiramiz
        if not customer.debt_balances:
            if float(customer.debt_balance or 0) > 0:
                legacy_curr = (getattr(customer, 'debt_currency', 'UZS') or 'UZS').strip().upper() or 'UZS'
                customer.debt_balances = {legacy_curr: float(customer.debt_balance)}
            else:
                customer.debt_balances = {}
        curr_uzs_debt = Decimal(str(customer.debt_balances.get("UZS", 0) or 0))
        if curr_uzs_debt < debt_reduction:
            raise HTTPException(status_code=400, detail="Mijoz qarzi qaytarish summasidan kam")

    # Faqat qarz hisobiga qaytarish: kassadan pul chiqmaydi (T0.29) — Transaction yozilmaydi,
    # bekor qilishda qarz reason matnidagi "payment:debt" bo'yicha tiklanadi.
    pure_debt = paid_total == 0 and debt_reduction > 0
    eff_payment_type = "debt" if pure_debt else data.payment_type

    # 6. Qoldiq (variant bo'yicha, qulf bilan) + harakat + partiya
    cust_name = customer.name if customer else "Noma'lum xaridor"
    rows = []  # (movement, item_total)
    for item, item_total in zip(data.items, line_totals):
        qty = Decimal(str(item.quantity))
        product = products[item.product_id]
        # payment_type va summa reason ga ham yoziladi (eski bekor qilish zaxirasi uchun)
        reason_text = (
            f"Qisman qaytarish: {cust_name}. "
            f"payment:{eff_payment_type}. summa:{item_total}. "
            f"{data.note or ''}".strip()
        )
        mov = receive_stock(
            db,
            product_id=item.product_id,
            quantity=qty,
            user_id=current_user.id,
            reason=reason_text,
            reference_type="return_from_customer",
            reference_id=customer.id if customer else None,   # mijoz ID saqlanadi yoki None
            warehouse_id=warehouse.id,
            variant_id=item.variant_id,
        )
        # Partiya: tannarx = joriy product.cost_price (sale_return bilan bir xil siyosat)
        db.add(Batch(
            product_id=product.id,
            variant_id=item.variant_id,
            warehouse_id=warehouse.id,
            lot_number=f"RETURN-C{mov.id}",
            initial_quantity=qty,
            quantity=qty,
            purchase_price=product.cost_price or Decimal("0"),
            company_id=cid,
        ))
        rows.append((mov, item_total))

    # 7. Qarz: debt_balance va debt_balances["UZS"] bir xil miqdorga kamayadi
    if debt_reduction > 0:
        customer.debt_balances["UZS"] = float(curr_uzs_debt - debt_reduction)
        customer.debt_balance = float(Decimal(str(customer.debt_balance or 0)) - debt_reduction)
        flag_modified(customer, "debt_balances")

    # 8. Ulushlar: naqd/karta/qarz har bir qatorga nisbat bo'yicha, tiyin farqi oxirgi qatorga
    def _split(amount: Decimal):
        shares = []
        acc = Decimal("0")
        for idx, (_, item_total) in enumerate(rows):
            if idx == len(rows) - 1:
                share = amount - acc
            elif total_amount > 0:
                share = (amount * item_total / total_amount).quantize(TIYIN, rounding=ROUND_DOWN)
            else:
                share = Decimal("0")
            shares.append(share)
            acc += share
        return shares

    cash_shares = _split(paid_cash)
    card_shares = _split(paid_card)
    debt_shares = _split(debt_reduction)

    # 9. Tranzaksiya (har bir harakat uchun) + kassa harakati (naqd/karta)
    open_session_id = None
    if wallet:
        ks = db.query(KassaSession).filter(
            KassaSession.wallet_id == wallet.id, KassaSession.status == "open"
        ).first()
        open_session_id = ks.id if ks else None

    pay_label = "qarzga" if eff_payment_type == "debt" else data.payment_type
    for idx, (mov, item_total) in enumerate(rows):
        if not pure_debt:
            db.add(Transaction(
                branch_id=tx_branch_id,
                company_id=cid,
                type="expense",          # Bizdan pul chiqdi (kassadan yoki qarz hisobida)
                amount=item_total,
                wallet_id=wallet.id if wallet else None,
                payment_type=data.payment_type,
                reference_type="return_from_customer",
                reference_id=mov.id,
                user_id=current_user.id,
                description=f"Mijozdan qaytarish ({pay_label}): {cust_name}",
                meta={
                    "customer_id": customer.id if customer else None,
                    "debt_reduced_uzs": float(debt_shares[idx]),
                    "paid_cash": float(cash_shares[idx]),
                    "paid_card": float(card_shares[idx]),
                },
            ))
        if wallet:
            for ptype, share in (("cash", cash_shares[idx]), ("card", card_shares[idx])):
                if share > 0:
                    db.add(KassaMovement(
                        wallet_id=wallet.id,
                        company_id=cid,
                        session_id=open_session_id,
                        direction="out",
                        payment_type=ptype,
                        amount=share,
                        currency="UZS",
                        reference_type="return_from_customer",
                        reference_id=mov.id,
                        description=f"Mijozdan qaytarish: {cust_name}",
                        created_by=current_user.id,
                    ))

    # 10. Kassa balansi
    if wallet and paid_total > 0:
        wallet.balance = Decimal(str(wallet.balance or 0)) - paid_total

    log_action_for(
        db, current_user, "CUSTOMER_RETURN", "stock_movement", rows[0][0].id if rows else None,
        new_values={
            "movement_ids": [mov.id for mov, _ in rows],
            "customer_id": customer.id if customer else None,
            "total_amount": float(total_amount),
            "paid_total": float(paid_total),
            "payment_type": data.payment_type,
        },
        branch_id=tx_branch_id,
    )
    db.commit()
    return {
        "message": "Mijozdan qaytarish muvaffaqiyatli saqlandi",
        "total_amount": str(total_amount),
        "items_count": len(rows),
        "movement_ids": [mov.id for mov, _ in rows],
        "wallet_id": wallet.id if wallet else None,
        "branch_id": tx_branch_id,
    }


@router.post("/return-to-supplier")
def return_to_supplier(
        data: SupplierReturnRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    """Ta'minotchiga qaytarish: qarz (qiymat − qaytgan pul) ga kamayadi, ortig'i avans;
    qaytgan pul kassaga kirim bo'ladi. Hujjat bekor qilinganda hammasi aynan tiklanadi."""
    from app.services.supplier_return_service import create_supplier_return

    result = create_supplier_return(db, data, current_user)
    db.commit()
    return {
        "message": "Vazvrat muvaffaqiyatli saqlandi",
        "total_value": str(result["value"]),
        "received": str(result["received"]),
    }


@router.post("/chiqims")
def create_chiqim(
        data: ChiqimBatchRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    # T1.8: ombor majburiy (ko'rsatilmasa — foydalanuvchi ko'lamidagi yagona ombor, aks holda 400)
    wh_id = resolve_chiqim_warehouse(db, current_user, data.warehouse_id)
    ref_id = create_chiqim_batch(db, data.items, current_user.id, company_id=current_user.company_id,
                                 warehouse_id=wh_id)
    log_action_for(
        db, current_user, "CHIQIM_CREATE", "chiqim", ref_id,
        new_values={
            "warehouse_id": wh_id,
            "items": [{"product_id": i.product_id, "variant_id": getattr(i, "variant_id", None),
                       "quantity": float(i.quantity), "type": i.type} for i in data.items],
        },
        branch_id=_warehouse_branch(db, wh_id),
    )
    db.commit()
    return {"message": "Chiqim muvaffaqiyatli saqlandi", "reference_id": ref_id}


from datetime import date, datetime, timedelta


@router.get("/chiqims", response_model=List[ChiqimDocumentOut])
def get_chiqims(
        user_id: Optional[int] = Query(None),
        warehouse_id: Optional[int] = Query(None),
        date_from: Optional[date] = Query(None),
        date_to: Optional[date] = Query(None),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    # T1.8: bekor qilingan (storno qilingan) chiqim harakatlari ro'yxatda ko'rinmaydi:
    # hujjatning oxirgi `chiqim_revert` harakatidan OLDINGI chiqim qatorlari tushmaydi
    revert_sq = (
        db.query(StockMovement.reference_id.label("rid"), func.max(StockMovement.id).label("rev_id"))
        .join(Product, Product.id == StockMovement.product_id)
        .filter(Product.company_id == current_user.company_id,
                StockMovement.reference_type == "chiqim_revert")
        .group_by(StockMovement.reference_id)
        .subquery()
    )
    q = (
        db.query(StockMovement)
        .join(Product, Product.id == StockMovement.product_id)
        .outerjoin(revert_sq, revert_sq.c.rid == StockMovement.reference_id)
        .filter(Product.company_id == current_user.company_id)
        .filter(StockMovement.reference_type == "chiqim")
        .filter(StockMovement.id >= func.coalesce(revert_sq.c.rev_id, 0))
    )
    if warehouse_id:
        q = q.filter(StockMovement.warehouse_id == warehouse_id)
    if user_id:
        q = q.filter(StockMovement.user_id == user_id)
    if date_from:
        q = q.filter(StockMovement.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(StockMovement.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))

    # T3.8: guruhlash SQL'da (xotira skip/limit ga bog'liq): hujjat = reference_id
    last_at = func.max(StockMovement.created_at)
    pos_qty = func.sum(case((StockMovement.quantity > 0, StockMovement.quantity), else_=0))
    page = (
        q.with_entities(
            StockMovement.reference_id, last_at, func.count(StockMovement.id), pos_qty,
            func.min(StockMovement.user_id), func.min(StockMovement.warehouse_id),
        )
        .group_by(StockMovement.reference_id)
        .order_by(last_at.desc(), StockMovement.reference_id.desc())
        .offset(skip).limit(limit)
        .all()
    )
    if not page:
        return []

    # Faqat sahifadagi hujjatlar uchun: sabab matnlari, foydalanuvchi va ombor nomlari
    page_ids = [r[0] for r in page]
    ref_cond = StockMovement.reference_id.in_([i for i in page_ids if i is not None])
    if None in page_ids:
        ref_cond = or_(ref_cond, StockMovement.reference_id.is_(None))
    reason_rows = q.filter(ref_cond).with_entities(StockMovement.reference_id, StockMovement.reason).distinct().all()
    reasons_by_ref: dict = {}
    for rid, reason in reason_rows:
        reasons_by_ref.setdefault(rid, []).append(reason)

    user_names = {
        u_id: name for u_id, name in db.query(User.id, User.name).filter(
            User.id.in_({r[4] for r in page if r[4]})).all()
    } if any(r[4] for r in page) else {}
    wh_names = {
        w_id: name for w_id, name in db.query(Warehouse.id, Warehouse.name).filter(
            Warehouse.id.in_({r[5] for r in page if r[5]})).all()
    } if any(r[5] for r in page) else {}

    grouped = []
    for rid, created_at, item_count, total_qty, g_user_id, g_wh_id in page:
        type_hints, doc_nums, reasons = set(), set(), set()
        for reason in reasons_by_ref.get(rid, []):
            # format: "TYPE | Hujjat: DOC | reason" yoki o'xshash
            rparts = [p.strip() for p in (reason or "").split("|")]
            if len(rparts) >= 1 and rparts[0]:
                type_hints.add(rparts[0])
            if len(rparts) >= 2 and rparts[1].startswith("Hujjat: "):
                doc_nums.add(rparts[1].replace("Hujjat: ", ""))
            elif len(rparts) >= 2:
                reasons.add(rparts[1])
            if len(rparts) >= 3:
                reasons.add(rparts[2])
        grouped.append(ChiqimDocumentOut(
            reference_id=rid,
            created_at=created_at,
            type_hints=list(type_hints),
            doc_nums=list(doc_nums),
            reasons=list(reasons),
            total_qty=Decimal(str(total_qty or 0)),
            item_count=item_count,
            user_name=user_names.get(g_user_id),
            warehouse_id=g_wh_id,
            warehouse_name=wh_names.get(g_wh_id),
        ))

    return grouped


@router.get("/chiqims/{id}", response_model=List[ChiqimDetailOut])
def get_chiqim_details(
        id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(*WAREHOUSE_ROLES)),
):
    # T1.8: faqat joriy (bekor qilinmagan) harakatlar
    active_ids = [m.id for m in active_chiqim_movements(db, current_user.company_id, id)]
    movements = (
        db.query(StockMovement)
        .filter(StockMovement.id.in_(active_ids))
        .options(joinedload(StockMovement.product))
        .order_by(StockMovement.id.asc())
        .all()
    ) if active_ids else []

    out = []
    for m in movements:
        parts = [p.strip() for p in (m.reason or "").split("|")]
        ctype = parts[0] if len(parts) > 0 else "unknown"
        doc_num = None
        reason = None
        if len(parts) > 1:
            if parts[1].startswith("Hujjat: "):
                doc_num = parts[1].replace("Hujjat: ", "")
                if len(parts) > 2:
                    reason = parts[2]
            else:
                reason = parts[1]

        out.append(ChiqimDetailOut(
            id=m.id,
            product_id=m.product_id,
            variant_id=m.variant_id,
            product_name=m.product.name,
            product_sku=m.product.sku,
            product_unit=m.product.unit or "dona",
            type=ctype,
            quantity=m.quantity,
            doc_num=doc_num,
            reason=reason,
            warehouse_id=m.warehouse_id,
            warehouse_name=m.warehouse.name if m.warehouse else None,
        ))
    return out


@router.delete("/chiqims/{id}")
def delete_chiqim(
        id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    # Verify owner company
    m = db.query(StockMovement).join(Product).filter(
        StockMovement.reference_type == "chiqim",
        StockMovement.reference_id == id,
        Product.company_id == current_user.company_id
    ).first()

    if not m:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chiqim topilmadi")

    delete_chiqim_batch(db, id, current_user.id, company_id=current_user.company_id)
    log_action_for(
        db, current_user, "CHIQIM_DELETE", "chiqim", id,
        old_values={"product_id": m.product_id, "warehouse_id": m.warehouse_id},
        new_values={"reverted": True},
        branch_id=_warehouse_branch(db, m.warehouse_id),
    )
    db.commit()
    return {"message": "Chiqim muvaffaqiyatli bekor qilindi"}


@router.put("/chiqims/{id}")
def update_chiqim(
        id: int,
        data: ChiqimBatchRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director)),
):
    """T1.8: chiqimni tahrirlash — eski hujjatni bekor qilish + yangisini shu reference_id bilan yozish
    BITTA tranzaksiyada (yangi qator xato bersa eski chiqim saqlanadi)."""
    old = active_chiqim_movements(db, current_user.company_id, id)
    if not old:
        raise HTTPException(status_code=404, detail="Chiqim topilmadi")
    # Ombor yuborilmasa asl ombor saqlanadi
    old_wh_id = next((m.warehouse_id for m in old if m.warehouse_id), None)
    wh_id = resolve_chiqim_warehouse(db, current_user, data.warehouse_id or old_wh_id)

    with db.begin_nested():
        delete_chiqim_batch(db, id, current_user.id, company_id=current_user.company_id)
        create_chiqim_batch(db, data.items, current_user.id, company_id=current_user.company_id,
                            warehouse_id=wh_id, reference_id=id)
    log_action_for(
        db, current_user, "CHIQIM_UPDATE", "chiqim", id,
        old_values={"warehouse_id": old_wh_id},
        new_values={
            "warehouse_id": wh_id,
            "items": [{"product_id": i.product_id, "variant_id": getattr(i, "variant_id", None),
                       "quantity": float(i.quantity), "type": i.type} for i in data.items],
        },
        branch_id=_warehouse_branch(db, wh_id),
    )
    db.commit()
    return {"message": "Chiqim muvaffaqiyatli yangilandi", "reference_id": id}


@router.post("/adjust")
def adjust_stock_level(
        data: StockAdjustRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_roles(UserRole.admin, UserRole.director, UserRole.manager)),
):
    cid = current_user.company_id
    # Ombor va mahsulot korxonaga tekshiriladi (begona bo'lsa 404, boshqa filial ombori — 403)
    warehouse = get_company_warehouse(db, current_user, data.warehouse_id)
    product = get_company_product(db, cid, data.product_id)
    if getattr(product, "product_type", None) in ("sell", "service"):
        raise HTTPException(
            status_code=400,
            detail="Tarkibiy yoki xizmat mahsulotining qoldig'ini o'zgartirib bo'lmaydi",
        )
    if data.variant_id:
        try:
            get_company_variant(db, product.id, data.variant_id)
        except HTTPException:
            raise HTTPException(status_code=404, detail="Variant topilmadi")
    m = adjust_stock(
        db=db,
        product_id=product.id,
        new_quantity=data.new_quantity,
        user_id=current_user.id,
        reason=data.reason,
        warehouse_id=warehouse.id,
        variant_id=data.variant_id,
        company_id=cid,
    )
    log_action_for(
        db, current_user, "STOCK_ADJUST", "product", product.id,
        old_values={"quantity": float(m.qty_before), "warehouse_id": warehouse.id, "variant_id": data.variant_id},
        new_values={"quantity": float(m.qty_after), "warehouse_id": warehouse.id,
                    "variant_id": data.variant_id, "reason": data.reason},
        branch_id=warehouse.branch_id,
    )
    db.commit()
    return {
        "message": "Qoldiq yangilandi",
        "product_id": data.product_id,
        "warehouse_id": warehouse.id,
        "qty_before": str(m.qty_before),
        "qty_after": str(m.qty_after),
    }


@router.get("/warehouses")
def list_warehouses(
        scope: Literal["context", "all"] = Query("context", description="context — joriy filial konteksti; all — korxonaning barcha omborlari"),
        branch_id: Optional[int] = Query(None, description="Faqat shu filial omborlari"),
        include_inactive: bool = Query(False, description="Nofaol omborlar ham qaytarilsin"),
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
        ctx: BranchContext = Depends(get_branch_context),
):
    # T1.1: yagona filial konteksti (X-Branch-Id); admin header'siz hammasini ko'radi.
    # T1.3: scope=all — transfer maqsadi va boshqaruv uchun korxonaning barcha omborlari (403 — ruxsatsiz)
    warehouses = list_company_warehouses(
        db, current_user, ctx, scope=scope, branch_id=branch_id, include_inactive=include_inactive,
    )
    return [
        {"id": w.id, "name": w.name, "type": w.type, "branch_id": w.branch_id,
         "branch_name": w.branch.name if w.branch else None, "is_active": bool(w.is_active)}
        for w in warehouses
    ]


@router.get("/expiring-batches", response_model=List[ExpiringBatchOut])
def get_expiring_batches(
    warehouse_id: Optional[int] = Query(None),
    branch_id: Optional[int] = Query(None),
    days: int = Query(30, ge=0, le=3650),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WAREHOUSE_ROLES, UserRole.accountant, UserRole.cashier)),
    ctx: BranchContext = Depends(get_branch_context),
):
    """T1.8: yaroqlilik muddati ro'yxati — umumiy `expired_batches_query` (cron/Telegram bilan bir xil qoida),
    ombor/filial ko'rsatiladi. Filialga biriktirilgan non-admin faqat o'z filiali omborlarini ko'radi."""
    from app.models.batch import Batch
    from app.models.product_variant import ProductVariant
    from app.utils.report_utils import local_today

    today_date = local_today()

    # Ombor ko'lami: korxona + (non-admin) o'z filiali + so'ralgan filial/ombor
    restrict = False
    wq = db.query(Warehouse.id).filter(Warehouse.company_id == current_user.company_id)
    scope_ids = ctx.scope_ids()  # T1.1: BranchContext (biriktirilgan filiallar / X-Branch-Id), users.branch_id emas
    if scope_ids is not None:
        wq = wq.filter(Warehouse.branch_id.in_(list(scope_ids)))
        restrict = True
    if branch_id:
        wq = wq.filter(Warehouse.branch_id == branch_id)
        restrict = True
    if warehouse_id:
        wq = wq.filter(Warehouse.id == warehouse_id)
        restrict = True
    warehouse_ids = [r[0] for r in wq.all()] if restrict else None

    rows = (
        expired_batches_query(
            db, current_user.company_id, today_date,
            warehouse_ids=warehouse_ids,
            expiry_until=today_date + timedelta(days=days),
        )
        .outerjoin(Warehouse, Warehouse.id == Batch.warehouse_id)
        .outerjoin(ProductVariant, ProductVariant.id == Batch.variant_id)
        .with_entities(Batch, Product.name, ProductVariant.name, Warehouse.name, Warehouse.branch_id)
        .all()
    )

    result = []
    for b, p_name, v_name, w_name, w_branch_id in rows:
        expiry = b.expiry_date.date() if hasattr(b.expiry_date, 'date') else b.expiry_date
        delta = (expiry - today_date).days
        result.append(ExpiringBatchOut(
            batch_id=b.id,
            product_id=b.product_id,
            product_name=p_name,
            variant_name=v_name,
            expiry_date=expiry,
            days_left=delta,
            quantity=b.quantity,
            is_expired=delta < 0,
            warehouse_id=b.warehouse_id,
            warehouse_name=w_name,
            branch_id=w_branch_id,
        ))

    result.sort(key=lambda x: x.days_left)
    return result


@router.post("/write-off-expired")
def write_off_expired(
    data: WriteOffExpiredRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles([UserRole.super_admin, UserRole.admin, UserRole.director, UserRole.manager])),
    ctx: BranchContext = Depends(get_branch_context),
):
    """T1.8: bitta (`batch_id`) yoki bir nechta (`batch_ids`) partiyani hisobdan chiqarish.
    Bitta partiya xato bersa — shu xato (404/400/403); ro'yxatda xato partiyalar `skipped` ga tushadi."""
    from app.models.batch import Batch
    from app.services.tenant_guards import WAREHOUSE_OTHER_BRANCH

    ids = []
    for bid in ([data.batch_id] if data.batch_id is not None else []) + list(data.batch_ids or []):
        if bid not in ids:
            ids.append(bid)
    single = len(ids) == 1

    written_off = []
    skipped = []
    for bid in ids:
        try:
            # Partiyani qulflaymiz va qoldiqni qayta tekshiramiz (parallel hisobdan chiqarishdan himoya)
            batch = db.query(Batch).filter(
                Batch.id == bid, Batch.company_id == current_user.company_id
            ).with_for_update().first()
            if not batch:
                raise HTTPException(status_code=404, detail="Batch topilmadi")
            if batch.quantity <= 0:
                raise HTTPException(status_code=400, detail="Qoldiq yo'q")

            scope_ids = ctx.scope_ids()  # T1.1: BranchContext, users.branch_id emas
            if batch.warehouse_id and scope_ids is not None:
                if _warehouse_branch(db, batch.warehouse_id) not in scope_ids:
                    raise HTTPException(status_code=403, detail=WAREHOUSE_OTHER_BRANCH)

            stock_level = db.query(StockLevel).filter(
                StockLevel.product_id == batch.product_id,
                StockLevel.warehouse_id == batch.warehouse_id,
                StockLevel.variant_id == batch.variant_id
            ).with_for_update().first()

            if not stock_level:
                raise HTTPException(status_code=400, detail="StockLevel topilmadi")
            if (stock_level.quantity or 0) <= 0:
                raise HTTPException(status_code=400, detail="Omborda bu partiya uchun qoldiq yo'q")
        except HTTPException as e:
            if single:
                raise
            skipped.append({"batch_id": bid, "reason": e.detail})
            continue

        # Faqat o'z omboridagi mavjud qoldiq bilan cheklab yechamiz — qoldiq manfiyga tushmaydi
        batch_qty = batch.quantity
        qty_to_write_off = min(batch_qty, max(stock_level.quantity, 0))
        diff = batch_qty - qty_to_write_off
        qty_before = stock_level.quantity
        stock_level.quantity -= qty_to_write_off
        qty_after = stock_level.quantity

        batch.quantity = 0

        reason = f"Muddati o'tgan (xodim: {current_user.name})"
        if diff > 0:
            reason += f"; qoldiq yetmadi, partiyadan {diff} nolga tushirildi"
        movement = StockMovement(
            product_id=batch.product_id,
            variant_id=batch.variant_id,
            warehouse_id=batch.warehouse_id,
            type=MovementType.EXPIRED,
            qty_before=qty_before,
            qty_after=qty_after,
            quantity=qty_to_write_off,
            reference_type="batch_write_off",
            reference_id=batch.id,
            user_id=current_user.id,
            reason=reason
        )
        db.add(movement)
        log_action_for(
            db, current_user, "EXPIRED_WRITE_OFF", "batch", batch.id,
            old_values={"product_id": batch.product_id, "quantity": float(qty_before)},
            new_values={"written_off": float(qty_to_write_off), "quantity": float(qty_after),
                        "warehouse_id": batch.warehouse_id},
            branch_id=_warehouse_branch(db, batch.warehouse_id),
        )
        written_off.append({"batch_id": batch.id, "quantity": float(qty_to_write_off)})
    db.commit()

    return {"message": "Muddati o'tgan mahsulot hisobdan chiqarildi", "written_off": written_off, "skipped": skipped}
