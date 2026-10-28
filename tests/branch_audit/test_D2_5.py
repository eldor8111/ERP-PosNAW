"""D2.5 — Retseptli dori sotuvi (backend): retsept saqlash. P.13: dorixonada sotuv cheklanmaydi — retsept ixtiyoriy.

Qamrov: retseptli va nazoratdagi dori retseptsiz ham sotiladi (rx_mode, blank turi rad etmaydi); berilgan retsept
(to'liq bo'lmasa ham) va retseptsiz sotish sababi saqlanadi; retsept product_id yoki item_index bilan, dori
aniqlanmagan yozuv — `rx_skipped` ogohlantirishi, 60 kundan eski retsept ogohlantirishi, aralash savat,
oflayn (created_at + Idempotency-Key) sotuv, sotuv tafsilotida `prescriptions`,
oddiy korxona regressiyasi (rx belgili mahsulot ham avvalgidek sotiladi, yangi maydonlar e'tiborsiz) va ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D2_5.py -q -p no:cacheprovider
"""
import itertools
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.moliya import Wallet
from app.models.prescription import SalePrescription
from app.models.product import Product
from app.models.product_pharma import ProductPharma
from app.models.sale import Sale, SaleItem
from app.models.user import UserWallet
from app.services.batch_allocator import tashkent_today

_n = itertools.count(1)


@pytest.fixture(autouse=True)
def _no_telegram(monkeypatch):
    """Sotuvdan keyingi Telegram bildirishnomasi jonli bazaga ulanmasin (fon vazifasi)."""
    import app.routers.sales as sales_router
    monkeypatch.setattr(sales_router, "notify_new_sale", lambda *a, **k: None)


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


def _product(db, c, wh, rx=False, control="none", pharma=True, qty=100):
    n = next(_n)
    p = Product(name=f"Dori D25-{n}", sku=f"D25-{n}", barcode=f"BD25-{n:06d}", company_id=c.id,
                cost_price=D("500"), sale_price=D("1000"))
    db.add(p)
    db.flush()
    if pharma:
        db.add(ProductPharma(product_id=p.id, company_id=c.id, is_rx=rx, control_class=control))
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty)))
    # dorixona rejimi yaroqli partiya talab qiladi (muddati kelajakda)
    db.add(Batch(product_id=p.id, warehouse_id=wh.id, quantity=D(qty), initial_quantity=D(qty), purchase_price=D("500"),
                 company_id=c.id, expiry_date=datetime.combine(tashkent_today() + timedelta(days=200), time.min)))
    db.flush()
    return p


def _body(lines, wh, **extra):
    total = sum(1000 * q for _, q in lines)
    body = {"items": [{"product_id": p.id, "quantity": q, "unit_price": 1000} for p, q in lines],
            "payment_type": "cash", "paid_amount": total, "paid_cash": total,
            "payments": [{"type": "cash", "amount": total}], "warehouse_id": wh.id}
    body.update(extra)
    return body


def _rx(product=None, days_ago=1, blank="simple", index=None, **kw):
    d = {"number": kw.pop("number", "AB-123456"), "issued_at": (tashkent_today() - timedelta(days=days_ago)).isoformat(),
         "doctor": "Karimov A.", "clinic": "3-poliklinika", "blank_type": blank}
    if product is not None:
        d["product_id"] = product.id
    if index is not None:
        d["item_index"] = index
    d.update(kw)
    return d


def _stock(db, p):
    sl = db.query(StockLevel).filter_by(product_id=p.id).one()
    db.refresh(sl)
    return D(str(sl.quantity))


@pytest.fixture
def ph(db, mk):
    """Dorixona yoqilgan korxona A (kassa bilan) va oddiy korxona B."""
    c, b, wh, admin = mk.tenant()
    _wallet(db, c, b, admin)
    _enable(db, c)
    c2, b2, wh2, admin2 = mk.tenant()
    _wallet(db, c2, b2, admin2)
    return dict(c=c, b=b, wh=wh, admin=admin, c2=c2, wh2=wh2, admin2=admin2)


# ───────────────────────── rx_mode = warn ─────────────────────────

def test_rx_drug_sells_without_prescription_or_reason(client, db, ph):
    """P.13: retseptli dori retseptsiz va sababsiz ham sotiladi — yozuv saqlanmaydi, ogohlantirish yo'q."""
    p = _product(db, ph["c"], ph["wh"], rx=True)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"]))
    assert r.status_code == 200, r.text
    assert _stock(db, p) == 99 and r.json()["warnings"] == []
    assert db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).count() == 0
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"], rx_override_reason="   "))
    assert r.status_code == 200 and db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).count() == 0


def test_warn_mode_reason_allows_sale_and_is_saved(client, db, ph):
    p = _product(db, ph["c"], ph["wh"], rx=True)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 2)], ph["wh"],
                                                                  rx_override_reason="Mijoz retseptni olib kelmadi"))
    assert r.status_code == 200, r.text
    assert _stock(db, p) == 98
    row = db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).one()
    assert row.reason_without_rx == "Mijoz retseptni olib kelmadi"
    assert row.number is None and row.product_id == p.id and row.company_id == ph["c"].id
    item = db.query(SaleItem).filter_by(sale_id=r.json()["id"]).one()
    assert row.sale_item_id == item.id
    # sotuv tafsilotida ko'rinadi
    g = client.login(ph["admin"]).get(f"/api/sales/{r.json()['id']}")
    assert g.status_code == 200
    pr = g.json()["prescriptions"]
    assert len(pr) == 1 and pr[0]["reason_without_rx"] == "Mijoz retseptni olib kelmadi"
    assert pr[0]["sale_item_id"] == item.id


def test_rx_mode_defaults_to_warn_for_old_settings(client, db, ph):
    """Sozlama bo'lmasa ham (default) rx_mode='warn' ishlaydi."""
    p = _product(db, ph["c"], ph["wh"], rx=True)
    assert ph["c"].pharmacy_settings in (None, {}) or "rx_mode" not in (ph["c"].pharmacy_settings or {})
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"], rx_override_reason="sabab"))
    assert r.status_code == 200, r.text


# ───────────────────────── rx_mode = block ─────────────────────────

def test_old_block_setting_no_longer_rejects(client, db, ph):
    """P.13: eski rx_mode='block' sozlamasi sotuvni rad etmaydi; sabab berilsa saqlanadi."""
    ph["c"].pharmacy_settings = {"rx_mode": "block"}
    db.flush()
    p = _product(db, ph["c"], ph["wh"], rx=True)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"], rx_override_reason="shoshilinch"))
    assert r.status_code == 200, r.text
    assert db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).one().reason_without_rx == "shoshilinch"


def test_block_mode_with_prescription_is_ok(client, db, ph):
    ph["c"].pharmacy_settings = {"rx_mode": "block"}
    db.flush()
    p = _product(db, ph["c"], ph["wh"], rx=True)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=[_rx(p)]))
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []


# ───────────────────────── retsept saqlash ─────────────────────────

def test_prescription_saved_by_product_id_and_visible_in_detail(client, db, ph):
    p = _product(db, ph["c"], ph["wh"], rx=True)
    q = _product(db, ph["c"], ph["wh"])      # oddiy dori — retsept shart emas
    r = client.login(ph["admin"]).post(
        "/api/sales/", json=_body([(q, 1), (p, 3)], ph["wh"], prescriptions=[_rx(p, patient="Aliyev B.")]))
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    row = db.query(SalePrescription).filter_by(sale_id=sid).one()
    assert (row.number, row.doctor, row.clinic, row.patient, row.blank_type) == \
        ("AB-123456", "Karimov A.", "3-poliklinika", "Aliyev B.", "simple")
    assert row.reason_without_rx is None
    item_p = db.query(SaleItem).filter_by(sale_id=sid, product_id=p.id).one()
    assert row.sale_item_id == item_p.id
    out = client.login(ph["admin"]).get(f"/api/sales/{sid}").json()["prescriptions"]
    assert len(out) == 1 and out[0]["number"] == "AB-123456" and out[0]["product_id"] == p.id
    assert out[0]["issued_at"] == (tashkent_today() - timedelta(days=1)).isoformat()


def test_prescription_by_item_index(client, db, ph):
    q = _product(db, ph["c"], ph["wh"])
    p = _product(db, ph["c"], ph["wh"], rx=True)
    r = client.login(ph["admin"]).post(
        "/api/sales/", json=_body([(q, 1), (p, 1)], ph["wh"], prescriptions=[_rx(index=1)]))
    assert r.status_code == 200, r.text
    row = db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).one()
    assert row.product_id == p.id


def test_prescription_invalid_input_never_blocks(client, db, ph):
    """P.13: noto'g'ri / to'liq bo'lmagan retsept sotuvni to'xtatmaydi: dori aniqlanmasa — ogohlantirish (saqlanmaydi),
    noma'lum blank turi — "simple", to'liq bo'lmagani — berilgan maydonlar bilan saqlanadi."""
    p = _product(db, ph["c"], ph["wh"], rx=True)
    other = _product(db, ph["c"], ph["wh"])
    cl = client.login(ph["admin"])

    def sell(pres):
        r = cl.post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=pres))
        assert r.status_code == 200, (pres, r.text)
        return r.json(), db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).all()

    for pres in ([_rx(other)], [_rx()], [_rx(index=5)], [{"product_id": p.id}]):
        out, rows = sell(pres)
        assert rows == [] and [w["code"] for w in out["warnings"]] == ["rx_skipped"], pres
    _out, rows = sell([_rx(p, blank="fake")])
    assert [x.blank_type for x in rows] == ["simple"]
    _out, rows = sell([_rx(p, days_ago=-3)])
    assert rows[0].issued_at == tashkent_today() + timedelta(days=3)
    _out, rows = sell([{"product_id": p.id, "number": "X", "issued_at": "noto'g'ri"}])
    assert [(x.number, x.issued_at, x.doctor, x.clinic) for x in rows] == [("X", None, None, None)]
    assert _stock(db, p) == 93 and _stock(db, other) == 100


def test_old_prescription_gives_warning_but_sells(client, db, ph):
    p = _product(db, ph["c"], ph["wh"], rx=True)
    q = _product(db, ph["c"], ph["wh"], rx=True)
    cl = client.login(ph["admin"])
    r = cl.post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=[_rx(p, days_ago=61, number="OLD-1")]))
    assert r.status_code == 200, r.text
    w = r.json()["warnings"]
    assert len(w) == 1 and w[0]["code"] == "rx_old" and w[0]["age_days"] == 61 and w[0]["number"] == "OLD-1"
    assert w[0]["product_id"] == p.id
    r = cl.post("/api/sales/", json=_body([(q, 1)], ph["wh"], prescriptions=[_rx(q, days_ago=60)]))
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []      # aynan 60 kun — ogohlantirishsiz


# ───────────────────────── nazorat toifasi ─────────────────────────

@pytest.mark.parametrize("control", ["narcotic", "psychotropic", "potent", "precursor"])
def test_controlled_drug_sells_without_prescription(client, db, ph, control):
    """P.13: nazoratdagi dori ham retseptsiz sotiladi; sabab berilsa saqlanadi."""
    p = _product(db, ph["c"], ph["wh"], rx=False, control=control)      # is_rx=False bo'lsa ham
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"], rx_override_reason="sabab bor"))
    assert r.status_code == 200, r.text
    assert _stock(db, p) == 99
    assert db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).one().reason_without_rx == "sabab bor"


@pytest.mark.parametrize("control", ["narcotic", "psychotropic", "potent", "precursor"])
def test_controlled_drug_simple_blank_is_saved(client, db, ph, control):
    p = _product(db, ph["c"], ph["wh"], rx=True, control=control)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=[_rx(p, blank="simple")]))
    assert r.status_code == 200, r.text
    assert db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).one().blank_type == "simple"


@pytest.mark.parametrize("control,blank", [("narcotic", "form_107"), ("narcotic", "special"),
                                           ("psychotropic", "form_148"), ("potent", "special")])
def test_controlled_drug_sells_with_special_blank(client, db, ph, control, blank):
    p = _product(db, ph["c"], ph["wh"], rx=True, control=control)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=[_rx(p, blank=blank)]))
    assert r.status_code == 200, r.text
    assert db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).one().blank_type == blank
    assert _stock(db, p) == 99


def test_mixed_cart_sells_and_records_given_data(client, db, ph):
    rx = _product(db, ph["c"], ph["wh"], rx=True)
    nar = _product(db, ph["c"], ph["wh"], control="narcotic")
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(rx, 1), (nar, 1)], ph["wh"],
                                                                  rx_override_reason="sabab"))
    assert r.status_code == 200, r.text
    rows = db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).all()
    assert {(x.product_id, x.reason_without_rx) for x in rows} == {(rx.id, "sabab"), (nar.id, "sabab")}
    # narkotikka retsept bor, oddiy retseptli dori uchun sabab bor -> ikkala yozuv saqlanadi
    r = client.login(ph["admin"]).post("/api/sales/", json=_body(
        [(rx, 1), (nar, 1)], ph["wh"], rx_override_reason="sabab", prescriptions=[_rx(nar, blank="form_107")]))
    assert r.status_code == 200, r.text
    rows = db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).all()
    assert {(x.product_id, x.number is None) for x in rows} == {(rx.id, True), (nar.id, False)}


def test_non_rx_product_in_pharmacy_needs_nothing(client, db, ph):
    p = _product(db, ph["c"], ph["wh"], rx=False)
    q = _product(db, ph["c"], ph["wh"], pharma=False)       # dori ma'lumoti yo'q mahsulot
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1), (q, 1)], ph["wh"]))
    assert r.status_code == 200, r.text
    assert db.query(SalePrescription).count() == 0
    assert r.json()["warnings"] == []


# ───────────────────────── oflayn navbat ─────────────────────────

def test_offline_sale_without_prescription_is_accepted(client, db, ph):
    """P.13: oflayn navbatdagi retseptsiz sotuv ham qabul qilinadi (rad etilib qolib ketmaydi)."""
    p = _product(db, ph["c"], ph["wh"], rx=True)
    created = (datetime.utcnow() - timedelta(minutes=30)).isoformat()
    body = _body([(p, 1)], ph["wh"], created_at=created, local_id="offline-uuid-1")
    cl = client.login(ph["admin"])
    r = cl.post("/api/sales/", json=body, headers={"Idempotency-Key": "d25-offline-1"})
    assert r.status_code == 200, r.text
    body2 = _body([(p, 1)], ph["wh"], created_at=created, local_id="offline-uuid-2", prescriptions=[_rx(p)])
    r = cl.post("/api/sales/", json=body2, headers={"Idempotency-Key": "d25-offline-2"})
    assert r.status_code == 200, r.text
    assert db.query(SalePrescription).filter_by(sale_id=r.json()["id"]).count() == 1


# ───────────────────────── oddiy korxona (regressiya) ─────────────────────────

def test_regular_company_ignores_rx_rules_and_fields(client, db, ph):
    c2, wh2, admin2 = ph["c2"], ph["wh2"], ph["admin2"]
    rx = _product(db, c2, wh2, rx=True)
    nar = _product(db, c2, wh2, control="narcotic")
    # retsept/sabab yuborilmasa ham sotiladi (modul o'chiq)
    r = client.login(admin2).post("/api/sales/", json=_body([(rx, 1), (nar, 1)], wh2))
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []
    # yangi maydonlar (hatto noto'g'ri bo'lsa ham) e'tiborsiz: saqlanmaydi, 400/422 bermaydi
    r = client.login(admin2).post("/api/sales/", json=_body(
        [(rx, 1)], wh2, prescriptions=[{"foo": "bar"}, _rx(rx, days_ago=200, blank="simple")], rx_override_reason="x"))
    assert r.status_code == 200, r.text
    assert r.json()["warnings"] == []
    assert db.query(SalePrescription).count() == 0
    g = client.login(admin2).get(f"/api/sales/{r.json()['id']}")
    assert g.status_code == 200 and g.json()["prescriptions"] == []


def test_pharmacy_disabled_after_package_expiry_behaves_as_regular(client, db, mk):
    c, b, wh, admin = mk.tenant()
    _wallet(db, c, b, admin)
    c.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=now - timedelta(days=40), ends_at=now - timedelta(days=10)))
    db.flush()
    p = _product(db, c, wh, rx=True)
    r = client.login(admin).post("/api/sales/", json=_body([(p, 1)], wh))
    assert r.status_code == 200, r.text


# ───────────────────────── izolyatsiya ─────────────────────────

def test_prescriptions_isolated_between_companies(client, db, ph):
    p = _product(db, ph["c"], ph["wh"], rx=True)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=[_rx(p)]))
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    # ijobiy: o'z korxonasi ko'radi
    assert len(client.login(ph["admin"]).get(f"/api/sales/{sid}").json()["prescriptions"]) == 1
    # B korxona foydalanuvchisi A sotuvini ko'ra olmaydi
    assert client.login(ph["admin2"]).get(f"/api/sales/{sid}").status_code in (403, 404)
    # B korxona A mahsulotini sota olmaydi va A retsept jadvaliga yozilmaydi
    before = db.query(SalePrescription).count()
    r2 = client.login(ph["admin2"]).post("/api/sales/", json=_body([(p, 1)], ph["wh2"], prescriptions=[_rx(p)]))
    assert r2.status_code in (400, 403, 404)
    assert db.query(SalePrescription).count() == before


def test_other_company_pharma_flags_do_not_leak(client, db, ph):
    """B korxona (oddiy) mahsulotidagi rx belgisi A ning sotuviga ta'sir qilmaydi va aksincha."""
    a_prod = _product(db, ph["c"], ph["wh"], rx=False)
    b_prod = _product(db, ph["c2"], ph["wh2"], rx=True)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(a_prod, 1)], ph["wh"]))
    assert r.status_code == 200, r.text
    r = client.login(ph["admin2"]).post("/api/sales/", json=_body([(b_prod, 1)], ph["wh2"]))
    assert r.status_code == 200, r.text
