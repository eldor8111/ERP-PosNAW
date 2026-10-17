"""T3.8 — Unumdorlik: keshlash, N+1, paginatsiya.

Qamrov: `list_sales` (sale_items agregatsiyasi faqat sahifadagi sale_id'lar uchun), `get_kassa_balances`
(1 ta GROUP BY so'rovi, eski algoritm bilan golden), `list_shifts` (skip/limit, X-Total-Count, cashier N+1 yo'q),
`list_orders` (customer_id/date filtrlari), `get_movements` (kontragent nomlari ≤ 3 so'rovda), `get_chiqims`
(SQL guruhlash, storno, eski algoritm bilan golden), `inventory-counts` (limit ≤ 200, `prepopulate=false`,
tezkor revizya yakunlash), `/products/{id}/variants` (bitta GROUP BY), `list_customers` (karta bo'yicha qidiruv),
`summary-stats`, `categorize_customers` (golden, N+1 yo'q), Telegram telefon qidiruvi, `/finance/payments/income`
`customer_id`; frontend (fayl-matn) tekshiruvlari va i18n pending kalitlari.

Eslatma: test bazasi SQLite, shuning uchun Postgres'ga xos SQL (`jsonb_each_text`, `regexp_replace`) yo'llarida
Python zaxira shoxi tekshiriladi; Postgres SQL matni esa dialekt bilan kompilyatsiya qilinib tekshiriladi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_8.py -q -p no:cacheprovider
"""
import itertools
import json
import re
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import event

from app.models.customer import Customer
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.inventory_count import CountStatus, InventoryCount, InventoryCountItem
from app.models.moliya import KassaMovement, KassaSession, Transaction, Wallet
from app.models.order import Order
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.purchase_order import POStatus, PurchaseOrder
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.shift import Shift
from app.models.supplier import Supplier
from app.models.user import UserRole

D = Decimal
_seq = itertools.count(1)
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "src"
PENDING = ROOT / "tests" / "branch_audit" / "i18n_pending" / "T3.8.json"


# ── Yordamchilar ─────────────────────────────────────────────────────────────

@contextmanager
def count_sql(db):
    """Bajarilgan SQL so'rovlar ro'yxati (matn)."""
    stmts = []
    conn = db.get_bind()

    def _hook(conn_, cursor, statement, parameters, context, executemany):
        stmts.append(statement)

    event.listen(conn, "before_cursor_execute", _hook)
    try:
        yield stmts
    finally:
        event.remove(conn, "before_cursor_execute", _hook)


def _selects(stmts, table):
    return [s for s in stmts if s.lstrip().upper().startswith("SELECT") and re.search(rf"\b{table}\b", s)]


def _product(db, company, **kw):
    n = next(_seq)
    p = Product(name=kw.pop("name", f"Tovar {n}"), sku=f"T38-{n}", barcode=f"B38-{n}", company_id=company.id,
                cost_price=D("500"), sale_price=D("1000"), **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, warehouse, qty, variant=None):
    sl = StockLevel(product_id=product.id, warehouse_id=warehouse.id, quantity=D(qty),
                    variant_id=variant.id if variant else None)
    db.add(sl)
    db.flush()
    return sl


def _customer(db, company, name=None, phone=None, **kw):
    c = Customer(name=name or f"Mijoz {next(_seq)}", phone=phone, company_id=company.id, is_active=True, **kw)
    db.add(c)
    db.flush()
    return c


def _sale(db, user, company, warehouse, branch, customer=None, items=1, amount=1000, paid=None, created_at=None, **kw):
    n = next(_seq)
    paid = amount if paid is None else paid
    s = Sale(number=f"S38-{n}", cashier_id=user.id, company_id=company.id, warehouse_id=warehouse.id,
             branch_id=branch.id, customer_id=customer.id if customer else None,
             total_amount=D(amount), paid_amount=D(paid), paid_cash=D(paid),
             payment_type=PaymentType.cash, status=SaleStatus.completed, **kw)
    if created_at:
        s.created_at = created_at
    db.add(s)
    db.flush()
    if items:
        p = _product(db, company)
        for _ in range(items):
            db.add(SaleItem(sale_id=s.id, product_id=p.id, warehouse_id=warehouse.id, quantity=D("1"),
                            unit_price=D("1000"), cost_price=D("500"), subtotal=D("1000")))
        db.flush()
    return s


@pytest.fixture
def w(db, mk):
    """Korxona A (admin, filial, ombor) va korxona B (admin, filial, ombor)."""
    ca, ba, wha, admin = mk.tenant(UserRole.admin)
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    return dict(ca=ca, ba=ba, wha=wha, admin=admin, cb=cb, bb=bb, whb=whb, admin_b=admin_b)


# ── 1. list_sales: items_count faqat sahifadagi sale_id'lar uchun ────────────

def test_list_sales_items_count_page_only(client, db, w):
    s1 = _sale(db, w["admin"], w["ca"], w["wha"], w["ba"], items=3)
    s2 = _sale(db, w["admin"], w["ca"], w["wha"], w["ba"], items=1)
    s3 = _sale(db, w["admin"], w["ca"], w["wha"], w["ba"], items=0)
    # begona korxona sotuvi (ro'yxatda ko'rinmasligi kerak)
    sb = _sale(db, w["admin_b"], w["cb"], w["whb"], w["bb"], items=5)

    with count_sql(db) as stmts:
        r = client.login(w["admin"]).get("/api/sales/?limit=50")
    assert r.status_code == 200, r.text
    got = {row["id"]: row["items_count"] for row in r.json()}
    assert got == {s1.id: 3, s2.id: 1, s3.id: 0}
    assert sb.id not in got

    # sale_items bo'yicha agregatsiya faqat IN (...) bilan cheklangan; butun jadval GROUP BY yo'q
    si = _selects(stmts, "sale_items")
    assert si, "sale_items so'rovi bo'lishi kerak"
    for s in si:
        assert re.search(r"sale_items\.sale_id IN", s), s
    assert not any("GROUP BY sale_items.sale_id" in s and "sale_items.sale_id IN" not in s for s in stmts)
    # asosiy so'rovlarda sale_items subquery (outer join) yo'q
    main = [s for s in _selects(stmts, "sales") if "FROM sales" in s and "ORDER BY" in s]
    assert main and all("sale_items" not in s for s in main)
    assert len(stmts) <= 10


def test_list_sales_pagination_and_total(client, db, w):
    for _ in range(5):
        _sale(db, w["admin"], w["ca"], w["wha"], w["ba"], items=2)
    r = client.login(w["admin"]).get("/api/sales/?limit=2&skip=2")
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert r.headers["X-Total-Count"] == "5"
    assert all(x["items_count"] == 2 for x in r.json())


# ── 2. kassa: 1 ta GROUP BY so'rovi, eski algoritm bilan golden ──────────────

def _wallet(db, company, branch, name="Kassa"):
    wl = Wallet(name=f"{name} {next(_seq)}", type="cash", balance=D(0), company_id=company.id,
                branch_id=branch.id, is_active=True, is_open=True)
    db.add(wl)
    db.flush()
    return wl


def _km(db, wallet, direction, ptype, amount, currency="UZS"):
    db.add(KassaMovement(wallet_id=wallet.id, company_id=wallet.company_id, direction=direction,
                         payment_type=ptype, amount=D(amount), currency=currency))


def _old_kassa_balances(db, wallet_id):
    """Eski algoritm (golden): har bir to'lov turi/valyuta uchun alohida SUM."""
    from app.routers.kassa import PAYMENT_TYPES
    from sqlalchemy import func
    ptypes = list(PAYMENT_TYPES)
    extra = [r[0] for r in db.query(KassaMovement.payment_type).filter(KassaMovement.wallet_id == wallet_id).distinct()
             if r[0] not in ptypes]
    result, total = {}, {}
    for pt in ptypes + sorted(extra):
        curs = [r[0] for r in db.query(KassaMovement.currency).filter(
            KassaMovement.wallet_id == wallet_id, KassaMovement.payment_type == pt).distinct()]
        arr = []
        for cur in curs:
            def _sum(direction):
                return float(db.query(func.coalesce(func.sum(KassaMovement.amount), 0)).filter(
                    KassaMovement.wallet_id == wallet_id, KassaMovement.payment_type == pt,
                    KassaMovement.currency == cur, KassaMovement.direction == direction).scalar() or 0)
            bal = _sum("in") - _sum("out")
            if bal != 0:
                arr.append({"currency": cur, "value": bal})
                total[cur] = total.get(cur, 0) + bal
        result[pt] = arr
    result["total"] = [{"currency": k, "value": v} for k, v in total.items() if v != 0]
    return result


def _norm_bal(b):
    """Valyutalar tartibi ma'noga ega emas — valyuta bo'yicha tartiblab solishtiramiz."""
    return {k: sorted(v, key=lambda x: x["currency"]) for k, v in b.items()}


def test_kassa_balances_single_query_and_golden(db, w):
    from app.routers.kassa import get_kassa_balances, get_kassa_balances_bulk
    wl = _wallet(db, w["ca"], w["ba"])
    wl2 = _wallet(db, w["ca"], w["ba"])
    for pt in ("cash", "card", "click", "payme"):
        _km(db, wl, "in", pt, 1000)
        _km(db, wl, "out", pt, 300)
        _km(db, wl, "in", pt, 5, "USD")
    _km(db, wl, "in", "uzcard", 777)
    _km(db, wl, "in", "ajabo_tur", 11)          # noma'lum tur ham balansdan yo'qolmasin
    _km(db, wl2, "in", "cash", 50)
    db.flush()

    with count_sql(db) as stmts:
        got = get_kassa_balances(wl.id, db)
    assert len(_selects(stmts, "kassa_movements")) == 1
    assert len(stmts) == 1
    assert _norm_bal(got) == _norm_bal(_old_kassa_balances(db, wl.id))

    with count_sql(db) as stmts:
        bulk = get_kassa_balances_bulk(db, [wl.id, wl2.id])
    assert len(stmts) == 1
    assert _norm_bal(bulk[wl.id]) == _norm_bal(got)
    assert _norm_bal(bulk[wl2.id]) == _norm_bal(_old_kassa_balances(db, wl2.id))


def test_list_wallets_query_count_independent_of_wallets(client, db, w):
    wallets = [_wallet(db, w["ca"], w["ba"]) for _ in range(3)]
    for wl in wallets:
        for pt in ("cash", "card", "click"):
            _km(db, wl, "in", pt, 100)
    db.flush()
    with count_sql(db) as stmts:
        r = client.login(w["admin"]).get("/api/kassa")
    assert r.status_code == 200, r.text
    # kassa harakatlari bo'yicha bitta so'rov (kassalar soni va to'lov turlariga bog'liq emas)
    assert len(_selects(stmts, "kassa_movements")) == 1
    ids = {x["id"] for x in r.json()}
    assert {wl.id for wl in wallets} <= ids
    for x in r.json():
        assert x["balances"]["cash"][0]["value"] == 100


# ── 3. shifts: skip/limit, X-Total-Count, cashier N+1 yo'q ───────────────────

def _shift(db, company, branch, cashier, hours_ago):
    sh = Shift(cashier_id=cashier.id, branch_id=branch.id, company_id=company.id, status="closed",
               opened_at=datetime.utcnow() - timedelta(hours=hours_ago))
    db.add(sh)
    db.flush()
    return sh


def test_list_shifts_pagination_no_n_plus_one(client, db, mk, w):
    cashiers = [mk.user(w["ca"], role=UserRole.cashier, branch=w["ba"]) for _ in range(4)]
    shifts = [_shift(db, w["ca"], w["ba"], cashiers[i % 4], i + 1) for i in range(6)]
    sb = _shift(db, w["cb"], w["bb"], mk.user(w["cb"], role=UserRole.cashier, branch=w["bb"]), 1)

    with count_sql(db) as stmts:
        r = client.login(w["admin"]).get("/api/shifts?limit=2&skip=2")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) == 2
    assert r.headers["X-Total-Count"] == "6"
    assert all(row.get("cashier_name") for row in data)
    assert sb.id not in {row["id"] for row in data}
    # kassir nomlari uchun alohida users so'rovi yo'q (joinedload)
    user_only = [s for s in _selects(stmts, "users") if "FROM users" in s and "shifts" not in s]
    assert user_only == []
    # tartib: yangisi birinchi (opened_at DESC) -> 3-4 smena
    assert [row["id"] for row in data] == [shifts[2].id, shifts[3].id]


# ── 4. orders: customer_id va sana filtrlari ─────────────────────────────────

def _order(db, company, branch, customer, product, created_at=None):
    o = Order(company_id=company.id, customer_id=customer.id, branch_id=branch.id, product_id=product.id,
              quantity=1, unit_price=10, total_amount=10, payment_type="cash")
    if created_at:
        o.created_at = created_at
    db.add(o)
    db.flush()
    return o


def test_list_orders_customer_and_date_filters(client, db, w):
    c1 = _customer(db, w["ca"])
    c2 = _customer(db, w["ca"])
    p = _product(db, w["ca"])
    o_old = _order(db, w["ca"], w["ba"], c1, p, datetime(2026, 1, 10, 12, 0))
    o_new = _order(db, w["ca"], w["ba"], c1, p, datetime(2026, 3, 10, 12, 0))
    o_other = _order(db, w["ca"], w["ba"], c2, p, datetime(2026, 3, 10, 12, 0))

    api = client.login(w["admin"])
    ids = lambda r: {x["id"] for x in r.json()} if r.json() and "id" in r.json()[0] else r.json()  # noqa: E731
    r = api.get(f"/api/orders?customer_id={c1.id}")
    assert r.status_code == 200, r.text
    flat = json.dumps(r.json())
    assert str(o_old.id) in flat and str(o_new.id) in flat
    assert r.headers["X-Total-Count"] == "2"

    r = api.get(f"/api/orders?customer_id={c1.id}&date_from=2026-03-01&date_to=2026-03-31")
    assert r.status_code == 200
    assert r.headers["X-Total-Count"] == "1"

    r = api.get("/api/orders?date_from=2026-03-01&date_to=2026-03-31")
    assert r.headers["X-Total-Count"] == "2"          # c1 yangi + c2
    assert o_other.id and ids  # noqa: B018


def test_list_orders_foreign_company_isolated(client, db, w):
    cb = _customer(db, w["cb"])
    pb = _product(db, w["cb"])
    _order(db, w["cb"], w["bb"], cb, pb)
    # A foydalanuvchisi B mijozi bo'yicha so'rasa — hech narsa ko'rmaydi
    r = client.login(w["admin"]).get(f"/api/orders?customer_id={cb.id}")
    assert r.status_code == 200
    assert r.json() == [] and r.headers["X-Total-Count"] == "0"
    # B o'z mijozi bo'yicha ko'radi (ijobiy yo'l)
    r = client.login(w["admin_b"]).get(f"/api/orders?customer_id={cb.id}")
    assert r.headers["X-Total-Count"] == "1"


# ── 5. inventory/movements: kontragent nomlari ≤ 3 so'rovda ──────────────────

def _movement(db, product, warehouse, user, ref_type, ref_id, created_at=None):
    m = StockMovement(product_id=product.id, warehouse_id=warehouse.id, type=MovementType.IN, qty_before=0,
                      qty_after=1, quantity=1, reference_type=ref_type, reference_id=ref_id, user_id=user.id)
    if created_at:
        m.created_at = created_at
    db.add(m)
    db.flush()
    return m


def test_movements_contragent_batched_and_golden(client, db, w):
    ca, ba, wha, admin = w["ca"], w["ba"], w["wha"], w["admin"]
    p = _product(db, ca)
    sup = Supplier(name="Ta'minotchi X", company_id=ca.id, is_active=True)
    db.add(sup)
    db.flush()
    pos = []
    for i in range(3):
        po = PurchaseOrder(number=f"PO38-{next(_seq)}", supplier_id=sup.id, warehouse_id=wha.id, company_id=ca.id,
                           status=POStatus.sent, created_by=admin.id)
        db.add(po)
        db.flush()
        pos.append(po)
    cust = _customer(db, ca, name="Mijoz Z")
    sale_with = _sale(db, admin, ca, wha, ba, customer=cust, items=0)
    sale_without = _sale(db, admin, ca, wha, ba, customer=None, items=0)

    expected = {}
    t0 = datetime(2026, 5, 1, 10, 0)
    seq = 0
    for po in pos:
        seq += 1
        expected[_movement(db, p, wha, admin, "purchase_order", po.id, t0 + timedelta(minutes=seq)).id] = "Ta'minotchi X"
    for rt in ("sale", "return_from_customer", "customer_return", "sale_refund"):
        seq += 1
        expected[_movement(db, p, wha, admin, rt, sale_with.id, t0 + timedelta(minutes=seq)).id] = "Mijoz Z"
    seq += 1
    expected[_movement(db, p, wha, admin, "sale", sale_without.id, t0 + timedelta(minutes=seq)).id] = None
    seq += 1
    expected[_movement(db, p, wha, admin, "sale", 999999, t0 + timedelta(minutes=seq)).id] = "Noma'lum mijoz"
    seq += 1
    expected[_movement(db, p, wha, admin, "return_from_customer", 999999, t0 + timedelta(minutes=seq)).id] = None
    seq += 1
    expected[_movement(db, p, wha, admin, "return_to_supplier", sup.id, t0 + timedelta(minutes=seq)).id] = "Ta'minotchi X"
    seq += 1
    expected[_movement(db, p, wha, admin, "chiqim", 5, t0 + timedelta(minutes=seq)).id] = None
    seq += 1
    expected[_movement(db, p, wha, admin, "sale", None, t0 + timedelta(minutes=seq)).id] = None

    with count_sql(db) as stmts:
        r = client.login(admin).get("/api/inventory/movements?limit=500")
    assert r.status_code == 200, r.text
    got = {row["id"]: row["contragent_name"] for row in r.json()}
    assert got == expected
    contra = [s for s in stmts if re.search(r"FROM (purchase_orders|sales|suppliers)\b", s) and "stock_movements" not in s]
    assert len(contra) <= 3, contra


def test_movements_foreign_company_not_visible(client, db, w):
    pb = _product(db, w["cb"])
    _movement(db, pb, w["whb"], w["admin_b"], "chiqim", 1)
    r = client.login(w["admin"]).get("/api/inventory/movements")
    assert r.status_code == 200 and r.json() == []
    r = client.login(w["admin_b"]).get("/api/inventory/movements")
    assert len(r.json()) == 1


# ── 6. inventory/chiqims: SQL guruhlash (eski algoritm bilan golden) ─────────

def _old_chiqims(db, company_id, skip=0, limit=50):
    """Eski algoritm (golden): hammasini yuklab, Python'da guruhlash."""
    from app.models.warehouse import Warehouse
    from sqlalchemy import func
    movements = (db.query(StockMovement).join(Product).filter(Product.company_id == company_id)
                 .filter(StockMovement.reference_type == "chiqim")
                 .order_by(StockMovement.created_at.desc()).all())
    reverts = dict(
        db.query(StockMovement.reference_id, func.max(StockMovement.id))
        .join(Product, Product.id == StockMovement.product_id)
        .filter(Product.company_id == company_id, StockMovement.reference_type == "chiqim_revert")
        .group_by(StockMovement.reference_id).all()
    )
    groups = {}
    for m in movements:
        rid = m.reference_id
        if m.id < reverts.get(rid, 0):
            continue
        if rid not in groups:
            wh = db.get(Warehouse, m.warehouse_id) if m.warehouse_id else None
            groups[rid] = dict(reference_id=rid, created_at=m.created_at, type_hints=set(), doc_nums=set(),
                               reasons=set(), total_qty=D("0"), item_count=0,
                               user_name=m.user.name if m.user else None, warehouse_id=m.warehouse_id,
                               warehouse_name=wh.name if wh else None)
        g = groups[rid]
        g["total_qty"] += max(D("0"), m.quantity)
        g["item_count"] += 1
        rparts = [x.strip() for x in (m.reason or "").split("|")]
        if len(rparts) >= 1 and rparts[0]:
            g["type_hints"].add(rparts[0])
        if len(rparts) >= 2 and rparts[1].startswith("Hujjat: "):
            g["doc_nums"].add(rparts[1].replace("Hujjat: ", ""))
        elif len(rparts) >= 2:
            g["reasons"].add(rparts[1])
        if len(rparts) >= 3:
            g["reasons"].add(rparts[2])
    out = sorted(groups.values(), key=lambda x: x["created_at"], reverse=True)
    return out[skip: skip + limit]


def _chiqim_mv(db, product, wh, user, ref, qty, reason, minute, rtype="chiqim"):
    m = StockMovement(product_id=product.id, warehouse_id=wh.id, type=MovementType.OUT, qty_before=10,
                      qty_after=10 - qty, quantity=qty, reference_type=rtype, reference_id=ref, user_id=user.id,
                      reason=reason)
    m.created_at = datetime(2026, 6, 1, 9, 0) + timedelta(minutes=minute)
    db.add(m)
    db.flush()
    return m


def test_chiqims_sql_grouping_golden_and_paging(client, db, mk, w):
    ca, wha, admin = w["ca"], w["wha"], w["admin"]
    p1, p2 = _product(db, ca), _product(db, ca)
    u2 = mk.user(ca, role=UserRole.warehouse, branch=w["ba"])
    minute = 0
    for ref in range(1, 6):
        for pr in (p1, p2):
            minute += 1
            reason = {0: "Brak | Hujjat: D-%d | izoh%d" % (ref, ref), 1: "Yo'qotish | Hujjat: D-%d" % ref,
                      2: "Boshqa | sabab%d" % ref, 3: None, 4: "Brak"}[ref % 5]
            _chiqim_mv(db, pr, wha, admin if ref % 2 else u2, ref, ref, reason, minute)
    # ref=2 storno qilindi: eski qatorlar ro'yxatdan tushadi, undan keyingi qayta chiqim ko'rinadi
    _chiqim_mv(db, p1, wha, admin, 2, 1, "Brak", 100, rtype="chiqim_revert")
    _chiqim_mv(db, p1, wha, admin, 2, 7, "Qayta | Hujjat: D-2b", 101)
    # begona korxona chiqimi
    pb = _product(db, w["cb"])
    _chiqim_mv(db, pb, w["whb"], w["admin_b"], 77, 3, "Boshqa", 5)

    api = client.login(admin)
    expected = _old_chiqims(db, ca.id, 0, 200)
    assert len(expected) == 5
    with count_sql(db) as stmts:
        r = api.get("/api/inventory/chiqims?limit=200")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 5
    # xotira: movements ro'yxati emas, guruhlangan so'rovlar (≤ 5 ta SELECT)
    assert len(stmts) <= 5

    def norm(rows, from_api):
        res = []
        for g in rows:
            if from_api:
                res.append((g["reference_id"], D(str(g["total_qty"])), g["item_count"], g["user_name"],
                            g["warehouse_id"], g["warehouse_name"], sorted(g["type_hints"]),
                            sorted(g["doc_nums"]), sorted(g["reasons"])))
            else:
                res.append((g["reference_id"], g["total_qty"], g["item_count"], g["user_name"], g["warehouse_id"],
                            g["warehouse_name"], sorted(g["type_hints"]), sorted(g["doc_nums"]),
                            sorted(g["reasons"])))
        return res

    assert norm(r.json(), True) == norm(expected, False)
    assert 77 not in {g["reference_id"] for g in r.json()}

    # sahifalash (SQL OFFSET/LIMIT) eski natijaning shu kesimi bilan bir xil
    r2 = api.get("/api/inventory/chiqims?limit=2&skip=2")
    assert [g["reference_id"] for g in r2.json()] == [g["reference_id"] for g in _old_chiqims(db, ca.id, 2, 2)]


def test_chiqims_foreign_company_isolated(client, db, w):
    pb = _product(db, w["cb"])
    _chiqim_mv(db, pb, w["whb"], w["admin_b"], 5, 3, "Boshqa", 1)
    assert client.login(w["admin"]).get("/api/inventory/chiqims").json() == []
    assert len(client.login(w["admin_b"]).get("/api/inventory/chiqims").json()) == 1


# ── 7. inventory-counts: limit ≤ 200, prepopulate=false, tezkor revizya ──────

def test_counts_limit_validation(client, w):
    api = client.login(w["admin"])
    assert api.get("/api/inventory-counts?limit=201").status_code == 422
    assert api.get("/api/inventory-counts?limit=0").status_code == 422
    assert api.get("/api/inventory-counts?limit=200").status_code == 200


def test_count_create_prepopulate_default_vs_false(client, db, w):
    ca, wha = w["ca"], w["wha"]
    for _ in range(3):
        _product(db, ca)
    api = client.login(w["admin"])
    r = api.post("/api/inventory-counts", json={"warehouse_id": wha.id})
    assert r.status_code == 200, r.text
    assert r.json()["item_count"] == 3                          # default prepopulate=true (o'zgarishsiz)
    cid = r.json()["id"]
    n_items = db.query(InventoryCountItem).filter(InventoryCountItem.count_id == cid).count()
    assert n_items == 3
    # ochiq revizyani yopamiz (bir omborda bitta ochiq)
    db.query(InventoryCount).filter(InventoryCount.id == cid).update({"status": CountStatus.cancelled})
    db.flush()

    r = api.post("/api/inventory-counts", json={"warehouse_id": wha.id, "prepopulate": False})
    assert r.status_code == 200, r.text
    assert r.json()["item_count"] == 0
    assert db.query(InventoryCountItem).filter(InventoryCountItem.count_id == r.json()["id"]).count() == 0


def test_count_create_foreign_warehouse_404(client, w):
    r = client.login(w["admin"]).post("/api/inventory-counts", json={"warehouse_id": w["whb"].id, "prepopulate": False})
    assert r.status_code == 404


def test_quick_count_flow_writes_one_row_and_finalize_adjusts(db, w):
    from app.schemas.inventory_count import CountCreate, CountItemUpdate
    from app.services.inventory_count_service import (
        create_inventory_count, finalize_inventory_count, start_inventory_count, update_count_items,
    )
    ca, wha, admin = w["ca"], w["wha"], w["admin"]
    target = _product(db, ca)
    others = [_product(db, ca) for _ in range(5)]
    _stock(db, target, wha, 10)
    for o in others:
        _stock(db, o, wha, 4)

    count = create_inventory_count(db, CountCreate(warehouse_id=wha.id, prepopulate=False), admin.id, ca.id)
    assert count._items_created == 0
    assert db.query(InventoryCountItem).filter(InventoryCountItem.count_id == count.id).count() == 0

    start_inventory_count(db, count.id, ca.id)
    update_count_items(db, count.id, [CountItemUpdate(product_id=target.id, counted_qty=D("7"))], admin.id, ca.id)
    rows = db.query(InventoryCountItem).filter(InventoryCountItem.count_id == count.id).all()
    assert len(rows) == 1                                           # faqat sanalgan qator
    assert rows[0].system_qty == D("10") and rows[0].counted_qty == D("7")

    finalize_inventory_count(db, count.id, admin.id, ca.id)
    db.flush()
    qty = lambda p: db.query(StockLevel).filter(StockLevel.product_id == p.id, StockLevel.warehouse_id == wha.id).one().quantity  # noqa: E731
    assert qty(target) == D("7")                                    # sanalgan qator to'g'ri tuzatildi
    assert all(qty(o) == D("4") for o in others)                    # qolgan tovarlarga tegilmadi


def test_count_create_default_still_prepopulates_full_catalog(db, w):
    from app.schemas.inventory_count import CountCreate
    from app.services.inventory_count_service import create_inventory_count
    for _ in range(4):
        _product(db, w["ca"])
    count = create_inventory_count(db, CountCreate(warehouse_id=w["wha"].id), w["admin"].id, w["ca"].id)
    assert count._items_created == 4
    assert CountCreate(warehouse_id=1).prepopulate is True


# ── 8. /products/{id}/variants: bitta GROUP BY ───────────────────────────────

def _variant(db, product, name):
    v = ProductVariant(product_id=product.id, name=name, sku=f"V38-{next(_seq)}", barcode=f"VB38-{next(_seq)}")
    db.add(v)
    db.flush()
    return v


def test_variants_stock_single_query_and_isolation(client, db, mk, w):
    ca, wha = w["ca"], w["wha"]
    wh2 = mk.warehouse(ca, w["ba"])
    p = _product(db, ca)
    vs = [_variant(db, p, f"V{i}") for i in range(4)]
    expected_all, expected_wh = {}, {}
    for i, v in enumerate(vs):
        _stock(db, p, wha, i + 1, variant=v)
        expected_wh[v.id] = float(i + 1)
        if i % 2:
            _stock(db, p, wh2, 10, variant=v)
        expected_all[v.id] = float(i + 1 + (10 if i % 2 else 0))
    api = client.login(w["admin"])

    with count_sql(db) as stmts:
        r = api.get(f"/api/products/{p.id}/variants")
    assert r.status_code == 200, r.text
    assert {x["id"]: x["stock_quantity"] for x in r.json()} == expected_all
    assert len(_selects(stmts, "stock_levels")) == 1

    r = api.get(f"/api/products/{p.id}/variants?warehouse_id={wha.id}")
    assert {x["id"]: x["stock_quantity"] for x in r.json()} == expected_wh

    # begona korxona mahsuloti -> 404
    assert client.login(w["admin_b"]).get(f"/api/products/{p.id}/variants").status_code == 404


# ── 9. customers: karta bo'yicha qidiruv, summary-stats ──────────────────────

def test_customers_search_matches_card_number(client, db, w):
    c1 = _customer(db, w["ca"], name="Alisher", phone="998901112233", card_number="2912345678901")
    _customer(db, w["ca"], name="Boshqa", phone="998907778899", card_number="2900000000000")
    cb = _customer(db, w["cb"], name="Begona", card_number="2911111111111")
    api = client.login(w["admin"])

    r = api.get("/api/customers?search=2912345678901&limit=20")
    assert r.status_code == 200, r.text
    assert [x["id"] for x in r.json()] == [c1.id]
    # bo'shliq/tire bilan terilgan karta ham topiladi
    r = api.get("/api/customers?search=2912-3456 78901")
    assert [x["id"] for x in r.json()] == [c1.id]
    # ism va telefon bo'yicha qidiruv o'zgarmagan
    assert [x["id"] for x in api.get("/api/customers?search=Alisher").json()] == [c1.id]
    assert [x["id"] for x in api.get("/api/customers?search=0111").json()] == [c1.id]
    # begona korxona kartasi ko'rinmaydi
    assert api.get(f"/api/customers?search={cb.card_number}").json() == []
    assert len(client.login(w["admin_b"]).get(f"/api/customers?search={cb.card_number}").json()) == 1


def test_customers_summary_stats_values(client, db, w):
    _customer(db, w["ca"])                                                     # qarzsiz
    _customer(db, w["ca"], debt_balances={"UZS": 1000, "USD": 5}, debt_balance=1000)
    _customer(db, w["ca"], debt_balances={"UZS": 500})
    _customer(db, w["ca"], debt_balances={}, debt_balance=250)                 # eski format: UZS zaxirasi
    _customer(db, w["ca"], debt_balances={"UZS": 0}, debt_balance=999)         # nol -> qarzdor emas
    _customer(db, w["cb"], debt_balances={"UZS": 77777})                       # begona korxona
    r = client.login(w["admin"]).get("/api/customers/summary-stats")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["total_customers"] == 5
    assert d["total_debtors"] == 3
    assert d["total_debts"] == {"UZS": 1750.0, "USD": 5.0}
    assert d["total_debt"] == 1750.0


def test_summary_stats_postgres_sql_is_aggregate_not_row_load():
    """Postgres shoxi: jadval Python'ga yuklanmaydi — agregat SQL (jsonb_each_text, GROUP BY) ishlatiladi."""
    src = (ROOT / "app" / "routers" / "customers.py").read_text(encoding="utf-8")
    i = src.index("def get_customers_summary_stats")
    body = src[i:src.index('@router.get("/distributors-report")')]
    assert "jsonb_each_text" in body and "::jsonb" in body and "GROUP BY k" in body and "UNION ALL" in body
    assert 'dialect.name == "postgresql"' in body


# ── 10. debt_scoring: categorize_customers (golden) ──────────────────────────

def _old_categorize(db, company_id):
    """Eski algoritm (golden): har mijoz uchun alohida so'rovlar."""
    from app.services import debt_scoring as ds
    from app.utils.report_utils import local_today
    res = []
    for c in db.query(Customer).filter(Customer.company_id == company_id, Customer.debt_balance > 0).all():
        sd = ds.calculate_debt_score(c.id, db)
        oldest = db.query(Sale).filter(Sale.customer_id == c.id, *ds._open_debt_filter()
                                       ).order_by(Sale.created_at.asc()).first()
        due, days = None, 0
        if oldest and oldest.debt_due_date:
            due = str(oldest.debt_due_date)
            days = (oldest.debt_due_date - local_today()).days
        res.append((c.id, c.name, ds.safe_float(c.debt_balance), due, days, sd["score"], sd["label"], sd["color"],
                    sd["avg_delay_days"], sd["pattern"]))
    return res


def test_categorize_customers_golden_and_no_n_plus_one(db, w):
    from app.services.debt_scoring import categorize_customers
    from app.utils.report_utils import local_today
    ca, ba, wha, admin = w["ca"], w["ba"], w["wha"], w["admin"]
    today = local_today()
    custs = []
    for i in range(6):
        c = _customer(db, ca, name=f"Qarzdor {i}", debt_balance=D(1000 * (i + 1)))
        custs.append(c)
        # ochiq qarzli sotuvlar: har xil muddat (kechikkan / kechikmagan / muddatsiz)
        _sale(db, admin, ca, wha, ba, customer=c, items=0, amount=1000, paid=0,
              created_at=datetime(2026, 1, 1 + i), debt_due_date=today - timedelta(days=i * 3))
        _sale(db, admin, ca, wha, ba, customer=c, items=0, amount=500, paid=0,
              created_at=datetime(2026, 2, 1 + i), debt_due_date=today + timedelta(days=5))
    _customer(db, ca, name="Qarzsiz", debt_balance=D(0))
    cb = _customer(db, w["cb"], name="Begona qarzdor", debt_balance=D(5000))
    _sale(db, w["admin_b"], w["cb"], w["whb"], w["bb"], customer=cb, items=0, amount=1000, paid=0)

    with count_sql(db) as stmts:
        got = categorize_customers(db, ca.id)
    assert "error" not in got, got.get("traceback")
    assert len(_selects(stmts, "sales")) == 1            # mijoz boshiga so'rov yo'q
    assert len(stmts) <= 3

    old = _old_categorize(db, ca.id)
    assert got["total_debtors"] == len(old) == 6
    new = [(x["id"], x["name"], x["debt"], x["due_date"], x["days_remaining"], x["trust_score"], x["trust_label"],
            x["trust_color"], x["avg_delay_days"], x["payment_pattern"]) for x in got["customers"]]
    assert sorted(new) == sorted(old)
    assert cb.id not in {x["id"] for x in got["customers"]}


def test_calculate_debt_score_accepts_preloaded_sales(db, w):
    from app.services import debt_scoring as ds
    c = _customer(db, w["ca"], debt_balance=D(100))
    s = _sale(db, w["admin"], w["ca"], w["wha"], w["ba"], customer=c, items=0, amount=1000, paid=0,
              debt_due_date=date.today() - timedelta(days=10))
    assert ds.calculate_debt_score(c.id, db) == ds.calculate_debt_score(c.id, db, sales=[s])
    assert ds.calculate_debt_score(c.id, db, sales=[])["score"] == 100


# ── 11. Telegram: telefon bo'yicha mijoz qidiruvi ────────────────────────────

def test_telegram_find_customer_by_phone_tail(db, w):
    from app.routers.telegram import _find_customer_by_phone_tail
    c = _customer(db, w["ca"], name="Tg mijoz", phone="+998 (90) 123-45-67")
    _customer(db, w["ca"], name="Qisqa", phone="1234567")
    inactive = _customer(db, w["ca"], name="Arxiv", phone="998901119999")
    inactive.is_active = False
    cb = _customer(db, w["cb"], name="Begona", phone="998905550000")
    db.flush()

    assert _find_customer_by_phone_tail(db, w["ca"].id, "998901234567").id == c.id
    assert _find_customer_by_phone_tail(db, w["ca"].id, "901234567").id == c.id          # oxirgi 9 raqam
    assert _find_customer_by_phone_tail(db, w["ca"].id, "998901119999") is None          # arxivlangan
    assert _find_customer_by_phone_tail(db, w["ca"].id, "998905550000") is None          # begona korxona
    assert _find_customer_by_phone_tail(db, w["cb"].id, "998905550000").id == cb.id      # ijobiy yo'l
    assert _find_customer_by_phone_tail(db, w["ca"].id, "998909999999") is None


def test_telegram_phone_lookup_postgres_sql_matches_index():
    """Postgres shoxi bitta SQL: right(regexp_replace(phone, '\\D', '', 'g'), 9) — indeks ifodasi bilan bir xil."""
    from sqlalchemy.dialects import postgresql
    import app.routers.telegram as tg
    src = Path(tg.__file__).read_text(encoding="utf-8")
    assert "func.right(digits, literal_column(\"9\"))" in src
    mig = (ROOT / "alembic" / "versions" / "t3_8_customers_phone_tail_index.py").read_text(encoding="utf-8")
    assert "right(regexp_replace(phone, '\\D', '', 'g'), 9)" in mig and "CONCURRENTLY" in mig
    assert "revision: str = 't3_8'" in mig and "down_revision: Union[str, None] = 't3_7'" in mig
    from sqlalchemy import func, literal_column, select
    digits = func.regexp_replace(Customer.phone, literal_column(r"'\D'"), literal_column("''"), literal_column("'g'"))
    sql = str(select(Customer.id).where(func.right(digits, literal_column("9")) == "x").compile(dialect=postgresql.dialect()))
    assert "right(regexp_replace(customers.phone, '\\D', '', 'g'), 9)" in sql


# ── 12. finance: /payments/income customer_id ───────────────────────────────

def test_income_payments_customer_filter(client, db, w):
    from app.routers.finance import FINANCE_ROLES  # noqa: F401
    ca, ba, wha, admin = w["ca"], w["ba"], w["wha"], w["admin"]
    wl = _wallet(db, ca, ba)
    c1, c2 = _customer(db, ca, name="Mijoz bir"), _customer(db, ca, name="Mijoz ikki")
    s1 = _sale(db, admin, ca, wha, ba, customer=c1, items=0)
    s2 = _sale(db, admin, ca, wha, ba, customer=c2, items=0)

    def tx(ref, rid, amount):
        t = Transaction(company_id=ca.id, branch_id=ba.id, wallet_id=wl.id, type="income", amount=D(amount),
                        payment_type="cash", currency_code="UZS", reference_type=ref, reference_id=rid)
        t.created_at = datetime(2026, 9, 10, 12, 0)
        db.add(t)
        db.flush()
        return t.id

    t_pay1 = tx("customer_payment", c1.id, 100)
    t_sale1 = tx("sale", s1.id, 200)
    t_pay2 = tx("customer_payment", c2.id, 300)
    t_sale2 = tx("sale", s2.id, 400)
    t_other = tx("invest", None, 500)

    api = client.login(admin)
    r = api.get(f"/api/finance/payments/income?customer_id={c1.id}")
    assert r.status_code == 200, r.text
    assert {x["id"] for x in r.json()["items"]} == {t_pay1, t_sale1}
    assert r.json()["total"] == 2

    r = api.get(f"/api/finance/payments/income?customer_id={c2.id}")
    assert {x["id"] for x in r.json()["items"]} == {t_pay2, t_sale2}

    # filtrsiz — hammasi (o'zgarishsiz)
    r = api.get("/api/finance/payments/income")
    assert {x["id"] for x in r.json()["items"]} == {t_pay1, t_sale1, t_pay2, t_sale2, t_other}

    # begona korxona foydalanuvchisi A mijozi bo'yicha hech narsa ko'rmaydi
    r = client.login(w["admin_b"]).get(f"/api/finance/payments/income?customer_id={c1.id}")
    assert r.status_code == 200 and r.json()["items"] == []


# ── 13. Frontend (fayl-matn) tekshiruvlari ───────────────────────────────────

def _read(rel):
    return (SRC / rel).read_text(encoding="utf-8")


def test_axios_dead_cache_removed():
    s = _read("api/axios.js")
    for bad in ("_cache", "_inflight", "apiGetCached", "_piggyback", "LONG_TTL", "getTTL", "cacheKey", "_inflightResolve"):
        assert bad not in s, bad
    assert "export function clearCache" in s       # AuthContext/BranchContext import qiladi
    # login/logout va filial header'i saqlangan
    assert "X-Branch-Id" in s and "_tryRefreshToken" in s


def test_use_branches_hook_contract():
    s = _read("hooks/useBranches.js")
    assert "export function useBranches" in s and "export function invalidateBranches" in s
    assert "60_000" in s or "60000" in s
    assert "localStorage.getItem('user')" in s and "company_id" in s
    assert "'/branches'" in s


def test_shifts_page_uses_hook_and_pagination():
    s = _read("pages/admin/Shifts.jsx")
    assert "useBranches" in s and "api.get('/branches" not in s
    assert "skip" in s and "limit" in s and "x-total-count" in s.lower()


def test_operations_no_dead_tabs_and_lazy_loading():
    s = _read("pages/admin/Operations.jsx")
    assert "api.get('/branches" not in s
    assert "limit: 15000" not in s and "/products/pos-list" in s
    for dead in ("function SalesTab", "function KirimlarTab", "function QoldiqTab", "tab === 'sales'",
                 "tab === 'kirimlar'", "tab === 'qoldiq'"):
        assert dead not in s, dead
    for live in ("QaytarishlarTab", "TransferlarTab", "ReviziyalarTab", "ChiqimlarTab"):
        assert f"function {live}" in s and f"<{live}" in s
    # mahsulot/ta'minotchi yuklashlari tab ochilganda
    assert "productsLoaded" in s and "suppliersLoaded" in s
    assert "api.get('/customers'" not in s and "CustomerPicker" in s


def test_customer_picker_server_search():
    s = _read("components/CustomerPicker.jsx")
    assert "AbortController" in s and "300" in s and "limit: PAGE_LIMIT" in s and "PAGE_LIMIT = 20" in s
    assert "params.search" in s and "`/customers/${value}`" in s
    # oflayn zaxira ro'yxat bo'yicha klientda qidiradi
    assert "online" in s and "localFiltered" in s


def test_poskassa_uses_customer_picker_and_keeps_offline_list():
    s = _read("pages/admin/PosKassa.jsx")
    assert "CustomerPicker" in s and "function CustSearch" not in s
    p = _read("hooks/usePosSync.js")
    assert "limit: 500" in p                       # oflayn zaxira


def test_customer_detail_uses_server_filters():
    s = _read("pages/admin/CustomerDetail.jsx")
    assert "'/finance/payments/income', { params: { customer_id: customerId }" in s
    assert "params: { customer_id: customerId" in s and "'/orders'" in s
    assert "api.get('/branches'" not in s and "useBranches" in s


def test_quick_count_sends_prepopulate_false():
    s = _read("pages/admin/InventoryCounts.jsx")
    assert "prepopulate: false" in s


def test_i18n_pending_keys_parity():
    d = json.loads(PENDING.read_text(encoding="utf-8"))
    assert set(d) == {"uz", "ru", "en"}
    assert set(d["uz"]) == set(d["ru"]) == set(d["en"]) and d["uz"]
    used = set(re.findall(r"customerPicker\.[A-Za-z]+", _read("components/CustomerPicker.jsx")))
    assert used <= set(d["uz"])
