"""T1.7 — StockMovement.warehouse_id barcha oqimlarda, /inventory/movements ombor/filial filtri,
NULL-omborli qoldiq qatorlari yaratilmasligi.

Qamrov: sotuv, transfer (ikkala tomoni), qo'lda tuzatish, revizya, sale_refund bekor qilish
harakatlarida warehouse_id; movements filtri (warehouse_id / branch_id, boshqa filial uchun 403,
javobda warehouse_name); get_or_create_stock(None) 400; deduct_stock omborsiz — birinchi faol
omborga; create_sale omborsiz — NULL qator yo'q; sotuvni o'chirishda qator ombori/varianti
bo'yicha qaytarish; ikki korxona izolyatsiyasi; migratsiya fayllari sintaksisi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_7.py -q -p no:cacheprovider
"""
import importlib.util
import itertools
import os
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.moliya import KassaSession, Wallet
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole
from app.schemas.sale import SaleCreate
from app.services.inventory_service import deduct_stock, first_active_warehouse_id, get_or_create_stock
from app.services.sale_create import create_sale

_seq = itertools.count(1)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company, cost="500", price="1000"):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T17-{n}", barcode=f"B17-{n}", company_id=company.id,
                cost_price=Decimal(cost), sale_price=Decimal(price))
    db.add(p)
    db.flush()
    return p


def _variant(db, product, name="L"):
    v = ProductVariant(product_id=product.id, name=name)
    db.add(v)
    db.flush()
    return v


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


def _null_rows(db):
    return db.query(StockLevel).filter(StockLevel.warehouse_id.is_(None)).count()


def _wallet(db, company, branch):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"),
               company_id=company.id, branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _sale_data(items, wh_id, amount, **extra):
    body = dict(items=items, payment_type="cash", warehouse_id=wh_id,
                payments=[{"type": "cash", "amount": amount}], paid_amount=Decimal(amount))
    body.update(extra)
    return SaleCreate(**body)


def _movs(db, ref_type, ref_id=None):
    q = db.query(StockMovement).filter(StockMovement.reference_type == ref_type)
    if ref_id is not None:
        q = q.filter(StockMovement.reference_id == ref_id)
    return q.order_by(StockMovement.id.asc()).all()


def _mov(db, product, wh, type_, ref_type, ref_id, qty=2, user=None):
    """Tayyor harakat qatori (qaytarishni bekor qilish testlari uchun)."""
    m = StockMovement(product_id=product.id, warehouse_id=wh.id, type=type_,
                      qty_before=Decimal("0"), qty_after=Decimal(qty), quantity=Decimal(qty),
                      reference_type=ref_type, reference_id=ref_id,
                      user_id=user.id if user else None, reason="test")
    db.add(m)
    db.flush()
    return m


@pytest.fixture
def w(db, mk):
    """A korxona: 2 filial (a1: wha, wha2; a2: whb), admin (a1), kassa; B korxona: admin, ombor."""
    ca, a1, wha, admin = mk.tenant(UserRole.admin)
    wha2 = mk.warehouse(ca, a1, name="Ombor A2")
    a2 = mk.branch(ca, "Filial A-2")
    whb = mk.warehouse(ca, a2, name="Ombor B")
    wallet = _wallet(db, ca, a1)
    cb, b1, whc, admin_b = mk.tenant(UserRole.admin)
    _wallet(db, cb, b1)
    return dict(ca=ca, a1=a1, a2=a2, wha=wha, wha2=wha2, whb=whb, admin=admin, wallet=wallet,
                cb=cb, b1=b1, whc=whc, admin_b=admin_b)


# ── 1. Har oqimda warehouse_id (qabul mezoni 2) ──────────────────────────────

def test_sale_movement_has_warehouse(db, w):
    p = _product(db, w["ca"])
    _stock(db, p, w["wha"], 10)
    sale = create_sale(db, _sale_data([{"product_id": p.id, "quantity": 2, "unit_price": 1000}],
                                      w["wha"].id, 2000), w["admin"])
    movs = _movs(db, "sale", sale.id)
    assert len(movs) == 1 and movs[0].warehouse_id == w["wha"].id
    assert _qty(db, p, w["wha"]) == Decimal("8")


def test_transfer_both_sides_have_warehouse(db, client, w):
    p = _product(db, w["ca"])
    _stock(db, p, w["wha"], 100)
    c = client.login(w["admin"])
    r = c.post("/api/transfers", json={"from_warehouse_id": w["wha"].id, "to_warehouse_id": w["whb"].id,
                                       "items": [{"product_id": p.id, "quantity": 10}],
                                       "two_step": False})  # T4.1: filiallararo standart ikki bosqichli
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    if not _movs(db, "stock_transfer", tid):
        r = c.post(f"/api/transfers/{tid}/confirm")
        assert r.status_code == 200, r.text
    movs = _movs(db, "stock_transfer", tid)
    by_type = {m.type: m for m in movs}
    assert set(by_type) == {MovementType.TRANSFER_OUT, MovementType.TRANSFER_IN}
    assert by_type[MovementType.TRANSFER_OUT].warehouse_id == w["wha"].id
    assert by_type[MovementType.TRANSFER_IN].warehouse_id == w["whb"].id
    assert all(m.warehouse_id is not None for m in movs)


def test_adjust_movement_has_warehouse(db, client, w):
    p = _product(db, w["ca"])
    _stock(db, p, w["whb"], 10)
    r = client.login(w["admin"]).post("/api/inventory/adjust", json={
        "product_id": p.id, "warehouse_id": w["whb"].id, "new_quantity": 7, "reason": "Inventar tuzatish"})
    assert r.status_code == 200, r.text
    movs = db.query(StockMovement).filter(StockMovement.product_id == p.id,
                                          StockMovement.type == MovementType.ADJUST).all()
    assert len(movs) == 1 and movs[0].warehouse_id == w["whb"].id
    assert _qty(db, p, w["whb"]) == Decimal("7")


def test_revision_movement_has_warehouse(db, client, w):
    p = _product(db, w["ca"])
    _stock(db, p, w["wha2"], 10)
    c = client.login(w["admin"])
    r = c.post("/api/inventory-counts", json={"warehouse_id": w["wha2"].id})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert c.post(f"/api/inventory-counts/{cid}/start").status_code == 200
    r = c.post(f"/api/inventory-counts/{cid}/items", json=[{"product_id": p.id, "counted_qty": 6}])
    assert r.status_code == 200, r.text
    r = c.post(f"/api/inventory-counts/{cid}/finalize")
    assert r.status_code == 200, r.text
    movs = _movs(db, "revision", cid)
    assert len(movs) == 1 and movs[0].warehouse_id == w["wha2"].id
    assert _qty(db, p, w["wha2"]) == Decimal("6")


def test_sale_refund_void_movement_has_warehouse(db, client, w):
    p = _product(db, w["ca"])
    _stock(db, p, w["whb"], 5)
    sale = Sale(number=f"S17{next(_seq):05d}", cashier_id=w["admin"].id, company_id=w["ca"].id,
                warehouse_id=w["wha"].id, total_amount=Decimal("2000"), paid_amount=Decimal("2000"),
                payment_type=PaymentType.cash, status=SaleStatus.completed)
    db.add(sale)
    db.flush()
    # Qaytarish harakati B omborga yozilgan (sarlavha ombori A dan farqli)
    m = _mov(db, p, w["whb"], MovementType.RETURN, "sale_refund", sale.id, qty=2, user=w["admin"])
    r = client.login(w["admin"]).delete(f"/api/inventory/movements/{m.id}")
    assert r.status_code == 200, r.text
    revert = _movs(db, "return_revert", m.id)
    assert len(revert) == 1 and revert[0].warehouse_id == w["whb"].id
    assert _qty(db, p, w["whb"]) == Decimal("3")
    assert _qty(db, p, w["wha"]) is None  # sarlavha omboriga tegilmadi


# ── 2. /inventory/movements filtri (qabul mezoni 3) ──────────────────────────

@pytest.fixture
def movs_setup(db, w):
    """Har omborda bittadan harakat: wha (a1), whb (a2), whc (B korxona)."""
    pa = _product(db, w["ca"])
    pb = _product(db, w["cb"])
    ma = _mov(db, pa, w["wha"], MovementType.IN, "manual_receive", 1)
    mb = _mov(db, pa, w["whb"], MovementType.IN, "manual_receive", 2)
    mc = _mov(db, pb, w["whc"], MovementType.IN, "manual_receive", 3)
    return dict(pa=pa, pb=pb, ma=ma, mb=mb, mc=mc)


def _ids(r):
    assert r.status_code == 200, r.text
    return {x["id"] for x in r.json()}


def test_movements_filter_by_warehouse_and_branch(client, w, movs_setup):
    s = movs_setup
    c = client.login(w["admin"])
    # admin header'siz hammasini ko'radi (faqat o'z korxonasi)
    assert _ids(c.get("/api/inventory/movements")) == {s["ma"].id, s["mb"].id}
    assert _ids(c.get(f"/api/inventory/movements?warehouse_id={w['whb'].id}")) == {s["mb"].id}
    assert _ids(c.get(f"/api/inventory/movements?branch_id={w['a2'].id}")) == {s["mb"].id}
    assert _ids(c.get(f"/api/inventory/movements?branch_id={w['a1'].id}")) == {s["ma"].id}
    # javobda ombor
    row = c.get(f"/api/inventory/movements?warehouse_id={w['whb'].id}").json()[0]
    assert row["warehouse_id"] == w["whb"].id and row["warehouse_name"] == "Ombor B"


def test_movements_branch_user_limited_and_403(client, mk, w, movs_setup):
    s = movs_setup
    manager_a2 = mk.user(w["ca"], role=UserRole.manager, branch=w["a2"])
    c = client.login(manager_a2)
    # filtrsiz — faqat o'z filiali omborlari
    assert _ids(c.get("/api/inventory/movements")) == {s["mb"].id}
    assert _ids(c.get(f"/api/inventory/movements?branch_id={w['a2'].id}")) == {s["mb"].id}
    # boshqa filial yoki uning ombori — 403
    r = c.get(f"/api/inventory/movements?branch_id={w['a1'].id}")
    assert r.status_code == 403, r.text
    r = c.get(f"/api/inventory/movements?warehouse_id={w['wha'].id}")
    assert r.status_code == 403, r.text


def test_movements_foreign_company_isolation(client, w, movs_setup):
    s = movs_setup
    c = client.login(w["admin_b"])
    assert _ids(c.get("/api/inventory/movements")) == {s["mc"].id}
    # A korxona ombori/filiali B admin uchun yo'q
    assert c.get(f"/api/inventory/movements?warehouse_id={w['wha'].id}").status_code == 404
    assert c.get(f"/api/inventory/movements?branch_id={w['a1'].id}").status_code == 404
    # A korxona harakati B uchun topilmaydi
    assert c.get(f"/api/inventory/movements/{s['ma'].id}").status_code == 404


# ── 3. NULL-ombor qo'riqchisi (qabul mezoni 7) ───────────────────────────────

def test_get_or_create_stock_none_400(db, w):
    p = _product(db, w["ca"])
    with pytest.raises(HTTPException) as e:
        get_or_create_stock(db, p.id, None)
    assert e.value.status_code == 400 and "Ombor" in e.value.detail
    assert _null_rows(db) == 0
    # faqat migratsiya/tozalash uchun allow_null
    s = get_or_create_stock(db, p.id, None, allow_null=True)
    assert s.warehouse_id is None


def test_deduct_stock_without_warehouse_uses_first_active(db, w):
    p = _product(db, w["ca"])
    # qoldiq umuman yo'q, ombor berilmagan, allow_negative — birinchi faol ombor (ORDER BY id)
    deduct_stock(db, p.id, Decimal("3"), w["admin"].id, reason="Chiqim", reference_type="chiqim",
                 reference_id=1, warehouse_id=None, allow_negative=True)
    assert _null_rows(db) == 0
    first_wh = first_active_warehouse_id(db, w["ca"].id)
    assert first_wh == w["wha"].id
    assert _qty(db, p, w["wha"]) == Decimal("-3")
    movs = _movs(db, "chiqim", 1)
    assert len(movs) == 1 and movs[0].warehouse_id == w["wha"].id


def test_deduct_stock_without_warehouse_no_active_warehouse_400(db, mk):
    c = mk.company()
    u = mk.user(c, role=UserRole.admin)
    p = _product(db, c)
    with pytest.raises(HTTPException) as e:
        deduct_stock(db, p.id, Decimal("1"), u.id, warehouse_id=None, allow_negative=True)
    assert e.value.status_code == 400
    assert _null_rows(db) == 0


def test_create_sale_without_warehouse_and_stock_no_null_row(db, mk):
    """Filialsiz xodim, mahsulotda qoldiq qatori yo'q, ombor berilmagan — NULL qator emas,
    korxonaning birinchi faol omborida qator ochiladi."""
    c = mk.company()
    b = mk.branch(c)
    wh = mk.warehouse(c, b)
    u = mk.user(c, role=UserRole.admin, branch=None)
    _wallet(db, c, b)
    p = _product(db, c)
    sale = create_sale(db, _sale_data([{"product_id": p.id, "quantity": 1, "unit_price": 1000}],
                                      None, 1000), u)
    assert _null_rows(db) == 0
    movs = _movs(db, "sale", sale.id)
    assert len(movs) == 1 and movs[0].warehouse_id == wh.id
    assert _qty(db, p, wh) == Decimal("-1")


# ── 4. Sotuvni o'chirish — harakat ombori va varianti bo'yicha (qabul mezoni 5) ──

def test_sale_delete_restores_to_movement_warehouse_and_variant(db, client, w):
    p = _product(db, w["ca"])
    v = _variant(db, p)
    _stock(db, p, w["wha"], 10)            # sarlavha ombori, variantsiz
    _stock(db, p, w["wha2"], 20, v.id)      # qator ombori (T1.9: sarlavha bilan bir filialdan), variantli
    sale = create_sale(db, _sale_data(
        [{"product_id": p.id, "quantity": 3, "unit_price": 1000, "warehouse_id": w["wha2"].id, "variant_id": v.id}],
        w["wha"].id, 3000), w["admin"])
    movs = _movs(db, "sale", sale.id)
    assert len(movs) == 1 and movs[0].warehouse_id == w["wha2"].id and movs[0].variant_id == v.id
    assert _qty(db, p, w["wha2"], v.id) == Decimal("17")

    r = client.login(w["admin"]).delete(f"/api/sales/{sale.id}")
    assert r.status_code == 200, r.text
    assert _qty(db, p, w["wha2"], v.id) == Decimal("20")
    assert _qty(db, p, w["wha"]) == Decimal("10")   # sarlavha omboriga qaytmadi
    assert _qty(db, p, w["wha2"]) is None            # variantsiz qator ochilmadi
    assert _null_rows(db) == 0


# ── 5. Model / migratsiya ────────────────────────────────────────────────────

def test_model_indexes_and_relationship():
    names = {i.name for i in StockMovement.__table__.indexes}
    assert {"ix_stock_movements_wh_created", "ix_stock_movements_reftype_refid"} <= names
    assert "uq_stock_product_variant_warehouse" in {i.name for i in StockLevel.__table__.indexes}
    assert "warehouse" in StockMovement.__mapper__.relationships


def test_stock_level_unique_index_enforced(db, w):
    """(product, warehouse, COALESCE(variant,0)) takrori bazada ham rad etiladi."""
    from sqlalchemy.exc import IntegrityError
    p = _product(db, w["ca"])
    _stock(db, p, w["wha"], 1)
    sp = db.begin_nested()
    with pytest.raises(IntegrityError):
        db.add(StockLevel(product_id=p.id, warehouse_id=w["wha"].id, quantity=Decimal("1")))
        db.flush()
    sp.rollback()


@pytest.mark.parametrize("fname,rev,down", [
    ("t1_7_stock_movements_warehouse_id.py", "t1_7", "t1_6"),
    ("t1_7b_null_warehouse_stock_cleanup.py", "t1_7b", "t1_7"),
])
def test_migration_files(fname, rev, down):
    path = os.path.join(ROOT, "alembic", "versions", fname)
    spec = importlib.util.spec_from_file_location(f"mig_{rev}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == rev and mod.down_revision == down
    assert callable(mod.upgrade) and callable(mod.downgrade)
    src = open(path, encoding="utf-8").read()
    if rev == "t1_7":
        assert "ADD COLUMN IF NOT EXISTS warehouse_id" in src
        for idx in ("ix_stock_movements_warehouse_id", "ix_stock_movements_wh_created", "ix_stock_movements_reftype_refid"):
            assert f"CREATE INDEX IF NOT EXISTS {idx}" in src
        for ref in ("'sale'", "'stock_transfer'", "'revision'", "'auto_batch_write_off'", "Ombor #"):
            assert ref in src
        assert "DROP COLUMN" not in src
    else:
        assert "DELETE FROM stock_levels WHERE warehouse_id IS NULL AND COALESCE(quantity, 0) = 0" in src
        # NOT NULL / CHECK cheklovi bu relizda qo'shilmaydi (NULL qatorlar tozalanmaguncha)
        assert "ADD CONSTRAINT" not in src and "SET NOT NULL" not in src


def test_no_null_warehouse_literals_in_app():
    """Qabul mezoni 6: app ichida `warehouse_id=None` / `warehouse_id == None` bilan qator yaratilmaydi
    (faqat funksiya parametri default'i va docstring ruxsat etiladi)."""
    import re
    hits = []
    for root, _dirs, files in os.walk(os.path.join(ROOT, "app")):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(root, f)
            for i, line in enumerate(open(path, encoding="utf-8"), 1):
                if re.search(r"warehouse_id\s*==\s*None", line) or (
                    "warehouse_id=None" in line and not line.lstrip().startswith(("def ", "#", "`", "'", '"'))
                    and "def " not in line and "`warehouse_id=None`" not in line
                ):
                    hits.append(f"{path}:{i}: {line.strip()}")
    assert hits == [], hits
