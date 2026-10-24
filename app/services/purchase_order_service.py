"""Xarid buyurtmalari (PO): yaratish, qabul qilish, tahrirlash, bekor qilish, o'chirish.

Qarz va to'lov qoidalari — app/services/supplier_ledger.py da. Qisqasi:
- ta'minotchi qarzi tovar qabul qilinganda paydo bo'ladi (qoralama/yuborilganda emas);
- xaridning balansga hissasi = qabul qilingan qiymat (chegirma bilan) − to'langan,
  u PurchaseOrder.supplier_debt da saqlanadi va har o'zgarishda farqi qo'shiladi;
- summalar bazada UZS da (unit_cost, total_amount, paid_amount), valyutali xarid
  exchange_rate (yaratilgandagi kurs) bo'yicha ta'minotchi valyutasiga o'tkaziladi.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from typing import List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.models.batch import Batch
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.supplier import Supplier
from app.models.user import User, UserRole
from app.models.warehouse import Warehouse
from app.services import supplier_ledger as ledger
from app.services.document_numbers import next_document_number, tashkent_today
from app.services.inventory_service import receive_stock
from app.services.pharmacy import pharmacy_context
from app.services.warehouse_access import assert_warehouse_branch_access

ZERO = Decimal("0")
TINY = Decimal("0.0005")


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


def generate_po_number(db: Session, company_id: int, branch_id: Optional[int] = None) -> str:
    """PO{YYYYMMDD}-{korxona}-{filial}-{NNNN} (T1.14): atomar hisoblagich bilan — o'chirilgan
    xariddan keyin ham, parallel so'rovlarda ham takrorlanmaydi."""
    return next_document_number(db, company_id=company_id, branch_id=branch_id, doc_type="PO")


# ─── Tekshiruvlar ────────────────────────────────────────────────────────────

def _get_po(db: Session, po_id: int, user: User) -> PurchaseOrder:
    q = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id)
    if user.role != UserRole.super_admin:
        q = q.filter(PurchaseOrder.company_id == user.company_id)
    po = q.first()
    if not po:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")
    # T1.3: filialga biriktirilgan non-bypass xodim boshqa filial omboridagi xaridni o'zgartira olmaydi (403)
    assert_warehouse_branch_access(db, user, None, po.warehouse_id)
    return po


def _company_supplier(db: Session, supplier_id: int, company_id: int) -> Supplier:
    s = db.query(Supplier).filter(Supplier.id == supplier_id, Supplier.company_id == company_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Ta'minotchi topilmadi")
    return s


def _company_warehouse(db: Session, warehouse_id: int, company_id: int) -> Warehouse:
    wh = db.query(Warehouse).filter(
        Warehouse.id == warehouse_id, Warehouse.company_id == company_id, Warehouse.is_active == True,
    ).first()
    if not wh:
        raise HTTPException(status_code=404, detail="Ombor topilmadi")
    return wh


def _company_product(db: Session, product_id: int, company_id: int) -> Product:
    prod = db.query(Product).filter(
        Product.id == product_id, Product.company_id == company_id, Product.is_deleted == False,
    ).first()
    if not prod:
        raise HTTPException(status_code=404, detail=f"Mahsulot topilmadi: {product_id}")
    if getattr(prod, "product_type", "stock") == "sell":
        raise HTTPException(status_code=400, detail=f"'{prod.name}' tarkibiy mahsulot bo'lgani uchun uni xarid qilib bo'lmaydi")
    return prod


# ─── Valyuta va qarz hissasi ─────────────────────────────────────────────────

def po_currency(po: PurchaseOrder) -> str:
    return (po.currency or "UZS").strip().upper() or "UZS"


def po_rate(db: Session, po: PurchaseOrder, persist: bool = True) -> Decimal:
    """Xarid kursi: yaratilgandagi kurs; eski xaridlarda joriy kurs (birinchi o'zgarishda qotiriladi)."""
    if po_currency(po) == "UZS":
        return Decimal("1")
    if po.exchange_rate and _d(po.exchange_rate) > 0:
        return _d(po.exchange_rate)
    rate = ledger.currency_rate(db, po.company_id, po_currency(po))
    if persist:
        po.exchange_rate = rate
    return rate


def recorded_contribution(db: Session, po: PurchaseOrder) -> Decimal:
    """Ta'minotchi balansiga shu xarid hozirgacha qo'shgan summa (supplier_debt_currency da)."""
    if po.supplier_debt is not None:
        return _d(po.supplier_debt)
    # Eski xaridlar: yaratilganda holatidan qat'i nazar (total − chegirma − to'langan) qo'shilgan,
    # faqat musbat bo'lsa; bekor qilish uni qaytarmagan.
    legacy_uzs = _d(po.total_amount) - _d(po.discount_amount) - _d(po.paid_amount)
    return legacy_uzs / po_rate(db, po, persist=False) if legacy_uzs > 0 else ZERO


def target_contribution(db: Session, po: PurchaseOrder, persist_rate: bool = True) -> Decimal:
    """Xaridning hozirgi hissasi (xarid valyutasida): qabul qilingan qiymat (chegirma ulushi bilan) − to'langan."""
    total = _d(po.total_amount)
    received = sum((_d(i.qty_received) * _d(i.unit_cost) for i in po.items), ZERO)
    ratio = (_d(po.discount_amount) / total) if total > 0 else ZERO
    net_received_uzs = received * (1 - ratio)
    return (net_received_uzs - _d(po.paid_amount)) / po_rate(db, po, persist=persist_rate)


def _item_currency(item: POItem) -> str:
    return (item.cost_currency or "UZS").strip().upper() or "UZS"


def is_mixed(po: PurchaseOrder) -> bool:
    """Qatorlarda so'mdan boshqa valyuta bormi. Ha bo'lsa qarz valyuta bo'yicha ajratiladi
    (so'mdagi qatorlar — so'mda, USD dagilar — USD da); yo'q bo'lsa butun xarid bitta valyutada."""
    return any(_item_currency(i) != "UZS" for i in po.items)


def rate_for(db: Session, po: PurchaseOrder, code: str, persist: bool = True) -> Decimal:
    """Xariddagi istalgan valyuta kursi (1 valyuta = N so'm): xarid yaratilgandagi kurs."""
    code = (code or "UZS").strip().upper() or "UZS"
    if code == "UZS":
        return Decimal("1")
    saved = (po.exchange_rates or {}).get(code)
    if saved and _d(saved) > 0:
        return _d(saved)
    if code == po_currency(po):
        return po_rate(db, po, persist)
    rate = ledger.currency_rate(db, po.company_id, code)
    if persist:
        po.exchange_rates = {**dict(po.exchange_rates or {}), code: float(rate)}
    return rate


def _stamp_rates(db: Session, po: PurchaseOrder) -> None:
    """Qatorlardagi (xarid valyutasidan boshqa) valyutalarning joriy kursini xaridga qotiradi."""
    pcur = po_currency(po)
    rates = {}
    for i in po.items:
        code = _item_currency(i)
        if code not in ("UZS", pcur):
            rates[code] = float(ledger.currency_rate(db, po.company_id, code))
    po.exchange_rates = rates


def _payment_events(db: Session, po: PurchaseOrder) -> list:
    """Xarid to'lovlari: [(valyuta, summa, so'm ekvivalenti)]; tranzaksiyasiz qolgan qism — so'mda."""
    events, covered = [], ZERO
    for tx in _po_payment_txs(db, po):
        code = (tx.currency_code or "UZS").strip().upper() or "UZS"
        amount = _d(tx.amount)
        meta = tx.meta or {}
        if meta.get("po_paid_uzs") is not None:
            uzs = _d(meta["po_paid_uzs"])
        else:
            uzs = amount * ledger.currency_rate(db, po.company_id, code)
        events.append((code, amount, uzs))
        covered += uzs
    residual = _d(po.paid_amount) - covered
    if residual > Decimal("1"):
        events.append(("UZS", residual, residual))
    return events


def _allocate_payment(db: Session, po: PurchaseOrder, parts: dict, code: str, amount: Decimal, uzs: Decimal,
                      persist: bool) -> None:
    """To'lovni qarz hissalariga taqsimlaydi: avval shu valyutadagi qarz, keyin boshqalari (kurs bo'yicha),
    ortig'i — to'lov valyutasida avans (manfiy hissa)."""
    remaining = amount
    own = parts.get(code, ZERO)
    if own > 0:
        take = min(own, remaining)
        parts[code] = own - take
        remaining -= take
    pay_rate = (uzs / amount) if amount > 0 else rate_for(db, po, code, persist)
    if remaining > TINY and pay_rate > 0:
        remaining_uzs = remaining * pay_rate
        for other in list(parts):
            debt = parts[other]
            if other == code or debt <= 0 or remaining_uzs <= TINY:
                continue
            r = rate_for(db, po, other, persist)
            cover_uzs = min(remaining_uzs, debt * r)
            parts[other] = debt - cover_uzs / r
            remaining_uzs -= cover_uzs
        remaining = remaining_uzs / pay_rate
    if remaining > TINY:
        parts[code] = parts.get(code, ZERO) - remaining


def target_parts(db: Session, po: PurchaseOrder, persist_rate: bool = True) -> dict:
    """Xaridning hozirgi qarz hissasi valyuta bo'yicha {valyuta: summa}.
    Oddiy xarid — bitta valyutada (eski hisob); aralash xarid — har qator o'z valyutasida."""
    pcur = po_currency(po)
    if not is_mixed(po):
        return {pcur: target_contribution(db, po, persist_rate)}
    total = _d(po.total_amount)
    ratio = (_d(po.discount_amount) / total) if total > 0 else ZERO
    value_uzs: dict = defaultdict(lambda: ZERO)
    parts: dict = {}
    for i in po.items:
        code = _item_currency(i)
        parts.setdefault(code, ZERO)
        value_uzs[code] += _d(i.qty_received) * _d(i.unit_cost)
    for code, v in value_uzs.items():
        parts[code] = v * (1 - ratio) / rate_for(db, po, code, persist_rate)
    parts.setdefault(pcur, ZERO)
    for code, amount, uzs in _payment_events(db, po):
        _allocate_payment(db, po, parts, code, amount, uzs, persist_rate)
    return parts


def _extra_parts(po: PurchaseOrder) -> dict:
    return {str(c).upper(): _d(v) for c, v in dict(po.supplier_debt_extra or {}).items()}


def _sync_supplier_debt(db: Session, po: PurchaseOrder) -> None:
    supplier = db.get(Supplier, po.supplier_id)
    if not supplier:
        return
    cur = po_currency(po)
    parts = target_parts(db, po)
    target = parts.pop(cur, ZERO)
    extra = {c: v for c, v in parts.items() if abs(v) >= Decimal("0.00005")}
    old = recorded_contribution(db, po)
    old_cur = (po.supplier_debt_currency or cur).upper()
    delta: dict = defaultdict(lambda: ZERO)
    delta[old_cur] -= old
    delta[cur] += target
    for c, v in _extra_parts(po).items():
        delta[c] -= v
    for c, v in extra.items():
        delta[c] += v
    for c, d in delta.items():
        ledger.add(db, supplier, c, d)
    po.supplier_debt = round(target, 4)
    po.supplier_debt_currency = cur
    po.supplier_debt_extra = {c: float(round(v, 4)) for c, v in extra.items()}


def display_amounts(db: Session, po: PurchaseOrder) -> dict:
    """Ro'yxat va ta'minotchi tarixi uchun bir xil hisob (xarid kursida, joriy kursda emas)."""
    cur = po_currency(po)
    rate = po_rate(db, po, persist=False)
    net_total = _d(po.total_amount) - _d(po.discount_amount)
    if po.supplier_debt is not None:
        contribution = recorded_contribution(db, po)
        extra = _extra_parts(po)
    else:
        parts = target_parts(db, po, persist_rate=False)
        contribution = parts.pop(cur, ZERO)
        extra = parts
    return {
        "currency": cur,
        "rate": rate,
        "total_cur": round(net_total / rate, 2),
        "paid_cur": round(_d(po.paid_amount) / rate, 2),
        "debt_cur": round(contribution, 2),
        "debt_uzs": round(contribution * rate, 2),
        # Aralash xarid: asosiy valyutadan boshqa valyutalardagi qarz {valyuta: summa}
        "debt_extra": {c: round(v, 2) for c, v in extra.items() if abs(v) >= Decimal("0.005")},
    }



# ─── Qabul qilish ────────────────────────────────────────────────────────────

def _to_datetime(v):
    if v is None or isinstance(v, datetime):
        return v
    return datetime.combine(v, datetime.min.time())


def _update_product_on_receipt(db: Session, product: Product, item: POItem, company_id: int,
                               user: Optional[User] = None, branch_id: Optional[int] = None) -> None:
    """Oxirgi xarid narxi — mahsulot tannarxi (mahsulot tannarx valyutasida); yangi sotuv narxlari.
    Variantli qator (T1.16): narxlar ProductVariant ga yoziladi (tannarx valyutasi parent mahsulotdan),
    parent Product narxlari o'zgarmaydi.
    T4.3: narx haqiqatan o'zgargan bo'lsa audit jurnaliga `PRICE_CHANGE` (eski/yangi qiymat bilan) yoziladi."""
    unit_uzs = _d(item.unit_cost)
    cur = (product.cost_currency or "UZS").strip().upper() or "UZS"
    cost = unit_uzs if cur == "UZS" else round(unit_uzs / ledger.currency_rate(db, company_id, cur), 4)
    target = product
    if item.variant_id:
        target = item.variant or db.get(ProductVariant, item.variant_id) or product
    _fields = ("cost_price", "sale_price", "wholesale_price")
    _old = {f: getattr(target, f, None) for f in _fields}
    target.cost_price = cost
    if item.new_sale_price is not None:
        target.sale_price = item.new_sale_price
    if item.new_wholesale_price is not None:
        target.wholesale_price = item.new_wholesale_price
    _new = {f: getattr(target, f, None) for f in _fields}

    def _same(a, b):
        return (a is None and b is None) or (a is not None and b is not None and _d(a) == _d(b))

    _changed = [f for f in _fields if not _same(_old[f], _new[f])]
    if _changed and user is not None:
        log_action(
            db, "PRICE_CHANGE", "product", product.id, user.id,
            old_values={**{f: (str(_old[f]) if _old[f] is not None else None) for f in _changed},
                        "variant_id": item.variant_id},
            new_values={**{f: (str(_new[f]) if _new[f] is not None else None) for f in _changed},
                        "variant_id": item.variant_id, "po_id": item.po_id if hasattr(item, "po_id") else None},
            company_id=company_id, branch_id=branch_id,
        )


# ─── Dorixona qoidalari (D1.3): faqat dorixona moduli yoqilgan korxonada ──────

def _round_price(price: Decimal, step: int, mode=ROUND_CEILING) -> Decimal:
    """Narxni `step` so'm qadamiga yaxlitlash (standart — yuqoriga); step=0 — faqat tiyin aniqligi."""
    if step and step > 0:
        return (price / step).to_integral_value(rounding=mode) * step
    return price.quantize(Decimal("0.01"), rounding=mode)


def _category_markup(product: Product, settings: dict) -> Decimal:
    """Mahsulot kategoriyasi (yoki ota kategoriyalari) ustamasi; yo'q bo'lsa — korxona sozlamasi."""
    cat = getattr(product, "category", None)
    for _ in range(10):  # ota kategoriyalar bo'ylab (tsikldan himoya)
        if cat is None:
            break
        if cat.markup_pct is not None:
            return _d(cat.markup_pct)
        cat = cat.parent
    return _d(settings.get("markup_pct"))


def _price_target(db: Session, product: Product, item: POItem):
    if item.variant_id:
        return item.variant or db.get(ProductVariant, item.variant_id) or product
    return product


def _auto_sale_price(product: Product, item: POItem, settings: dict) -> Optional[Decimal]:
    """Kirim narxi * (1 + ustama%), yuqoriga yaxlitlangan. Qo'lda narx berilgan yoki ustama yo'q bo'lsa — None."""
    unit = _d(item.unit_cost)
    if item.new_sale_price is not None or unit <= 0:
        return None
    pct = _category_markup(product, settings)
    if pct <= 0:
        return None
    step = int(settings.get("price_round") or 0)
    auto = _round_price(unit * (1 + pct / 100), step)
    max_pct = _d(settings.get("max_markup_pct"))
    if max_pct > 0 and auto > unit * (1 + max_pct / 100):
        auto = _round_price(unit * (1 + max_pct / 100), step, ROUND_FLOOR)  # yaxlitlash chegaradan oshirib yubormasin
    return auto


def suggested_sale_prices(db: Session, po: PurchaseOrder) -> dict:
    """Qabul oynasi uchun: {po_item_id: hisoblangan sotuv narxi}. Faqat dorixona yoqilgan korxonada (aks holda bo'sh)."""
    enabled, settings = pharmacy_context(db, po.company_id)
    if not enabled:
        return {}
    out = {}
    for it in po.items:
        product = it.product or db.get(Product, it.product_id)
        price = _auto_sale_price(product, it, settings) if product else None
        if price is not None:
            out[it.id] = price
    return out


def _plan_sale_price(db: Session, product: Product, item: POItem, settings: dict, label: str) -> Optional[Decimal]:
    """Dorixona: qabulda yangi sotuv narxi (ustama bilan) va narx chegarasi tekshiruvi.
    Qaytaradi: avtomatik hisoblangan narx (yoki None — qo'lda berilgan / ustama yo'q)."""
    unit = _d(item.unit_cost)
    auto = _auto_sale_price(product, item, settings)
    max_pct = _d(settings.get("max_markup_pct"))
    limit = unit * (1 + max_pct / 100) if (max_pct > 0 and unit > 0) else None
    if limit is not None:
        eff = item.new_sale_price if item.new_sale_price is not None else auto
        if eff is None:
            eff = _price_target(db, product, item).sale_price
        if eff is not None and _d(eff) > limit + Decimal("0.01"):
            raise HTTPException(
                status_code=400,
                detail=f"{label}: sotuv narxi ({_d(eff):.0f}) kirim narxiga nisbatan eng ko'p ruxsat etilgan "
                       f"ustamadan ({max_pct:.0f}%) oshib ketdi — narx {limit:.0f} dan oshmasligi kerak",
            )
    return auto


def _check_pharmacy_lots(label: str, lots: list, settings: dict, today, warnings: List[str]) -> None:
    """Dorixona: yaroqlilik muddati majburiy (P.5: seriya ixtiyoriy — bo'sh bo'lsa partiya avtomatik nom oladi);
    muddati o'tgan rad etiladi; qolgan muddat kam bo'lsa ogohlantirish."""
    min_pct = _d(settings.get("min_shelf_life_pct"))
    for j, (lot, expiry, manufacture, _qty) in enumerate(lots, 1):
        where = f"{label} ({j}-seriya)" if len(lots) > 1 else label
        if expiry is None:
            raise HTTPException(status_code=400, detail=f"{where}: yaroqlilik muddati majburiy (dorixona rejimi)")
        exp_d = expiry.date() if isinstance(expiry, datetime) else expiry
        if exp_d < today:
            raise HTTPException(status_code=400, detail=f"{where}: yaroqlilik muddati o'tgan ({exp_d:%d.%m.%Y})")
        if manufacture is None:
            continue
        man_d = manufacture.date() if isinstance(manufacture, datetime) else manufacture
        if man_d >= exp_d:
            raise HTTPException(status_code=400, detail=f"{where}: ishlab chiqarilgan sana yaroqlilik muddatidan oldin bo'lishi kerak")
        if min_pct > 0:
            pct = Decimal((exp_d - today).days) * 100 / Decimal((exp_d - man_d).days)
            if pct < min_pct:
                warnings.append(f"{where}: qolgan yaroqlilik muddati {pct:.0f}% (minimal {min_pct:.0f}%)")


def _plan_receipt(db: Session, po: PurchaseOrder, n: int, item: POItem, lots: list,
                  pharm: Tuple[bool, dict], warnings: List[str]) -> Optional[Decimal]:
    """Bitta qator qabulini tekshiradi (yozmaydi). Dorixona yoqilgan bo'lsa — seriya/muddat/narx qoidalari."""
    enabled, settings = pharm
    if not enabled:
        return None
    product = item.product or db.get(Product, item.product_id)
    label = f"{n}-qator '{product.name}'"
    _check_pharmacy_lots(label, lots, settings, tashkent_today(), warnings)
    return _plan_sale_price(db, product, item, settings, label)


def _receive_item(db: Session, po: PurchaseOrder, item: POItem, qty: Decimal, user: User,
                  lot: Optional[str] = None, expiry=None, manufacture=None,
                  lots: Optional[list] = None, sale_price: Optional[Decimal] = None) -> None:
    """lots — D1.3: [(seriya, muddat, ishlab chiqarilgan sana, miqdor)], har biri alohida Batch;
    berilmasa bitta partiya (lot/expiry/manufacture). sale_price — ustama bilan hisoblangan narx."""
    product = item.product or db.get(Product, item.product_id)
    if getattr(product, "product_type", "stock") == "sell":
        raise HTTPException(status_code=400, detail=f"'{product.name}' tarkibiy mahsulot bo'lgani uchun uni qabul qilib bo'lmaydi")
    receive_stock(
        db=db, product_id=item.product_id, quantity=qty, user_id=user.id,
        reason=f"PO #{po.number} qabul", reference_type="purchase_order", reference_id=po.id,
        warehouse_id=po.warehouse_id, variant_id=item.variant_id,
    )
    if lots is None:
        lots = [(lot, expiry, manufacture, qty)]
    for lot_no, lot_expiry, lot_manufacture, lot_qty in lots:
        db.add(Batch(
            product_id=item.product_id, variant_id=item.variant_id, warehouse_id=po.warehouse_id,
            lot_number=(lot_no or "").strip() or f"PO-{po.number}",   # P.5: bo'sh/probelli seriya — avtomatik nom
            manufacture_date=_to_datetime(lot_manufacture),
            expiry_date=_to_datetime(lot_expiry) or item.expiry_date,  # qabulda berilmasa — xarid qatoridagi muddat
            initial_quantity=lot_qty, quantity=lot_qty, purchase_price=item.unit_cost,
            po_id=po.id, company_id=po.company_id,
        ))
    item.qty_received = _d(item.qty_received) + qty
    if sale_price is not None and item.new_sale_price is None:
        item.new_sale_price = sale_price  # dorixona ustamasi: mavjud mantiq bilan mahsulot narxiga yoziladi
    _update_product_on_receipt(db, product, item, po.company_id, user, branch_id=getattr(po.warehouse, "branch_id", None))


def _register_marking(db: Session, po: PurchaseOrder, n: int, item: POItem, qty: Decimal, codes,
                      pharm: Tuple[bool, dict], warnings: List[str]) -> None:
    """D3.2: dorixona rejimida qabul qatoridagi markirovka kodlarini `in_stock` holatida yozadi.
    Modul o'chiq korxonada yoki mahsulot `requires_marking` bo'lmasa hech narsa qilinmaydi."""
    codes = [c for c in (codes or []) if c and str(c).strip()]
    if not codes or not pharm[0]:
        return
    product = item.product or db.get(Product, item.product_id)
    label = f"{n}-qator '{product.name}'"
    if not product.requires_marking:
        warnings.append(f"{label}: mahsulot markirovka talab qilmaydi — kodlar e'tiborga olinmadi")
        return
    from app.routers.pharmacy_marking import register_receipt_codes
    batches = (
        db.query(Batch)
        .filter(Batch.po_id == po.id, Batch.product_id == item.product_id, Batch.variant_id == item.variant_id)
        .order_by(Batch.id.asc()).all()
    )
    register_receipt_codes(db, po=po, product=product, codes=codes, batches=batches, label=label,
                           warnings=warnings, expected_qty=qty)


def _refresh_status(po: PurchaseOrder) -> None:
    if all(_d(i.qty_received) >= _d(i.qty_ordered) for i in po.items):
        po.status = POStatus.received
    elif any(_d(i.qty_received) > 0 for i in po.items):
        po.status = POStatus.partial


# ─── To'lov ──────────────────────────────────────────────────────────────────

def _po_payment_txs(db: Session, po: PurchaseOrder):
    from app.models.moliya import Transaction
    return db.query(Transaction).filter(
        Transaction.reference_type == "purchase_order",
        Transaction.reference_id == po.id,
        Transaction.company_id == po.company_id,
    ).order_by(Transaction.id).all()


def _record_po_payment(db: Session, po: PurchaseOrder, user: User, paid_uzs: Decimal, *,
                       payment_type: Optional[str], payment_currency: Optional[str],
                       payment_amount: Optional[Decimal], wallet_id: Optional[int], created_at=None):
    """Kassadan chiqqan pul: haqiqiy valyuta va summasi bilan (qarz hisobi uchun paid_amount — UZS)."""
    if paid_uzs <= 0:
        return None
    code = (payment_currency or "UZS").strip().upper() or "UZS"
    amount = _d(payment_amount) if (code != "UZS" and payment_amount) else paid_uzs
    if code == "UZS":
        amount = paid_uzs
    return ledger.record_cash(
        db, user=user, direction="out", amount=amount, currency=code, payment_type=payment_type or "cash",
        wallet_id=wallet_id, reference_type="purchase_order", reference_id=po.id,
        description=f"Ta'minotchi to'lovi #{po.number}" + (f" ({amount} {code})" if code != "UZS" else ""),
        meta={"po_paid_uzs": str(paid_uzs)}, warehouse_id=po.warehouse_id, created_at=created_at,
        prefer_warehouse=True,  # T1.16: xarajat tovar kirgan ombor filialiga yoziladi
    )


def remove_po_payment(db: Session, tx) -> None:
    """Xarid to'lovi tranzaksiyasi o'chirildi (Moliya / ta'minotchi sahifasidan): kassa qaytadi,
    xaridning to'langan summasi kamayadi va ta'minotchi qarzi shunga oshadi."""
    po = db.query(PurchaseOrder).filter(
        PurchaseOrder.id == tx.reference_id, PurchaseOrder.company_id == tx.company_id,
    ).first()
    if po is None:
        ledger.reverse_cash(db, tx)
        return
    if po.supplier_debt is None:  # eski xarid: hozirgi hissani qotirib, faqat farqni qo'llaymiz
        po.supplier_debt = recorded_contribution(db, po)
        po.supplier_debt_currency = po_currency(po)
    meta = tx.meta or {}
    if meta.get("po_paid_uzs") is not None:
        paid_uzs = _d(meta["po_paid_uzs"])
    else:
        paid_uzs = _d(tx.amount) * ledger.currency_rate(db, po.company_id, tx.currency_code)
    po.paid_amount = max(ZERO, _d(po.paid_amount) - paid_uzs)
    ledger.reverse_cash(db, tx)
    _sync_supplier_debt(db, po)


def _resolve_item_variant(db: Session, prod: Product, variant_id: Optional[int]) -> Optional[ProductVariant]:
    """PO qatori varianti (T1.16): `parent` mahsulot uchun variant majburiy va aynan shu mahsulotniki
    bo'lishi kerak; oddiy mahsulotga variant berilsa 400."""
    is_parent = getattr(prod, "product_type", "stock") == "parent"
    if not variant_id:
        if is_parent:
            raise HTTPException(status_code=400, detail=f"'{prod.name}': Variantli mahsulot uchun variant tanlang")
        return None
    if not is_parent:
        raise HTTPException(status_code=400, detail=f"'{prod.name}' variantli mahsulot emas — variant ko'rsatilmasligi kerak")
    variant = db.query(ProductVariant).filter(
        ProductVariant.id == variant_id, ProductVariant.product_id == prod.id,
    ).first()
    if not variant:
        raise HTTPException(status_code=404, detail=f"Variant topilmadi: {variant_id}")
    return variant


def _unit_ratio(db: Session, company_id: int, product_id: int, unit_id, pharm: Tuple[bool, dict]) -> Decimal:
    """D2.4: qadoq birligi (quti/blister) nisbati — asosiy birlikda nechta. `unit_id` yo'q -> 1 (hech narsa o'zgarmaydi).
    Birlik faqat dorixona rejimida va shu korxonaning shu mahsulotiniki bo'lishi shart."""
    if not unit_id:
        return Decimal("1")
    if not pharm[0]:
        raise HTTPException(status_code=400, detail="Qadoq birliklari (quti, blister) faqat dorixona rejimida ishlaydi")
    from app.models.product_units import ProductUnit
    u = db.query(ProductUnit).filter(
        ProductUnit.id == unit_id, ProductUnit.product_id == product_id, ProductUnit.company_id == company_id,
    ).first()
    if not u:
        raise HTTPException(status_code=404, detail="Birlik topilmadi")
    return _d(u.ratio)


def _build_items(db: Session, po: PurchaseOrder, items_data, company_id: int) -> Decimal:
    total = ZERO
    pharm = None   # D2.4: faqat `unit_id` li qator bo'lsa, bir marta olinadi
    for it in items_data:
        prod = _company_product(db, it.product_id, company_id)
        variant = _resolve_item_variant(db, prod, getattr(it, "variant_id", None))
        # D2.4: kirim birligi (quti): miqdor * nisbat, narx / nisbat — qoldiq va tannarx asosiy birlikda.
        qty_ordered, unit_cost = it.qty_ordered, it.unit_cost
        original_cost = it.original_unit_cost if it.original_unit_cost is not None else it.unit_cost
        if getattr(it, "unit_id", None):
            if pharm is None:
                pharm = pharmacy_context(db, company_id)
            ratio = _unit_ratio(db, company_id, prod.id, it.unit_id, pharm)
            qty_ordered = _d(it.qty_ordered) * ratio
            unit_cost = (_d(it.unit_cost) / ratio).quantize(Decimal("0.01"))
            original_cost = (_d(original_cost) / ratio).quantize(Decimal("0.0001"))
        item = POItem(
            product_id=prod.id,
            variant_id=variant.id if variant else None,
            qty_ordered=qty_ordered,
            qty_received=ZERO,
            unit_cost=unit_cost,
            cost_currency=(it.cost_currency or "UZS").strip().upper() or "UZS",
            original_unit_cost=original_cost,
            expiry_date=it.expiry_date,
            lot_number=(getattr(it, "lot_number", None) or "").strip() or None,
            manufacture_date=getattr(it, "manufacture_date", None),
            new_sale_price=it.new_sale_price,
            new_wholesale_price=it.new_wholesale_price,
        )
        item.product = prod
        item.variant = variant
        po.items.append(item)
        total += _d(qty_ordered) * _d(unit_cost)
    return total


def _check_discount(discount: Decimal, total: Decimal) -> Decimal:
    if discount > total + Decimal("0.01"):
        raise HTTPException(status_code=400, detail="Chegirma xarid summasidan oshib ketdi")
    return min(discount, total)


# ─── Amallar ─────────────────────────────────────────────────────────────────

def create_purchase_order(db: Session, data, current_user: User) -> PurchaseOrder:
    cid = current_user.company_id
    supplier = _company_supplier(db, data.supplier_id, cid)
    po_wh = _company_warehouse(db, data.warehouse_id, cid)
    # T1.3: non-bypass xodim faqat o'z filiali omboriga xarid yarata oladi
    assert_warehouse_branch_access(db, current_user, None, po_wh.id)
    currency = (data.currency or "UZS").strip().upper() or "UZS"
    status = data.status or POStatus.draft

    po = PurchaseOrder(
        number=generate_po_number(db, cid, po_wh.branch_id), supplier_id=supplier.id, warehouse_id=data.warehouse_id,
        note=data.note, expected_date=data.expected_date, created_by=current_user.id, company_id=cid,
        supplier_invoice_number=(getattr(data, "supplier_invoice_number", None) or "").strip() or None,
        supplier_invoice_date=getattr(data, "supplier_invoice_date", None),
        status=POStatus.draft, currency=currency, exchange_rate=ledger.currency_rate(db, cid, currency),
        total_amount=ZERO, paid_amount=ZERO, discount_amount=ZERO,
        supplier_debt=ZERO, supplier_debt_currency=currency,  # yangi xarid — hissa hali 0
    )
    db.add(po)
    db.flush()

    total = _build_items(db, po, data.items, cid)
    _stamp_rates(db, po)
    po.total_amount = total
    po.discount_amount = _check_discount(_d(data.discount_amount), total)
    po.paid_amount = _d(data.paid_amount)
    db.flush()

    if status == POStatus.received:
        pharm = pharmacy_context(db, cid)
        warnings: List[str] = []
        plan = []
        for n, item in enumerate(po.items, 1):
            qty = _d(item.qty_ordered)
            lots = [(item.lot_number, item.expiry_date, item.manufacture_date, qty)]
            plan.append((item, qty, lots, _plan_receipt(db, po, n, item, lots, pharm, warnings)))
        for item, qty, lots, sale_price in plan:
            _receive_item(db, po, item, qty, current_user, lot=item.lot_number, manufacture=item.manufacture_date,
                          sale_price=sale_price)
        po.status = POStatus.received
        po.receive_warnings = warnings
    else:
        po.status = status

    _record_po_payment(
        db, po, current_user, po.paid_amount, payment_type=data.payment_type,
        payment_currency=data.payment_currency, payment_amount=data.payment_amount, wallet_id=data.wallet_id,
    )
    _sync_supplier_debt(db, po)
    log_action(db, action="CREATE", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               new_values={"number": po.number, "status": po.status.value, "total": str(total),
                           "paid": str(po.paid_amount), "currency": currency, "supplier_id": supplier.id})
    db.flush()
    return po


def receive_purchase_order(db: Session, po_id: int, data, current_user: User) -> PurchaseOrder:
    po = _get_po(db, po_id, current_user)
    if po.status == POStatus.cancelled:
        raise HTTPException(status_code=400, detail="Bekor qilingan buyurtmaga qabul qilib bo'lmaydi")
    if po.status == POStatus.received:
        raise HTTPException(status_code=400, detail="Buyurtma allaqachon to'liq qabul qilingan")

    items_map = {item.id: item for item in po.items}
    pharm = pharmacy_context(db, po.company_id)  # D1.3: bitta amal uchun bir marta
    warnings: List[str] = []
    planned = defaultdict(lambda: ZERO)
    plan = []
    for n, r in enumerate(data.items, 1):
        item = items_map.get(r.po_item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"PO item ID={r.po_item_id} topilmadi")
        # D2.4: qabul birligi (quti): kiritilgan miqdor * nisbat = asosiy birlikdagi qabul (unit_id yo'q -> 1)
        ratio = _unit_ratio(db, po.company_id, item.product_id, getattr(r, "unit_id", None), pharm)
        if getattr(r, "lots", None):
            qty = sum((_d(x.qty) for x in r.lots), ZERO)
            if r.qty_received and abs(_d(r.qty_received) - qty) > TINY:
                raise HTTPException(
                    status_code=400,
                    detail=f"{n}-qator: seriyalar yig'indisi ({qty}) qabul miqdoriga ({_d(r.qty_received)}) teng emas",
                )
            qty = qty * ratio
            lots = [(x.lot_number, x.expiry_date or item.expiry_date, x.manufacture_date or item.manufacture_date,
                     _d(x.qty) * ratio)
                    for x in r.lots]
        else:
            qty = _d(r.qty_received) * ratio
            if qty <= 0:
                continue
            lots = [(r.lot_number or item.lot_number, r.expiry_date or item.expiry_date,
                     getattr(r, "manufacture_date", None) or item.manufacture_date, qty)]
        remaining = _d(item.qty_ordered) - _d(item.qty_received) - planned[item.id]
        if qty > remaining + TINY:
            raise HTTPException(status_code=400, detail=f"Qabul miqdori ({qty}) qolgan miqdordan ({remaining}) ko'p")
        planned[item.id] += qty
        plan.append((item, qty, lots, _plan_receipt(db, po, n, item, lots, pharm, warnings),
                     getattr(r, "marking_codes", None), n))   # D3.2: markirovka kodlari (ixtiyoriy)
    if not plan:
        raise HTTPException(status_code=400, detail="Qabul qilinadigan miqdor kiritilmagan")
    for item, qty, lots, sale_price, mk_codes, n in plan:
        _receive_item(db, po, item, qty, current_user, lots=lots, sale_price=sale_price)
        _register_marking(db, po, n, item, qty, mk_codes, pharm, warnings)
    if getattr(data, "supplier_invoice_number", None):
        po.supplier_invoice_number = data.supplier_invoice_number.strip() or po.supplier_invoice_number
    if getattr(data, "supplier_invoice_date", None):
        po.supplier_invoice_date = data.supplier_invoice_date
    po.receive_warnings = warnings

    _refresh_status(po)
    _sync_supplier_debt(db, po)
    log_action(db, action="RECEIVE", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               new_values={"items": [{"po_item_id": r.po_item_id, "qty": str(r.qty_received)} for r in data.items],
                           "status": po.status.value})
    db.flush()
    return po


def cancel_purchase_order(db: Session, po_id: int, current_user: User) -> PurchaseOrder:
    """Bekor qilish: qabul qilinmagan qism uchun qarz yo'q; qabul qilingan qism va to'lov
    haqiqiy bo'lgani uchun saqlanadi (eski xaridlardagi ortiqcha qarz shu yerda tuzatiladi)."""
    po = _get_po(db, po_id, current_user)
    if po.status in (POStatus.received, POStatus.cancelled):
        raise HTTPException(status_code=400, detail=f"'{po.status.value}' holatdagi buyurtmani bekor qilib bo'lmaydi")
    po.status = POStatus.cancelled
    _sync_supplier_debt(db, po)
    log_action(db, action="CANCEL", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               new_values={"number": po.number})
    db.flush()
    return po


def delete_purchase_order(db: Session, po_id: int, current_user: User) -> None:
    """O'chirish: qabul qilingan tovar ombordan aynan shu miqdorda ayiriladi (sotilgan bo'lsa —
    o'chirish taqiqlanadi), to'lovlar kassaga qaytariladi, qarz hissasi aynan qaytariladi."""
    from app.models.inventory import StockLevel, StockMovement, MovementType

    po = _get_po(db, po_id, current_user)

    # 1. Shu xariddan kelgan partiyalar ishlatilganmi?
    batches = db.query(Batch).filter(
        Batch.company_id == po.company_id,
        or_(Batch.po_id == po.id,
            and_(Batch.po_id.is_(None), Batch.lot_number == f"purchase_order-{po.id}")),  # eski avto-qabul
    ).all()
    used = [b for b in batches if _d(b.quantity) + TINY < _d(b.initial_quantity)]
    if used:
        names = sorted({(db.get(Product, b.product_id).name if db.get(Product, b.product_id) else str(b.product_id)) for b in used})
        raise HTTPException(
            status_code=400,
            detail=f"Bu xariddagi tovarlar sotilgan yoki ishlatilgan ({', '.join(names)}) — "
                   f"xaridni o'chirib bo'lmaydi. Ortiqchasini ta'minotchiga qaytarish orqali rasmiylashtiring.",
        )

    # 2. Qoldiqni aynan qabul qilingan miqdorga kamaytirish
    movements = db.query(StockMovement).filter(
        StockMovement.reference_type == "purchase_order",
        StockMovement.reference_id == po.id,
        StockMovement.type == MovementType.IN,
    ).all()
    need = defaultdict(lambda: ZERO)
    for m in movements:
        need[(m.product_id, m.variant_id)] += _d(m.quantity)
    stocks = {}
    for (pid, vid), qty in need.items():
        q = db.query(StockLevel).filter(StockLevel.product_id == pid, StockLevel.warehouse_id == po.warehouse_id)
        q = q.filter(StockLevel.variant_id == vid) if vid else q.filter(StockLevel.variant_id.is_(None))
        stock = q.with_for_update().first()
        if not stock or _d(stock.quantity) + TINY < qty:
            prod = db.get(Product, pid)
            raise HTTPException(
                status_code=400,
                detail=f"'{prod.name if prod else pid}' qoldig'i ({_d(stock.quantity) if stock else 0}) "
                       f"qabul qilingan miqdordan ({qty}) kam — xaridni o'chirib bo'lmaydi",
            )
        stocks[(pid, vid)] = stock
    for (pid, vid), qty in need.items():
        stock = stocks[(pid, vid)]
        before = _d(stock.quantity)
        stock.quantity = before - qty
        db.add(StockMovement(
            product_id=pid, variant_id=vid, warehouse_id=po.warehouse_id, type=MovementType.OUT,
            qty_before=before, qty_after=before - qty, quantity=qty,
            reference_type="purchase_order_delete", reference_id=po.id, user_id=current_user.id,
            reason=f"PO #{po.number} o'chirildi",
        ))
    for b in batches:
        b.quantity = 0
        b.po_id = None

    # 3. To'lovlar kassaga qaytadi
    for tx in _po_payment_txs(db, po):
        ledger.reverse_cash(db, tx)

    # 4. Qarz hissasi aynan qaytariladi (boshqa xaridlar qarziga tegmaydi)
    supplier = db.get(Supplier, po.supplier_id)
    if supplier:
        ledger.add(db, supplier, (po.supplier_debt_currency or po_currency(po)), -recorded_contribution(db, po))
        for c, v in _extra_parts(po).items():
            ledger.add(db, supplier, c, -v)

    log_action(db, action="DELETE", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               old_values={"number": po.number, "status": po.status.value, "total": str(po.total_amount),
                           "paid": str(po.paid_amount), "supplier_id": po.supplier_id})
    db.flush()
    db.delete(po)
    db.commit()


def update_purchase_order(db: Session, po_id: int, data, current_user: User) -> PurchaseOrder:
    """Faqat qoralama yoki yuborilgan xaridni tahrirlash (qabul qilingan miqdorlar yo'qolmasligi uchun)."""
    po = _get_po(db, po_id, current_user)
    if po.status not in (POStatus.draft, POStatus.sent):
        raise HTTPException(status_code=400, detail="Faqat qoralama yoki yuborilgan xaridni tahrirlash mumkin")
    cid = po.company_id

    # Eski hissani to'liq olib tashlaymiz — oxirida yangi holat bo'yicha qo'shiladi
    old_supplier = db.get(Supplier, po.supplier_id)
    old_cur = (po.supplier_debt_currency or po_currency(po)).upper()
    if old_supplier:
        ledger.add(db, old_supplier, old_cur, -recorded_contribution(db, po))
        for c, v in _extra_parts(po).items():
            ledger.add(db, old_supplier, c, -v)
    po.supplier_debt = ZERO
    po.supplier_debt_extra = {}
    po.supplier_debt_currency = old_cur

    if data.supplier_id is not None:
        po.supplier_id = _company_supplier(db, data.supplier_id, cid).id
    wh_changed_to = None
    if data.warehouse_id is not None:
        new_wh = _company_warehouse(db, data.warehouse_id, cid)
        # T1.3: non-bypass xodim xaridni boshqa filial omboriga ko'chira olmaydi (403)
        assert_warehouse_branch_access(db, current_user, None, new_wh.id)
        if new_wh.id != po.warehouse_id:
            wh_changed_to = new_wh
        po.warehouse_id = new_wh.id
    if data.note is not None:
        po.note = data.note
    if data.expected_date is not None:
        po.expected_date = data.expected_date
    if getattr(data, "supplier_invoice_number", None) is not None:
        po.supplier_invoice_number = data.supplier_invoice_number.strip() or None
    if getattr(data, "supplier_invoice_date", None) is not None:
        po.supplier_invoice_date = data.supplier_invoice_date
    if data.currency:
        new_cur = data.currency.strip().upper()
        if new_cur != po_currency(po):
            po.currency = new_cur
            po.exchange_rate = ledger.currency_rate(db, cid, new_cur)

    if data.items is not None:
        po.items.clear()
        db.flush()
        po.total_amount = _build_items(db, po, data.items, cid)
        _stamp_rates(db, po)
    if data.discount_amount is not None:
        po.discount_amount = data.discount_amount
    po.discount_amount = _check_discount(_d(po.discount_amount), _d(po.total_amount))

    if data.paid_amount is not None:
        old_txs = _po_payment_txs(db, po)
        wallet_id = data.wallet_id or (old_txs[0].wallet_id if old_txs else None)
        ptype = data.payment_type or (old_txs[0].payment_type if old_txs else "cash")
        created_at = old_txs[0].created_at if old_txs else None
        for tx in old_txs:
            ledger.reverse_cash(db, tx)
        po.paid_amount = _d(data.paid_amount)
        _record_po_payment(
            db, po, current_user, po.paid_amount, payment_type=ptype,
            payment_currency=data.payment_currency, payment_amount=data.payment_amount,
            wallet_id=wallet_id, created_at=created_at,
        )
    elif wh_changed_to is not None and wh_changed_to.branch_id:
        # T1.16: to'lov qayta yozilmasa — mavjud xarid to'lovlari xarajati yangi ombor filialiga o'tadi
        for tx in _po_payment_txs(db, po):
            tx.branch_id = wh_changed_to.branch_id

    db.flush()
    _sync_supplier_debt(db, po)
    log_action(db, action="UPDATE", entity_type="purchase_order", entity_id=po.id, user_id=current_user.id,
               new_values={"total": str(po.total_amount), "paid": str(po.paid_amount),
                           "currency": po_currency(po), "supplier_id": po.supplier_id})
    db.flush()
    return po
