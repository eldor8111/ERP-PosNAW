"""D1.4 — Dorixona rejimida qaytarishda asl partiyaga qaytarish.

Qamrov: to'liq (/sales/return) va qisman (/sales/{id}/return-items) qaytarish; ikki partiyali qator
(oxirgi ajratilgandan boshlab, ketma-ket qaytarishlar); muddati o'tgan partiya; eski sotuv (ajratma yo'q) —
seriya/muddat majburiy (400, hech narsa yozilmaydi) va berilsa yangi partiya; oddiy korxonada avvalgi
xatti-harakat (RETURN/sale_refund partiya); ikki korxona izolyatsiyasi; frontend i18n kalitlari.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D1_4.py -q -p no:cacheprovider
"""
import itertools
import json
import pathlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.moliya import KassaSession, Wallet
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleItemBatch
from app.models.user import UserRole
from app.schemas.sale import PartialReturnItem, SaleCreate, SaleItemCreate, SaleReturnRequest
from app.services.sale_create import create_sale
from app.services.sale_partial_return import process_partial_return
from app.services.sale_return import create_return_sale

ROOT = pathlib.Path(__file__).resolve().parents[2]
_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

class _ReturnItemLot(PartialReturnItem):
    """Sxemaga (app/schemas/sale.py) seriya/muddat maydonlari qo'shilgunча servisni tekshirish uchun."""
    lot_number: Optional[str] = None
    expiry_date: Optional[date] = None


class _SaleItemLot(SaleItemCreate):
    lot_number: Optional[str] = None
    expiry_date: Optional[date] = None


def _enable_pharmacy(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _wallet(db, company, branch):
    wl = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"),
                company_id=company.id, branch_id=branch.id, is_active=True, is_open=True)
    db.add(wl)
    db.flush()
    db.add(KassaSession(wallet_id=wl.id, company_id=company.id, status="open"))
    db.flush()
    return wl


@pytest.fixture
def w(db, mk):
    """Korxona A (dorixona yoqilmagan; testda yoqiladi) va korxona B."""
    ca, ba, wha, admin = mk.tenant(UserRole.admin)
    wallet = _wallet(db, ca, ba)
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    _wallet(db, cb, bb)
    return dict(ca=ca, wha=wha, admin=admin, wallet=wallet, cb=cb, whb=whb, admin_b=admin_b)


def _product(db, company, wh, qty):
    n = next(_seq)
    p = Product(name=f"Dori {n}", sku=f"D14-{n}", barcode=f"BD14-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()
    return p


def _batch(db, company, product, wh, qty, lot, expiry):
    b = Batch(product_id=product.id, warehouse_id=wh.id, lot_number=lot, expiry_date=expiry,
              initial_quantity=Decimal(qty), quantity=Decimal(qty), purchase_price=Decimal("500"),
              company_id=company.id)
    db.add(b)
    db.flush()
    return b


def _stock(db, product, wh):
    db.expire_all()
    row = db.query(StockLevel).filter(StockLevel.product_id == product.id,
                                      StockLevel.warehouse_id == wh.id).first()
    return Decimal(str(row.quantity))


def _bq(db, batch):
    db.refresh(batch)
    return Decimal(str(batch.quantity))


def _sell(db, w, product, qty):
    """create_sale orqali sotuv: partiyalar FIFO ajratiladi va SaleItemBatch yoziladi."""
    amount = Decimal(qty) * Decimal("1000")
    return create_sale(db, SaleCreate(
        items=[{"product_id": product.id, "quantity": qty, "unit_price": 1000}],
        payment_type="cash", warehouse_id=w["wha"].id, paid_amount=amount,
        payments=[{"type": "cash", "amount": amount}],
    ), w["admin"])


def _two_batch_setup(db, w, expiry2=None):
    """Bitta dori: B1 (3 ta, 2027-01), B2 (3 ta, 2027-06); 5 ta sotildi -> B1:3, B2:2."""
    p = _product(db, w["ca"], w["wha"], 6)
    b1 = _batch(db, w["ca"], p, w["wha"], 3, "SER-1", datetime(2027, 1, 31))
    b2 = _batch(db, w["ca"], p, w["wha"], 3, "SER-2", expiry2 or datetime(2027, 6, 30))
    sale = _sell(db, w, p, 5)
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()
    sibs = db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id == item.id).order_by(SaleItemBatch.id).all()
    assert [(s.batch_id, s.quantity) for s in sibs] == [(b1.id, Decimal("3")), (b2.id, Decimal("2"))]
    assert _bq(db, b1) == 0 and _bq(db, b2) == 1
    return p, b1, b2, sale, item


def _partial(client, w, sale, item, qty, user=None):
    return client.login(user or w["admin"]).post(f"/api/sales/{sale.id}/return-items", json={
        "items": [{"sale_item_id": item.id, "quantity": qty}], "payment_type": "cash",
    })


def _full(client, w, sale, product, qty, user=None):
    return client.login(user or w["admin"]).post("/api/sales/return", json={
        "items": [{"product_id": product.id, "quantity": qty}], "payment_type": "cash",
        "paid_amount": qty * 1000, "paid_cash": qty * 1000, "warehouse_id": w["wha"].id,
        "original_sale_id": sale.id,
    })


def _batches(db, product):
    return db.query(Batch).filter(Batch.product_id == product.id).order_by(Batch.id).all()


# ── 1. Dorixona: qisman qaytarish ────────────────────────────────────────────

def test_pharmacy_partial_return_goes_to_original_batches_tail_first(db, client, w):
    _enable_pharmacy(db, w["ca"])
    p, b1, b2, sale, item = _two_batch_setup(db, w)

    r = _partial(client, w, sale, item, 3)             # oxirgi ajratilgan B2 dan 2, so'ng B1 dan 1
    assert r.status_code == 200, r.text
    assert _bq(db, b2) == 3 and _bq(db, b1) == 1
    assert _stock(db, p, w["wha"]) == Decimal("4")      # 1 + 3
    assert len(_batches(db, p)) == 2                    # yangi RETURN/sale_refund partiya ochilmadi

    r = _partial(client, w, sale, item, 2)             # B1 dan qolgan 2
    assert r.status_code == 200, r.text
    assert _bq(db, b1) == 3 and _bq(db, b2) == 3
    assert _stock(db, p, w["wha"]) == Decimal("6")
    assert len(_batches(db, p)) == 2
    # seriya va muddat o'zgarmaydi
    assert (b1.lot_number, b1.expiry_date) == ("SER-1", datetime(2027, 1, 31))
    assert (b2.lot_number, b2.expiry_date) == ("SER-2", datetime(2027, 6, 30))

    # qaytarish miqdoridan ortig'i baribir 400
    assert _partial(client, w, sale, item, 1).status_code == 400


def test_pharmacy_partial_return_to_expired_batch_goes_to_that_batch(db, client, w):
    _enable_pharmacy(db, w["ca"])
    p, b1, b2, sale, item = _two_batch_setup(db, w)
    b2.expiry_date = datetime(2020, 1, 1)               # sotuvdan keyin muddati o'tdi
    db.flush()
    r = _partial(client, w, sale, item, 2)
    assert r.status_code == 200, r.text
    assert _bq(db, b2) == 3 and _bq(db, b1) == 0
    assert len(_batches(db, p)) == 2


# ── 2. Dorixona: to'liq qaytarish ────────────────────────────────────────────

def test_pharmacy_full_return_goes_to_original_batches(db, client, w):
    _enable_pharmacy(db, w["ca"])
    p, b1, b2, sale, item = _two_batch_setup(db, w)

    r = _full(client, w, sale, p, 3)
    assert r.status_code == 200, r.text
    assert _bq(db, b2) == 3 and _bq(db, b1) == 1
    assert _stock(db, p, w["wha"]) == Decimal("4")
    assert len(_batches(db, p)) == 2 and not any((b.lot_number or "").startswith("RETURN-") for b in _batches(db, p))

    # keyingi qaytarish (qisman yo'l) ham shu hisobni davom ettiradi
    r = _partial(client, w, sale, item, 2)
    assert r.status_code == 200, r.text
    assert _bq(db, b1) == 3 and _bq(db, b2) == 3
    assert len(_batches(db, p)) == 2


def test_pharmacy_full_return_two_lines_same_product_do_not_double_take(db, client, w):
    _enable_pharmacy(db, w["ca"])
    p, b1, b2, sale, item = _two_batch_setup(db, w)
    r = client.login(w["admin"]).post("/api/sales/return", json={
        "items": [{"product_id": p.id, "quantity": 2}, {"product_id": p.id, "quantity": 2}],
        "payment_type": "cash", "paid_amount": 4000, "paid_cash": 4000,
        "warehouse_id": w["wha"].id, "original_sale_id": sale.id,
    })
    assert r.status_code == 200, r.text
    assert _bq(db, b2) == 3 and _bq(db, b1) == 2       # B2 ga 2, B1 ga 2 (jami 4)
    assert len(_batches(db, p)) == 2


# ── 3. Dorixona: eski sotuv (asl ajratma yo'q) ───────────────────────────────

def _old_sale(db, w):
    """Ajratma yo'q eski sotuv: SaleItemBatch qatorlari o'chiriladi."""
    p = _product(db, w["ca"], w["wha"], 4)
    sale = _sell(db, w, p, 4)
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()
    db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id == item.id).delete()
    db.flush()
    return p, sale, item


def test_pharmacy_old_sale_partial_requires_lot_and_expiry(db, client, w):
    p, sale, item = _old_sale(db, w)
    _enable_pharmacy(db, w["ca"])         # sotuv modul yoqilishidan oldin qilingan (eski sotuv)
    before_batches = len(_batches(db, p))
    before_stock = _stock(db, p, w["wha"])

    r = _partial(client, w, sale, item, 2)
    assert r.status_code == 400, r.text
    assert "lot_number" in r.json()["detail"] and "expiry_date" in r.json()["detail"]
    # hech narsa yozilmadi
    assert _stock(db, p, w["wha"]) == before_stock
    assert len(_batches(db, p)) == before_batches
    assert db.query(Sale).filter(Sale.original_sale_id == sale.id).count() == 0
    db.refresh(item)
    assert (item.returned_quantity or 0) == 0

    # servis darajasida faqat seriya (muddatsiz) — yana 400
    req = SaleReturnRequest(items=[_ReturnItemLot(sale_item_id=item.id, quantity=2, lot_number="X1")],
                            payment_type="cash")
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        process_partial_return(db, sale.id, req, w["admin"])
    assert ei.value.status_code == 400


def test_pharmacy_old_sale_partial_with_lot_creates_batch_with_lot_and_expiry(db, w):
    p, sale, item = _old_sale(db, w)
    _enable_pharmacy(db, w["ca"])         # sotuv modul yoqilishidan oldin qilingan (eski sotuv)
    req = SaleReturnRequest(
        items=[_ReturnItemLot(sale_item_id=item.id, quantity=2, lot_number="OLD-77", expiry_date=date(2028, 3, 31))],
        payment_type="cash",
    )
    process_partial_return(db, sale.id, req, w["admin"])
    new = [b for b in _batches(db, p) if b.lot_number == "OLD-77"]
    assert len(new) == 1
    assert new[0].expiry_date == datetime(2028, 3, 31)
    assert new[0].quantity == Decimal("2") and new[0].initial_quantity == Decimal("2")
    assert new[0].company_id == w["ca"].id and new[0].warehouse_id == w["wha"].id
    assert _stock(db, p, w["wha"]) == Decimal("2")       # 4 sotildi (0 qoldi) + 2 qaytdi
    assert not any((b.lot_number or "").startswith("sale_refund") for b in _batches(db, p))


def test_pharmacy_old_sale_full_return_requires_lot_then_creates_batch(db, client, w):
    p, sale, item = _old_sale(db, w)
    _enable_pharmacy(db, w["ca"])         # sotuv modul yoqilishidan oldin qilingan (eski sotuv)
    r = _full(client, w, sale, p, 2)
    assert r.status_code == 400, r.text
    assert "lot_number" in r.json()["detail"]
    assert len(_batches(db, p)) == 0 or all(not (b.lot_number or "").startswith("RETURN-") for b in _batches(db, p))
    assert db.query(Sale).filter(Sale.original_sale_id == sale.id).count() == 0

    data = SaleCreate(
        items=[_SaleItemLot(product_id=p.id, quantity=2, lot_number="OLD-88", expiry_date=date(2028, 5, 31))],
        payment_type="cash", paid_amount=Decimal("2000"), paid_cash=Decimal("2000"),
        warehouse_id=w["wha"].id, original_sale_id=sale.id,
    )
    create_return_sale(db, data, w["admin"])
    lots = [b.lot_number for b in _batches(db, p)]
    assert "OLD-88" in lots and not any(l.startswith("RETURN-") for l in lots if l)
    nb = [b for b in _batches(db, p) if b.lot_number == "OLD-88"][0]
    assert nb.expiry_date == datetime(2028, 5, 31) and nb.quantity == Decimal("2")


def test_pharmacy_return_without_original_sale_requires_lot(db, client, w):
    _enable_pharmacy(db, w["ca"])
    p = _product(db, w["ca"], w["wha"], 5)
    r = client.login(w["admin"]).post("/api/sales/return", json={
        "items": [{"product_id": p.id, "quantity": 1}], "payment_type": "cash",
        "paid_amount": 1000, "paid_cash": 1000, "warehouse_id": w["wha"].id, "wallet_id": w["wallet"].id,
    })
    assert r.status_code == 400, r.text
    assert "lot_number" in r.json()["detail"]
    assert _stock(db, p, w["wha"]) == Decimal("5")


# ── 4. Oddiy korxona — regressiya ────────────────────────────────────────────

def test_regular_company_partial_return_keeps_old_behavior(db, client, w):
    p, b1, b2, sale, item = _two_batch_setup(db, w)     # modul yoqilmagan
    r = _partial(client, w, sale, item, 3)
    assert r.status_code == 200, r.text
    # asl partiyalarga tegilmaydi, qaytgan tovar uchun yangi partiya ochiladi
    assert _bq(db, b1) == 0 and _bq(db, b2) == 1
    extra = [b for b in _batches(db, p) if b.id not in (b1.id, b2.id)]
    assert len(extra) == 1 and extra[0].quantity == Decimal("3") and extra[0].expiry_date is None
    assert _stock(db, p, w["wha"]) == Decimal("4")


def test_regular_company_full_return_creates_return_batch(db, client, w):
    p, b1, b2, sale, item = _two_batch_setup(db, w)
    r = _full(client, w, sale, p, 3)
    assert r.status_code == 200, r.text
    assert _bq(db, b1) == 0 and _bq(db, b2) == 1
    extra = [b for b in _batches(db, p) if b.id not in (b1.id, b2.id)]
    assert len(extra) == 1 and extra[0].lot_number.startswith("RETURN-") and extra[0].quantity == Decimal("3")


def test_regular_company_old_sale_return_needs_no_lot(db, client, w):
    p, sale, item = _old_sale(db, w)
    assert _partial(client, w, sale, item, 2).status_code == 200
    assert _stock(db, p, w["wha"]) == Decimal("2")
    p2 = _product(db, w["ca"], w["wha"], 3)
    r = client.login(w["admin"]).post("/api/sales/return", json={
        "items": [{"product_id": p2.id, "quantity": 1}], "payment_type": "cash",
        "paid_amount": 1000, "paid_cash": 1000, "warehouse_id": w["wha"].id, "wallet_id": w["wallet"].id,
    })
    assert r.status_code == 200, r.text
    assert _stock(db, p2, w["wha"]) == Decimal("4")


# ── 5. Izolyatsiya ───────────────────────────────────────────────────────────

def test_other_company_cannot_return_into_foreign_batches(db, client, w):
    _enable_pharmacy(db, w["ca"])
    _enable_pharmacy(db, w["cb"])
    p, b1, b2, sale, item = _two_batch_setup(db, w)
    assert _partial(client, w, sale, item, 1, user=w["admin_b"]).status_code == 404
    r = client.login(w["admin_b"]).post("/api/sales/return", json={
        "items": [{"product_id": p.id, "quantity": 1}], "payment_type": "cash",
        "paid_amount": 1000, "paid_cash": 1000, "warehouse_id": w["whb"].id,
        "original_sale_id": sale.id,
    })
    assert r.status_code in (403, 404), r.text
    assert _bq(db, b1) == 0 and _bq(db, b2) == 1        # A partiyalari o'zgarmadi
    # o'z resursi ishlaydi
    assert _partial(client, w, sale, item, 1).status_code == 200
    assert _bq(db, b2) == 2


# ── 6. Frontend ──────────────────────────────────────────────────────────────

def test_frontend_wiring_and_i18n_keys():
    pending = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D1.4.json").read_text(encoding='utf-8'))
    assert set(pending) == {'uz', 'ru', 'en'}
    assert set(pending['uz']) == set(pending['ru']) == set(pending['en']) and pending['uz']
    for fname in ('PosReturn.jsx', 'PartialReturnModal.jsx'):
        src = (ROOT / 'frontend' / 'src' / 'pages' / 'admin' / fname).read_text(encoding='utf-8')
        assert 'lot_number' in src and 'expiry_date' in src and 'useCompanyFeatures' in src
        used = {k for k in pending['uz'] if k in src}
        assert used, f'{fname}: pending kalitlar ishlatilmagan'
