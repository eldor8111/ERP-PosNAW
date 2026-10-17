"""T0.31 — To'liq va qisman qaytarishni to'g'rilash.

Qamrov: qisman qaytarishda filial tekshiruvi, pul kassirning default (yoki asl sotuv) kassasidan
chiqishi, kassa topilmasa 400 (hech narsa o'zgarmaydi), USD sotuvda KassaMovement/Transaction
valyutasi va Wallet.balance o'zgarmasligi, tovar sotilgan ombor va variantga qaytishi, virtual
(sell) mahsulot, Sale.original_sale_id, Idempotency-Key (ikkala yo'l), /sales/return da
paid <= total, original_sale_id bilan bog'lash va qoldiq nazorati, ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T0_31.py -q -p no:cacheprovider
"""
import itertools
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.currency import Currency
from app.models.inventory import StockLevel, StockMovement
from app.models.moliya import KassaMovement, KassaSession, Transaction, Wallet
from app.models.product import Product, ProductConversion
from app.models.product_variant import ProductVariant
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole, UserWallet

_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _wallet(db, company, branch, balance=0, is_open=True, active=True):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id if branch else None,
               is_active=active, is_open=is_open)
    db.add(w)
    db.flush()
    return w


def _attach(db, user, wallet, default=True):
    db.add(UserWallet(user_id=user.id, wallet_id=wallet.id, is_default=default, company_id=wallet.company_id))
    db.flush()


def _product(db, company, ptype="simple", cost="500", price="1000"):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T031-{n}", barcode=f"B031-{n}", company_id=company.id,
                cost_price=Decimal(cost), sale_price=Decimal(price), product_type=ptype)
    db.add(p)
    db.flush()
    return p


def _variant(db, product):
    v = ProductVariant(product_id=product.id, name=f"V{next(_seq)}")
    db.add(v)
    db.flush()
    return v


def _qty(db, product, wh, variant_id=None):
    q = db.query(StockLevel).filter(StockLevel.product_id == product.id, StockLevel.warehouse_id == wh.id)
    q = q.filter(StockLevel.variant_id == variant_id) if variant_id is not None else q.filter(StockLevel.variant_id.is_(None))
    row = q.first()
    return Decimal(str(row.quantity)) if row else Decimal("0")


def _sale(db, company, cashier, wh, product, qty=3, price=1000, item_wh=None, variant_id=None,
          currency=None, rate=1, wallet=None, customer_id=None):
    """Tayyor (completed) sotuv: bitta qator; wallet berilsa shu kassaga 'in' harakati yoziladi."""
    sub = Decimal(qty) * Decimal(price)
    total = sub * Decimal(rate)
    s = Sale(number=f"S3{next(_seq):06d}", cashier_id=cashier.id, company_id=company.id,
             warehouse_id=wh.id if wh else None, total_amount=total, paid_amount=total,
             paid_cash=total, payment_type=PaymentType.cash, status=SaleStatus.completed,
             currency_id=currency.id if currency else None, exchange_rate=Decimal(rate),
             customer_id=customer_id)
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, variant_id=variant_id,
                    warehouse_id=(item_wh or wh).id if (item_wh or wh) else None,
                    quantity=Decimal(qty), unit_price=Decimal(price), cost_price=product.cost_price,
                    discount=Decimal("0"), subtotal=sub, returned_quantity=Decimal("0"),
                    currency_code=currency.code if currency else "UZS", exchange_rate=Decimal(rate)))
    if wallet is not None:
        db.add(KassaMovement(wallet_id=wallet.id, company_id=company.id, direction="in", payment_type="cash",
                             amount=sub, currency=currency.code if currency else "UZS",
                             reference_type="sale", reference_id=s.id, created_by=cashier.id))
    db.flush()
    db.refresh(s)
    return s


def _return_doc(db, original):
    return db.query(Sale).filter(Sale.original_sale_id == original.id).all()


def _counts(db):
    return (db.query(Sale).count(), db.query(SaleItem).count(), db.query(StockMovement).count(),
            db.query(Transaction).count(), db.query(KassaMovement).count())


def _bal(db, wallet):
    db.expire(wallet)
    return Decimal(str(wallet.balance or 0))


@pytest.fixture
def w(db, mk):
    """Korxona A: 2 filial (A1, A2), har birida ombor, kassir va kassa; admin. Korxona B: admin + kassa."""
    ca, ba1, wh1, cash1 = mk.tenant(UserRole.cashier)
    ba2 = mk.branch(ca, name="Filial A2")
    wh2 = mk.warehouse(ca, ba2, name="Ombor A2")
    wh1b = mk.warehouse(ca, ba1, name="Ombor A1-b")
    cash2 = mk.user(ca, role=UserRole.cashier, branch=ba2)
    admin = mk.user(ca, role=UserRole.admin, branch=ba1)
    # Tuzoq: eng kichik id'li ochiq kassa A2 filialida va hech kimga biriktirilmagan
    trap = _wallet(db, ca, ba2, 777)
    wallet1 = _wallet(db, ca, ba1, 100000)
    wallet2 = _wallet(db, ca, ba2, 100000)
    _attach(db, cash1, wallet1)
    _attach(db, cash2, wallet2)
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    wallet_b = _wallet(db, cb, bb, 5000)
    usd = Currency(name="US Dollar", code="USD", rate=Decimal("12000"), company_id=ca.id)
    db.add(usd)
    db.flush()
    return SimpleNamespace(ca=ca, ba1=ba1, ba2=ba2, wh1=wh1, wh1b=wh1b, wh2=wh2, cash1=cash1, cash2=cash2,
                           admin=admin, trap=trap, wallet1=wallet1, wallet2=wallet2,
                           cb=cb, admin_b=admin_b, wallet_b=wallet_b, whb=whb, usd=usd)


def _post_partial(client, user, sale, qty, headers=None, **extra):
    item = sale.items[0]
    body = {"items": [{"sale_item_id": item.id, "quantity": qty}], "payment_type": "cash"}
    body.update(extra)
    return client.login(user).post(f"/api/sales/{sale.id}/return-items", json=body, headers=headers or {})


def _post_return(client, user, items, wh, paid, headers=None, **extra):
    body = {"items": items, "payment_type": "cash", "paid_amount": paid, "paid_cash": paid,
            "warehouse_id": wh.id}
    body.update(extra)
    return client.login(user).post("/api/sales/return", json=body, headers=headers or {})


# ── 1. Qisman qaytarish: filial va kassa ─────────────────────────────────────

def test_other_branch_cashier_cannot_partial_return(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p)
    before = _counts(db)
    r = _post_partial(client, w.cash2, sale, 1)
    assert r.status_code in (403, 404), r.text
    assert _counts(db) == before
    db.refresh(sale.items[0])
    assert sale.items[0].returned_quantity == 0 and sale.status == SaleStatus.completed
    assert _bal(db, w.wallet2) == Decimal("100000") and _bal(db, w.trap) == Decimal("777")


def test_partial_return_money_from_cashier_default_wallet(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=3, price=1000)
    r = _post_partial(client, w.cash1, sale, 2)
    assert r.status_code == 200, r.text
    ret = _return_doc(db, sale)
    assert len(ret) == 1 and ret[0].original_sale_id == sale.id
    tx = db.query(Transaction).filter(Transaction.reference_type == "sale_refund",
                                      Transaction.reference_id == ret[0].id).all()
    assert len(tx) == 1 and tx[0].type == "expense" and tx[0].wallet_id == w.wallet1.id
    assert tx[0].amount == Decimal("2000") and tx[0].currency_code == "UZS"
    assert tx[0].branch_id == w.ba1.id
    km = db.query(KassaMovement).filter(KassaMovement.reference_type == "sale_refund",
                                        KassaMovement.reference_id == ret[0].id).all()
    assert len(km) == 1 and km[0].direction == "out" and km[0].wallet_id == w.wallet1.id
    assert km[0].amount == Decimal("2000") and km[0].currency == "UZS"
    assert _bal(db, w.wallet1) == Decimal("98000")
    # Tuzoq (korxonadagi birinchi ochiq kassa) va boshqa filial kassasi tegilmaydi
    assert _bal(db, w.trap) == Decimal("777") and _bal(db, w.wallet2) == Decimal("100000")
    db.refresh(sale.items[0])
    assert sale.items[0].returned_quantity == Decimal("2")
    assert sale.status == SaleStatus.partial_refund


def test_partial_return_falls_back_to_original_sale_wallet(client, db, w, mk):
    """Kassirda biriktirilgan kassa yo'q: asl sotuv kassasi (ochiq bo'lsa) ishlatiladi."""
    free_cashier = mk.user(w.ca, role=UserRole.cashier, branch=w.ba1)
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, free_cashier, w.wh1, p, wallet=w.wallet1)
    r = _post_partial(client, free_cashier, sale, 1)
    assert r.status_code == 200, r.text
    assert _bal(db, w.wallet1) == Decimal("99000")
    assert _bal(db, w.trap) == Decimal("777")


def test_partial_return_no_wallet_400_and_nothing_changes(client, db, w, mk):
    free_cashier = mk.user(w.ca, role=UserRole.cashier, branch=w.ba1)
    p = _product(db, w.ca)
    closed = _wallet(db, w.ca, w.ba1, 1000, is_open=False)
    sale = _sale(db, w.ca, free_cashier, w.wh1, p, wallet=closed)
    before = _counts(db)
    r = _post_partial(client, free_cashier, sale, 1)
    assert r.status_code == 400, r.text
    assert "kassa" in r.json()["detail"].lower()
    assert _counts(db) == before
    db.refresh(sale.items[0])
    assert sale.items[0].returned_quantity == 0 and sale.status == SaleStatus.completed
    assert _bal(db, closed) == Decimal("1000")


def test_partial_return_requested_wallet_rules(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p)
    # Kassirga biriktirilmagan kassa -> 403
    r = _post_partial(client, w.cash1, sale, 1, wallet_id=w.wallet2.id)
    assert r.status_code == 403, r.text
    # Boshqa korxona kassasi -> 404
    r = _post_partial(client, w.cash1, sale, 1, wallet_id=w.wallet_b.id)
    assert r.status_code == 404, r.text
    assert _return_doc(db, sale) == []
    # Admin istalgan o'z kassasini tanlay oladi
    r = _post_partial(client, w.admin, sale, 1, wallet_id=w.wallet2.id)
    assert r.status_code == 200, r.text
    assert _bal(db, w.wallet2) == Decimal("99000")
    # Yopiq kassa -> 400
    closed = _wallet(db, w.ca, w.ba1, 0, is_open=False)
    r = _post_partial(client, w.admin, sale, 1, wallet_id=closed.id)
    assert r.status_code == 400


def test_partial_return_usd_sale_does_not_touch_wallet_balance(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=3, price=10, currency=w.usd, rate=12000)
    r = _post_partial(client, w.cash1, sale, 1)
    assert r.status_code == 200, r.text
    ret = _return_doc(db, sale)[0]
    km = db.query(KassaMovement).filter(KassaMovement.reference_type == "sale_refund",
                                        KassaMovement.reference_id == ret.id).one()
    assert km.currency == "USD" and km.amount == Decimal("10") and km.direction == "out"
    tx = db.query(Transaction).filter(Transaction.reference_type == "sale_refund",
                                      Transaction.reference_id == ret.id).one()
    assert tx.currency_code == "USD" and tx.amount == Decimal("10")
    assert _bal(db, w.wallet1) == Decimal("100000")


# ── 2. Ombor, variant, virtual mahsulot ──────────────────────────────────────

def test_partial_return_goes_back_to_item_warehouse_and_variant(client, db, w):
    p = _product(db, w.ca)
    v = _variant(db, p)
    # Sotuv sarlavhasi wh1 da, lekin qator wh1b dan sotilgan
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=2, item_wh=w.wh1b, variant_id=v.id)
    r = _post_partial(client, w.cash1, sale, 2)
    assert r.status_code == 200, r.text
    assert _qty(db, p, w.wh1b, v.id) == Decimal("2")
    assert _qty(db, p, w.wh1) == Decimal("0") and _qty(db, p, w.wh1, v.id) == Decimal("0")
    ret = _return_doc(db, sale)[0]
    ri = db.query(SaleItem).filter(SaleItem.sale_id == ret.id).one()
    assert ri.warehouse_id == w.wh1b.id and ri.variant_id == v.id
    mv = db.query(StockMovement).filter(StockMovement.reference_type == "sale_refund",
                                        StockMovement.reference_id == ret.id).one()
    assert mv.warehouse_id == w.wh1b.id and mv.variant_id == v.id
    assert sale.status == SaleStatus.refunded


def test_partial_return_warehouse_undetermined_400(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, None, p)
    sale.items[0].warehouse_id = None
    db.flush()
    r = _post_partial(client, w.admin, sale, 1)
    assert r.status_code == 400 and "Ombor" in r.json()["detail"]
    # So'rovdagi zaxira ombor ishlaydi
    r = _post_partial(client, w.admin, sale, 1, warehouse_id=w.wh1.id, wallet_id=w.wallet1.id)
    assert r.status_code == 200, r.text
    assert _qty(db, p, w.wh1) == Decimal("1")


def test_partial_return_virtual_product_returns_to_source(client, db, w):
    src = _product(db, w.ca)
    sell = _product(db, w.ca, ptype="sell")
    db.add(ProductConversion(sell_product_id=sell.id, source_product_id=src.id, ratio=Decimal("0.5")))
    db.flush()
    sale = _sale(db, w.ca, w.cash1, w.wh1, sell, qty=4, price=1000)
    r = _post_partial(client, w.cash1, sale, 2)
    assert r.status_code == 200, r.text
    assert _qty(db, src, w.wh1) == Decimal("1.0")           # 2 * 0.5
    assert _qty(db, sell, w.wh1) == Decimal("0")


# ── 3. Idempotentlik ─────────────────────────────────────────────────────────

def test_partial_return_idempotency_key(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=3)
    h = {"Idempotency-Key": "pr-key-1"}
    r1 = _post_partial(client, w.cash1, sale, 1, headers=h)
    r2 = _post_partial(client, w.cash1, sale, 1, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert len(_return_doc(db, sale)) == 1
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == "sale_refund").count() == 1
    assert _bal(db, w.wallet1) == Decimal("99000")
    assert r1.json()["id"] == r2.json()["id"] == sale.id
    db.refresh(sale.items[0])
    assert sale.items[0].returned_quantity == Decimal("1")


def test_idempotency_key_too_long_400(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p)
    r = _post_partial(client, w.cash1, sale, 1, headers={"Idempotency-Key": "k" * 65})
    assert r.status_code == 400


# ── 4. /sales/return ─────────────────────────────────────────────────────────

def test_full_return_paid_exceeds_total_400(client, db, w):
    p = _product(db, w.ca)
    before = _counts(db)
    r = _post_return(client, w.cash1, [{"product_id": p.id, "quantity": 2, "unit_price": 1000}], w.wh1, 2500)
    assert r.status_code == 400, r.text
    assert "oshmasligi" in r.json()["detail"]
    assert _counts(db) == before


def test_full_return_writes_money_from_default_wallet_with_currency(client, db, w):
    p = _product(db, w.ca)
    r = _post_return(client, w.cash1, [{"product_id": p.id, "quantity": 2, "unit_price": 1000}], w.wh1, 2000)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    tx = db.query(Transaction).filter(Transaction.reference_type == "sale_refund", Transaction.reference_id == sid).one()
    assert tx.wallet_id == w.wallet1.id and tx.type == "expense" and tx.currency_code == "UZS"
    km = db.query(KassaMovement).filter(KassaMovement.reference_type == "sale_refund",
                                        KassaMovement.reference_id == sid).one()
    assert km.wallet_id == w.wallet1.id and km.direction == "out" and km.currency == "UZS"
    assert _bal(db, w.wallet1) == Decimal("98000")
    assert _bal(db, w.trap) == Decimal("777")
    item = db.query(SaleItem).filter(SaleItem.sale_id == sid).one()
    assert item.warehouse_id == w.wh1.id
    assert _qty(db, p, w.wh1) == Decimal("2")


def test_full_return_usd_keeps_wallet_balance(client, db, w):
    p = _product(db, w.ca)
    r = _post_return(client, w.cash1, [{"product_id": p.id, "quantity": 1, "unit_price": 10}], w.wh1, 10,
                     currency_id=w.usd.id)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    km = db.query(KassaMovement).filter(KassaMovement.reference_id == sid,
                                        KassaMovement.reference_type == "sale_refund").one()
    tx = db.query(Transaction).filter(Transaction.reference_id == sid,
                                      Transaction.reference_type == "sale_refund").one()
    assert km.currency == "USD" and tx.currency_code == "USD"
    assert _bal(db, w.wallet1) == Decimal("100000")


def test_full_return_no_wallet_400_nothing_written(client, db, w, mk):
    free_cashier = mk.user(w.ca, role=UserRole.cashier, branch=w.ba1)
    p = _product(db, w.ca)
    before = _counts(db)
    r = _post_return(client, free_cashier, [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], w.wh1, 1000)
    assert r.status_code == 400, r.text
    assert "kassa" in r.json()["detail"].lower()
    assert _counts(db) == before
    assert _bal(db, w.trap) == Decimal("777")


def test_full_return_writes_even_without_branch(client, db, mk):
    """Filialsiz korxona: Transaction va KassaMovement baribir yoziladi (tx_branch_id ga bog'liq emas)."""
    c = mk.company()
    wh = mk.warehouse(c, None)
    u = mk.user(c, role=UserRole.admin)
    wl = _wallet(db, c, None, 5000)
    _attach(db, u, wl)
    p = _product(db, c)
    r = _post_return(client, u, [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], wh, 1000)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    tx = db.query(Transaction).filter(Transaction.reference_id == sid, Transaction.reference_type == "sale_refund").one()
    assert tx.branch_id is None and tx.wallet_id == wl.id
    assert db.query(KassaMovement).filter(KassaMovement.reference_id == sid,
                                          KassaMovement.reference_type == "sale_refund").count() == 1
    assert _bal(db, wl) == Decimal("4000")


def test_full_return_idempotency_key(client, db, w):
    p = _product(db, w.ca)
    items = [{"product_id": p.id, "quantity": 1, "unit_price": 1000}]
    h = {"Idempotency-Key": "ret-key-1"}
    r1 = _post_return(client, w.cash1, items, w.wh1, 1000, headers=h)
    r2 = _post_return(client, w.cash1, items, w.wh1, 1000, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert r1.json()["id"] == r2.json()["id"]
    assert db.query(Sale).filter(Sale.idempotency_key == "ret-key-1").count() == 1
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == "sale_refund").count() == 1
    assert _bal(db, w.wallet1) == Decimal("99000")
    assert _qty(db, p, w.wh1) == Decimal("1")


def test_full_return_variant_goes_back(client, db, w):
    p = _product(db, w.ca)
    v = _variant(db, p)
    r = _post_return(client, w.cash1, [{"product_id": p.id, "variant_id": v.id, "quantity": 2,
                                        "unit_price": 1000}], w.wh1, 2000)
    assert r.status_code == 200, r.text
    assert _qty(db, p, w.wh1, v.id) == Decimal("2") and _qty(db, p, w.wh1) == Decimal("0")
    item = db.query(SaleItem).filter(SaleItem.sale_id == r.json()["id"]).one()
    assert item.variant_id == v.id and item.warehouse_id == w.wh1.id


def test_full_return_foreign_variant_400(client, db, w):
    p = _product(db, w.ca)
    other = _product(db, w.ca)
    v = _variant(db, other)
    r = _post_return(client, w.cash1, [{"product_id": p.id, "variant_id": v.id, "quantity": 1,
                                        "unit_price": 1000}], w.wh1, 1000)
    assert r.status_code == 400


def test_full_return_foreign_warehouse_404(client, db, w):
    p = _product(db, w.ca)
    r = _post_return(client, w.admin, [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], w.whb, 1000)
    assert r.status_code == 404


# ── 5. /sales/return + original_sale_id ──────────────────────────────────────

def test_full_return_linked_to_original_sale(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=3, price=1000)
    # Mijoz yuborgan narx (99999) e'tiborsiz: asl qator narxi (1000) olinadi
    r = _post_return(client, w.cash1, [{"product_id": p.id, "quantity": 1, "unit_price": 99999}], w.wh1, 1000,
                     original_sale_id=sale.id)
    assert r.status_code == 200, r.text
    ret = db.query(Sale).filter(Sale.id == r.json()["id"]).one()
    assert ret.original_sale_id == sale.id and ret.total_amount == Decimal("1000")
    db.refresh(sale.items[0])
    assert sale.items[0].returned_quantity == Decimal("1")
    assert sale.status == SaleStatus.partial_refund
    # Qolgan 2 donani qaytarish — status refunded
    r = _post_return(client, w.cash1, [{"product_id": p.id, "quantity": 2}], w.wh1, 2000, original_sale_id=sale.id)
    assert r.status_code == 200, r.text
    db.refresh(sale)
    assert sale.status == SaleStatus.refunded


def test_full_return_over_original_remaining_400(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=2)
    before = _counts(db)
    r = _post_return(client, w.cash1, [{"product_id": p.id, "quantity": 3}], w.wh1, 1000, original_sale_id=sale.id)
    assert r.status_code == 400, r.text
    assert _counts(db) == before
    db.refresh(sale.items[0])
    assert sale.items[0].returned_quantity == 0


def test_full_return_product_not_in_original_400(client, db, w):
    p = _product(db, w.ca)
    other = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=2)
    r = _post_return(client, w.cash1, [{"product_id": other.id, "quantity": 1}], w.wh1, 1000,
                     original_sale_id=sale.id)
    assert r.status_code == 400, r.text


def test_full_return_original_sale_isolation(client, db, w):
    pb = _product(db, w.cb)
    sale_b = _sale(db, w.cb, w.admin_b, w.whb, pb)
    p = _product(db, w.ca)
    r = _post_return(client, w.admin, [{"product_id": p.id, "quantity": 1}], w.wh1, 1000,
                     original_sale_id=sale_b.id)
    assert r.status_code == 404, r.text
    # Boshqa filial kassiri A1 sotuvini bog'lay olmaydi
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=2)
    r = _post_return(client, w.cash2, [{"product_id": p.id, "quantity": 1}], w.wh2, 1000, original_sale_id=sale.id)
    assert r.status_code in (403, 404), r.text
    assert _return_doc(db, sale) == []


def test_full_return_cannot_use_already_refunded_original(client, db, w):
    p = _product(db, w.ca)
    sale = _sale(db, w.ca, w.cash1, w.wh1, p, qty=1)
    sale.status = SaleStatus.refunded
    db.flush()
    r = _post_return(client, w.cash1, [{"product_id": p.id, "quantity": 1}], w.wh1, 1000, original_sale_id=sale.id)
    assert r.status_code == 400


# ── 6. Ikki korxona izolyatsiyasi va ijobiy yo'l ─────────────────────────────

def test_company_isolation_partial_return(client, db, w):
    pa = _product(db, w.ca)
    sale_a = _sale(db, w.ca, w.cash1, w.wh1, pa)
    pb = _product(db, w.cb)
    sale_b = _sale(db, w.cb, w.admin_b, w.whb, pb)
    before = _counts(db)
    r = _post_partial(client, w.admin_b, sale_a, 1)           # B admin -> A sotuvi
    assert r.status_code == 404, r.text
    r = _post_partial(client, w.admin, sale_b, 1)             # A admin -> B sotuvi
    assert r.status_code == 404, r.text
    assert _counts(db) == before
    assert _bal(db, w.wallet_b) == Decimal("5000")


def test_positive_path_own_company(client, db, w):
    pb = _product(db, w.cb)
    sale_b = _sale(db, w.cb, w.admin_b, w.whb, pb, qty=2, wallet=w.wallet_b)
    r = _post_partial(client, w.admin_b, sale_b, 1)
    assert r.status_code == 200, r.text                        # asl sotuv kassasi (biriktirilmagan, ochiq)
    assert _bal(db, w.wallet_b) == Decimal("4000")
    assert _qty(db, pb, w.whb) == Decimal("1")


def test_full_return_mixed_payment_splits_cash_and_card(client, db, w):
    p = _product(db, w.ca)
    r = client.login(w.cash1).post("/api/sales/return", json={
        "items": [{"product_id": p.id, "quantity": 3, "unit_price": 1000}],
        "payment_type": "mixed", "paid_amount": 3000, "paid_cash": 1000, "paid_card": 2000,
        "warehouse_id": w.wh1.id,
    })
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    kms = db.query(KassaMovement).filter(KassaMovement.reference_type == "sale_refund",
                                         KassaMovement.reference_id == sid).all()
    assert sorted((k.payment_type, k.amount) for k in kms) == [("card", Decimal("2000")), ("cash", Decimal("1000"))]
    assert db.query(Transaction).filter(Transaction.reference_type == "sale_refund",
                                        Transaction.reference_id == sid).count() == 2
    assert _bal(db, w.wallet1) == Decimal("97000")
