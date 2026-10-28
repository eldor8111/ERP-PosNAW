"""D3.3 — Dorixona rejimi: partiya holatlari (karantin, brak, qaytarib olingan).

Qamrov: Batch.status; sotuv (allocate_batches / lock_batches / sotuv API) faqat faol partiyadan;
`GET /api/pharmacy/batches` filtrlari; `POST /api/pharmacy/batches/{id}/status` (sabab majburiy, audit log);
ta'minotchiga qaytarishda aniq partiya (brak/karantin ham); oddiy korxona regressiyasi; ikki korxona izolyatsiyasi;
filial ruxsati; rollar.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D3_3.py -q -p no:cacheprovider
"""
import itertools
import json
import pathlib
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.moliya import Wallet
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleItemBatch
from app.models.supplier import Supplier
from app.models.user import UserRole, UserWallet
from app.services.batch_allocator import allocate_batches, lock_batches, tashkent_today
from app.services.supplier_return_service import create_supplier_return

ROOT = pathlib.Path(__file__).resolve().parents[2]
_n = itertools.count(1)


def _dt(days):
    if days is None:
        return None
    return datetime.combine(tashkent_today() + timedelta(days=days), time.min)


def _enable(db, c):
    c.pharmacy_enabled = True
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


def _product(db, c):
    n = next(_n)
    p = Product(name=f"Dori D33-{n}", sku=f"D33-{n}", barcode=f"BD33-{n:06d}", company_id=c.id,
                cost_price=D("500"), sale_price=D("1000"))
    db.add(p)
    db.flush()
    return p


def _stock(db, p, wh, qty):
    sl = StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty))
    db.add(sl)
    db.flush()
    return sl


def _batch(db, p, wh, qty, expiry_days, status=None, age_days=0, lot=None):
    b = Batch(product_id=p.id, warehouse_id=wh.id if wh else None, quantity=D(qty), initial_quantity=D(qty),
              purchase_price=D(100), company_id=p.company_id, expiry_date=_dt(expiry_days),
              lot_number=lot or f"L{next(_n)}", status=status,
              created_at=datetime.utcnow() - timedelta(days=age_days))
    db.add(b)
    db.flush()
    return b


def _bq(db, b):
    db.refresh(b)
    return D(str(b.quantity))


def _sale_body(p, qty, wh):
    total = 1000 * qty
    return {"items": [{"product_id": p.id, "quantity": qty, "unit_price": 1000}],
            "payment_type": "cash", "paid_amount": total, "paid_cash": total,
            "payments": [{"type": "cash", "amount": total}], "warehouse_id": wh.id}


@pytest.fixture
def ph(db, mk):
    """Dorixona yoqilgan korxona A va oddiy korxona B (har birida kassa, mahsulot, ombor qoldig'i)."""
    c, b, wh, admin = mk.tenant()
    _wallet(db, c, b, admin)
    _enable(db, c)
    p = _product(db, c)
    sl = _stock(db, p, wh, 100)
    c2, b2, wh2, admin2 = mk.tenant()
    _wallet(db, c2, b2, admin2)
    p2 = _product(db, c2)
    sl2 = _stock(db, p2, wh2, 100)
    return dict(c=c, b=b, wh=wh, admin=admin, p=p, sl=sl, c2=c2, b2=b2, wh2=wh2, admin2=admin2, p2=p2, sl2=sl2)


# ───────────────────────── Ajratish (allocate / lock) ─────────────────────────

def test_allocate_takes_active_first_then_quarantine_defect_recalled(db, ph):
    """P.13: avval faol partiya, yetmasa faol bo'lmaganlari (sotuv rad etilmaydi), ular `invalid` belgisi bilan."""
    c, wh, p = ph["c"], ph["wh"], ph["p"]
    bad = [_batch(db, p, wh, 50, 10, status=st) for st in ("quarantine", "defect", "recalled")]
    ok = _batch(db, p, wh, 5, 200, status="active")
    allocs, short = allocate_batches(db, company_id=c.id, product_id=p.id, variant_id=None,
                                     warehouse_id=wh.id, quantity=8, pharmacy=True)
    assert [(a["batch_id"], a.get("invalid", False)) for a in allocs] == [(ok.id, False), (bad[0].id, True)]
    assert short == 0 and D(str(allocs[1]["quantity"])) == 3


def test_lock_batches_includes_non_active(db, ph):
    """P.13: dorixona sotuvi faol bo'lmagan partiyadan ham yechishi mumkin — ular ham qulflanadi."""
    c, wh, p = ph["c"], ph["wh"], ph["p"]
    act = _batch(db, p, wh, 5, 100)
    nul = _batch(db, p, wh, 5, 100, status="active")
    qua = _batch(db, p, wh, 5, 100, status="quarantine")
    got = {b.id for b in lock_batches(db, c.id, [(p.id, None, wh.id)])}
    assert got == {act.id, nul.id, qua.id}


def test_plain_store_null_status_unchanged(db, ph):
    """Regressiya: oddiy korxonada status NULL — hamma partiya FIFO bilan ajratiladi (muddati o'tgani ham)."""
    c2, wh2, p2 = ph["c2"], ph["wh2"], ph["p2"]
    old = _batch(db, p2, wh2, 4, -30, age_days=10)     # muddati o'tgan, lekin oddiy do'kon uchun ahamiyatsiz
    new = _batch(db, p2, wh2, 10, 100, age_days=1)
    allocs, short = allocate_batches(db, company_id=c2.id, product_id=p2.id, variant_id=None,
                                     warehouse_id=wh2.id, quantity=6)
    assert [(a["batch_id"], a["quantity"]) for a in allocs] == [(old.id, D(4)), (new.id, D(2))]
    assert short == 0


# ───────────────────────── Sotuv API ─────────────────────────

def test_pharmacy_sale_skips_quarantined_batch(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    quar = _batch(db, p, wh, 10, 30, status="quarantine")      # muddati yaqin, lekin karantinda
    good = _batch(db, p, wh, 10, 90)
    r = client.login(ph["admin"]).post("/api/sales/", json=_sale_body(p, 4, wh))
    assert r.status_code == 200, r.text
    assert _bq(db, quar) == 10 and _bq(db, good) == 6
    item = db.query(SaleItem).filter_by(sale_id=r.json()["id"]).one()
    sib = db.query(SaleItemBatch).filter_by(sale_item_id=item.id).all()
    assert [s.batch_id for s in sib] == [good.id]


def test_pharmacy_sale_with_only_non_active_batches_is_sold_with_warning(client, db, ph):
    """P.13: faqat karantin / brak partiya qolgan dori ham sotiladi — javobda ogohlantirish."""
    p, wh = ph["p"], ph["wh"]
    bq = _batch(db, p, wh, 10, 90, status="quarantine")
    bd = _batch(db, p, wh, 10, 90, status="defect")
    r = client.login(ph["admin"]).post("/api/sales/", json=_sale_body(p, 1, wh))
    assert r.status_code == 200, r.text
    assert [x["code"] for x in r.json()["warnings"]] == ["sold_invalid_batch"]
    assert _bq(db, bq) + _bq(db, bd) == 19
    db.refresh(ph["sl"])
    assert D(str(ph["sl"].quantity)) == 99


def test_status_change_back_to_active_sells_again(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    b = _batch(db, p, wh, 10, 90, status="quarantine")
    cl = client.login(ph["admin"])
    r = cl.post("/api/sales/", json=_sale_body(p, 1, wh))
    assert r.status_code == 200 and [x["code"] for x in r.json()["warnings"]] == ["sold_invalid_batch"]
    r = cl.post(f"/api/pharmacy/batches/{b.id}/status", json={"status": "active", "reason": "Tekshiruvdan o'tdi"})
    assert r.status_code == 200, r.text
    r = cl.post("/api/sales/", json=_sale_body(p, 3, wh))
    assert r.status_code == 200 and r.json()["warnings"] == []                 # faol bo'lgach — ogohlantirishsiz
    assert _bq(db, b) == 6


def test_plain_store_sale_regression(client, db, ph):
    """Oddiy korxona: muddati o'tgan partiya avvalgidek sotiladi (status NULL)."""
    p2, wh2 = ph["p2"], ph["wh2"]
    old = _batch(db, p2, wh2, 10, -5)
    r = client.login(ph["admin2"]).post("/api/sales/", json=_sale_body(p2, 3, wh2))
    assert r.status_code == 200, r.text
    assert _bq(db, old) == 7


# ───────────────────────── Holat API ─────────────────────────

def test_list_filters(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    a = _batch(db, p, wh, 5, 10, lot="AAA-1")
    q = _batch(db, p, wh, 6, 40, status="quarantine", lot="BBB-2")
    d = _batch(db, p, wh, 7, 80, status="defect", lot="CCC-3")
    _batch(db, p, wh, 0, 80, lot="ZERO")
    cl = client.login(ph["admin"])
    rows = cl.get("/api/pharmacy/batches").json()
    assert {r["batch_id"] for r in rows} == {a.id, q.id, d.id}      # qoldig'i 0 yashiriladi
    row = next(r for r in rows if r["batch_id"] == q.id)
    assert row["status"] == "quarantine" and row["lot_number"] == "BBB-2" and row["quantity"] == 6
    assert row["warehouse_id"] == wh.id and row["days_left"] == 40 and row["product_id"] == p.id
    assert next(r for r in rows if r["batch_id"] == a.id)["status"] == "active"

    ids = lambda **k: {r["batch_id"] for r in cl.get("/api/pharmacy/batches", params=k).json()}  # noqa: E731
    assert ids(status="quarantine") == {q.id}
    assert ids(status="active") == {a.id}
    assert ids(lot="ccc") == {d.id}
    assert ids(product_id=p.id, warehouse_id=wh.id) == {a.id, q.id, d.id}
    assert ids(expiry_from=_dt(30).date().isoformat(), expiry_to=_dt(60).date().isoformat()) == {q.id}
    assert ids(include_empty="true") >= {a.id, q.id, d.id}
    assert len(ids(include_empty="true")) == 4
    assert cl.get("/api/pharmacy/batches", params={"status": "xxx"}).status_code == 422


def test_set_status_requires_reason_and_writes_audit(client, db, ph):
    p, wh = ph["p"], ph["wh"]
    b = _batch(db, p, wh, 10, 90)
    cl = client.login(ph["admin"])
    assert cl.post(f"/api/pharmacy/batches/{b.id}/status", json={"status": "defect", "reason": "  "}).status_code == 400
    assert cl.post(f"/api/pharmacy/batches/{b.id}/status", json={"status": "defect"}).status_code == 422
    assert cl.post(f"/api/pharmacy/batches/{b.id}/status", json={"status": "weird", "reason": "x"}).status_code == 422
    db.refresh(b)
    assert b.status is None

    r = cl.post(f"/api/pharmacy/batches/{b.id}/status", json={"status": "defect", "reason": "Qadoq shikastlangan"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "defect" and r.json()["previous_status"] == "active"
    db.refresh(b)
    assert b.status == "defect" and b.status_reason == "Qadoq shikastlangan"
    assert b.status_changed_by == ph["admin"].id and b.status_changed_at is not None
    log = db.query(AuditLog).filter_by(action="BATCH_STATUS", entity_id=b.id).one()
    assert log.company_id == ph["c"].id and log.user_id == ph["admin"].id
    assert log.old_values["status"] == "active" and log.new_values["status"] == "defect"
    assert log.new_values["reason"] == "Qadoq shikastlangan"
    # Xuddi shu holat qayta o'rnatilmaydi
    assert cl.post(f"/api/pharmacy/batches/{b.id}/status", json={"status": "defect", "reason": "yana"}).status_code == 400


def test_roles(client, db, ph, mk):
    p, wh = ph["p"], ph["wh"]
    b = _batch(db, p, wh, 10, 90)
    cashier = mk.user(ph["c"], role=UserRole.cashier, branch=ph["b"])
    cl = client.login(cashier)
    assert cl.get("/api/pharmacy/batches").status_code == 403
    assert cl.post(f"/api/pharmacy/batches/{b.id}/status", json={"status": "defect", "reason": "x"}).status_code == 403
    db.refresh(b)
    assert b.status is None


def test_plain_store_cannot_use_pharmacy_batches_api(client, db, ph):
    p2, wh2 = ph["p2"], ph["wh2"]
    b = _batch(db, p2, wh2, 10, 90)
    cl = client.login(ph["admin2"])
    assert cl.get("/api/pharmacy/batches").status_code == 403
    assert cl.post(f"/api/pharmacy/batches/{b.id}/status", json={"status": "defect", "reason": "x"}).status_code == 403
    db.refresh(b)
    assert b.status is None


def test_company_isolation(client, db, ph, mk):
    """A korxona foydalanuvchisi B korxona partiyasini ko'rmaydi va o'zgartira olmaydi."""
    c3, b3, wh3, admin3 = mk.tenant()
    _enable(db, c3)
    p3 = _product(db, c3)
    foreign = _batch(db, p3, wh3, 10, 90, lot="FOREIGN")
    own = _batch(db, ph["p"], ph["wh"], 10, 90, lot="OWN")
    cl = client.login(ph["admin"])
    rows = cl.get("/api/pharmacy/batches").json()
    assert {r["batch_id"] for r in rows} == {own.id}                # ijobiy: o'zinikini ko'radi
    assert cl.get("/api/pharmacy/batches", params={"warehouse_id": wh3.id}).status_code == 404
    r = cl.post(f"/api/pharmacy/batches/{foreign.id}/status", json={"status": "defect", "reason": "x"})
    assert r.status_code == 404
    db.refresh(foreign)
    assert foreign.status is None
    assert cl.post(f"/api/pharmacy/batches/{own.id}/status", json={"status": "recalled", "reason": "Qaytarib olindi"}).status_code == 200


def test_branch_scope(client, db, ph, mk):
    """Filial xodimi boshqa filial ombori partiyasini o'zgartira olmaydi (403)."""
    c = ph["c"]
    b2 = mk.branch(c)
    wh_other = mk.warehouse(c, b2)
    p = ph["p"]
    other = _batch(db, p, wh_other, 10, 90)
    mine = _batch(db, p, ph["wh"], 10, 90)
    mgr = mk.user(c, role=UserRole.manager, branch=ph["b"])
    cl = client.login(mgr)
    assert cl.post(f"/api/pharmacy/batches/{other.id}/status", json={"status": "defect", "reason": "x"}).status_code == 403
    assert cl.post(f"/api/pharmacy/batches/{mine.id}/status", json={"status": "quarantine", "reason": "x"}).status_code == 200
    assert {r["batch_id"] for r in cl.get("/api/pharmacy/batches").json()} == {mine.id}
    assert cl.get("/api/pharmacy/batches", params={"warehouse_id": wh_other.id}).status_code == 403
    db.refresh(other)
    assert other.status is None


# ───────────────────────── Ta'minotchiga qaytarish ─────────────────────────

def _supplier(db, c):
    s = Supplier(name=f"Ta'minotchi {next(_n)}", company_id=c.id, is_active=True)
    db.add(s)
    db.flush()
    return s


def _ret(supplier, wh, product, qty, batch_id=None):
    item = SimpleNamespace(product_id=product.id, variant_id=None, quantity=D(qty), unit_cost=D(100), batch_id=batch_id)
    return SimpleNamespace(supplier_id=supplier.id, warehouse_id=wh.id, items=[item], received_amount=D(0),
                           wallet_id=None, payment_type="cash", note=None)


def test_supplier_return_from_exact_quarantined_batch(db, ph):
    c, wh, p, admin = ph["c"], ph["wh"], ph["p"], ph["admin"]
    s = _supplier(db, c)
    older = _batch(db, p, wh, 10, 90, age_days=20)                  # FIFO bo'yicha birinchi bo'lardi
    bad = _batch(db, p, wh, 10, 30, status="defect", age_days=1)
    res = create_supplier_return(db, _ret(s, wh, p, 4, batch_id=bad.id), admin)
    assert res["value"] == D(400)
    assert _bq(db, bad) == 6 and _bq(db, older) == 10               # aniq partiya kamaydi
    log = db.query(AuditLog).filter_by(action="RETURN_TO_SUPPLIER", entity_id=s.id).one()
    assert log.new_values["movements"][0]["batches"] == [[bad.id, "4"]]


def test_supplier_return_batch_validation(db, ph, mk):
    c, wh, p, admin = ph["c"], ph["wh"], ph["p"], ph["admin"]
    s = _supplier(db, c)
    mine = _batch(db, p, wh, 3, 90, status="quarantine")
    c3, b3, wh3, _ = mk.tenant()
    foreign = _batch(db, _product(db, c3), wh3, 10, 90)
    with pytest.raises(HTTPException) as e:
        create_supplier_return(db, _ret(s, wh, p, 1, batch_id=foreign.id), admin)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        create_supplier_return(db, _ret(s, wh, p, 5, batch_id=mine.id), admin)   # partiyada 3 ta
    assert e.value.status_code == 400
    assert _bq(db, mine) == 3
    db.refresh(ph["sl"])
    assert D(str(ph["sl"].quantity)) == 100                                          # qoldiq o'zgarmadi


def test_supplier_return_without_batch_id_unchanged_in_pharmacy(db, ph):
    """batch_id berilmasa — avvalgidek eng eskisidan (FIFO)."""
    c, wh, p, admin = ph["c"], ph["wh"], ph["p"], ph["admin"]
    s = _supplier(db, c)
    older = _batch(db, p, wh, 10, 90, age_days=20)
    newer = _batch(db, p, wh, 10, 30, status="quarantine", age_days=1)
    create_supplier_return(db, _ret(s, wh, p, 4), admin)
    assert _bq(db, older) == 6 and _bq(db, newer) == 10


def test_supplier_return_plain_store_ignores_batch_id(db, ph):
    """Regressiya: oddiy korxonada batch_id e'tiborga olinmaydi, FIFO ishlaydi."""
    c2, wh2, p2, admin2 = ph["c2"], ph["wh2"], ph["p2"], ph["admin2"]
    s = _supplier(db, c2)
    older = _batch(db, p2, wh2, 10, 90, age_days=20)
    newer = _batch(db, p2, wh2, 10, 90, age_days=1)
    create_supplier_return(db, _ret(s, wh2, p2, 4, batch_id=newer.id), admin2)
    assert _bq(db, older) == 6 and _bq(db, newer) == 10


# ───────────────────────── i18n / migratsiya ─────────────────────────

def test_migration_and_model_columns():
    src = (ROOT / "alembic" / "versions" / "d3_3_batch_status.py").read_text(encoding="utf-8")
    assert "revision: str = 'd3_3'" in src and "down_revision: Union[str, Sequence[str], None] = 'd3_2'" in src
    for col in ("status", "status_reason", "status_changed_at", "status_changed_by"):
        assert hasattr(Batch, col)
        assert f"ADD COLUMN IF NOT EXISTS {col} " in src


def test_i18n_pending_keys_in_all_languages():
    data = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D3.3.json").read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert data["uz"] and set(data["uz"]) == set(data["ru"]) == set(data["en"])
    panel = (ROOT / "frontend" / "src" / "pages" / "admin" / "pharmacy" / "BatchesPanel.jsx").read_text(encoding="utf-8")
    import re
    used = set(re.findall(r"tf\('(pharmacyBatches\.[A-Za-z0-9_]+)'", panel))
    assert used and used <= set(data["uz"])
