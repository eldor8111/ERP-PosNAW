"""Filial narxlari (T4.3): korxona narxini filial bo'yicha ustidan yozish (default — korxona narxi)."""
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.dependencies import require_roles
from app.database import get_db
from app.models.branch import Branch
from app.models.branch_price import BranchProductPrice
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import User, UserRole

router = APIRouter(prefix="/branch-prices", tags=["Branch prices"])

# Filial narxini boshqarish: admin va director; manager — faqat o'z filialida
BRANCH_PRICE_ROLES = (UserRole.admin, UserRole.director, UserRole.manager)
BULK_LIMIT = 1000

BRANCH_NOT_FOUND = "Filial topilmadi"
PRODUCT_NOT_FOUND = "Mahsulot topilmadi"
VARIANT_NOT_FOUND = "Variant topilmadi"
PRICE_REQUIRED = "Kamida bitta narx (chakana yoki ulgurji) kiritilishi kerak"
PRICE_NEGATIVE = "Narx manfiy bo'lishi mumkin emas"
PRICE_INVALID = "Narx noto'g'ri"
BRANCH_FORBIDDEN = "Bu filial narxlarini o'zgartirishga ruxsat yo'q"
SAME_BRANCH = "Manba va maqsad filial bir xil bo'lishi mumkin emas"
BULK_TOO_MANY = f"Bir so'rovda ko'pi bilan {BULK_LIMIT} qator yuborish mumkin"


class BranchPriceIn(BaseModel):
    sale_price: Optional[Decimal] = None
    wholesale_price: Optional[Decimal] = None


class BranchPriceBulkRow(BaseModel):
    product_id: int
    variant_id: Optional[int] = None
    sale_price: Optional[Decimal] = None
    wholesale_price: Optional[Decimal] = None


class BranchPriceBulkIn(BaseModel):
    items: List[BranchPriceBulkRow]


def _get_branch(db: Session, user: User, branch_id: int) -> Branch:
    """Filial faqat o'z korxonasidan; begona/yo'q filial — 404."""
    branch = db.query(Branch).filter(Branch.id == branch_id, Branch.company_id == user.company_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail=BRANCH_NOT_FOUND)
    return branch


def _assert_can_edit(db: Session, user: User, branch: Branch) -> None:
    """manager — faqat o'z filialida (filiali bo'lsa); admin/director/super_admin — hamma filialda."""
    if user.role != UserRole.manager:
        return
    from app.core.branch_context import effective_branch_ids
    allowed = set(effective_branch_ids(db, user))
    if user.branch_id:
        allowed.add(user.branch_id)
    if allowed and branch.id not in allowed:
        raise HTTPException(status_code=403, detail=BRANCH_FORBIDDEN)


def _get_product(db: Session, user: User, product_id: int) -> Product:
    product = db.query(Product).filter(
        Product.id == product_id,
        Product.company_id == user.company_id,
        Product.is_deleted == False,  # noqa: E712
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail=PRODUCT_NOT_FOUND)
    return product


def _check_variant(db: Session, product: Product, variant_id: Optional[int]) -> None:
    if variant_id is None:
        return
    ok = db.query(ProductVariant.id).filter(
        ProductVariant.id == variant_id, ProductVariant.product_id == product.id,
    ).first()
    if not ok:
        raise HTTPException(status_code=404, detail=VARIANT_NOT_FOUND)


def _clean_price(value):
    """Narxni tekshiradi: None -> None; manfiy yoki noto'g'ri -> 400."""
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail=PRICE_INVALID)
    if not d.is_finite():
        raise HTTPException(status_code=400, detail=PRICE_INVALID)
    if d < 0:
        raise HTTPException(status_code=400, detail=PRICE_NEGATIVE)
    return d


def _find(db: Session, branch_id: int, product_id: int, variant_id: Optional[int]) -> Optional[BranchProductPrice]:
    q = db.query(BranchProductPrice).filter(
        BranchProductPrice.branch_id == branch_id,
        BranchProductPrice.product_id == product_id,
    )
    if variant_id is None:
        q = q.filter(BranchProductPrice.variant_id.is_(None))
    else:
        q = q.filter(BranchProductPrice.variant_id == variant_id)
    return q.first()


def _snap(row: Optional[BranchProductPrice]) -> Optional[dict]:
    if row is None:
        return None
    return {
        "sale_price": str(row.sale_price) if row.sale_price is not None else None,
        "wholesale_price": str(row.wholesale_price) if row.wholesale_price is not None else None,
    }


def _upsert(db: Session, user: User, branch: Branch, product: Product, variant_id: Optional[int],
            fields: dict) -> tuple:
    """Filial narxini yaratadi/yangilaydi. `fields` — faqat berilgan ustunlar (`sale_price`/`wholesale_price`);
    berilmaganlari avvalgicha qoladi. Ikkala narx ham bo'sh bo'lib qolsa 400. -> (row, changed)."""
    existing = _find(db, branch.id, product.id, variant_id)
    old = _snap(existing)
    sale = existing.sale_price if existing is not None else None
    wholesale = existing.wholesale_price if existing is not None else None
    if "sale_price" in fields:
        sale = _clean_price(fields["sale_price"])
    if "wholesale_price" in fields:
        wholesale = _clean_price(fields["wholesale_price"])
    if sale is None and wholesale is None:
        raise HTTPException(status_code=400, detail=PRICE_REQUIRED)

    if existing is None:
        row = BranchProductPrice(
            company_id=user.company_id, branch_id=branch.id, product_id=product.id, variant_id=variant_id,
            sale_price=sale, wholesale_price=wholesale, created_by=user.id,
        )
        db.add(row)
        db.flush()
    else:
        row = existing
        same_sale = (row.sale_price is None and sale is None) or (
            row.sale_price is not None and sale is not None and Decimal(str(row.sale_price)) == sale)
        same_wh = (row.wholesale_price is None and wholesale is None) or (
            row.wholesale_price is not None and wholesale is not None and Decimal(str(row.wholesale_price)) == wholesale)
        if same_sale and same_wh:
            return row, False
        row.sale_price = sale
        row.wholesale_price = wholesale
        db.flush()
    log_action(
        db, "BRANCH_PRICE_SET", "branch_price", row.id, user.id,
        old_values=old,
        new_values={**_snap(row), "branch_id": branch.id, "product_id": product.id, "variant_id": variant_id},
        company_id=user.company_id, branch_id=branch.id,
    )
    return row, True


def _row_out(row: BranchProductPrice) -> dict:
    return {
        "id": row.id, "branch_id": row.branch_id, "product_id": row.product_id, "variant_id": row.variant_id,
        "sale_price": row.sale_price, "wholesale_price": row.wholesale_price,
    }


@router.get("")
@router.get("/")
def list_branch_prices(
    branch_id: int = Query(...),
    search: Optional[str] = Query(None),
    only_overridden: bool = Query(False),
    product_id: Optional[int] = Query(None, description="Bitta mahsulot uchun (mahsulot kartochkasi)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*BRANCH_PRICE_ROLES)),
):
    """Mahsulotlar ro'yxati: korxona narxi, shu filial narxi (bo'lsa) va farq."""
    branch = _get_branch(db, current_user, branch_id)
    q = db.query(Product).filter(
        Product.company_id == current_user.company_id,
        Product.is_deleted == False,  # noqa: E712
    )
    if search and search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(or_(Product.name.ilike(like), Product.sku.ilike(like), Product.barcode.ilike(like)))
    if product_id is not None:
        q = q.filter(Product.id == product_id)
    if only_overridden:
        q = q.filter(Product.id.in_(
            db.query(BranchProductPrice.product_id).filter(BranchProductPrice.branch_id == branch.id)
        ))
    total = q.with_entities(func.count(Product.id)).scalar() or 0
    products = q.order_by(Product.name.asc(), Product.id.asc()).offset(skip).limit(limit).all()

    rows = []
    if products:
        rows = db.query(BranchProductPrice).filter(
            BranchProductPrice.branch_id == branch.id,
            BranchProductPrice.product_id.in_([p.id for p in products]),
        ).all()
    base = {r.product_id: r for r in rows if r.variant_id is None}
    variants = {}
    for r in rows:
        if r.variant_id is not None:
            variants.setdefault(r.product_id, []).append(
                {"variant_id": r.variant_id, "sale_price": r.sale_price, "wholesale_price": r.wholesale_price})

    def _diff(branch_val, company_val):
        if branch_val is None or company_val is None:
            return None
        return Decimal(str(branch_val)) - Decimal(str(company_val))

    items = []
    for p in products:
        r = base.get(p.id)
        bs = r.sale_price if r else None
        bw = r.wholesale_price if r else None
        items.append({
            "product_id": p.id, "name": p.name, "sku": p.sku, "barcode": p.barcode,
            "sale_price": p.sale_price, "wholesale_price": p.wholesale_price,
            "sale_currency": p.sale_currency, "wholesale_currency": p.wholesale_currency,
            "branch_sale_price": bs, "branch_wholesale_price": bw,
            "diff_sale": _diff(bs, p.sale_price), "diff_wholesale": _diff(bw, p.wholesale_price),
            "has_override": r is not None or bool(variants.get(p.id)),
            "variant_prices": variants.get(p.id, []),
        })
    return {"items": items, "total": total, "skip": skip, "limit": limit, "branch_id": branch.id}


@router.put("/{branch_id}/{product_id}")
def set_branch_price(
    branch_id: int,
    product_id: int,
    data: BranchPriceIn,
    variant_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*BRANCH_PRICE_ROLES)),
):
    branch = _get_branch(db, current_user, branch_id)
    _assert_can_edit(db, current_user, branch)
    product = _get_product(db, current_user, product_id)
    _check_variant(db, product, variant_id)
    fields = {k: getattr(data, k) for k in data.model_fields_set if k in ("sale_price", "wholesale_price")}
    row, _changed = _upsert(db, current_user, branch, product, variant_id, fields)
    db.commit()
    return _row_out(row)


@router.delete("/{branch_id}/{product_id}")
def delete_branch_price(
    branch_id: int,
    product_id: int,
    variant_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*BRANCH_PRICE_ROLES)),
):
    """Filial narxini o'chirish — shu filial yana korxona narxiga qaytadi."""
    branch = _get_branch(db, current_user, branch_id)
    _assert_can_edit(db, current_user, branch)
    _get_product(db, current_user, product_id)
    row = _find(db, branch.id, product_id, variant_id)
    if row is None or row.company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Filial narxi topilmadi")
    old = {**_snap(row), "branch_id": branch.id, "product_id": product_id, "variant_id": variant_id}
    row_id = row.id
    db.delete(row)
    log_action(
        db, "BRANCH_PRICE_DELETE", "branch_price", row_id, current_user.id,
        old_values=old, new_values=None, company_id=current_user.company_id, branch_id=branch.id,
    )
    db.commit()
    return {"deleted": True}


@router.post("/{branch_id}/bulk")
def bulk_set_branch_prices(
    branch_id: int,
    data: BranchPriceBulkIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*BRANCH_PRICE_ROLES)),
):
    """Ommaviy yuklash (<= 1000 qator). Har qator alohida savepoint'da: xato qator boshqalarni to'xtatmaydi."""
    branch = _get_branch(db, current_user, branch_id)
    _assert_can_edit(db, current_user, branch)
    if len(data.items) > BULK_LIMIT:
        raise HTTPException(status_code=400, detail=BULK_TOO_MANY)

    saved, skipped, errors = 0, 0, []
    for idx, it in enumerate(data.items, start=1):
        try:
            with db.begin_nested():
                product = _get_product(db, current_user, it.product_id)
                _check_variant(db, product, it.variant_id)
                fields = {k: getattr(it, k) for k in ("sale_price", "wholesale_price")
                          if k in it.model_fields_set}
                _row, changed = _upsert(db, current_user, branch, product, it.variant_id, fields)
            if changed:
                saved += 1
            else:
                skipped += 1
        except HTTPException as exc:
            errors.append({"row": idx, "error": str(exc.detail)})
    db.commit()
    return {"saved": saved, "skipped": skipped, "errors": errors}


@router.post("/{branch_id}/copy-from/{src_branch_id}")
def copy_branch_prices(
    branch_id: int,
    src_branch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*BRANCH_PRICE_ROLES)),
):
    """Boshqa filial narxlarini shu filialga nusxalash (mavjud narxlar ustidan yoziladi)."""
    branch = _get_branch(db, current_user, branch_id)
    src = _get_branch(db, current_user, src_branch_id)
    if branch.id == src.id:
        raise HTTPException(status_code=400, detail=SAME_BRANCH)
    _assert_can_edit(db, current_user, branch)

    src_rows = db.query(BranchProductPrice).join(
        Product, Product.id == BranchProductPrice.product_id,
    ).filter(
        BranchProductPrice.branch_id == src.id,
        BranchProductPrice.company_id == current_user.company_id,
        Product.is_deleted == False,  # noqa: E712
    ).all()
    copied = 0
    for r in src_rows:
        product = db.query(Product).filter(Product.id == r.product_id).first()
        fields = {"sale_price": r.sale_price, "wholesale_price": r.wholesale_price}
        with db.begin_nested():
            _row, changed = _upsert(db, current_user, branch, product, r.variant_id, fields)
        if changed:
            copied += 1
    db.commit()
    return {"copied": copied, "total": len(src_rows)}
