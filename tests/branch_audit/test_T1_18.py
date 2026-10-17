"""T1.18 — Ishlab chiqarishda filial kesimi va lock xatolari (STOCK-31).

1) calculate_shortages: yozmaydi (INSERT yo'q) va qulf olmaydi (FOR UPDATE yo'q);
2) xom ashyo tannarxi yechilgan partiyalar narxidan (FIFO), partiyasiz — zaxira narx;
3) /production/orders — warehouse_id/branch_id filtri, filialli xodim uchun 403;
4) /production/alerts — kam qoldiq ombor bo'yicha.
"""
import itertools
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import event, func

from app.models.batch import Batch
from app.models.bom import BOM, BOMItem
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.production_order import ProductionOrder, ProductionOrderStatus
from app.models.user import UserRole
from app.services.production_service import calculate_shortages, complete_production_order

_n = itertools.count(1)
D = Decimal


def _product(db, company, ptype="raw_material", cost=0, min_stock=0, name=None):
    n = next(_n)
    p = Product(sku=f"T118-{n}", barcode=f"T118B{n:06d}", name=name or f"Mahsulot {n}",
                company_id=company.id, product_type=ptype, cost_price=cost, min_stock=min_stock)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty):
    s = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=qty)
    db.add(s)
    db.flush()
    return s


def _batch(db, company, product, wh, qty, price, age):
    b = Batch(product_id=product.id, warehouse_id=wh.id, company_id=company.id,
              initial_quantity=qty, quantity=qty, purchase_price=price,
              created_at=datetime(2026, 1, 1) + timedelta(days=age))
    db.add(b)
    db.flush()
    return b


def _bom(db, company, finished, comps):
    bom = BOM(product_id=finished.id, name=f"BOM {next(_n)}", company_id=company.id)
    db.add(bom)
    db.flush()
    for comp, qty in comps:
        db.add(BOMItem(bom_id=bom.id, component_product_id=comp.id, quantity_per_unit=qty))
    db.flush()
    db.refresh(bom)
    return bom


def _order(db, company, user, bom, src, dst, status=ProductionOrderStatus.draft, qty=10):
    o = ProductionOrder(number=f"MO-T118-{next(_n)}", bom_id=bom.id, product_id=bom.product_id,
                        planned_quantity=qty, warehouse_id=src.id, target_warehouse_id=dst.id,
                        status=status, created_by=user.id, company_id=company.id)
    db.add(o)
    db.flush()
    return o


def _setup(mk, db):
    """Korxona: manba/maqsad ombor, un (xom ashyo), non (tayyor), BOM: 1 non = 2 un."""
    c, b, src, u = mk.tenant()
    c.manufacturing_enabled = True
    dst = mk.warehouse(c, b)
    flour = _product(db, c, cost=5, name="Un")
    bread = _product(db, c, ptype="simple", name="Non")
    bom = _bom(db, c, bread, [(flour, D("2"))])
    return SimpleNamespace(c=c, b=b, src=src, dst=dst, u=u, flour=flour, bread=bread, bom=bom)


# ── 1. calculate_shortages: yozmaydi va qulf olmaydi ─────────────────────────

def test_shortages_does_not_insert_or_lock(mk, db):
    s = _setup(mk, db)
    sql = []

    def _log(conn, cursor, statement, *a):
        sql.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _log)
    before = db.query(func.count(StockLevel.id)).scalar()
    try:
        res = calculate_shortages(db, s.bom, D("10"), s.src.id)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _log)

    assert db.query(func.count(StockLevel.id)).scalar() == before
    assert not [o for o in db.new if isinstance(o, StockLevel)]
    assert not [q for q in sql if "FOR UPDATE" in q.upper()]
    assert not [q for q in sql if q.lstrip().upper().startswith(("INSERT", "UPDATE"))]
    # Qator yo'q — mavjud qoldiq 0, yetishmovchilik = kerakli miqdor
    assert len(res) == 1
    assert res[0]["available_quantity"] == 0
    assert res[0]["required_quantity"] == D("20")
    assert res[0]["shortage"] == D("20")


def test_shortages_existing_row_and_enough(mk, db):
    s = _setup(mk, db)
    _stock(db, s.flour, s.src, D("15"))
    res = calculate_shortages(db, s.bom, D("10"), s.src.id)
    assert res[0]["available_quantity"] == D("15")
    assert res[0]["shortage"] == D("5")
    assert calculate_shortages(db, s.bom, D("5"), s.src.id) == []
    # Boshqa ombordagi qoldiq hisobga olinmaydi
    other = mk.warehouse(s.c, s.b)
    assert calculate_shortages(db, s.bom, D("10"), other.id)[0]["available_quantity"] == 0


def test_get_order_endpoint_writes_nothing(mk, db, client):
    s = _setup(mk, db)
    o = _order(db, s.c, s.u, s.bom, s.src, s.dst)
    before = db.query(func.count(StockLevel.id)).scalar()
    r = client.login(s.u).get(f"/api/production/orders/{o.id}")
    assert r.status_code == 200, r.text
    assert D(str(r.json()["shortages"][0]["available_quantity"])) == 0
    assert db.query(func.count(StockLevel.id)).scalar() == before


# ── 2. Tannarx partiyadan ─────────────────────────────────────────────────────

def test_complete_cost_from_fifo_batches(mk, db):
    s = _setup(mk, db)
    s.flour.cost_price = D("99")      # joriy tannarx e'tiborga olinmasligi kerak
    _stock(db, s.flour, s.src, D("30"))
    _batch(db, s.c, s.flour, s.src, D("10"), D("10"), age=0)   # eski, arzon
    _batch(db, s.c, s.flour, s.src, D("20"), D("20"), age=5)   # yangi, qimmat
    o = _order(db, s.c, s.u, s.bom, s.src, s.dst, ProductionOrderStatus.in_progress)
    # 8 non => 16 un: 10 * 10 + 6 * 20 = 220
    data = SimpleNamespace(produced_quantity=D("8"), defect_quantity=D("0"), costs=[])
    complete_production_order(db, o.id, s.u.id, s.c.id, data)
    assert o.total_cost == D("220")
    assert o.unit_cost == D("27.5")
    left = {b.purchase_price: b.quantity
            for b in db.query(Batch).filter(Batch.product_id == s.flour.id)}
    assert left[D("10")] == 0 and left[D("20")] == D("14")


def test_complete_cost_fallback_without_batches(mk, db):
    s = _setup(mk, db)           # un tannarxi 5
    _stock(db, s.flour, s.src, D("30"))      # narxsiz kirim: partiya yo'q
    o = _order(db, s.c, s.u, s.bom, s.src, s.dst, ProductionOrderStatus.in_progress)
    data = SimpleNamespace(produced_quantity=D("4"), defect_quantity=D("0"), costs=[])
    complete_production_order(db, o.id, s.u.id, s.c.id, data)
    assert o.total_cost == D("40")           # 8 un * 5
    assert o.unit_cost == D("10")


def test_complete_cost_partial_batches_use_fallback_for_rest(mk, db):
    s = _setup(mk, db)
    _stock(db, s.flour, s.src, D("30"))
    _batch(db, s.c, s.flour, s.src, D("3"), D("10"), age=0)
    o = _order(db, s.c, s.u, s.bom, s.src, s.dst, ProductionOrderStatus.in_progress)
    data = SimpleNamespace(produced_quantity=D("4"), defect_quantity=D("0"), costs=[])
    complete_production_order(db, o.id, s.u.id, s.c.id, data)
    assert o.total_cost == D("55")           # 3*10 + 5*5


# ── 3. Buyurtmalar ro'yxati: filial/ombor filtri ──────────────────────────────

def test_list_branch_filter_and_isolation(mk, db, client):
    s = _setup(mk, db)
    b2 = mk.branch(s.c)
    src2, dst2 = mk.warehouse(s.c, b2), mk.warehouse(s.c, b2)
    o1 = _order(db, s.c, s.u, s.bom, s.src, s.dst)
    o2 = _order(db, s.c, s.u, s.bom, src2, dst2)
    # Boshqa korxona buyurtmasi ko'rinmasligi kerak
    s2 = _setup(mk, db)
    o3 = _order(db, s2.c, s2.u, s2.bom, s2.src, s2.dst)

    admin = mk.user(s.c, role=UserRole.admin)
    cl = client.login(admin)

    def ids(r):
        assert r.status_code == 200, r.text
        return {x["id"] for x in r.json()}

    assert ids(cl.get("/api/production/orders")) == {o1.id, o2.id}
    r = cl.get(f"/api/production/orders?branch_id={b2.id}")
    assert ids(r) == {o2.id}
    assert r.json()[0]["branch_id"] == b2.id and r.json()[0]["branch_name"] == b2.name
    assert ids(cl.get(f"/api/production/orders?branch_id={s.b.id}")) == {o1.id}
    assert ids(cl.get(f"/api/production/orders?warehouse_id={src2.id}")) == {o2.id}
    # Boshqa korxona filiali so'ralsa — hech narsa chiqmaydi
    assert cl.get(f"/api/production/orders?branch_id={s2.b.id}").json() == []
    assert o3.id not in ids(cl.get("/api/production/orders"))


def test_list_branch_user_scoped_and_403(mk, db, client):
    s = _setup(mk, db)
    b2 = mk.branch(s.c)
    src2, dst2 = mk.warehouse(s.c, b2), mk.warehouse(s.c, b2)
    o1 = _order(db, s.c, s.u, s.bom, s.src, s.dst)
    _order(db, s.c, s.u, s.bom, src2, dst2)
    wh_user = mk.user(s.c, role=UserRole.warehouse, branch=s.b)
    cl = client.login(wh_user)
    r = cl.get("/api/production/orders")
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [o1.id]          # avtomatik o'z filiali
    assert cl.get(f"/api/production/orders?branch_id={s.b.id}").status_code == 200
    assert cl.get(f"/api/production/orders?branch_id={b2.id}").status_code == 403


# ── 4. Alerts: kam qoldiq ombor bo'yicha ──────────────────────────────────────

def test_alerts_low_stock_per_warehouse(mk, db, client):
    """T2.3: kam qoldiq mahsulot darajasida (doiradagi omborlar yig'indisi), ombor kesimi `warehouses` da."""
    s = _setup(mk, db)
    wh_b = mk.warehouse(s.c, s.b)
    s.flour.min_stock = 10
    _stock(db, s.flour, s.src, D("3"))       # A: kam
    _stock(db, s.flour, wh_b, D("100"))      # B: ko'p (jami 103 > 10) -> kam qoldiq EMAS
    r = client.login(s.u).get("/api/production/alerts")
    assert r.status_code == 200, r.text
    assert [x for x in r.json()["low_stock"] if x["product_id"] == s.flour.id] == []
    # jami <= min_stock bo'lsa — bitta qator, ombor kesimi bilan
    s2 = _setup(mk, db)
    wh_b2 = mk.warehouse(s2.c, s2.b)
    s2.flour.min_stock = 10
    _stock(db, s2.flour, s2.src, D("3"))
    _stock(db, s2.flour, wh_b2, D("4"))      # jami 7 <= 10
    r = client.login(s2.u).get("/api/production/alerts")
    assert r.status_code == 200, r.text
    low = [x for x in r.json()["low_stock"] if x["product_id"] == s2.flour.id]
    assert len(low) == 1
    assert low[0]["quantity"] == 7.0 and low[0]["warehouse_id"] is None
    assert {w["warehouse_id"]: w["qty"] for w in low[0]["warehouses"]} == {s2.src.id: 3.0, wh_b2.id: 4.0}


def test_alerts_company_isolation(mk, db, client):
    s = _setup(mk, db)
    s2 = _setup(mk, db)
    s2.flour.min_stock = 10
    _stock(db, s2.flour, s2.src, D("1"))
    r = client.login(s.u).get("/api/production/alerts")
    assert r.status_code == 200
    assert s2.flour.id not in {x["product_id"] for x in r.json()["low_stock"]}
