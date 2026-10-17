"""T0.30 — Sotuvni o'chirish/tahrirlash/qaytarishda qoldiq va kassa teskarisi.

Qamrov: o'chirishda KassaMovement(sale_cancel) va Wallet.balance; ikki marta tahrirda takror
teskari yo'q; pending buyurtmani to'lov bilan tasdiqlashda SalePayment/Transaction/KassaMovement;
qator ombori va variant bo'yicha qaytarish (eski NULL-omborli harakatlar ham); completed -> pending
nisbiy qaytarish; partiya/SaleItemBatch sinxronligi; qaytarilgan sotuv va R-hujjat uchun 400;
original_sale_id; pending -> cancelled / completed -> cancelled; ikki korxona izolyatsiyasi;
create_sale regressiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T0_30.py -q -p no:cacheprovider
"""
import itertools
from decimal import Decimal

import pytest

from app.models.batch import Batch
from app.models.customer import Customer
from app.models.inventory import StockLevel, StockMovement
from app.models.moliya import KassaMovement, KassaSession, Transaction, Wallet
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import PaymentType, Sale, SaleItem, SaleItemBatch, SalePayment, SaleStatus
from app.models.user import UserRole
from app.routers.kassa import get_kassa_balances
from app.schemas.sale import SaleCreate
from app.services.sale_create import create_sale

_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _wallet(db, company, branch, balance=0):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _customer(db, company, debt=0):
    n = next(_seq)
    c = Customer(name=f"Mijoz {n}", company_id=company.id, phone=f"99891{n:07d}",
                 debt_balance=Decimal(debt), debt_balances={"UZS": float(debt)} if debt else {})
    db.add(c)
    db.flush()
    return c


def _product(db, company, wh=None, qty=100, cost="500", price="1000", variant_id=None):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T030-{n}", barcode=f"B030-{n}", company_id=company.id,
                cost_price=Decimal(cost), sale_price=Decimal(price))
    db.add(p)
    db.flush()
    if wh is not None:
        db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty), variant_id=variant_id))
        db.flush()
    return p


def _stock(db, product, wh, qty, variant_id=None):
    s = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(qty), variant_id=variant_id)
    db.add(s)
    db.flush()
    return s


def _qty(db, product, wh, variant_id=None):
    q = db.query(StockLevel).filter(StockLevel.product_id == product.id, StockLevel.warehouse_id == wh.id)
    q = q.filter(StockLevel.variant_id == variant_id) if variant_id is not None else q.filter(StockLevel.variant_id.is_(None))
    row = q.first()
    return Decimal(str(row.quantity)) if row else None


def _batch(db, company, product, wh, qty, price="500", variant_id=None):
    b = Batch(product_id=product.id, variant_id=variant_id, warehouse_id=wh.id, lot_number=f"L{next(_seq)}",
              initial_quantity=Decimal(qty), quantity=Decimal(qty), purchase_price=Decimal(price),
              company_id=company.id)
    db.add(b)
    db.flush()
    return b


def _sale_data(items, wh, price=1000, payments=None, payment_type="cash", paid_amount=None, **extra):
    body = dict(items=items, payment_type=payment_type, warehouse_id=wh.id)
    if payments is not None:
        body["payments"] = payments
    if paid_amount is None:
        paid_amount = sum((Decimal(str(p["amount"])) for p in (payments or [])
                           if p["type"] not in ("debt", "cashback", "mixed")), Decimal("0"))
    body["paid_amount"] = paid_amount
    body.update(extra)
    return SaleCreate(**body)


def _cash_sale(db, w, product, qty=1, price=1000, **extra):
    """Bitta mahsulot, naqd to'liq to'langan sotuv (create_sale orqali)."""
    amount = Decimal(qty) * Decimal(price)
    return create_sale(db, _sale_data(
        [{"product_id": product.id, "quantity": qty, "unit_price": price}], w["wha"],
        payments=[{"type": "cash", "amount": amount}], **extra,
    ), w["admin"])


def _pending_sale(db, w, product, qty=5, price=1000, customer=None, wh=None, variant_id=None):
    """Ulgurji/agent buyurtmasi: pending holat, harakatsiz."""
    wh = wh or w["wha"]
    s = Sale(number=f"S9{next(_seq):06d}", cashier_id=w["admin"].id, company_id=w["ca"].id,
             warehouse_id=wh.id, customer_id=customer.id if customer else None,
             total_amount=Decimal(qty) * Decimal(price), paid_amount=Decimal("0"),
             payment_type=PaymentType.cash, status=SaleStatus.pending)
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, variant_id=variant_id, warehouse_id=wh.id,
                    quantity=Decimal(qty), unit_price=Decimal(price), cost_price=product.cost_price,
                    discount=Decimal("0"), subtotal=Decimal(qty) * Decimal(price)))
    db.flush()
    db.refresh(s)
    return s


def _kms(db, sale, ref):
    return db.query(KassaMovement).filter(
        KassaMovement.reference_type == ref, KassaMovement.reference_id == sale.id,
    ).all()


def _cash_balance(db, wallet):
    bal = get_kassa_balances(wallet.id, db)
    return sum(x["value"] for x in bal.get("cash", []))


def _wallet_balance(db, wallet):
    db.expire(wallet)
    return Decimal(str(wallet.balance or 0))


@pytest.fixture
def w(db, mk):
    """Korxona A (admin, kassa, 2 ombor) va korxona B (admin, kassa)."""
    ca, ba, wha, admin = mk.tenant(UserRole.admin)
    whb = mk.warehouse(ca, ba, name="Ombor B")
    wallet = _wallet(db, ca, ba, 0)
    cb, bb, whc, admin_b = mk.tenant(UserRole.admin)
    wallet_b = _wallet(db, cb, bb, 0)
    return dict(ca=ca, ba=ba, wha=wha, whb=whb, admin=admin, wallet=wallet,
                cb=cb, admin_b=admin_b, wallet_b=wallet_b, whc=whc)


# ── 1. O'chirishda kassa teskarisi ───────────────────────────────────────────

def test_delete_reverses_cash_and_wallet(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    sale = _cash_sale(db, w, p, qty=1, price=1_000_000)
    assert _wallet_balance(db, w["wallet"]) == Decimal("1000000")
    assert _cash_balance(db, w["wallet"]) == 1_000_000
    assert db.query(SalePayment).filter(SalePayment.sale_id == sale.id).count() == 1
    sale_id = sale.id

    r = client.login(w["admin"]).delete(f"/api/sales/{sale_id}")
    assert r.status_code == 200, r.text

    cancels = db.query(KassaMovement).filter(KassaMovement.reference_type == "sale_cancel",
                                             KassaMovement.reference_id == sale_id).all()
    assert len(cancels) == 1 and cancels[0].direction == "out" and cancels[0].amount == Decimal("1000000")
    assert cancels[0].wallet_id == w["wallet"].id and cancels[0].session_id is not None
    assert _wallet_balance(db, w["wallet"]) == Decimal("0")
    assert _cash_balance(db, w["wallet"]) == 0
    # Asl kirim harakati audit uchun qoladi; smena (SalePayment) kamayadi
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == "sale",
                                          KassaMovement.reference_id == sale_id).count() == 1
    assert db.query(SalePayment).filter(SalePayment.sale_id == sale_id).count() == 0
    assert db.query(Transaction).filter(Transaction.reference_type == "sale",
                                        Transaction.reference_id == sale_id).count() == 0
    # Qo'shimcha expense/sale_refund yozilmaydi
    assert db.query(Transaction).filter(Transaction.reference_id == sale_id, Transaction.type == "expense").count() == 0
    assert _qty(db, p, w["wha"]) == Decimal("10")


def test_delete_without_kassa_movement_does_not_touch_wallet(db, client, w):
    """Eski sotuv (KassaMovement yo'q): hamyon balansi buzilmaydi."""
    p = _product(db, w["ca"], w["wha"], qty=10)
    sale = _cash_sale(db, w, p, qty=1, price=5000)
    db.query(KassaMovement).filter(KassaMovement.reference_id == sale.id).delete()
    w["wallet"].balance = Decimal("5000")
    db.flush()
    r = client.login(w["admin"]).delete(f"/api/sales/{sale.id}")
    assert r.status_code == 200
    assert _wallet_balance(db, w["wallet"]) == Decimal("5000")
    assert db.query(KassaMovement).filter(KassaMovement.reference_type == "sale_cancel").count() == 0


# ── 2. Ikki marta tahrir — takror teskari yo'q ───────────────────────────────

def test_double_edit_keeps_wallet_equal_to_last_payment(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=100)
    sale = _cash_sale(db, w, p, qty=1, price=100_000)
    c = client.login(w["admin"])

    def edit(price):
        body = {"items": [{"product_id": p.id, "quantity": 1, "unit_price": price}],
                "payment_type": "cash", "paid_amount": price,
                "payments": [{"type": "cash", "amount": price}], "warehouse_id": w["wha"].id}
        r = c.put(f"/api/sales/{sale.id}", json=body)
        assert r.status_code == 200, r.text

    edit(70_000)
    edit(30_000)
    assert _wallet_balance(db, w["wallet"]) == Decimal("30000")
    assert _cash_balance(db, w["wallet"]) == 30_000
    # Eski harakatlar o'chmaydi: 3 ta kirim (yaratish + 2 tahrir), 2 ta teskari
    assert len(_kms(db, sale, "sale")) == 3
    assert len(_kms(db, sale, "sale_cancel")) == 2
    # Yangi kirim avval teskari qilingan asl hamyonga tushadi
    assert all(m.wallet_id == w["wallet"].id for m in _kms(db, sale, "sale"))
    assert db.query(SalePayment).filter(SalePayment.sale_id == sale.id).count() == 1
    txs = db.query(Transaction).filter(Transaction.reference_type == "sale", Transaction.reference_id == sale.id).all()
    assert len(txs) == 1 and txs[0].amount == Decimal("30000") and txs[0].wallet_id == w["wallet"].id


# ── 3. Pending buyurtmani to'lov bilan tasdiqlash — kassaga tushadi ──────────

def test_confirm_pending_with_paid_amount_posts_to_kassa(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=100)
    cust = _customer(db, w["ca"])
    sale = _pending_sale(db, w, p, qty=5, price=1_000_000, customer=cust)
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json={"status": "completed", "paid_amount": 5_000_000})
    assert r.status_code == 200, r.text

    sps = db.query(SalePayment).filter(SalePayment.sale_id == sale.id).all()
    assert len(sps) == 1 and sps[0].amount == Decimal("5000000") and sps[0].payment_type == "cash"
    txs = db.query(Transaction).filter(Transaction.reference_type == "sale", Transaction.reference_id == sale.id).all()
    assert len(txs) == 1 and txs[0].type == "income" and txs[0].amount == Decimal("5000000")
    kms = _kms(db, sale, "sale")
    assert len(kms) == 1 and kms[0].direction == "in" and kms[0].amount == Decimal("5000000")
    assert _cash_balance(db, w["wallet"]) == 5_000_000
    assert _wallet_balance(db, w["wallet"]) == Decimal("5000000")
    assert _qty(db, p, w["wha"]) == Decimal("95")
    db.refresh(cust)
    assert Decimal(str(cust.debt_balance or 0)) == Decimal("0")


def test_confirm_pending_full_edit_with_payments_posts_to_kassa(db, client, w):
    """UlgurjiSotuv tasdiqlash yo'li: PUT items + payments."""
    p = _product(db, w["ca"], w["wha"], qty=100)
    sale = _pending_sale(db, w, p, qty=2, price=1000)
    body = {"items": [{"product_id": p.id, "quantity": 2, "unit_price": 1000}], "status": "completed",
            "payment_type": "cash", "paid_amount": 2000, "payments": [{"type": "cash", "amount": 2000}],
            "warehouse_id": w["wha"].id}
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json=body)
    assert r.status_code == 200, r.text
    assert len(_kms(db, sale, "sale")) == 1
    assert _wallet_balance(db, w["wallet"]) == Decimal("2000")
    assert db.query(Transaction).filter(Transaction.reference_id == sale.id, Transaction.type == "income").count() == 1
    assert _qty(db, p, w["wha"]) == Decimal("98")


def test_decrease_paid_amount_simple_path_is_400(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    sale = _cash_sale(db, w, p, qty=1, price=5000)
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json={"paid_amount": 1000})
    assert r.status_code == 400
    assert "kamaytirish" in r.json()["detail"]


def test_put_refunded_status_is_400(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    sale = _cash_sale(db, w, p, qty=1, price=5000)
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json={"status": "refunded"})
    assert r.status_code == 400


# ── 4. Qator ombori va variant bo'yicha qaytarish ───────────────────────────

def test_delete_restores_line_warehouse_not_header(db, client, w):
    p1 = _product(db, w["ca"], w["wha"], qty=10)
    p2 = _product(db, w["ca"], w["wha"], qty=10)
    _stock(db, p2, w["whb"], 20)
    sale = create_sale(db, _sale_data(
        [{"product_id": p1.id, "quantity": 1, "unit_price": 1000},
         {"product_id": p2.id, "quantity": 3, "unit_price": 1000, "warehouse_id": w["whb"].id}],
        w["wha"], payments=[{"type": "cash", "amount": 4000}],
    ), w["admin"])
    assert _qty(db, p2, w["whb"]) == Decimal("17") and _qty(db, p2, w["wha"]) == Decimal("10")
    # create_sale harakatga omborni yozadi
    movs = db.query(StockMovement).filter(StockMovement.reference_id == sale.id, StockMovement.product_id == p2.id).all()
    assert len(movs) == 1 and movs[0].warehouse_id == w["whb"].id

    r = client.login(w["admin"]).delete(f"/api/sales/{sale.id}")
    assert r.status_code == 200
    assert _qty(db, p2, w["whb"]) == Decimal("20")
    assert _qty(db, p2, w["wha"]) == Decimal("10")
    assert _qty(db, p1, w["wha"]) == Decimal("10")


def test_delete_legacy_movement_without_warehouse_uses_sale_item(db, client, w):
    """Eski yozuvlar: StockMovement.warehouse_id NULL — SaleItem.warehouse_id bo'yicha."""
    p2 = _product(db, w["ca"], w["wha"], qty=10)
    _stock(db, p2, w["whb"], 20)
    sale = create_sale(db, _sale_data(
        [{"product_id": p2.id, "quantity": 3, "unit_price": 1000, "warehouse_id": w["whb"].id}],
        w["wha"], payments=[{"type": "cash", "amount": 3000}],
    ), w["admin"])
    db.query(StockMovement).filter(StockMovement.reference_id == sale.id).update({"warehouse_id": None})
    db.flush()
    r = client.login(w["admin"]).delete(f"/api/sales/{sale.id}")
    assert r.status_code == 200
    assert _qty(db, p2, w["whb"]) == Decimal("20")
    assert _qty(db, p2, w["wha"]) == Decimal("10")
    assert db.query(StockLevel).filter(StockLevel.product_id == p2.id, StockLevel.warehouse_id.is_(None)).count() == 0


def test_delete_restores_variant_row(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)  # variantsiz qator 10
    v_l = ProductVariant(product_id=p.id, name="L", sku=f"VL{next(_seq)}")
    v_m = ProductVariant(product_id=p.id, name="M", sku=f"VM{next(_seq)}")
    db.add_all([v_l, v_m])
    db.flush()
    _stock(db, p, w["wha"], 5, variant_id=v_l.id)
    _stock(db, p, w["wha"], 5, variant_id=v_m.id)
    sale = create_sale(db, _sale_data(
        [{"product_id": p.id, "quantity": 2, "unit_price": 1000, "variant_id": v_l.id}],
        w["wha"], payments=[{"type": "cash", "amount": 2000}],
    ), w["admin"])
    assert _qty(db, p, w["wha"], v_l.id) == Decimal("3")
    r = client.login(w["admin"]).delete(f"/api/sales/{sale.id}")
    assert r.status_code == 200
    assert _qty(db, p, w["wha"], v_l.id) == Decimal("5")
    assert _qty(db, p, w["wha"], v_m.id) == Decimal("5")
    assert _qty(db, p, w["wha"]) == Decimal("10")


# ── 5. completed -> pending: nisbiy qaytarish ────────────────────────────────

def test_unconfirm_restores_relative_not_absolute(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    sale_a = _cash_sale(db, w, p, qty=2, price=1000)   # 10 -> 8
    _cash_sale(db, w, p, qty=3, price=1000)            # 8 -> 5
    assert _qty(db, p, w["wha"]) == Decimal("5")
    r = client.login(w["admin"]).put(f"/api/sales/{sale_a.id}", json={"status": "pending"})
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["wha"]) == Decimal("7")
    assert db.query(StockMovement).filter(StockMovement.reference_id == sale_a.id).count() == 0
    # Pending'ga qaytgan sotuv qayta tasdiqlansa yana yechiladi
    r = client.login(w["admin"]).put(f"/api/sales/{sale_a.id}", json={"status": "completed"})
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["wha"]) == Decimal("5")


# ── 6-7. Partiyalar va variant tahrirda ──────────────────────────────────────

def _sib_sum(db, sale):
    ids = [i.id for i in db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()]
    if not ids:
        return Decimal("0")
    return sum((Decimal(str(s.quantity)) for s in db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id.in_(ids)).all()), Decimal("0"))


def test_edit_keeps_batches_in_sync(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=100)
    b = _batch(db, w["ca"], p, w["wha"], 100, price="700")
    sale = _cash_sale(db, w, p, qty=3, price=1000)
    db.refresh(b)
    assert b.quantity == Decimal("97") and _sib_sum(db, sale) == Decimal("3")
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()
    assert item.cost_price == Decimal("700")

    body = {"items": [{"product_id": p.id, "quantity": 5, "unit_price": 1000}], "payment_type": "cash",
            "paid_amount": 5000, "payments": [{"type": "cash", "amount": 5000}], "warehouse_id": w["wha"].id}
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json=body)
    assert r.status_code == 200, r.text
    db.refresh(b)
    assert b.quantity == Decimal("95") and _sib_sum(db, sale) == Decimal("5")
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()
    assert item.cost_price == Decimal("700")
    assert _qty(db, p, w["wha"]) == Decimal("95")

    # Ikkinchi tahrir ham shishirmaydi
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json=body)
    assert r.status_code == 200, r.text
    db.refresh(b)
    assert b.quantity == Decimal("95") and _sib_sum(db, sale) == Decimal("5")


def test_confirm_pending_deducts_batches(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=100)
    b = _batch(db, w["ca"], p, w["wha"], 50, price="600")
    sale = _pending_sale(db, w, p, qty=4, price=1000)
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json={"status": "completed"})
    assert r.status_code == 200, r.text
    db.refresh(b)
    assert b.quantity == Decimal("46") and _sib_sum(db, sale) == Decimal("4")
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()
    assert item.cost_price == Decimal("600")
    # Pending'ga qaytarilsa partiya ham qaytadi
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json={"status": "pending"})
    assert r.status_code == 200, r.text
    db.refresh(b)
    assert b.quantity == Decimal("50") and _sib_sum(db, sale) == Decimal("0")


def test_edit_keeps_variant_and_deducts_variant_row(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    v_l = ProductVariant(product_id=p.id, name="L", sku=f"VL{next(_seq)}")
    db.add(v_l)
    db.flush()
    _stock(db, p, w["wha"], 8, variant_id=v_l.id)
    sale = create_sale(db, _sale_data(
        [{"product_id": p.id, "quantity": 2, "unit_price": 1000, "variant_id": v_l.id}],
        w["wha"], payments=[{"type": "cash", "amount": 2000}],
    ), w["admin"])
    body = {"items": [{"product_id": p.id, "quantity": 3, "unit_price": 1000, "variant_id": v_l.id}],
            "payment_type": "cash", "paid_amount": 3000, "payments": [{"type": "cash", "amount": 3000}],
            "warehouse_id": w["wha"].id}
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json=body)
    assert r.status_code == 200, r.text
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()
    assert item.variant_id == v_l.id
    assert _qty(db, p, w["wha"], v_l.id) == Decimal("5")
    assert _qty(db, p, w["wha"]) == Decimal("10")
    # Boshqa mahsulot varianti — 404
    p2 = _product(db, w["ca"], w["wha"], qty=10)
    body["items"][0]["product_id"] = p2.id
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json=body)
    assert r.status_code == 404


def test_confirm_pending_deducts_variant_and_line_warehouse(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    v_l = ProductVariant(product_id=p.id, name="L", sku=f"VL{next(_seq)}")
    db.add(v_l)
    db.flush()
    _stock(db, p, w["whb"], 8, variant_id=v_l.id)
    sale = _pending_sale(db, w, p, qty=5, price=1000, wh=w["wha"])
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()
    item.variant_id = v_l.id
    item.warehouse_id = w["whb"].id
    db.flush()
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json={"status": "completed"})
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["whb"], v_l.id) == Decimal("3")
    assert _qty(db, p, w["wha"]) == Decimal("10")
    assert db.query(StockLevel).filter(StockLevel.product_id == p.id, StockLevel.variant_id.is_(None),
                                       StockLevel.quantity < 0).count() == 0


# ── 8-9. Qaytarish bilan bog'liq sotuvlar ────────────────────────────────────

def _partial_return(db, client, w, sale, qty):
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).first()
    r = client.login(w["admin"]).post(f"/api/sales/{sale.id}/return-items", json={
        "items": [{"sale_item_id": item.id, "quantity": qty}], "payment_type": "cash",
    })
    assert r.status_code == 200, r.text
    return db.query(Sale).filter(Sale.original_sale_id == sale.id).one()


def test_returned_sale_and_return_doc_cannot_be_deleted_or_edited(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=50)
    sale = _cash_sale(db, w, p, qty=10, price=1000)
    assert _qty(db, p, w["wha"]) == Decimal("40")
    ret = _partial_return(db, client, w, sale, 4)
    assert _qty(db, p, w["wha"]) == Decimal("44")
    assert ret.number.startswith("R") and ret.original_sale_id == sale.id
    db.refresh(sale)
    assert sale.status == SaleStatus.partial_refund
    expenses_before = db.query(Transaction).filter(Transaction.type == "expense").count()

    c = client.login(w["admin"])
    r = c.delete(f"/api/sales/{sale.id}")
    assert r.status_code == 400 and "o'chirib" in r.json()["detail"]
    r = c.put(f"/api/sales/{sale.id}", json={"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}],
                                            "payment_type": "cash", "paid_amount": 1000})
    assert r.status_code == 400 and "tahrirlab" in r.json()["detail"]
    r = c.put(f"/api/sales/{sale.id}", json={"status": "completed"})
    assert r.status_code == 400
    r = c.put(f"/api/sales/{sale.id}", json={"paid_amount": 20000})
    assert r.status_code == 400
    # Faqat izoh ruxsat
    r = c.put(f"/api/sales/{sale.id}", json={"note": "izoh"})
    assert r.status_code == 200, r.text
    # Qaytarish hujjati
    r = c.delete(f"/api/sales/{ret.id}")
    assert r.status_code == 400
    r = c.put(f"/api/sales/{ret.id}", json={"status": "completed"})
    assert r.status_code == 400

    assert _qty(db, p, w["wha"]) == Decimal("44")
    assert db.query(Transaction).filter(Transaction.type == "expense").count() == expenses_before


def test_partial_return_sets_original_sale_id_and_restores_variant_line_warehouse(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    v_l = ProductVariant(product_id=p.id, name="L", sku=f"VL{next(_seq)}")
    db.add(v_l)
    db.flush()
    _stock(db, p, w["whb"], 8, variant_id=v_l.id)
    sale = create_sale(db, _sale_data(
        [{"product_id": p.id, "quantity": 3, "unit_price": 1000, "variant_id": v_l.id, "warehouse_id": w["whb"].id}],
        w["wha"], payments=[{"type": "cash", "amount": 3000}],
    ), w["admin"])
    assert _qty(db, p, w["whb"], v_l.id) == Decimal("5")
    ret = _partial_return(db, client, w, sale, 2)
    assert ret.original_sale_id == sale.id
    assert _qty(db, p, w["whb"], v_l.id) == Decimal("7")
    assert _qty(db, p, w["wha"]) == Decimal("10")
    ret_item = db.query(SaleItem).filter(SaleItem.sale_id == ret.id).one()
    assert ret_item.variant_id == v_l.id and ret_item.warehouse_id == w["whb"].id
    # Qaytarish partiyasi ham variant va ombor bilan
    rb = db.query(Batch).filter(Batch.lot_number == f"sale_refund-{ret.id}").one()
    assert rb.variant_id == v_l.id and rb.warehouse_id == w["whb"].id


# ── 10. pending -> cancelled / completed -> cancelled ────────────────────────

def test_pending_to_cancelled_does_not_touch_stock_or_debt(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    cust = _customer(db, w["ca"], debt=0)
    sale = _pending_sale(db, w, p, qty=5, price=1000, customer=cust)
    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json={"status": "cancelled", "paid_amount": 0})
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["wha"]) == Decimal("10")
    db.refresh(cust)
    assert Decimal(str(cust.debt_balance or 0)) == Decimal("0")
    assert db.query(StockMovement).filter(StockMovement.reference_id == sale.id).count() == 0
    assert db.query(SalePayment).filter(SalePayment.sale_id == sale.id).count() == 0


def test_completed_to_cancelled_full_reverse(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    b = _batch(db, w["ca"], p, w["wha"], 10)
    cust = _customer(db, w["ca"], debt=0)
    sale = create_sale(db, _sale_data(
        [{"product_id": p.id, "quantity": 4, "unit_price": 1000}], w["wha"],
        payments=[{"type": "cash", "amount": 3000}, {"type": "debt", "amount": 1000}],
        customer_id=cust.id, payment_type="mixed",
    ), w["admin"])
    db.refresh(cust)
    assert Decimal(str(cust.debt_balance)) == Decimal("1000")
    assert _wallet_balance(db, w["wallet"]) == Decimal("3000")

    r = client.login(w["admin"]).put(f"/api/sales/{sale.id}", json={"status": "cancelled"})
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["wha"]) == Decimal("10")
    db.refresh(b)
    assert b.quantity == Decimal("10")
    db.refresh(cust)
    assert Decimal(str(cust.debt_balance or 0)) == Decimal("0")
    assert _wallet_balance(db, w["wallet"]) == Decimal("0")
    assert _cash_balance(db, w["wallet"]) == 0
    assert len(_kms(db, sale, "sale_cancel")) == 1
    assert db.query(Transaction).filter(Transaction.reference_id == sale.id, Transaction.type == "income").count() == 0
    # Sotuv qatori qoladi
    db.refresh(sale)
    assert sale.status == SaleStatus.cancelled
    # Bekor qilingan sotuvni o'chirish — 400
    assert client.login(w["admin"]).delete(f"/api/sales/{sale.id}").status_code == 400


# ── 11. Takroriy o'chirish ───────────────────────────────────────────────────

def test_second_delete_is_404_and_stock_not_doubled(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    sale = _cash_sale(db, w, p, qty=3, price=1000)
    c = client.login(w["admin"])
    assert c.delete(f"/api/sales/{sale.id}").status_code == 200
    assert c.delete(f"/api/sales/{sale.id}").status_code == 404
    assert _qty(db, p, w["wha"]) == Decimal("10")
    assert _wallet_balance(db, w["wallet"]) == Decimal("0")


# ── Ikki korxona izolyatsiyasi ───────────────────────────────────────────────

def test_other_company_cannot_delete_or_edit(db, client, w):
    p = _product(db, w["ca"], w["wha"], qty=10)
    sale = _cash_sale(db, w, p, qty=1, price=1000)
    cb = client.login(w["admin_b"])
    assert cb.delete(f"/api/sales/{sale.id}").status_code == 404
    assert cb.put(f"/api/sales/{sale.id}", json={"status": "cancelled"}).status_code == 404
    assert cb.put(f"/api/sales/{sale.id}", json={"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1}],
                                              "payment_type": "cash", "paid_amount": 1}).status_code == 404
    assert _qty(db, p, w["wha"]) == Decimal("9")
    assert _wallet_balance(db, w["wallet"]) == Decimal("1000")
    assert _wallet_balance(db, w["wallet_b"]) == Decimal("0")
    # O'z korxonasi — ishlaydi
    assert client.login(w["admin"]).delete(f"/api/sales/{sale.id}").status_code == 200
    assert _qty(db, p, w["wha"]) == Decimal("10")


# ── Regressiya: create_sale yozuvlari avvalgidek ─────────────────────────────

def test_create_sale_regression_records(db, w):
    p = _product(db, w["ca"], w["wha"], qty=100)
    _batch(db, w["ca"], p, w["wha"], 2, price="400")
    _batch(db, w["ca"], p, w["wha"], 10, price="500")
    cust = _customer(db, w["ca"])

    # payments ro'yxati: cash + card + debt
    sale = create_sale(db, _sale_data(
        [{"product_id": p.id, "quantity": 4, "unit_price": 1000}], w["wha"],
        payments=[{"type": "cash", "amount": 2000}, {"type": "card", "amount": 1000}, {"type": "debt", "amount": 1000}],
        customer_id=cust.id, payment_type="mixed",
    ), w["admin"])
    sps = db.query(SalePayment).filter(SalePayment.sale_id == sale.id).all()
    assert sorted((s.payment_type, s.amount) for s in sps) == [("card", Decimal("1000")), ("cash", Decimal("2000")), ("debt", Decimal("1000"))]
    txs = db.query(Transaction).filter(Transaction.reference_type == "sale", Transaction.reference_id == sale.id).all()
    assert sorted((t.payment_type, t.amount) for t in txs) == [("card", Decimal("1000")), ("cash", Decimal("2000"))]
    assert all(t.type == "income" and t.wallet_id == w["wallet"].id and t.currency_code == "UZS"
               and t.branch_id == w["ba"].id and t.description.startswith("Sotuv to'lovi #") for t in txs)
    kms = _kms(db, sale, "sale")
    assert sorted((m.payment_type, m.amount) for m in kms) == [("card", Decimal("1000")), ("cash", Decimal("2000"))]
    assert all(m.direction == "in" and m.currency == "UZS" and m.session_id is not None
               and m.created_by == w["admin"].id and m.description == f"Sotuv #{sale.number}" for m in kms)
    assert _wallet_balance(db, w["wallet"]) == Decimal("3000")
    # FIFO: 2 ta 400 dan, 2 ta 500 dan -> tannarx 450
    sibs = db.query(SaleItemBatch).join(SaleItem, SaleItem.id == SaleItemBatch.sale_item_id).filter(SaleItem.sale_id == sale.id).all()
    assert sorted((s.quantity, s.unit_cost) for s in sibs) == [(Decimal("2"), Decimal("400")), (Decimal("2"), Decimal("500"))]
    item = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).one()
    assert item.cost_price == Decimal("450")
    assert _qty(db, p, w["wha"]) == Decimal("96")

    # Aralash (paid_cash/paid_card) va bitta tur
    s2 = create_sale(db, _sale_data([{"product_id": p.id, "quantity": 1, "unit_price": 1000}], w["wha"],
                                    payment_type="mixed", paid_amount=Decimal("1000"), paid_cash=Decimal("600"),
                                    paid_card=Decimal("400")), w["admin"])
    assert sorted((s.payment_type, s.amount) for s in db.query(SalePayment).filter(SalePayment.sale_id == s2.id)) == [("card", Decimal("400")), ("cash", Decimal("600"))]
    assert db.query(Transaction).filter(Transaction.reference_id == s2.id, Transaction.reference_type == "sale").count() == 2
    assert len(_kms(db, s2, "sale")) == 2
    s3 = create_sale(db, _sale_data([{"product_id": p.id, "quantity": 1, "unit_price": 1000}], w["wha"],
                                    payment_type="card", paid_amount=Decimal("1000")), w["admin"])
    assert [(s.payment_type, s.amount) for s in db.query(SalePayment).filter(SalePayment.sale_id == s3.id)] == [("card", Decimal("1000"))]
    assert db.query(Transaction).filter(Transaction.reference_id == s3.id, Transaction.reference_type == "sale").count() == 1
    assert len(_kms(db, s3, "sale")) == 1
    assert _wallet_balance(db, w["wallet"]) == Decimal("5000")
    # Qarz: SalePayment bor, Transaction/KassaMovement yo'q
    s4 = create_sale(db, _sale_data([{"product_id": p.id, "quantity": 1, "unit_price": 1000}], w["wha"],
                                    payment_type="debt", paid_amount=Decimal("0"), customer_id=cust.id), w["admin"])
    assert db.query(Transaction).filter(Transaction.reference_id == s4.id, Transaction.reference_type == "sale").count() == 0
    assert len(_kms(db, s4, "sale")) == 0


def test_migration_file_syntax_and_backfill_sql():
    """Migratsiya ishga tushirilmaydi (PG regex); fayl tuzilishi va backfill SQL matni tekshiriladi."""
    import importlib.util, os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions", "t030_sales_original_sale_id.py")
    spec = importlib.util.spec_from_file_location("t030_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "t0_30" and mod.down_revision == 't028'
    src = open(path, encoding="utf-8").read()
    assert "original_sale_id" in src and "ix_sales_original_sale_id" in src
    assert "Qisman qaytarish (Sotuv #%)" in src and "substring(r.note from 'Sotuv #([^)]+)')" in src
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_kassa_movements_ref" in src
