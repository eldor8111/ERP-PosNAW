"""D1.2 — Dorixona rejimi: FEFO va muddati o'tgan dorini sotishni bloklash.

Qamrov (sotuv API orqali): FEFO tartibi (eski FIFO emas), faqat muddati o'tgan partiya qolsa 400 va
StockLevel/partiya/sotuv yozuvlari o'zgarmaydi, `allow_negative` / `pos_allow_negative_stock` chetlab o'tmaydi,
`expiry_block_days`, muddati NULL partiya (yaroqli, FEFO oxirida), xizmat mahsuloti, bir mahsulot ikki qatorda,
sotuv tahriri va kutilayotgan sotuvni tasdiqlash, `pharmacy_context` sotuvga bir marta, oddiy korxona regressiyasi
(muddati o'tgan partiya avvalgidek sotiladi) va ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D1_2.py -q -p no:cacheprovider
"""
import itertools
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.category import Category
from app.models.inventory import StockLevel, StockMovement
from app.models.moliya import Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleItemBatch, SaleStatus
from app.models.user import UserWallet
from app.schemas.sale import SaleUpdate
from app.services.batch_allocator import (
    allocate_batches, assert_pharmacy_sellable, expiry_cutoff, tashkent_today,
)
from app.services.sale_update import update_sale

_n = itertools.count(1)


def _dt(days):
    """Bugundan `days` kun keyingi sana (00:00); None — muddatsiz."""
    if days is None:
        return None
    return datetime.combine(tashkent_today() + timedelta(days=days), time.min)


def _enable(db, c, **settings):
    c.pharmacy_enabled = True
    if settings:
        c.pharmacy_settings = settings
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _wallet(db, c, b, user):
    w = Wallet(name=f"Kassa {next(_n)}", type="cash", balance=D(0), company_id=c.id, branch_id=b.id,
               is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(UserWallet(user_id=user.id, wallet_id=w.id, is_default=True, company_id=c.id))
    db.flush()
    return w


def _product(db, c, **kw):
    n = next(_n)
    p = Product(name=kw.pop("name", f"Dori D12-{n}"), sku=f"D12-{n}", barcode=f"BD12-{n:06d}", company_id=c.id,
                cost_price=D("500"), sale_price=D("1000"), **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, p, wh, qty):
    sl = StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty))
    db.add(sl)
    db.flush()
    return sl


def _batch(db, p, wh, qty, expiry_days, age_days=0, price=100):
    b = Batch(product_id=p.id, warehouse_id=wh.id if wh else None, quantity=D(qty), initial_quantity=D(qty),
              purchase_price=D(price), company_id=p.company_id, expiry_date=_dt(expiry_days),
              created_at=datetime.utcnow() - timedelta(days=age_days))
    db.add(b)
    db.flush()
    return b


def _body(lines, wh, **extra):
    """lines: [(product, qty), ...]"""
    total = sum(1000 * q for _, q in lines)
    body = {"items": [{"product_id": p.id, "quantity": q, "unit_price": 1000} for p, q in lines],
            "payment_type": "cash", "paid_amount": total, "paid_cash": total,
            "payments": [{"type": "cash", "amount": total}], "warehouse_id": wh.id}
    body.update(extra)
    return body


def _bq(db, b):
    db.refresh(b)
    return D(str(b.quantity))


def _sq(db, sl):
    db.refresh(sl)
    return D(str(sl.quantity))


@pytest.fixture
def ph(db, mk):
    """Dorixona yoqilgan korxona A (kassa bilan) va oddiy korxona B."""
    c, b, wh, admin = mk.tenant()
    _wallet(db, c, b, admin)
    _enable(db, c)
    p = _product(db, c)
    sl = _stock(db, p, wh, 100)
    c2, b2, wh2, admin2 = mk.tenant()
    _wallet(db, c2, b2, admin2)
    return dict(c=c, b=b, wh=wh, admin=admin, p=p, sl=sl, c2=c2, wh2=wh2, admin2=admin2)


def _no_sale_written(db, c, sl, before_qty):
    assert db.query(Sale).filter(Sale.company_id == c.id).count() == 0
    assert _sq(db, sl) == before_qty
    assert db.query(StockMovement).filter(StockMovement.product_id == sl.product_id).count() == 0


# ───────────────────────── FEFO ─────────────────────────

def test_pharmacy_sale_takes_earliest_expiry_first_not_fifo(client, db, ph):
    """Qabul: ikki partiya — avval muddati yaqini yechiladi (kirim tartibi emas)."""
    p, wh = ph["p"], ph["wh"]
    far = _batch(db, p, wh, 10, 120, age_days=20)      # avval kirgan, lekin muddati uzoq (2027-01)
    near = _batch(db, p, wh, 10, 60, age_days=1)       # keyin kirgan, muddati yaqin (2026-12)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 4)], wh))
    assert r.status_code == 200, r.text
    assert _bq(db, near) == 6 and _bq(db, far) == 10
    item = db.query(SaleItem).filter_by(sale_id=r.json()["id"]).one()
    sib = db.query(SaleItemBatch).filter_by(sale_item_id=item.id).all()
    assert [(s.batch_id, D(str(s.quantity))) for s in sib] == [(near.id, D(4))]     # qaysi seriya/muddat sotilgani
    assert _sq(db, ph["sl"]) == 96


def test_pharmacy_sale_spills_to_next_batch_in_fefo_order(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    far = _batch(db, p, wh, 10, 120, age_days=20)
    near = _batch(db, p, wh, 3, 60, age_days=1)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 5)], wh))
    assert r.status_code == 200, r.text
    assert _bq(db, near) == 0 and _bq(db, far) == 8


def test_pharmacy_null_expiry_batch_is_valid_and_last(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    legacy = _batch(db, p, wh, 10, None, age_days=50)        # eski "seriya noma'lum"
    dated = _batch(db, p, wh, 3, 200, age_days=1)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 5)], wh))
    assert r.status_code == 200, r.text
    assert _bq(db, dated) == 0 and _bq(db, legacy) == 8      # avval muddatlisi, so'ng NULL
    # faqat NULL muddatli partiya ham sotiladi
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 8)], wh))
    assert r.status_code == 200, r.text
    assert _bq(db, legacy) == 0


# ───────────────────────── bloklash ─────────────────────────

def test_pharmacy_only_expired_batch_blocks_sale_and_changes_nothing(client, db, ph):
    """Qabul: faqat muddati o'tgan partiya qolgan dori sotilmaydi, StockLevel o'zgarmaydi."""
    p, wh = ph["p"], ph["wh"]
    expired = _batch(db, p, wh, 100, -3)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], wh))
    assert r.status_code == 400
    assert r.json()["detail"] == f"{p.name}: yaroqli qoldiq 0, muddati o'tgan yoki yaroqsiz 100"
    _no_sale_written(db, ph["c"], ph["sl"], D(100))
    assert _bq(db, expired) == 100
    assert db.query(SaleItemBatch).count() == 0


def test_pharmacy_message_shows_valid_and_invalid_amounts(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    _batch(db, p, wh, 5, -1)
    _batch(db, p, wh, 2, 30)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 3)], wh))
    assert r.status_code == 400
    assert r.json()["detail"] == f"{p.name}: yaroqli qoldiq 2, muddati o'tgan yoki yaroqsiz 5"
    # yaroqli miqdorning o'zi sotiladi, muddati o'tgani tegilmaydi
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 2)], wh))
    assert r.status_code == 200, r.text
    assert D(str(db.query(Batch).filter(Batch.product_id == p.id, Batch.expiry_date < _dt(0)).one().quantity)) == 5


@pytest.mark.parametrize("allow_negative", [True, False])
def test_pharmacy_block_ignores_allow_negative_settings(client, db, ph, allow_negative):
    """`pos_allow_negative_stock` yoqiq bo'lsa ham muddati o'tgan dori sotilmaydi."""
    p, wh = ph["p"], ph["wh"]
    ph["c"].pos_allow_negative_stock = allow_negative
    db.flush()
    _batch(db, p, wh, 100, -10)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], wh))
    assert r.status_code == 400
    _no_sale_written(db, ph["c"], ph["sl"], D(100))


def test_pharmacy_no_batches_at_all_is_blocked(client, db, ph):
    """Yaroqli partiya yo'q (partiyasiz qoldiq) — TZ bo'yicha sotuv rad etiladi."""
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(ph["p"], 1)], ph["wh"]))
    assert r.status_code == 400
    assert "yaroqli qoldiq 0" in r.json()["detail"]
    _no_sale_written(db, ph["c"], ph["sl"], D(100))


def test_pharmacy_same_product_in_two_lines_is_summed(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    _batch(db, p, wh, 3, 30)
    body = _body([(p, 2), (p, 2)], wh)
    r = client.login(ph["admin"]).post("/api/sales/", json=body)
    assert r.status_code == 400
    assert "yaroqli qoldiq 3" in r.json()["detail"]
    _no_sale_written(db, ph["c"], ph["sl"], D(100))
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 2), (p, 1)], wh))
    assert r.status_code == 200, r.text


def test_pharmacy_second_line_blocked_changes_nothing_for_first(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    good = _batch(db, p, wh, 10, 30)
    p2 = _product(db, ph["c"])
    sl2 = _stock(db, p2, wh, 10)
    _batch(db, p2, wh, 10, -5)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 2), (p2, 1)], wh))
    assert r.status_code == 400 and p2.name in r.json()["detail"]
    assert _bq(db, good) == 10 and _sq(db, ph["sl"]) == 100 and _sq(db, sl2) == 10
    assert db.query(Sale).filter(Sale.company_id == ph["c"].id).count() == 0


def test_pharmacy_service_product_is_not_blocked(client, db, ph):
    svc = _product(db, ph["c"], product_type="service")
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(svc, 1)], ph["wh"]))
    assert r.status_code == 200, r.text


# ───────────────────────── expiry_block_days ─────────────────────────

def test_pharmacy_expiry_block_days_treats_near_expiry_as_invalid(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    ph["c"].pharmacy_settings = {"expiry_block_days": 10}
    db.flush()
    near = _batch(db, p, wh, 5, 10)         # 10 kun qoldi -> yaroqsiz
    ok = _batch(db, p, wh, 5, 11)           # 11 kun qoldi -> yaroqli
    cl = client.login(ph["admin"])
    r = cl.post("/api/sales/", json=_body([(p, 6)], wh))
    assert r.status_code == 400
    assert r.json()["detail"] == f"{p.name}: yaroqli qoldiq 5, muddati o'tgan yoki yaroqsiz 5"
    r = cl.post("/api/sales/", json=_body([(p, 5)], wh))
    assert r.status_code == 200, r.text
    assert _bq(db, near) == 5 and _bq(db, ok) == 0


def test_expiry_cutoff_rules():
    t = tashkent_today()
    assert expiry_cutoff(t, 0) == datetime.combine(t, time.min)                       # bugun tugasa hali yaroqli
    assert expiry_cutoff(t, 7) == datetime.combine(t + timedelta(days=8), time.min)   # 7 kun va kam -> yaroqsiz


# ───────────────────────── allocator / pharmacy_context ─────────────────────────

def test_allocator_pharmacy_flag_applies_fefo_and_drops_expired_but_default_does_not(db, ph):
    p, wh, c = ph["p"], ph["wh"], ph["c"]
    expired = _batch(db, p, wh, 5, -2, age_days=30)
    ok = _batch(db, p, wh, 5, 40, age_days=1)
    off, short = allocate_batches(db, company_id=c.id, product_id=p.id, variant_id=None, warehouse_id=wh.id,
                                  quantity=7, deduct=False)
    assert [a["batch_id"] for a in off] == [expired.id, ok.id] and short == 0     # oddiy qoida: FIFO
    on, short = allocate_batches(db, company_id=c.id, product_id=p.id, variant_id=None, warehouse_id=wh.id,
                                 quantity=7, deduct=False, pharmacy=True)
    assert [a["batch_id"] for a in on] == [ok.id] and short == 2                  # muddati o'tgani chetlatildi


def test_assert_pharmacy_sellable_noop_when_module_off(db, ph):
    p, wh = ph["p"], ph["wh"]
    _batch(db, p, wh, 5, -2)
    assert_pharmacy_sellable(db, company_id=ph["c"].id, lines=[(p, None, wh.id, 5)], pharmacy_ctx=(False, {}))


def test_pharmacy_context_called_once_per_sale(client, db, ph, monkeypatch):
    import app.services.sale_create as sc
    import app.services.pharmacy as pharmacy_mod
    p, wh = ph["p"], ph["wh"]
    p2 = _product(db, ph["c"])
    p3 = _product(db, ph["c"])
    for x in (p, p2, p3):
        _batch(db, x, wh, 10, 30)
    _stock(db, p2, wh, 10)
    _stock(db, p3, wh, 10)
    calls = []
    real = pharmacy_mod.pharmacy_context

    def counting(db_, company_id):
        calls.append(company_id)
        return real(db_, company_id)

    monkeypatch.setattr(sc, "pharmacy_context", counting)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1), (p2, 1), (p3, 1)], wh))
    assert r.status_code == 200, r.text
    assert calls == [ph["c"].id]


# ───────────────────────── tahrir va tasdiqlash ─────────────────────────

def test_update_sale_blocks_over_valid_and_keeps_old_sale(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    b = _batch(db, p, wh, 10, 30)
    cl = client.login(ph["admin"])
    r = cl.post("/api/sales/", json=_body([(p, 3)], wh))
    assert r.status_code == 200, r.text
    sale_id = r.json()["id"]
    assert _bq(db, b) == 7 and _sq(db, ph["sl"]) == 97
    # muddati o'tib ketgan partiya qo'shiladi (yaroqsiz) — tahrirda 11 dona yaroqli 10 dan ko'p
    _batch(db, p, wh, 50, -1)
    r = cl.put(f"/api/sales/{sale_id}", json={
        "items": [{"product_id": p.id, "quantity": 11, "unit_price": 1000, "warehouse_id": wh.id}],
        "paid_amount": 11000})
    assert r.status_code == 400, r.text
    assert "yaroqli qoldiq 10" in r.json()["detail"]
    # eski sotuv o'z holicha (teskari ta'sirlar yozilmagan)
    assert _bq(db, b) == 7 and _sq(db, ph["sl"]) == 97
    assert D(str(db.query(SaleItem).filter_by(sale_id=sale_id).one().quantity)) == 3
    # eski sotuv partiyasiga qaytadigan miqdor hisobga olinadi: 10 ta (7 + 3) tahrirda ruxsat
    r = cl.put(f"/api/sales/{sale_id}", json={
        "items": [{"product_id": p.id, "quantity": 10, "unit_price": 1000, "warehouse_id": wh.id}],
        "paid_amount": 10000})
    assert r.status_code == 200, r.text
    assert _bq(db, b) == 0


def test_confirm_pending_sale_blocks_expired(db, ph):
    p, wh, c, admin = ph["p"], ph["wh"], ph["c"], ph["admin"]
    expired = _batch(db, p, wh, 100, -4)
    sale = Sale(number=f"D12-P{next(_n)}", cashier_id=admin.id, company_id=c.id, warehouse_id=wh.id,
                branch_id=ph["b"].id, total_amount=D(1000), paid_amount=D(0), payment_type=PaymentType.cash,
                status=SaleStatus.pending)
    db.add(sale)
    db.flush()
    db.add(SaleItem(sale_id=sale.id, product_id=p.id, warehouse_id=wh.id, unit="dona", quantity=D(1),
                    unit_price=D(1000), cost_price=D(0), discount=D(0), subtotal=D(1000)))
    db.flush()
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        update_sale(db, sale.id, SaleUpdate(status=SaleStatus.completed, paid_amount=D(1000)), admin)
    assert e.value.status_code == 400 and "yaroqli qoldiq 0" in e.value.detail
    db.refresh(sale)
    assert sale.status == SaleStatus.pending
    assert _bq(db, expired) == 100 and _sq(db, ph["sl"]) == 100
    # yaroqli partiya qo'shilsa tasdiqlanadi va FEFO bilan yechiladi
    ok = _batch(db, p, wh, 5, 90)
    update_sale(db, sale.id, SaleUpdate(status=SaleStatus.completed, paid_amount=D(1000)), admin)
    assert _bq(db, ok) == 4 and _bq(db, expired) == 100


# ───────────────────────── oddiy korxona (regressiya) ─────────────────────────

def test_regular_company_still_sells_expired_batch_as_before(client, db, ph):
    c2, wh2, admin2 = ph["c2"], ph["wh2"], ph["admin2"]
    p = _product(db, c2)
    sl = _stock(db, p, wh2, 10)
    old = _batch(db, p, wh2, 10, -30, age_days=40)          # muddati o'tgan, lekin kategoriya perishable emas
    r = client.login(admin2).post("/api/sales/", json=_body([(p, 4)], wh2))
    assert r.status_code == 200, r.text
    assert _bq(db, old) == 6 and _sq(db, sl) == 6


def test_regular_company_stockless_batches_and_fifo_unchanged(client, db, ph):
    c2, wh2, admin2 = ph["c2"], ph["wh2"], ph["admin2"]
    p = _product(db, c2)
    sl = _stock(db, p, wh2, 10)
    first = _batch(db, p, wh2, 3, 200, age_days=30)          # FIFO: avval kirgan, muddati uzoq
    second = _batch(db, p, wh2, 7, 10, age_days=1)
    r = client.login(admin2).post("/api/sales/", json=_body([(p, 4)], wh2))
    assert r.status_code == 200, r.text
    assert _bq(db, first) == 0 and _bq(db, second) == 6


def test_regular_company_without_any_batches_sells_as_before(client, db, ph):
    c2, wh2, admin2 = ph["c2"], ph["wh2"], ph["admin2"]
    p = _product(db, c2)
    sl = _stock(db, p, wh2, 10)
    r = client.login(admin2).post("/api/sales/", json=_body([(p, 2)], wh2))
    assert r.status_code == 200, r.text
    assert _sq(db, sl) == 8


def test_regular_company_perishable_category_rule_unchanged(client, db, ph):
    """Perishable kategoriya qoidasi: muddati o'tgan chetlatiladi, yetmagan qism 400 BERMAYDI (avvalgidek)."""
    c2, wh2, admin2 = ph["c2"], ph["wh2"], ph["admin2"]
    cat = Category(name="Sut", company_id=c2.id, is_perishable=True)
    db.add(cat)
    db.flush()
    p = _product(db, c2, category_id=cat.id)
    sl = _stock(db, p, wh2, 10)
    expired = _batch(db, p, wh2, 5, -2, age_days=9)
    soon = _batch(db, p, wh2, 5, 3, age_days=1)
    r = client.login(admin2).post("/api/sales/", json=_body([(p, 7)], wh2))
    assert r.status_code == 200, r.text
    assert _bq(db, expired) == 5 and _bq(db, soon) == 0


def test_module_off_package_expired_behaves_as_regular(client, db, mk):
    """Bayroq yoqilgan, lekin paketi tugagan korxona — oddiy do'kon sifatida sotadi."""
    c, b, wh, admin = mk.tenant()
    _wallet(db, c, b, admin)
    c.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=now - timedelta(days=40), ends_at=now - timedelta(days=10)))
    db.flush()
    p = _product(db, c)
    _stock(db, p, wh, 5)
    _batch(db, p, wh, 5, -3)
    r = client.login(admin).post("/api/sales/", json=_body([(p, 1)], wh))
    assert r.status_code == 200, r.text


# ───────────────────────── ikki korxona izolyatsiyasi ─────────────────────────

def test_other_company_cannot_sell_pharmacy_product_and_batches_untouched(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    b = _batch(db, p, wh, 10, 30)
    r = client.login(ph["admin2"]).post("/api/sales/", json=_body([(p, 1)], ph["wh2"]))
    assert r.status_code in (403, 404), r.text
    assert _bq(db, b) == 10 and _sq(db, ph["sl"]) == 100


def test_other_company_valid_batches_do_not_count_for_pharmacy(client, db, ph):
    """Boshqa korxona partiyasi (shu mahsulot id si bilan ham) yaroqli qoldiqqa qo'shilmaydi."""
    p, wh = ph["p"], ph["wh"]
    _batch(db, p, wh, 100, -5)                              # A: faqat muddati o'tgan
    foreign = Batch(product_id=p.id, warehouse_id=wh.id, quantity=D(100), initial_quantity=D(100),
                    purchase_price=D(1), company_id=ph["c2"].id, expiry_date=_dt(90))
    db.add(foreign)
    db.flush()
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], wh))
    assert r.status_code == 400
    assert "yaroqli qoldiq 0" in r.json()["detail"]
    assert _bq(db, foreign) == 100


def test_own_resource_positive_path(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    _batch(db, p, wh, 10, 30)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 2)], wh))
    assert r.status_code == 200, r.text
