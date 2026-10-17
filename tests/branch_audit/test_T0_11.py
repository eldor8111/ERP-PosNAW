"""T0.11 — Mijozdan qaytarish (return-from-customer) xavfsizligi va to'g'riligi.

Ikki korxona (A, B): har birida filial, ombor, kassa, mijoz, mahsulot, variant.
A foydalanuvchisi B resurslarini yuborganda 404 va B ma'lumotlari o'zgarmasligi,
o'z resurslari bilan esa qoldiq (variant bo'yicha), partiya, tranzaksiya, kassa
harakati va qarz to'g'ri yozilishi, bekor qilishda to'liq teskari bo'lishi tekshiriladi.
"""
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.customer import Customer
from app.models.inventory import StockLevel, StockMovement, MovementType
from app.models.moliya import KassaMovement, KassaSession, Transaction, Wallet
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.user import UserRole

URL = "/api/inventory/return-from-customer"


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, balance=100000, is_open=True, is_active=True, name=None):
    w = Wallet(name=name or f"Kassa {company.id}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id if branch else None,
               is_active=is_active, is_open=is_open)
    db.add(w)
    db.flush()
    return w


def _customer(db, company, debt=5000):
    c = Customer(name=f"Mijoz {company.id}", company_id=company.id,
                 debt_balance=Decimal(debt), debt_balances={"UZS": float(debt)})
    db.add(c)
    db.flush()
    return c


def _product(db, company, name="Tovar", ptype="simple", cost="700"):
    p = Product(sku=f"SKU{company.id}-{name}", barcode=f"BC{company.id}-{name}", name=name,
                company_id=company.id, cost_price=Decimal(cost), sale_price=Decimal("1000"),
                product_type=ptype)
    db.add(p)
    db.flush()
    return p


def _variant(db, product, name="L"):
    v = ProductVariant(product_id=product.id, name=name)
    db.add(v)
    db.flush()
    return v


def _stock(db, product, wh, qty, variant=None):
    s = StockLevel(product_id=product.id, warehouse_id=wh.id,
                   variant_id=variant.id if variant else None, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


def _stock_qty(db, product, wh, variant=None):
    q = db.query(StockLevel).filter(StockLevel.product_id == product.id, StockLevel.warehouse_id == wh.id)
    q = q.filter(StockLevel.variant_id == variant.id) if variant else q.filter(StockLevel.variant_id.is_(None))
    s = q.first()
    return Decimal(str(s.quantity)) if s else None


def _bal(db, wallet):
    db.refresh(wallet)
    return Decimal(str(wallet.balance))


def _debt(db, customer):
    db.refresh(customer)
    return Decimal(str(customer.debt_balance)), Decimal(str((customer.debt_balances or {}).get("UZS", 0)))


def _payload(t, **kw):
    p = dict(customer_id=t['cust_a'].id, warehouse_id=t['wha'].id, payment_type="debt",
             items=[{"product_id": t['pa'].id, "quantity": 2, "unit_price": 1000}])
    p.update(kw)
    return p


@pytest.fixture
def t(db, mk):
    """A va B korxonalar: filial, ombor, kassa (ochiq sessiya bilan), mijoz, mahsulot, variant, xodimlar."""
    ca, ba, wha, ua = mk.tenant()            # ua — admin (filial ba)
    cb, bb, whb, ub = mk.tenant()
    ba2 = mk.branch(ca)                      # A ning ikkinchi filiali
    wha2 = mk.warehouse(ca, ba2)
    uw = mk.user(ca, role=UserRole.warehouse, branch=ba)   # filialli omborchi
    ua_nobranch = mk.user(ca, role=UserRole.admin)          # filialsiz admin
    wa = _wallet(db, ca, ba)
    wb = _wallet(db, cb, bb)
    ks = KassaSession(wallet_id=wa.id, company_id=ca.id, status="open")
    db.add(ks)
    db.flush()
    cust_a = _customer(db, ca)
    cust_b = _customer(db, cb)
    pa = _product(db, ca, "A-tovar")
    pa2 = _product(db, ca, "A-tovar-2")
    va = _variant(db, pa)
    pb = _product(db, cb, "B-tovar")
    vb = _variant(db, pb)
    return dict(ca=ca, ba=ba, wha=wha, ua=ua, ba2=ba2, wha2=wha2, uw=uw, ua_nobranch=ua_nobranch,
                wa=wa, ks=ks, cust_a=cust_a, pa=pa, pa2=pa2, va=va,
                cb=cb, bb=bb, whb=whb, ub=ub, wb=wb, cust_b=cust_b, pb=pb, vb=vb)


def _snapshot_b(db, t):
    return (_debt(db, t['cust_b']), _bal(db, t['wb']),
            db.query(StockLevel).filter(StockLevel.warehouse_id == t['whb'].id).count(),
            db.query(StockLevel).join(Product).filter(Product.company_id == t['cb'].id).count())


# ─── 1. Begona korxona resurslari → 404, B ma'lumotlari o'zgarmaydi ─────────

@pytest.mark.parametrize("field,key,extra", [
    ("customer_id", "cust_b", {}),
    ("warehouse_id", "whb", {}),
    ("product_id", "pb", {}),
    ("wallet_id", "wb", {"payment_type": "cash"}),
])
def test_foreign_resource_404(client, db, t, field, key, extra):
    before = _snapshot_b(db, t)
    payload = _payload(t, **extra)
    if field == "product_id":
        payload["items"][0]["product_id"] = t[key].id
    else:
        payload[field] = t[key].id
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 404, r.text
    assert _snapshot_b(db, t) == before
    assert db.query(StockMovement).filter(StockMovement.reference_type == "return_from_customer").count() == 0
    assert db.query(Transaction).count() == 0


# ─── 2. Filial: boshqa filial ombori 403, admin istalgan ombor ──────────────

def test_other_branch_warehouse_403_for_warehouse_role(client, db, t):
    r = client.login(t['uw']).post(URL, json=_payload(t, warehouse_id=t['wha2'].id))
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "Bu ombor sizning filialingizga tegishli emas"
    assert _stock_qty(db, t['pa'], t['wha2']) is None


def test_admin_any_warehouse_ok_and_branch_from_warehouse(client, db, t):
    # ua — ba filialidagi admin, ombor ba2 filialida → tx.branch_id = ba2
    # (naqd: sof qarzga qaytarishda T0.29 bo'yicha Transaction yozilmaydi)
    r = client.login(t['ua']).post(
        URL, json=_payload(t, warehouse_id=t['wha2'].id, payment_type="cash", wallet_id=t['wa'].id))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["branch_id"] == t['ba2'].id
    txs = db.query(Transaction).filter(Transaction.reference_type == "return_from_customer").all()
    assert len(txs) == 1 and txs[0].branch_id == t['ba2'].id
    assert txs[0].company_id == t['ca'].id and txs[0].user_id == t['ua'].id


def test_branchless_admin_no_500(client, db, t):
    r = client.login(t['ua_nobranch']).post(URL, json=_payload(t))
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] == t['ba'].id


# ─── 3. Variant ─────────────────────────────────────────────────────────────

def test_variant_of_other_product_400(client, db, t):
    payload = _payload(t)
    payload["items"][0]["variant_id"] = t['vb'].id   # B mahsulotining varianti
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 400, r.text
    assert _stock_qty(db, t['pa'], t['wha']) is None


def test_variant_stock_row_and_movement(client, db, t):
    _stock(db, t['pa'], t['wha'], 10)                    # variantsiz qator — o'zgarmasligi kerak
    payload = _payload(t)
    payload["items"][0]["variant_id"] = t['va'].id
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 200, r.text
    assert _stock_qty(db, t['pa'], t['wha'], t['va']) == Decimal("2")
    assert _stock_qty(db, t['pa'], t['wha']) == Decimal("10")
    mov = db.get(StockMovement, r.json()["movement_ids"][0])
    assert mov.variant_id == t['va'].id and mov.warehouse_id == t['wha'].id
    assert mov.type == MovementType.IN and mov.reference_id == t['cust_a'].id


# ─── 4. Partiya ─────────────────────────────────────────────────────────────

def test_batch_created_per_movement(client, db, t):
    payload = _payload(t)
    payload["items"][0]["variant_id"] = t['va'].id
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 200, r.text
    mid = r.json()["movement_ids"][0]
    b = db.query(Batch).filter(Batch.lot_number == f"RETURN-C{mid}").one()
    assert b.warehouse_id == t['wha'].id and b.variant_id == t['va'].id
    assert Decimal(str(b.quantity)) == Decimal("2") and Decimal(str(b.initial_quantity)) == Decimal("2")
    assert Decimal(str(b.purchase_price)) == Decimal("700") and b.company_id == t['ca'].id


# ─── 5-6. Kassa: KassaMovement, balans, yetmasa 400, kassa topilmasa 400 ────

def test_cash_return_writes_kassa_movement(client, db, t):
    r = client.login(t['uw']).post(URL, json=_payload(t, payment_type="cash", wallet_id=t['wa'].id))
    assert r.status_code == 200, r.text
    assert r.json()["wallet_id"] == t['wa'].id
    assert _bal(db, t['wa']) == Decimal("98000")
    kms = db.query(KassaMovement).filter(KassaMovement.reference_type == "return_from_customer").all()
    assert len(kms) == 1
    km = kms[0]
    assert km.direction == "out" and km.payment_type == "cash" and Decimal(str(km.amount)) == Decimal("2000")
    assert km.wallet_id == t['wa'].id and km.session_id == t['ks'].id and km.company_id == t['ca'].id
    # qarz o'zgarmaydi
    assert _debt(db, t['cust_a']) == (Decimal("5000"), Decimal("5000"))
    tx = db.query(Transaction).one()
    assert tx.wallet_id == t['wa'].id and tx.payment_type == "cash" and tx.meta["paid_cash"] == 2000.0


def test_card_return_default_wallet(client, db, t):
    # wallet_id berilmasa — korxonaning birinchi ochiq kassasi
    r = client.login(t['uw']).post(URL, json=_payload(t, payment_type="card", customer_id=None))
    assert r.status_code == 200, r.text
    assert r.json()["wallet_id"] == t['wa'].id
    assert _bal(db, t['wa']) == Decimal("98000")
    km = db.query(KassaMovement).one()
    assert km.payment_type == "card" and km.direction == "out"


def test_cash_insufficient_balance_400_rollback(client, db, t):
    t['wa'].balance = Decimal("500")
    db.flush()
    r = client.login(t['uw']).post(URL, json=_payload(t, payment_type="cash", wallet_id=t['wa'].id))
    assert r.status_code == 400, r.text
    assert "mablag" in r.json()["detail"]
    assert _stock_qty(db, t['pa'], t['wha']) is None
    assert _bal(db, t['wa']) == Decimal("500")
    assert db.query(KassaMovement).count() == 0 and db.query(Batch).count() == 0


def test_cash_no_wallet_400(client, db, t):
    t['wa'].is_open = False
    db.flush()
    r = client.login(t['uw']).post(URL, json=_payload(t, payment_type="cash"))
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Kassa tanlang"
    assert _stock_qty(db, t['pa'], t['wha']) is None
    # yopiq kassa aniq berilsa ham 400
    r = client.login(t['uw']).post(URL, json=_payload(t, payment_type="cash", wallet_id=t['wa'].id))
    assert r.status_code == 400 and r.json()["detail"] == "Kassa yopiq"


# ─── 8. Qarz ────────────────────────────────────────────────────────────────

def test_debt_return_reduces_both_balances(client, db, t):
    r = client.login(t['uw']).post(URL, json=_payload(t))
    assert r.status_code == 200, r.text
    assert _debt(db, t['cust_a']) == (Decimal("3000"), Decimal("3000"))
    # Sof qarzga qaytarish: kassadan pul chiqmaydi — Transaction ham, KassaMovement ham yo'q (T0.29)
    assert db.query(Transaction).count() == 0
    assert db.query(KassaMovement).count() == 0
    mov = db.query(StockMovement).filter(StockMovement.reference_type == "return_from_customer").one()
    assert "payment:debt" in (mov.reason or "")


def test_debt_less_than_amount_400(client, db, t):
    payload = _payload(t)
    payload["items"][0]["quantity"] = 6     # 6000 > 5000
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Mijoz qarzi qaytarish summasidan kam"
    assert _debt(db, t['cust_a']) == (Decimal("5000"), Decimal("5000"))
    assert _stock_qty(db, t['pa'], t['wha']) is None


def test_debt_without_customer_400(client, db, t):
    r = client.login(t['uw']).post(URL, json=_payload(t, customer_id=None))
    assert r.status_code == 400 and "mijoz" in r.json()["detail"].lower()


def test_mixed_remainder_from_debt(client, db, t):
    payload = _payload(t, payment_type="mixed", wallet_id=t['wa'].id, paid_cash=500, paid_card=300)
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 200, r.text
    assert _bal(db, t['wa']) == Decimal("99200")
    assert _debt(db, t['cust_a']) == (Decimal("3800"), Decimal("3800"))
    kms = {k.payment_type: Decimal(str(k.amount)) for k in db.query(KassaMovement).all()}
    assert kms == {"cash": Decimal("500"), "card": Decimal("300")}
    tx = db.query(Transaction).one()
    assert tx.meta == {"customer_id": t['cust_a'].id, "debt_reduced_uzs": 1200.0, "paid_cash": 500.0, "paid_card": 300.0}


def test_mixed_remainder_without_customer_400(client, db, t):
    payload = _payload(t, payment_type="mixed", wallet_id=t['wa'].id, paid_cash=500, customer_id=None)
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 400, r.text
    assert _bal(db, t['wa']) == Decimal("100000")


def test_paid_more_than_total_400(client, db, t):
    payload = _payload(t, payment_type="mixed", wallet_id=t['wa'].id, paid_cash=5000)
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 400


# ─── 9. Bir mahsulot ikki narx bilan ────────────────────────────────────────

def test_same_product_two_prices_amounts(client, db, t):
    # Aralash: 1000 naqd, qolgan 3000 qarzdan (sof qarzda Transaction yozilmaydi — T0.29)
    payload = _payload(t, payment_type="mixed", wallet_id=t['wa'].id, paid_cash=1000, items=[
        {"product_id": t['pa'].id, "quantity": 1, "unit_price": 1000},
        {"product_id": t['pa'].id, "quantity": 2, "unit_price": 1500, "variant_id": t['va'].id},
    ])
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 200, r.text
    ids = r.json()["movement_ids"]
    amounts = {tx.reference_id: Decimal(str(tx.amount)) for tx in db.query(Transaction).all()}
    assert amounts == {ids[0]: Decimal("1000"), ids[1]: Decimal("3000")}
    assert _debt(db, t['cust_a']) == (Decimal("2000"), Decimal("2000"))
    assert _bal(db, t['wa']) == Decimal("99000")


# ─── Sxema ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {"items": []},
    {"payment_type": "bonus"},
    {"items": [{"product_id": 1, "quantity": 0, "unit_price": 100}]},
    {"items": [{"product_id": 1, "quantity": 1, "unit_price": -1}]},
])
def test_schema_rejects(client, db, t, bad):
    r = client.login(t['uw']).post(URL, json=_payload(t, **bad))
    assert r.status_code == 422, r.text


def test_virtual_product_400(client, db, t):
    pv = _product(db, t['ca'], "Virtual", ptype="sell")
    payload = _payload(t)
    payload["items"][0]["product_id"] = pv.id
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 400


# ─── 10. Bekor qilish ───────────────────────────────────────────────────────

def _do_cash_return(client, db, t, variant=True):
    payload = _payload(t, payment_type="cash", wallet_id=t['wa'].id)
    if variant:
        payload["items"][0]["variant_id"] = t['va'].id
    r = client.login(t['uw']).post(URL, json=payload)
    assert r.status_code == 200, r.text
    return r.json()["movement_ids"][0]


def test_delete_cash_return_full_revert(client, db, t):
    mid = _do_cash_return(client, db, t)
    assert _bal(db, t['wa']) == Decimal("98000")
    r = client.login(t['uw']).delete(f"/api/inventory/movements/{mid}")
    assert r.status_code == 200, r.text
    assert _stock_qty(db, t['pa'], t['wha'], t['va']) == Decimal("0")
    b = db.query(Batch).filter(Batch.lot_number == f"RETURN-C{mid}").one()
    assert Decimal(str(b.quantity)) == Decimal("0")
    assert _bal(db, t['wa']) == Decimal("100000")
    assert db.query(Transaction).count() == 0
    # T1.19: asl harakat o'chirilmaydi — "[bekor qilingan]" deb belgilanadi
    assert "[bekor qilingan]" in (db.get(StockMovement, mid).reason or "")
    rev = db.query(StockMovement).filter(StockMovement.reference_type == "return_revert").one()
    assert rev.variant_id == t['va'].id and rev.warehouse_id == t['wha'].id and rev.type == MovementType.OUT
    kms = db.query(KassaMovement).filter(KassaMovement.reference_type == "return_from_customer_revert").all()
    assert len(kms) == 1 and kms[0].direction == "in" and Decimal(str(kms[0].amount)) == Decimal("2000")
    assert kms[0].session_id == t['ks'].id
    # asl chiqim yozuvi o'chirilmagan
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == "return_from_customer").count() == 1


def test_delete_debt_return_restores_debt(client, db, t):
    r = client.login(t['uw']).post(URL, json=_payload(t))
    mid = r.json()["movement_ids"][0]
    assert _debt(db, t['cust_a']) == (Decimal("3000"), Decimal("3000"))
    r = client.login(t['uw']).delete(f"/api/inventory/movements/{mid}")
    assert r.status_code == 200, r.text
    assert _debt(db, t['cust_a']) == (Decimal("5000"), Decimal("5000"))
    assert _stock_qty(db, t['pa'], t['wha']) == Decimal("0")


def test_delete_insufficient_stock_400_nothing_changes(client, db, t):
    mid = _do_cash_return(client, db, t)
    s = db.query(StockLevel).filter(StockLevel.variant_id == t['va'].id).one()
    s.quantity = Decimal("1")      # tovar sotilgan
    db.flush()
    r = client.login(t['uw']).delete(f"/api/inventory/movements/{mid}")
    assert r.status_code == 400, r.text
    assert "Qoldiq yetarli emas" in r.json()["detail"]
    assert _bal(db, t['wa']) == Decimal("98000")
    assert db.query(Transaction).count() == 1 and db.get(StockMovement, mid) is not None
    assert db.query(KassaMovement).filter(KassaMovement.direction == "in").count() == 0
    assert _stock_qty(db, t['pa'], t['wha'], t['va']) == Decimal("1")


def test_delete_batch_partially_sold_400(client, db, t):
    mid = _do_cash_return(client, db, t)
    b = db.query(Batch).filter(Batch.lot_number == f"RETURN-C{mid}").one()
    b.quantity = Decimal("1")
    db.flush()
    r = client.login(t['uw']).delete(f"/api/inventory/movements/{mid}")
    assert r.status_code == 400, r.text
    assert _bal(db, t['wa']) == Decimal("98000")
    assert _stock_qty(db, t['pa'], t['wha'], t['va']) == Decimal("2")


def test_delete_legacy_foreign_customer_404(client, db, t):
    # Eski yozuv: reference_id = B mijozi, reason'da "qarzga summa:"
    _stock(db, t['pa'], t['wha'], 5)
    m = StockMovement(product_id=t['pa'].id, warehouse_id=t['wha'].id, type=MovementType.IN,
                      qty_before=3, qty_after=5, quantity=2, reference_type="return_from_customer",
                      reference_id=t['cust_b'].id, user_id=t['uw'].id,
                      reason="Qisman qaytarish: X. payment:debt. summa:5000000.")
    db.add(m)
    db.flush()
    r = client.login(t['uw']).delete(f"/api/inventory/movements/{m.id}")
    assert r.status_code == 404, r.text
    assert _debt(db, t['cust_b']) == (Decimal("5000"), Decimal("5000"))
    assert _stock_qty(db, t['pa'], t['wha']) == Decimal("5")
    assert db.get(StockMovement, m.id) is not None


def test_delete_foreign_wallet_tx_409(client, db, t):
    _stock(db, t['pa'], t['wha'], 5)
    m = StockMovement(product_id=t['pa'].id, warehouse_id=t['wha'].id, type=MovementType.IN,
                      qty_before=3, qty_after=5, quantity=2, reference_type="return_from_customer",
                      reference_id=t['cust_a'].id, user_id=t['uw'].id, reason="payment:cash. summa:2000.")
    db.add(m)
    db.flush()
    db.add(Transaction(branch_id=t['ba'].id, company_id=t['ca'].id, type="expense", amount=Decimal("2000"),
                       wallet_id=t['wb'].id, reference_type="return_from_customer", reference_id=m.id))
    db.flush()
    r = client.login(t['uw']).delete(f"/api/inventory/movements/{m.id}")
    assert r.status_code == 409, r.text
    assert _bal(db, t['wb']) == Decimal("100000")
    assert _stock_qty(db, t['pa'], t['wha']) == Decimal("5")
    assert db.query(Transaction).count() == 1


def test_delete_legacy_without_meta_regex_fallback(client, db, t):
    # Eski (meta'siz) qarzga qaytarish: summa reason'dan olinadi, mijoz o'z korxonasidan
    _stock(db, t['pa'], t['wha'], 5)
    m = StockMovement(product_id=t['pa'].id, warehouse_id=t['wha'].id, type=MovementType.IN,
                      qty_before=3, qty_after=5, quantity=2, reference_type="return_from_customer",
                      reference_id=t['cust_a'].id, user_id=t['uw'].id,
                      reason="Qisman qaytarish: X. payment:debt. summa:2000. qarzga")
    db.add(m)
    db.flush()
    db.add(Transaction(branch_id=t['ba'].id, company_id=t['ca'].id, type="expense", amount=Decimal("2000"),
                       wallet_id=None, reference_type="return_from_customer", reference_id=m.id))
    db.flush()
    r = client.login(t['uw']).delete(f"/api/inventory/movements/{m.id}")
    assert r.status_code == 200, r.text
    assert _debt(db, t['cust_a']) == (Decimal("7000"), Decimal("7000"))
    assert _stock_qty(db, t['pa'], t['wha']) == Decimal("3")


# ─── 11. PUT /inventory/{id}/movements ──────────────────────────────────────

def _manual_in(db, t):
    _stock(db, t['pa'], t['wha'], 5)
    m = StockMovement(product_id=t['pa'].id, warehouse_id=t['wha'].id, type=MovementType.IN,
                      qty_before=0, qty_after=5, quantity=5, reference_type="manual_receive",
                      reference_id=None, user_id=t['ua'].id, reason="kirim")
    db.add(m)
    db.flush()
    return m


def test_put_reference_fields_rejected(client, db, t):
    m = _manual_in(db, t)
    r = client.login(t['ua']).put(f"/api/inventory/{m.id}/movements", json={
        "reference_type": "return_from_customer", "reference_id": t['cust_b'].id, "reason": "qarzga summa:5000000"})
    assert r.status_code == 422, r.text
    db.refresh(m)
    assert m.reference_type == "manual_receive" and m.reference_id is None and m.reason == "kirim"
    # quantity ham o'zgarmaydi
    r = client.login(t['ua']).put(f"/api/inventory/{m.id}/movements", json={"quantity": 100})
    assert r.status_code == 422


def test_put_reason_only_admin(client, db, t):
    m = _manual_in(db, t)
    r = client.login(t['uw']).put(f"/api/inventory/{m.id}/movements", json={"reason": "x"})
    assert r.status_code == 403, r.text
    r = client.login(t['ua']).put(f"/api/inventory/{m.id}/movements", json={"reason": "yangi izoh"})
    assert r.status_code == 200, r.text
    db.refresh(m)
    assert m.reason == "yangi izoh" and m.reference_type == "manual_receive"


def test_put_locked_movement_400(client, db, t):
    r = client.login(t['uw']).post(URL, json=_payload(t))
    mid = r.json()["movement_ids"][0]
    r = client.login(t['ua']).put(f"/api/inventory/{mid}/movements", json={"reason": "x"})
    assert r.status_code == 400, r.text


# ─── Yordamchilar (tenant_guards) ───────────────────────────────────────────

def test_tenant_guards_helpers(db, t):
    from fastapi import HTTPException
    from app.services import tenant_guards as tg
    assert tg.get_company_warehouse(db, t['uw'], t['wha'].id).id == t['wha'].id
    with pytest.raises(HTTPException) as e:
        tg.get_company_warehouse(db, t['uw'], t['whb'].id)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        tg.get_company_warehouse(db, t['uw'], t['wha2'].id)
    assert e.value.status_code == 403
    assert tg.get_company_warehouse(db, t['uw'], t['wha2'].id, enforce_branch=False).id == t['wha2'].id
    with pytest.raises(HTTPException):
        tg.get_company_customer(db, t['ca'].id, t['cust_b'].id)
    with pytest.raises(HTTPException):
        tg.get_company_product(db, t['ca'].id, t['pb'].id)
    assert tg.get_company_variant(db, t['pa'].id, t['va'].id).id == t['va'].id
    with pytest.raises(HTTPException) as e:
        tg.get_company_variant(db, t['pa'].id, t['vb'].id)
    assert e.value.status_code == 400
    assert tg.get_company_wallet(db, t['ca'].id, t['wa'].id).id == t['wa'].id
    with pytest.raises(HTTPException) as e:
        tg.get_company_wallet(db, t['ca'].id, t['wb'].id)
    assert e.value.status_code == 404
    assert tg.find_default_wallet(db, t['uw']).id == t['wa'].id


def test_resolve_branch_id_prefer_warehouse(db, t):
    from app.services.sale_helpers import resolve_branch_id
    # T1.9: default ham ombor filiali birinchi (operatsiya joyi), prefer_warehouse eski chaqiruvlar uchun
    assert resolve_branch_id(db, t['ua'], t['wha2'].id) == t['ba2'].id
    # prefer_warehouse: ombor filiali
    assert resolve_branch_id(db, t['ua'], t['wha2'].id, prefer_warehouse=True) == t['ba2'].id
    # begona ombor — korxona filtri: foydalanuvchi filiali qaytadi
    assert resolve_branch_id(db, t['ua'], t['whb'].id, prefer_warehouse=True) == t['ba'].id
    # filialsiz admin + begona ombor → korxonaning birinchi filiali
    assert resolve_branch_id(db, t['ua_nobranch'], t['whb'].id) == t['ba'].id
