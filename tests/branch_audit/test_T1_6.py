"""T1.6 — FIFO partiyalar va qulflarni ombor bo'yicha cheklash (`batch_allocator`).

Qamrov: allocator birlik testlari (ombor tartibi, NULL partiya, shortfall, perishable/FEFO, muddati o'tgan),
create_sale (1-5 mezonlar), qulf SQL'i (faqat kerakli kalitlar, barqaror tartib), ketma-ket sotuvlarda
partiya yig'indisi, update_sale (partiya == qoldiq), chiqim (`_deduct_batches_fifo`), ikki korxona izolyatsiyasi,
/reports/inventory ombor kesimidagi o'rtacha tannarx.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_6.py -q -p no:cacheprovider

Eslatma: SQLite `FOR UPDATE` ni bajarmaydi, shuning uchun qulf qoidalari ORM so'rovlarini PostgreSQL
dialektiga kompilyatsiya qilib tekshiriladi; haqiqiy parallel qulf testi (ikki SessionLocal + threading)
faqat PostgreSQL stendida mumkin.
"""
import itertools
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from app.models.batch import Batch
from app.models.category import Category
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.product import Product
from app.models.sale import SaleItem, SaleItemBatch
from app.models.user import UserRole
from app.schemas.sale import SaleCreate, SaleUpdate
from app.services.batch_allocator import allocate_batches, lock_stock_rows, tashkent_today
from app.services.inventory_service import _deduct_batches_fifo
from app.services.sale_create import create_sale
from app.services.sale_update import update_sale

_n = itertools.count(1)
D = Decimal


def _product(db, company, **kw):
    n = next(_n)
    p = Product(name=kw.pop("name", f"Tovar T16-{n}"), sku=f"T16-{n}", barcode=f"BC16-{n:06d}",
                company_id=company.id, cost_price=kw.pop("cost_price", D("999")),
                sale_price=D("10000"), **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=D(qty))
    db.add(sl)
    db.flush()
    return sl


def _batch(db, product, wh, qty, price, age_days=0, expiry=None, company=None):
    b = Batch(product_id=product.id, warehouse_id=wh.id if wh else None, quantity=D(qty), initial_quantity=D(qty),
              purchase_price=D(price), company_id=company.id if company else product.company_id,
              created_at=datetime.utcnow() - timedelta(days=age_days), expiry_date=expiry)
    db.add(b)
    db.flush()
    return b


def _sale(prod_qty, wh=None, **kw):
    """prod_qty: [(product, qty), ...]"""
    items = [{"product_id": p.id, "quantity": q, "unit_price": 10000} for p, q in prod_qty]
    total = sum(10000 * q for _, q in prod_qty)
    if wh is not None:
        kw["warehouse_id"] = wh.id
    return SaleCreate(items=items, payment_type="cash", paid_amount=D(total), **kw)


@pytest.fixture
def w(db, mk):
    """Bitta korxona/filial, ikki ombor (A, B), mahsulot P."""
    c, b, wa, admin = mk.tenant()
    wb = mk.warehouse(c, b)
    p = _product(db, c)
    return {"c": c, "b": b, "wa": wa, "wb": wb, "admin": admin, "p": p}


def _bq(db, batch):
    db.flush()
    db.refresh(batch)
    return D(str(batch.quantity))


# ───────────────────────── allocator birlik testlari ─────────────────────────

def test_allocator_warehouse_first_then_null_never_other(db, w):
    a_old = _batch(db, w["p"], w["wa"], 5, 7000, age_days=1)
    null_b = _batch(db, w["p"], None, 5, 6000, age_days=10)
    b_old = _batch(db, w["p"], w["wb"], 50, 5000, age_days=30)   # boshqa ombor — olinmaydi
    allocs, shortfall = allocate_batches(
        db, company_id=w["c"].id, product_id=w["p"].id, variant_id=None,
        warehouse_id=w["wa"].id, quantity=D("8"),
    )
    assert [(a["batch_id"], a["quantity"]) for a in allocs] == [(a_old.id, D("5")), (null_b.id, D("3"))]
    assert shortfall == 0
    assert _bq(db, a_old) == 0 and _bq(db, null_b) == 2 and _bq(db, b_old) == 50


def test_allocator_shortfall_when_only_other_warehouse_has_batches(db, w):
    b_batch = _batch(db, w["p"], w["wb"], 10, 5000)
    allocs, shortfall = allocate_batches(
        db, company_id=w["c"].id, product_id=w["p"].id, variant_id=None,
        warehouse_id=w["wa"].id, quantity=D("4"),
    )
    assert allocs == [] and shortfall == D("4")
    assert _bq(db, b_batch) == 10


def test_allocator_fifo_within_warehouse_by_created_at_then_id(db, w):
    newer = _batch(db, w["p"], w["wa"], 3, 9000, age_days=1)
    older = _batch(db, w["p"], w["wa"], 3, 8000, age_days=5)
    allocs, _ = allocate_batches(
        db, company_id=w["c"].id, product_id=w["p"].id, variant_id=None,
        warehouse_id=w["wa"].id, quantity=D("4"),
    )
    assert [a["batch_id"] for a in allocs] == [older.id, newer.id]
    assert [a["quantity"] for a in allocs] == [D("3"), D("1")]


def test_allocator_perishable_skips_expired_and_uses_fefo(db, mk, w):
    cat = Category(name="Sut", company_id=w["c"].id, is_perishable=True)
    db.add(cat)
    db.flush()
    p = _product(db, w["c"], category_id=cat.id)
    today = tashkent_today()
    expired = _batch(db, p, w["wa"], 5, 1000, age_days=9, expiry=datetime.combine(today - timedelta(days=1), datetime.min.time()))
    late = _batch(db, p, w["wa"], 5, 2000, age_days=8, expiry=datetime.combine(today + timedelta(days=20), datetime.min.time()))
    soon = _batch(db, p, w["wa"], 5, 3000, age_days=1, expiry=datetime.combine(today + timedelta(days=2), datetime.min.time()))
    no_exp = _batch(db, p, w["wa"], 5, 4000, age_days=20)
    allocs, shortfall = allocate_batches(
        db, company_id=w["c"].id, product_id=p.id, variant_id=None, warehouse_id=w["wa"].id,
        quantity=D("12"), perishable=True, today=today,
    )
    assert [a["batch_id"] for a in allocs] == [soon.id, late.id, no_exp.id]   # NULL muddat oxirida
    assert [a["quantity"] for a in allocs] == [D("5"), D("5"), D("2")]
    assert shortfall == 0
    assert _bq(db, expired) == 5   # muddati o'tgan tegilmaydi

    # perishable bo'lmasa — muddatdan qat'i nazar FIFO (eng eski birinchi)
    allocs2, _ = allocate_batches(
        db, company_id=w["c"].id, product_id=p.id, variant_id=None, warehouse_id=w["wa"].id,
        quantity=D("1"), perishable=False, deduct=False,
    )
    assert allocs2[0]["batch_id"] == no_exp.id or allocs2[0]["batch_id"] == expired.id


def test_allocator_deduct_false_does_not_mutate(db, w):
    b = _batch(db, w["p"], w["wa"], 5, 7000)
    allocs, shortfall = allocate_batches(
        db, company_id=w["c"].id, product_id=w["p"].id, variant_id=None,
        warehouse_id=w["wa"].id, quantity=D("9"), deduct=False,
    )
    assert allocs[0]["quantity"] == D("5") and shortfall == D("4")
    assert _bq(db, b) == 5


# ───────────────────────── create_sale: 1-5 mezonlar ─────────────────────────

def test_sale_takes_batches_only_from_selected_warehouse(db, w):
    """Mezon 1 va 4."""
    p = w["p"]
    _stock(db, p, w["wa"], 10)
    _stock(db, p, w["wb"], 10)
    a = _batch(db, p, w["wa"], 10, 7000, age_days=1)
    b = _batch(db, p, w["wb"], 10, 5000, age_days=30)   # eski
    sale = create_sale(db, _sale([(p, 10)], w["wa"]), w["admin"])
    item = db.query(SaleItem).filter_by(sale_id=sale.id).one()
    assert D(str(item.cost_price)) == D("7000")
    assert _bq(db, a) == 0 and _bq(db, b) == 10
    sibs = db.query(SaleItemBatch).filter_by(sale_item_id=item.id).all()
    assert [s.batch_id for s in sibs] == [a.id]
    movs = db.query(StockMovement).filter_by(reference_type="sale", reference_id=sale.id).all()
    assert movs and all(m.warehouse_id == item.warehouse_id == w["wa"].id for m in movs)
    assert all(m.type == MovementType.OUT for m in movs)


def test_sale_uses_null_warehouse_batch_when_warehouse_has_none(db, w):
    """Mezon 2."""
    p = w["p"]
    _stock(db, p, w["wa"], 10)
    null_b = _batch(db, p, None, 10, 6000)
    sale = create_sale(db, _sale([(p, 10)], w["wa"]), w["admin"])
    item = db.query(SaleItem).filter_by(sale_id=sale.id).one()
    assert D(str(item.cost_price)) == D("6000")
    assert _bq(db, null_b) == 0


def test_sale_shortfall_uses_product_cost_price_and_no_400(db, w):
    """Mezon 3: partiya yetmasa qolgan qism product.cost_price bilan; boshqa ombor partiyasi olinmaydi."""
    p = w["p"]
    _stock(db, p, w["wa"], 10)
    a = _batch(db, p, w["wa"], 4, 7000)
    b = _batch(db, p, w["wb"], 100, 1)
    sale = create_sale(db, _sale([(p, 10)], w["wa"]), w["admin"])
    item = db.query(SaleItem).filter_by(sale_id=sale.id).one()
    # (4*7000 + 6*999) / 10
    assert D(str(item.cost_price)) == (D("28000") + D("5994")) / 10
    assert _bq(db, a) == 0 and _bq(db, b) == 100


def test_sale_virtual_product_shortfall_uses_source_cost(db, w):
    """Mezon 3 (virtual mahsulot): fallback source_product.cost_price."""
    from app.models.product import ProductConversion
    src = _product(db, w["c"], cost_price=D("300"))
    virt = _product(db, w["c"], product_type="sell", cost_price=D("111"))
    db.add(ProductConversion(sell_product_id=virt.id, source_product_id=src.id, ratio=D("2"), company_id=w["c"].id)
           if hasattr(ProductConversion, "company_id") else
           ProductConversion(sell_product_id=virt.id, source_product_id=src.id, ratio=D("2")))
    db.flush()
    _stock(db, src, w["wa"], 20)
    sale = create_sale(db, _sale([(virt, 3)], w["wa"]), w["admin"])
    item = db.query(SaleItem).filter_by(sale_id=sale.id).one()
    assert D(str(item.cost_price)) == D("600")           # 2 * source.cost_price (300)
    assert D(str(db.query(StockLevel).filter_by(product_id=src.id, warehouse_id=w["wa"].id).one().quantity)) == D("14")


def test_sale_perishable_skips_expired_and_fefo(db, w):
    """Mezon 5."""
    cat = Category(name="Sut", company_id=w["c"].id, is_perishable=True)
    db.add(cat)
    db.flush()
    p = _product(db, w["c"], category_id=cat.id)
    _stock(db, p, w["wa"], 20)
    today = tashkent_today()
    expired = _batch(db, p, w["wa"], 5, 1000, age_days=9, expiry=datetime.combine(today - timedelta(days=2), datetime.min.time()))
    late = _batch(db, p, w["wa"], 5, 2000, age_days=8, expiry=datetime.combine(today + timedelta(days=30), datetime.min.time()))
    soon = _batch(db, p, w["wa"], 5, 3000, age_days=1, expiry=datetime.combine(today + timedelta(days=3), datetime.min.time()))
    sale = create_sale(db, _sale([(p, 7)], w["wa"]), w["admin"])
    item = db.query(SaleItem).filter_by(sale_id=sale.id).one()
    assert _bq(db, expired) == 5 and _bq(db, soon) == 0 and _bq(db, late) == 3
    assert abs(D(str(item.cost_price)) - (5 * D("3000") + 2 * D("2000")) / 7) < D("0.001")


def test_sale_without_warehouse_resolved_is_400_not_other_warehouse(db, mk):
    """Ombor aniqlanmasa 400 (boshqa ombordan yechilmaydi) — T1.5 qoidasi bilan umumiy."""
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    mk.warehouse(c, b1)
    mk.warehouse(c, b2)
    admin = mk.user(c, role=UserRole.admin)
    p = _product(db, c)
    with pytest.raises(HTTPException) as ei:
        create_sale(db, _sale([(p, 1)]), admin)
    assert ei.value.status_code == 400


# ───────────────────────── qulf qoidalari ─────────────────────────

class _Capture:
    """Session'dagi barcha ORM so'rovlarini PostgreSQL SQL'iga kompilyatsiya qilib yig'adi."""

    def __init__(self, db):
        self.db = db
        self.sql = []

    def _on(self, state):
        if state.is_select:
            try:
                c = state.statement.compile(dialect=postgresql.dialect())
                self.sql.append((str(c), dict(c.params)))
            except Exception:
                pass

    def __enter__(self):
        event.listen(self.db, "do_orm_execute", self._on)
        return self

    def __exit__(self, *a):
        event.remove(self.db, "do_orm_execute", self._on)

    def locking(self):
        return [(s, p) for s, p in self.sql if "FOR UPDATE" in s]


def test_lock_only_selected_keys_in_stable_order(db, w):
    """Mezon 6: FOR UPDATE faqat tanlangan (mahsulot, variant, ombor) kalitlariga — butun mahsulotga emas."""
    p, q = w["p"], _product(db, w["c"])
    for prod in (p, q):
        _stock(db, prod, w["wa"], 10)
        _stock(db, prod, w["wb"], 10)
        _batch(db, prod, w["wa"], 10, 100)
        _batch(db, prod, w["wb"], 10, 100)
    with _Capture(db) as cap:
        create_sale(db, _sale([(q, 1), (p, 1)], w["wa"]), w["admin"])
    locks = cap.locking()
    sl = [(s, pr) for s, pr in locks if "FROM stock_levels" in s and "FROM stock_levels" in s.split("WHERE")[0]]
    assert sl, "StockLevel qulfi topilmadi"
    for s, _ in sl:
        assert "(stock_levels.product_id, coalesce(stock_levels.variant_id" in s and "stock_levels.warehouse_id) IN" in s
        assert "ORDER BY stock_levels.id" in s
    # Kalitlar faqat tanlangan ombor (A) uchun va tartiblangan — savat tartibidan ([q, p]) qat'i nazar
    expected = sorted([(p.id, 0, w["wa"].id), (q.id, 0, w["wa"].id)])
    assert sl[0][1]["param_1"] == expected
    bl = [(s, pr) for s, pr in locks if "FROM batches" in s]
    assert bl and all("ORDER BY batches.id" in s for s, _ in bl)
    # Tanlanmagan ombor (B) hech bir qulf kalitida yo'q
    for _, pr in locks:
        for v in pr.values():
            if isinstance(v, list):
                assert all(t[-1] != w["wb"].id for t in v if isinstance(t, tuple))
        assert w["wb"].id not in [v for k, v in pr.items() if "warehouse" in k]


def test_lock_stock_rows_returns_only_requested_keys(db, w):
    p = w["p"]
    sa = _stock(db, p, w["wa"], 5)
    _stock(db, p, w["wb"], 7)
    rows = lock_stock_rows(db, [(p.id, None, w["wa"].id)])
    assert list(rows.keys()) == [(p.id, None, w["wa"].id)] and rows[(p.id, None, w["wa"].id)].id == sa.id


def test_reversed_carts_and_sequential_sales_keep_batches_equal_to_sold(db, w):
    """Mezon 7: ketma-ket sotuvlarda Σ partiya kamayishi == Σ sotilgan; [X,Y] va [Y,X] muammosiz."""
    x, y = w["p"], _product(db, w["c"])
    for prod in (x, y):
        _stock(db, prod, w["wa"], 100)
        _batch(db, prod, w["wa"], 50, 100, age_days=2)
        _batch(db, prod, w["wa"], 50, 200, age_days=1)
    create_sale(db, _sale([(x, 7), (y, 3)], w["wa"]), w["admin"])
    create_sale(db, _sale([(y, 5), (x, 11)], w["wa"]), w["admin"])
    for prod, sold in ((x, 18), (y, 8)):
        left = sum(D(str(b.quantity)) for b in db.query(Batch).filter_by(product_id=prod.id))
        assert left == 100 - sold
        st = db.query(StockLevel).filter_by(product_id=prod.id, warehouse_id=w["wa"].id).one()
        assert D(str(st.quantity)) == 100 - sold


# ───────────────────────── update_sale: 8-mezon ─────────────────────────

def test_update_sale_batches_follow_stock_and_write_sale_item_batches(db, w):
    p = w["p"]
    _stock(db, p, w["wa"], 50)
    a1 = _batch(db, p, w["wa"], 20, 7000, age_days=3)
    a2 = _batch(db, p, w["wa"], 30, 8000, age_days=2)
    b = _batch(db, p, w["wb"], 40, 1000, age_days=9)
    sale = create_sale(db, _sale([(p, 5)], w["wa"]), w["admin"])

    def _sum_batches():
        return sum(D(str(x.quantity)) for x in db.query(Batch).filter(Batch.id.in_([a1.id, a2.id, b.id])))

    def _stock_qty():
        return D(str(db.query(StockLevel).filter_by(product_id=p.id, warehouse_id=w["wa"].id).one().quantity))

    batches_before, stock_before = _sum_batches(), _stock_qty()
    update_sale(db, sale.id, SaleUpdate(
        items=[{"product_id": p.id, "quantity": 25, "unit_price": 10000, "warehouse_id": w["wa"].id}],
        paid_amount=D("250000"),
    ), w["admin"])
    assert batches_before - _sum_batches() == stock_before - _stock_qty() == D("20")
    assert _bq(db, b) == 40   # boshqa ombor partiyasi tegilmagan
    items = db.query(SaleItem).filter_by(sale_id=sale.id).all()
    sibs = db.query(SaleItemBatch).filter(SaleItemBatch.sale_item_id.in_([i.id for i in items])).all()
    assert sibs and sum(D(str(s.quantity)) for s in sibs) == D("25")
    # 25 dona: a1 (20 × 7000) + a2 (5 × 8000)
    assert D(str(items[0].cost_price)) == (20 * D("7000") + 5 * D("8000")) / 25


# ───────────────────────── chiqim (_deduct_batches_fifo) ─────────────────────────

def test_deduct_batches_fifo_shares_rule_with_sale(db, w):
    p = w["p"]
    a = _batch(db, p, w["wa"], 3, 100, age_days=2)
    null_b = _batch(db, p, None, 3, 100, age_days=9)
    other = _batch(db, p, w["wb"], 10, 100, age_days=30)
    taken = _deduct_batches_fifo(db, p.id, D("5"), w["wa"].id, w["c"].id)
    assert [(bt.id, q) for bt, q in taken] == [(a.id, D("3")), (null_b.id, D("2"))]
    assert _bq(db, other) == 10
    # strict: yetmasa 400 va hech narsa kamaymaydi
    with pytest.raises(HTTPException) as ei:
        _deduct_batches_fifo(db, p.id, D("50"), w["wa"].id, w["c"].id)
    assert ei.value.status_code == 400
    assert _bq(db, null_b) == 1
    # strict=False: borini oladi
    taken2 = _deduct_batches_fifo(db, p.id, D("50"), w["wa"].id, w["c"].id, strict=False)
    assert sum(q for _, q in taken2) == D("1") and _bq(db, other) == 10


# ───────────────────────── izolyatsiya ─────────────────────────

def test_other_company_batches_and_warehouse_untouched(db, mk, w):
    """A korxona sotuvi B korxona partiyasiga tegmaydi; B ombori bilan sotuv rad etiladi."""
    c2, _b2, wh2, admin2 = mk.tenant()
    p2 = _product(db, c2)
    _stock(db, p2, wh2, 10)
    foreign = _batch(db, p2, wh2, 10, 5000)

    p = w["p"]
    _stock(db, p, w["wa"], 10)
    mine = _batch(db, p, w["wa"], 10, 7000)
    # (ijobiy yo'l) o'z resursi ishlaydi
    create_sale(db, _sale([(p, 2)], w["wa"]), w["admin"])
    assert _bq(db, mine) == 8 and _bq(db, foreign) == 10
    # begona ombor
    with pytest.raises(HTTPException) as ei:
        create_sale(db, _sale([(p, 1)], wh2), w["admin"])
    assert ei.value.status_code in (403, 404)
    # begona mahsulot (A foydalanuvchisi B mahsulotini sota olmaydi)
    with pytest.raises(HTTPException) as ei2:
        create_sale(db, _sale([(p2, 1)], w["wa"]), w["admin"])
    assert ei2.value.status_code in (400, 403, 404)
    assert _bq(db, foreign) == 10
    # allocator ham company_id bo'yicha cheklaydi
    allocs, shortfall = allocate_batches(
        db, company_id=w["c"].id, product_id=p2.id, variant_id=None, warehouse_id=wh2.id, quantity=D("1"),
    )
    assert allocs == [] and shortfall == D("1")


# ───────────────────────── /reports/inventory ─────────────────────────

def test_inventory_report_avg_cost_per_warehouse(db, client, w):
    p = w["p"]
    _stock(db, p, w["wa"], 10)
    _stock(db, p, w["wb"], 10)
    _batch(db, p, w["wa"], 10, 7000)
    _batch(db, p, w["wb"], 10, 5000)
    r = client.login(w["admin"]).get("/api/reports/inventory")
    assert r.status_code == 200, r.text
    by_wh = {row["warehouse_id"]: row for row in r.json() if row["product_id"] == p.id}
    assert by_wh[w["wa"].id]["cost_price"] == 7000 and by_wh[w["wb"].id]["cost_price"] == 5000
    assert by_wh[w["wa"].id]["value"] == 70000


def test_inventory_report_falls_back_to_company_avg_then_cost_price(db, client, w):
    p = w["p"]
    q = _product(db, w["c"], cost_price=D("123"))
    wc = w["wb"]
    _stock(db, p, w["wa"], 10)
    _stock(db, p, wc, 4)           # shu omborda partiya yo'q -> korxona o'rtachasi
    _batch(db, p, w["wa"], 10, 7000)
    _stock(db, q, wc, 3)           # umuman partiya yo'q -> product.cost_price
    rows = client.login(w["admin"]).get("/api/reports/inventory").json()
    assert next(r for r in rows if r["product_id"] == p.id and r["warehouse_id"] == wc.id)["cost_price"] == 7000
    assert next(r for r in rows if r["product_id"] == q.id)["cost_price"] == 123


def test_inventory_report_isolated_between_companies(db, mk, client, w):
    c2, _b2, wh2, admin2 = mk.tenant()
    p2 = _product(db, c2)
    _stock(db, p2, wh2, 5)
    _batch(db, p2, wh2, 5, 1)
    _stock(db, w["p"], w["wa"], 1)
    ids = {r["product_id"] for r in client.login(w["admin"]).get("/api/reports/inventory").json()}
    assert p2.id not in ids and w["p"].id in ids
    ids2 = {r["product_id"] for r in client.login(admin2).get("/api/reports/inventory").json()}
    assert w["p"].id not in ids2 and p2.id in ids2
