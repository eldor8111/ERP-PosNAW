"""T1.9 — sales.branch_id snapshot va yagona filial atributsiyasi.

Qamrov: sotuv yaratishda branch_id (ombor -> kassir -> birinchi faol filial) va tranzaksiya filiali = sotuv
filiali; qator omborlari bir filialdan bo'lishi (400); tahrirda filial va tranzaksiyalar o'zgarmasligi
(boshqa filial admini), ombor o'zgarsa faqat admin/direktor; qaytarish hujjati asl sotuv filialini
oladi; ombor PATCH bilan ko'chirilgandan keyin hisobot (snapshot) o'zgarmasligi + audit; filial
hisobotlari Sale.branch_id bo'yicha va filiallar yig'indisi jami bilan teng; NULL-omborli sotuv o'z
filialida ro'yxatda ko'rinishi; buyurtma yetkazish haqi sotuv filialida; javobda filial nomi (chek);
resolve_branch_id / resolve_txn_branch tartibi va korxona filtri; ikki korxona izolyatsiyasi;
migratsiya backfill (SQLite'da).

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_9.py -q -p no:cacheprovider
"""
import importlib.util
import itertools
import os
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.audit_log import AuditLog
from app.models.branch import Branch
from app.models.inventory import StockLevel
from app.models.moliya import Expense, KassaSession, Transaction, Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.user import UserRole
from app.schemas.sale import SaleCreate
from app.services.sale_create import create_sale
from app.services.sale_helpers import (
    SALE_MIXED_BRANCH, apply_sale_branch_filter, branch_of_sale, resolve_branch_id, resolve_txn_branch,
)

_seq = itertools.count(1)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company, price="1000"):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T19-{n}", barcode=f"B19-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal(price))
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty=100):
    s = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


def _wallet(db, company, branch):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"),
               company_id=company.id, branch_id=branch.id if branch else None, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _data(items, wh_id, amount):
    return SaleCreate(items=items, payment_type="cash", warehouse_id=wh_id,
                      payments=[{"type": "cash", "amount": amount}], paid_amount=Decimal(amount))


def _sell(db, user, product, wh, qty=1, price=1000):
    return create_sale(db, _data(
        [{"product_id": product.id, "quantity": qty, "unit_price": price}],
        wh.id if wh else None, qty * price), user)


def _tx(db, sale):
    return db.query(Transaction).filter(
        Transaction.reference_type == "sale", Transaction.reference_id == sale.id,
    ).all()


@pytest.fixture
def w(db, mk):
    """A korxona: a1 (wh1, wh1b), a2 (wh2); adminlar; kassir; kassa. B korxona: admin + ombor + sotuv."""
    ca, a1, wh1, admin1 = mk.tenant(UserRole.admin)
    wh1b = mk.warehouse(ca, a1, name="Ombor A1-b")
    a2 = mk.branch(ca, "Filial A-2")
    wh2 = mk.warehouse(ca, a2, name="Ombor A2")
    admin2 = mk.user(ca, role=UserRole.admin, branch=a2)
    cashier1 = mk.user(ca, role=UserRole.cashier, branch=a1)
    manager1 = mk.user(ca, role=UserRole.manager, branch=a1)
    _wallet(db, ca, a1)
    p = _product(db, ca)
    for wh in (wh1, wh1b, wh2):
        _stock(db, p, wh)
    cb, b1, whb, admin_b = mk.tenant(UserRole.admin)
    _wallet(db, cb, b1)
    pb = _product(db, cb)
    _stock(db, pb, whb)
    return dict(ca=ca, a1=a1, a2=a2, wh1=wh1, wh1b=wh1b, wh2=wh2, admin1=admin1, admin2=admin2,
                cashier1=cashier1, manager1=manager1, p=p, cb=cb, b1=b1, whb=whb, admin_b=admin_b, pb=pb)


# ── 1. Yaratish: Sale.branch_id va tranzaksiya filiali ───────────────────────

def test_sale_branch_is_warehouse_branch_and_tx_follow(db, w):
    # a1 filial admini a2 omboridan sotadi: sotuv va pul a2 ga yoziladi (kassir filialiga emas)
    sale = _sell(db, w["admin1"], w["p"], w["wh2"])
    assert sale.branch_id == w["a2"].id
    txs = _tx(db, sale)
    assert txs and all(t.branch_id == w["a2"].id for t in txs)


def test_sale_own_branch_warehouse(db, w):
    sale = _sell(db, w["cashier1"], w["p"], w["wh1"])
    assert sale.branch_id == w["a1"].id
    assert all(t.branch_id == w["a1"].id for t in _tx(db, sale))


def test_branchless_warehouse_falls_back_to_user_branch(db, mk, w):
    wh_free = mk.warehouse(w["ca"], None, name="Filialsiz ombor")
    _stock(db, w["p"], wh_free)
    sale = _sell(db, w["admin2"], w["p"], wh_free)
    assert sale.branch_id == w["a2"].id
    assert all(t.branch_id == w["a2"].id for t in _tx(db, sale))


def test_no_user_branch_no_warehouse_branch_first_active_branch(db, mk):
    c = mk.company()
    inactive = mk.branch(c, "Nofaol", is_active=False)
    first = mk.branch(c, "Birinchi faol")
    mk.branch(c, "Ikkinchi faol")
    wh_free = mk.warehouse(c, None)
    admin = mk.user(c, role=UserRole.admin, branch=None)
    _wallet(db, c, first)
    p = _product(db, c)
    _stock(db, p, wh_free)
    sale = _sell(db, admin, p, wh_free)
    assert inactive.id < first.id
    assert sale.branch_id == first.id
    assert all(t.branch_id == first.id for t in _tx(db, sale))


def test_pending_sale_gets_branch(db, w):
    from app.services.sale_create import create_pending_sale
    data = SaleCreate(items=[{"product_id": w["p"].id, "quantity": 1, "unit_price": 1000}],
                      payment_type="cash", warehouse_id=w["wh2"].id, paid_amount=Decimal("0"))
    sale = create_pending_sale(db, data, w["admin1"])
    assert sale.status == SaleStatus.pending and sale.branch_id == w["a2"].id


def test_items_from_other_branch_warehouse_400(db, w):
    from fastapi import HTTPException
    data = _data([{"product_id": w["p"].id, "quantity": 1, "unit_price": 1000, "warehouse_id": w["wh2"].id}],
                 w["wh1"].id, 1000)
    with pytest.raises(HTTPException) as e:
        create_sale(db, data, w["admin1"])
    assert e.value.status_code == 400 and e.value.detail == SALE_MIXED_BRANCH
    assert db.query(Sale).count() == 0


def test_items_from_same_branch_other_warehouse_ok(db, w):
    data = _data([{"product_id": w["p"].id, "quantity": 1, "unit_price": 1000, "warehouse_id": w["wh1b"].id}],
                 w["wh1"].id, 1000)
    sale = create_sale(db, data, w["admin1"])
    assert sale.branch_id == w["a1"].id


# ── 2. Tahrir: filial va tranzaksiyalar o'zgarmaydi ──────────────────────────

def _edit_body(p, amount=2000, **extra):
    body = {"items": [{"product_id": p.id, "quantity": 2, "unit_price": amount // 2}],
            "payment_type": "cash", "paid_amount": amount, "payments": [{"type": "cash", "amount": amount}]}
    body.update(extra)
    return body


def test_other_branch_admin_edit_keeps_branch_and_tx_branch(client, db, w):
    sale = _sell(db, w["cashier1"], w["p"], w["wh1"])
    assert sale.branch_id == w["a1"].id
    r = client.login(w["admin2"]).put(f"/api/sales/{sale.id}", json=_edit_body(w["p"]))
    assert r.status_code == 200, r.text
    assert r.json()["branch_id"] == w["a1"].id
    db.refresh(sale)
    assert sale.branch_id == w["a1"].id
    txs = _tx(db, sale)
    assert txs and all(t.branch_id == w["a1"].id for t in txs)
    assert sum(Decimal(str(t.amount)) for t in txs) == Decimal("2000")


def test_edit_warehouse_to_other_branch_admin_moves_sale_branch(client, db, w):
    sale = _sell(db, w["cashier1"], w["p"], w["wh1"])
    r = client.login(w["admin1"]).put(f"/api/sales/{sale.id}", json=_edit_body(w["p"], warehouse_id=w["wh2"].id))
    assert r.status_code == 200, r.text
    db.refresh(sale)
    assert sale.warehouse_id == w["wh2"].id and sale.branch_id == w["a2"].id
    assert all(t.branch_id == w["a2"].id for t in _tx(db, sale))


def test_edit_warehouse_to_other_branch_non_admin_403(client, db, w):
    sale = _sell(db, w["manager1"], w["p"], w["wh1"])
    r = client.login(w["manager1"]).put(f"/api/sales/{sale.id}", json=_edit_body(w["p"], warehouse_id=w["wh2"].id))
    assert r.status_code == 403, r.text
    db.refresh(sale)
    assert sale.warehouse_id == w["wh1"].id and sale.branch_id == w["a1"].id


def test_edit_warehouse_same_branch_keeps_branch(client, db, w):
    sale = _sell(db, w["manager1"], w["p"], w["wh1"])
    r = client.login(w["manager1"]).put(f"/api/sales/{sale.id}", json=_edit_body(w["p"], warehouse_id=w["wh1b"].id))
    assert r.status_code == 200, r.text
    db.refresh(sale)
    assert sale.warehouse_id == w["wh1b"].id and sale.branch_id == w["a1"].id


# ── 3. O'chirish va qaytarish asl filialda ───────────────────────────────────

def test_delete_other_branch_admin_removes_sale_tx(client, db, w):
    sale = _sell(db, w["cashier1"], w["p"], w["wh1"])
    sid = sale.id
    r = client.login(w["admin2"]).delete(f"/api/sales/{sid}")
    assert r.status_code == 200, r.text
    assert db.query(Transaction).filter(Transaction.reference_type == "sale", Transaction.reference_id == sid,
                                        Transaction.type == "income").count() == 0


def test_return_document_inherits_original_sale_branch(db, w):
    orig = _sell(db, w["cashier1"], w["p"], w["wh1"])
    # Qaytarish hujjati boshqa filial xodimi nomidan, hatto ombor ko'rsatilmasa ham asl filialni oladi
    ret = Sale(number="R-T19-1", cashier_id=w["admin2"].id, company_id=w["ca"].id, total_amount=Decimal("1000"),
               paid_amount=Decimal("1000"), payment_type=PaymentType.cash, status=SaleStatus.refunded,
               original_sale_id=orig.id)
    db.add(ret)
    db.flush()
    assert ret.branch_id == orig.branch_id == w["a1"].id


def test_partial_return_api_keeps_original_branch(client, db, w):
    orig = _sell(db, w["cashier1"], w["p"], w["wh1"], qty=2)
    item = orig.items[0]
    r = client.login(w["admin2"]).post(
        f"/api/sales/{orig.id}/return-items", json={"items": [{"sale_item_id": item.id, "quantity": 1}]})
    assert r.status_code == 200, r.text
    ret = db.query(Sale).filter(Sale.original_sale_id == orig.id).first()
    assert ret is not None and ret.branch_id == w["a1"].id


# ── 4. Ombor ko'chirilsa tarix o'zgarmaydi (snapshot) + audit ────────────────

def test_warehouse_move_keeps_branch_reports_and_audits(client, db, w):
    _sell(db, w["cashier1"], w["p"], w["wh1"], qty=3)
    def report(branch):
        r = client.login(w["admin1"]).get(f"/api/reports/profit-loss?branch_id={branch.id}")
        assert r.status_code == 200, r.text
        return r.json()["gross_revenue"]
    before_a1, before_a2 = report(w["a1"]), report(w["a2"])
    assert before_a1 == 3000 and before_a2 == 0
    r = client.login(w["admin1"]).patch(f"/api/warehouses/{w['wh1'].id}", json={"branch_id": w["a2"].id})
    assert r.status_code == 200, r.text
    assert report(w["a1"]) == before_a1 and report(w["a2"]) == before_a2
    log = db.query(AuditLog).filter(AuditLog.action == "WAREHOUSE_BRANCH_CHANGE",
                                    AuditLog.entity_id == w["wh1"].id).first()
    assert log is not None


# ── 5. Hisobotlar: Sale.branch_id bo'yicha, Σ filiallar == jami ──────────────

def test_reports_sum_of_branches_equals_total(client, db, w):
    _sell(db, w["cashier1"], w["p"], w["wh1"], qty=2)            # a1: 2000
    _sell(db, w["admin1"], w["p"], w["wh2"], qty=5)              # a2 omboridan a1 admini: a2: 5000
    wh_free = None
    # NULL-omborli sotuv (xizmat): filial hisobotida o'z filialida ko'rinishi uchun branch_id bilan
    db.add(Sale(number="S-T19-NULLWH", cashier_id=w["cashier1"].id, company_id=w["ca"].id,
                branch_id=w["a1"].id, warehouse_id=wh_free, total_amount=Decimal("700"),
                paid_amount=Decimal("700"), payment_type=PaymentType.cash, status=SaleStatus.completed))
    db.flush()
    c = client.login(w["admin1"])

    def pl(branch=None):
        q = f"?branch_id={branch.id}" if branch else ""
        r = c.get(f"/api/reports/profit-loss{q}")
        assert r.status_code == 200, r.text
        return r.json()["gross_revenue"]

    total = pl()
    assert total == 7700
    assert pl(w["a1"]) == 2700 and pl(w["a2"]) == 5000
    assert pl(w["a1"]) + pl(w["a2"]) == total

    def sales_rep(branch=None):
        q = f"?branch_id={branch.id}" if branch else ""
        r = c.get(f"/api/reports/sales{q}")
        assert r.status_code == 200, r.text
        return sum(r.json()["summary"]["sales_by_currency"].values())

    assert sales_rep() == 7700
    assert sales_rep(w["a1"]) + sales_rep(w["a2"]) == sales_rep()
    assert sales_rep(w["a2"]) == 5000

    # Dashboard (summary): sotuv filtri Sale.branch_id bo'yicha
    def dash(branch=None):
        d1 = (datetime.utcnow() - timedelta(days=1)).date().isoformat()
        d2 = (datetime.utcnow() + timedelta(days=1)).date().isoformat()
        q = f"&branch_id={branch.id}" if branch else ""
        r = c.get(f"/api/dashboard/summary?date_from={d1}&date_to={d2}{q}")
        assert r.status_code == 200, r.text
        return r.json()["sales"]["revenue"]

    assert dash() == 7700
    assert dash(w["a1"]) == 2700 and dash(w["a2"]) == 5000

    # Mahsulot hisoboti (sales_report._sale_filters): qator miqdori filial bo'yicha bo'linadi
    def top_qty(branch=None):
        q = f"?branch_id={branch.id}" if branch else ""
        r = c.get(f"/api/reports/top-products{q}")
        assert r.status_code == 200, r.text
        return sum(x["total_qty"] for x in r.json())

    assert top_qty() == 7 and top_qty(w["a1"]) == 2 and top_qty(w["a2"]) == 5


def test_pnl_other_income_and_expense_same_branch_rule(client, db, w):
    # Daromad (Sale.branch_id) va xarajat (Expense.branch_id) bir qoida bilan filialga bog'lanadi
    _sell(db, w["admin1"], w["p"], w["wh2"], qty=4)  # a2: 4000
    c = client.login(w["admin1"])
    r2 = c.get(f"/api/reports/profit-loss?branch_id={w['a2'].id}")
    r1 = c.get(f"/api/reports/profit-loss?branch_id={w['a1'].id}")
    assert r2.json()["gross_revenue"] == 4000 and r1.json()["gross_revenue"] == 0


# ── 6. Ro'yxat/detal: NULL-omborli sotuv, filial nomi, izolyatsiya ────────────

def test_cashier_sees_own_branch_sale_without_warehouse(client, db, w):
    s = Sale(number="S-T19-WHNULL", cashier_id=w["admin1"].id, company_id=w["ca"].id, branch_id=w["a1"].id,
             total_amount=Decimal("100"), paid_amount=Decimal("100"), payment_type=PaymentType.cash,
             status=SaleStatus.completed)
    db.add(s)
    db.flush()
    r = client.login(w["cashier1"]).get("/api/sales/")
    assert r.status_code == 200, r.text
    assert s.id in [x["id"] for x in r.json()]
    other = [x for x in client.login(w["admin2"]).get(f"/api/sales/?branch_id={w['a2'].id}").json()]
    assert s.id not in [x["id"] for x in other]


def test_sale_detail_and_list_have_branch_name(client, db, w):
    w["a1"].address = "Toshkent, Chilonzor"
    w["a1"].phone = "+998901112233"
    sale = _sell(db, w["cashier1"], w["p"], w["wh1"])
    c = client.login(w["cashier1"])
    d = c.get(f"/api/sales/{sale.id}")
    assert d.status_code == 200, d.text
    j = d.json()
    assert j["branch_id"] == w["a1"].id and j["branch_name"] == w["a1"].name
    assert j["branch_address"] == "Toshkent, Chilonzor" and j["branch_phone"] == "+998901112233"
    lst = c.get("/api/sales/").json()
    row = [x for x in lst if x["id"] == sale.id][0]
    assert row["branch_id"] == w["a1"].id and row["branch_name"] == w["a1"].name


def test_post_sales_response_has_branch_name(client, db, w):
    body = {"items": [{"product_id": w["p"].id, "quantity": 1, "unit_price": 1000}], "payment_type": "cash",
            "warehouse_id": w["wh1"].id, "paid_amount": 1000, "payments": [{"type": "cash", "amount": 1000}]}
    r = client.login(w["cashier1"]).post("/api/sales/", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["branch_name"] == w["a1"].name and r.json()["branch_id"] == w["a1"].id


def test_receipt_builder_uses_branch_name():
    src = open(os.path.join(ROOT, "frontend", "src", "utils", "receiptBuilder.js"), encoding="utf-8").read()
    assert "sale.branch_name || sale.account_name" in src


def test_company_isolation_sales_and_reports(client, db, w):
    sale_a = _sell(db, w["cashier1"], w["p"], w["wh1"])
    sale_b = _sell(db, w["admin_b"], w["pb"], w["whb"])
    assert sale_b.branch_id == w["b1"].id
    # B admini A sotuvini ko'rmaydi, A foydalanuvchisi B sotuvini ko'rmaydi
    assert client.login(w["admin_b"]).get(f"/api/sales/{sale_a.id}").status_code == 404
    assert client.login(w["admin1"]).get(f"/api/sales/{sale_b.id}").status_code == 404
    ids_b = [x["id"] for x in client.login(w["admin_b"]).get("/api/sales/").json()]
    assert sale_a.id not in ids_b and sale_b.id in ids_b
    # Begona filial bo'yicha hisobot: T2.1 dan beri 404 (avval bo'sh 200 edi)
    r = client.login(w["admin1"]).get(f"/api/reports/profit-loss?branch_id={w['b1'].id}")
    assert r.status_code == 404
    # Ijobiy yo'l: o'z sotuvi ishlaydi
    assert client.login(w["cashier1"]).get(f"/api/sales/{sale_a.id}").status_code == 200


def test_apply_sale_branch_filter_uses_snapshot(db, w):
    s_in = _sell(db, w["admin1"], w["p"], w["wh1"])
    s_out = _sell(db, w["admin1"], w["p"], w["wh2"])
    ids = [r[0] for r in apply_sale_branch_filter(db.query(Sale.id), db, w["cashier1"]).all()]
    assert s_in.id in ids and s_out.id not in ids
    # Ombor keyin boshqa filialga o'tsa ham kassirga ko'rinish o'zgarmaydi
    w["wh1"].branch_id = w["a2"].id
    db.flush()
    ids = [r[0] for r in apply_sale_branch_filter(db.query(Sale.id), db, w["cashier1"]).all()]
    assert s_in.id in ids and s_out.id not in ids


# ── 7. Buyurtma -> sotuv: yetkazish haqi sotuv filialida ─────────────────────

def test_delivery_fee_uses_sale_branch(db, w):
    from app.services.order_to_sale import record_delivery_fee
    sale = _sell(db, w["cashier1"], w["p"], w["wh1"])          # a1
    record_delivery_fee(db, sale, Decimal("30000"), "cash", w["admin2"])   # a2 xodimi bajaradi
    fee = db.query(Transaction).filter(Transaction.reference_type == "delivery_fee",
                                       Transaction.reference_id == sale.id).first()
    assert fee is not None and fee.branch_id == w["a1"].id


def test_order_group_to_sale_branch_matches_order_branch(db, mk, w):
    from app.models.order import Order
    from app.models.customer import Customer
    from app.services.order_to_sale import maybe_create_sale_for_delivered_group
    w["ca"].orders_auto_create_sale = True
    cust = Customer(name="Mijoz", phone="998900000001", company_id=w["ca"].id, branch_id=w["a2"].id)
    db.add(cust)
    db.flush()
    cols = {c.name for c in Order.__table__.columns}
    kw = dict(customer_id=cust.id, product_id=w["p"].id, quantity=1, unit_price=1000.0,
              total_amount=1000.0, branch_id=w["a2"].id, company_id=w["ca"].id,
              payment_type="cash", delivery_fee=0.0)
    order = Order(**{k: v for k, v in kw.items() if k in cols})
    db.add(order)
    db.flush()
    maybe_create_sale_for_delivered_group(db, [order], acting_user=w["admin1"])   # a1 admini bajaradi
    sale = db.get(Sale, order.sale_id) if order.sale_id else None
    assert sale is not None, "avto-sotuv yaratilmadi"
    assert sale.branch_id == w["a2"].id
    assert all(t.branch_id == w["a2"].id for t in _tx(db, sale))


# ── 8. resolve_* tartibi va korxona filtri ───────────────────────────────────

def test_resolve_branch_id_order_and_company_filter(db, mk, w):
    # ombor filiali foydalanuvchi filialidan ustun
    assert resolve_branch_id(db, w["admin1"], w["wh2"].id) == w["a2"].id
    # ombor yo'q -> foydalanuvchi filiali
    assert resolve_branch_id(db, w["admin1"]) == w["a1"].id
    # begona ombor e'tiborga olinmaydi (korxona filtri)
    assert resolve_branch_id(db, w["admin1"], w["whb"].id) == w["a1"].id
    # filialsiz admin + begona ombor -> korxonaning asosiy/birinchi faol filiali (begona emas)
    nb = mk.user(w["ca"], role=UserRole.admin, branch=None)
    got = resolve_branch_id(db, nb, w["whb"].id)
    assert got in (w["a1"].id, w["a2"].id)


def test_resolve_txn_branch_priority(db, mk, w):
    sale = _sell(db, w["admin1"], w["p"], w["wh2"])                   # branch a2
    # 1) sale.branch_id
    assert resolve_txn_branch(db, w["admin1"], sale=sale) == w["a2"].id
    # ombor filiali (sale.branch_id yo'q)
    s2 = Sale(number="S-T19-X", cashier_id=w["admin1"].id, company_id=w["ca"].id, branch_id=None,
              warehouse_id=w["wh1"].id)
    assert resolve_txn_branch(db, w["admin2"], sale=s2) == w["a1"].id
    assert resolve_txn_branch(db, w["admin2"], warehouse_id=w["wh1b"].id) == w["a1"].id
    # 3) wallet.branch_id
    wal = _wallet(db, w["ca"], w["a1"])
    assert resolve_txn_branch(db, w["admin2"], wallet=wal) == w["a1"].id
    # 4) foydalanuvchi filiali
    assert resolve_txn_branch(db, w["admin2"]) == w["a2"].id
    # begona ombor/begona filial e'tiborga olinmaydi
    assert resolve_txn_branch(db, w["admin2"], warehouse_id=w["whb"].id) == w["a2"].id
    # 5) birinchi faol filial
    nb = mk.user(w["ca"], role=UserRole.admin, branch=None)
    assert resolve_txn_branch(db, nb) == w["a1"].id


def test_branch_of_sale_snapshot_then_warehouse(db, w):
    s = Sale(number="S-T19-Y", cashier_id=w["admin1"].id, company_id=w["ca"].id, warehouse_id=w["wh2"].id)
    assert branch_of_sale(db, s) == w["a2"].id          # eski qator: ombor filiali
    s.branch_id = w["a1"].id
    assert branch_of_sale(db, s) == w["a1"].id          # snapshot ustun


# ── 9. Migratsiya ────────────────────────────────────────────────────────────

def _load_migration():
    path = os.path.join(ROOT, "alembic", "versions", "t1_9_sales_branch_id.py")
    spec = importlib.util.spec_from_file_location("t1_9_migration", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_metadata():
    m = _load_migration()
    assert m.revision == "t1_9" and m.down_revision == "t1_8"
    assert callable(m.upgrade) and callable(m.downgrade)


def test_migration_backfill_steps(db, mk, w):
    """Backfill SQL (a, b, d, e bosqichlari — SQLite'da to'g'ridan-to'g'ri; c — DISTINCT ON o'rniga
    ekvivalent MIN)."""
    from app.models.shift import Shift
    m = _load_migration()
    ca = w["ca"]

    def mk_sale(num, cashier, wh=None, shift=None):
        s = Sale(number=num, cashier_id=cashier.id, company_id=ca.id, warehouse_id=wh.id if wh else None,
                 shift_id=shift.id if shift else None, total_amount=Decimal("1"), paid_amount=Decimal("1"),
                 payment_type=PaymentType.cash, status=SaleStatus.completed)
        db.add(s)
        db.flush()
        db.execute(text("UPDATE sales SET branch_id = NULL WHERE id = :i"), {"i": s.id})
        db.expire(s)
        return s

    nobr = mk.user(ca, role=UserRole.cashier, branch=None)
    s_wh = mk_sale("M1", nobr, wh=w["wh2"])                              # a) ombor -> a2
    sh = Shift(cashier_id=nobr.id, company_id=ca.id, branch_id=w["a2"].id, status="open")
    db.add(sh)
    db.flush()
    s_shift = mk_sale("M2", nobr, shift=sh)                              # b) smena -> a2
    s_tx = mk_sale("M3", nobr)                                           # c) tranzaksiya -> a1
    db.add(Transaction(company_id=ca.id, branch_id=w["a1"].id, type="income", amount=Decimal("1"),
                       payment_type="cash", reference_type="sale", reference_id=s_tx.id))
    s_cash = mk_sale("M4", w["cashier1"])                                # d) kassir -> a1
    s_none = mk_sale("M5", nobr)                                         # ikki filialli korxona: NULL qoladi
    # begona korxona ombori bilan sotuv: filial yozilmasligi kerak (korxona sharti)
    s_foreign = mk_sale("M6", nobr, wh=w["whb"])
    # e) bitta filialli korxona
    c1 = mk.company()
    only = mk.branch(c1)
    u1 = mk.user(c1, role=UserRole.admin, branch=None)
    s_single = Sale(number="M7", cashier_id=u1.id, company_id=c1.id, total_amount=Decimal("1"),
                    paid_amount=Decimal("1"), payment_type=PaymentType.cash, status=SaleStatus.completed)
    db.add(s_single)
    db.flush()
    db.execute(text("UPDATE sales SET branch_id = NULL WHERE id = :i"), {"i": s_single.id})

    ids = [s_wh.id, s_shift.id, s_tx.id, s_cash.id, s_none.id, s_foreign.id, s_single.id]
    lo, hi = min(ids), max(ids)
    for name, sql in m.BACKFILL_STEPS:
        if name == "transaction":
            sql = sql.replace(
                "SELECT DISTINCT ON (reference_id) reference_id, branch_id", "SELECT reference_id, MIN(branch_id) AS branch_id"
            ).replace("ORDER BY reference_id, id", "GROUP BY reference_id")
        db.execute(text(sql), {"lo": lo, "hi": hi})

    def br(i):
        return db.execute(text("SELECT branch_id FROM sales WHERE id = :i"), {"i": i}).scalar()

    assert br(s_wh.id) == w["a2"].id
    assert br(s_shift.id) == w["a2"].id
    assert br(s_tx.id) == w["a1"].id
    assert br(s_cash.id) == w["a1"].id
    assert br(s_none.id) is None
    assert br(s_foreign.id) is None
    assert br(s_single.id) == only.id


def test_model_has_column_and_index():
    cols = {c.name for c in Sale.__table__.columns}
    assert "branch_id" in cols
    names = {i.name for i in Sale.__table__.indexes}
    assert "ix_sale_company_branch_created" in names and "ix_sales_branch_id" in names
