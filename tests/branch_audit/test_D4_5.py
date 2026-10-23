"""D4.5 — Dorixona tahlili: GET /api/pharmacy/analytics/sales va /summary, izolyatsiya va regressiya."""
import json
import pathlib
from datetime import datetime, timedelta, timezone
from itertools import count

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole

ROOT = pathlib.Path(__file__).resolve().parents[2]
_n = count(1)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _pharmacy(db, company):
    company.pharmacy_enabled = True
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=datetime.now(timezone.utc),
                          ends_at=datetime.now(timezone.utc) + timedelta(days=30)))
    db.flush()


def _product(db, company, name, manufacturer=None, country=None, is_rx=False, min_stock=0):
    n = next(_n)
    p = Product(name=name, sku=f"AN{n}", barcode=f"AB{n:08d}", company_id=company.id,
                min_stock=min_stock, cost_price=500, sale_price=1000)
    db.add(p)
    db.flush()
    if manufacturer or country or is_rx:
        db.add(ProductPharma(product_id=p.id, company_id=company.id, manufacturer=manufacturer,
                             country=country, is_rx=is_rx))
        db.flush()
    return p


def _substance(db, company, name):
    s = PharmaSubstance(company_id=company.id, name_uz=name)
    db.add(s)
    db.flush()
    return s


def _link(db, product, substance):
    db.add(ProductSubstance(product_id=product.id, substance_id=substance.id))
    db.flush()


def _sell(db, company, user, wh, product, qty, price, cost, days_ago=1, returned=0,
          status=SaleStatus.completed):
    n = next(_n)
    s = Sale(number=f"AS{n:08d}", cashier_id=user.id, total_amount=price * qty, paid_amount=price * qty,
             payment_type=PaymentType.cash, status=status, company_id=company.id, warehouse_id=wh.id,
             branch_id=wh.branch_id, created_at=_now() - timedelta(days=days_ago))
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, warehouse_id=wh.id, quantity=qty,
                    unit_price=price, cost_price=cost, subtotal=price * qty, returned_quantity=returned))
    db.flush()
    return s


def _by_name(data):
    return {g["name"]: g for g in data["groups"]}


def _setup(db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    para = _substance(db, c, "Paratsetamol")
    ibu = _substance(db, c, "Ibuprofen")
    p1 = _product(db, c, "Panadol", manufacturer="GSK", country="Angliya")
    p2 = _product(db, c, "Efferalgan", manufacturer="UPSA", country="Fransiya")
    p3 = _product(db, c, "Nurofen", manufacturer="gsk ", country="Angliya")   # registr/probel farqi bilan bir xil
    p4 = _product(db, c, "Nomalum dori")                                        # ma'lumotsiz
    _link(db, p1, para)
    _link(db, p2, para)
    _link(db, p3, ibu)
    _link(db, p3, para)   # ikki moddali
    _sell(db, c, admin, w, p1, 10, 1000, 600)     # tushum 10000, tannarx 6000
    _sell(db, c, admin, w, p2, 5, 2000, 1000)     # 10000 / 5000
    _sell(db, c, admin, w, p3, 4, 3000, 2000, returned=1)   # sof 3: 9000 / 6000
    _sell(db, c, admin, w, p4, 2, 1000, 400)      # 2000 / 800
    _sell(db, c, admin, w, p1, 100, 1000, 600, days_ago=60)                       # davrdan tashqari
    _sell(db, c, admin, w, p1, 100, 1000, 600, status=SaleStatus.cancelled)       # bekor qilingan
    return c, b, w, admin, (p1, p2, p3, p4)


def test_sales_by_substance(client, db, mk):
    c, b, w, admin, (p1, p2, p3, p4) = _setup(db, mk)
    r = client.login(admin).get(f"/api/pharmacy/analytics/sales?group=substance&branch_id={b.id}")
    assert r.status_code == 200, r.text
    data = r.json()
    g = _by_name(data)
    # Paratsetamol: p1 + p2 + p3
    par = g["Paratsetamol"]
    assert par["quantity"] == 18 and par["revenue"] == 29000 and par["cost"] == 17000
    assert par["margin"] == 12000 and par["margin_pct"] == round(12000 / 29000 * 100, 2)
    assert par["markup_pct"] == round(12000 / 17000 * 100, 2) and par["products_count"] == 3
    ibu = g["Ibuprofen"]
    assert ibu["quantity"] == 3 and ibu["revenue"] == 9000 and ibu["cost"] == 6000   # qaytarilgani ayirilgan
    # Moddasiz dori -> "ko'rsatilmagan" guruh, oxirida
    assert data["groups"][-1]["name"] is None and data["groups"][-1]["revenue"] == 2000
    # Jami moddalar bo'yicha takrorlanmaydi
    assert data["total"]["revenue"] == 31000 and data["total"]["cost"] == 17800 and data["total"]["margin"] == 13200
    assert data["overlap"] is True
    assert data["groups"][0]["name"] == "Paratsetamol"      # tushum bo'yicha kamayish


def test_sales_by_manufacturer_and_country(client, db, mk):
    c, b, w, admin, _ = _setup(db, mk)
    cl = client.login(admin)
    data = cl.get("/api/pharmacy/analytics/sales?group=manufacturer").json()
    g = _by_name(data)
    assert g["GSK"]["revenue"] == 19000 and g["GSK"]["products_count"] == 2     # "gsk " birlashtirildi
    assert g["UPSA"]["revenue"] == 10000 and g[None]["revenue"] == 2000
    assert data["overlap"] is False and data["total"]["revenue"] == 31000
    data = cl.get("/api/pharmacy/analytics/sales?group=country").json()
    g = _by_name(data)
    assert g["Angliya"]["revenue"] == 19000 and g["Fransiya"]["revenue"] == 10000
    assert g["Angliya"]["margin"] == 19000 - 12000


def test_sales_period_and_validation(client, db, mk):
    c, b, w, admin, (p1, *_r) = _setup(db, mk)
    cl = client.login(admin)
    today = _now().date()
    # 90 kunlik davr: eski sotuv ham kiradi (10 + 100 dona p1, p3 dan 3 dona)
    frm = (today - timedelta(days=90)).isoformat()
    data = cl.get(f"/api/pharmacy/analytics/sales?group=manufacturer&from={frm}&to={today.isoformat()}").json()
    assert _by_name(data)["GSK"]["quantity"] == 10 + 100 + 3
    assert data["from"] == frm
    assert cl.get("/api/pharmacy/analytics/sales?group=boshqa").status_code == 422
    assert cl.get(f"/api/pharmacy/analytics/sales?from={today.isoformat()}&to={frm}").status_code == 400
    # sotuv bo'lmagan davr
    old = (today - timedelta(days=200)).isoformat()
    data = cl.get(f"/api/pharmacy/analytics/sales?from={old}&to={old}").json()
    assert data["groups"] == [] and data["total"]["revenue"] == 0 and data["total"]["margin_pct"] is None


def test_summary(client, db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    c.pharmacy_settings = {"expiry_warn_days": 30}
    rx = _product(db, c, "Retseptli", is_rx=True)
    plain = _product(db, c, "Oddiy", min_stock=10)
    out = _product(db, c, "Tugagan")
    db.add(StockLevel(product_id=rx.id, warehouse_id=w.id, quantity=50))
    db.add(StockLevel(product_id=plain.id, warehouse_id=w.id, quantity=3))       # minimaldan past
    for days, qty in ((10, 5), (20, 5), (90, 5), (-5, 5), (-40, 5), (15, 0)):    # oxirgisi qoldiqsiz
        db.add(Batch(product_id=rx.id, warehouse_id=w.id, company_id=c.id, quantity=qty, initial_quantity=5,
                     expiry_date=_now() + timedelta(days=days), purchase_price=100))
    _sell(db, c, admin, w, rx, 2, 1000, 500, days_ago=0)
    _sell(db, c, admin, w, rx, 1, 1000, 500, days_ago=0)
    _sell(db, c, admin, w, rx, 1, 1000, 500, days_ago=3)                          # bugun emas
    _sell(db, c, admin, w, plain, 1, 1000, 500, days_ago=2)
    _sell(db, c, admin, w, out, 1, 1000, 500, days_ago=2)
    db.flush()
    r = client.login(admin).get(f"/api/pharmacy/analytics/summary?branch_id={b.id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["expiring_batches"] == 2 and d["expired_batches"] == 2 and d["expiry_warn_days"] == 30
    assert d["defektura_count"] == 2          # plain (kam) + out (tugagan); rx yetarli
    assert d["rx_sales_today"] == 2


def test_isolation_between_companies(client, db, mk):
    c, b, w, admin, (p1, *_r) = _setup(db, mk)
    c2, b2, w2, admin2 = mk.tenant()
    _pharmacy(db, c2)
    q = _product(db, c2, "B dori", manufacturer="Begona", country="Hind")
    _sell(db, c2, admin2, w2, q, 7, 1000, 100)
    cl = client.login(admin)
    data = cl.get("/api/pharmacy/analytics/sales?group=manufacturer").json()
    assert "Begona" not in _by_name(data) and "GSK" in _by_name(data)         # o'ziniki ishlaydi
    assert cl.get(f"/api/pharmacy/analytics/sales?branch_id={b2.id}").status_code == 404
    assert cl.get(f"/api/pharmacy/analytics/summary?branch_id={b2.id}").status_code == 404
    d2 = client.login(admin2).get("/api/pharmacy/analytics/sales?group=manufacturer").json()
    assert set(_by_name(d2)) == {"Begona"} and d2["total"]["revenue"] == 7000


def test_roles_and_branch_scope(client, db, mk):
    c, b, w, admin, _ = _setup(db, mk)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    assert client.login(cashier).get("/api/pharmacy/analytics/sales").status_code == 403
    assert client.login(cashier).get("/api/pharmacy/analytics/summary").status_code == 403
    b3 = mk.branch(c)
    mk.warehouse(c, b3)
    wh_user = mk.user(c, role=UserRole.warehouse, branch=b3)
    cl = client.login(wh_user)
    assert cl.get(f"/api/pharmacy/analytics/sales?branch_id={b.id}").status_code == 403
    r = cl.get("/api/pharmacy/analytics/sales")
    assert r.status_code == 200 and r.json()["groups"] == []                  # o'z filialida sotuv yo'q


def test_regular_shop_unaffected(client, db, mk):
    """Regressiya: oddiy do'kon — dorixona endpointlari yopiq, mavjud endpointlar o'zgarmagan."""
    c, b, w, admin = mk.tenant()
    p = _product(db, c, "Oddiy tovar")
    db.add(StockLevel(product_id=p.id, warehouse_id=w.id, quantity=5))
    _sell(db, c, admin, w, p, 3, 1000, 500)
    cl = client.login(admin)
    for url in ("/api/pharmacy/analytics/sales", "/api/pharmacy/analytics/summary"):
        r = cl.get(url)
        assert r.status_code == 403 and "Dorixona" in r.json()["detail"]
    r = cl.get("/api/inventory/stock")
    assert r.status_code == 200 and any(row["product_id"] == p.id for row in r.json())
    assert cl.get("/api/companies/me/features").json()["pharmacy"] is False


def test_pending_i18n_keys_and_frontend_wiring():
    data = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D4.5.json").read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"]) and data["uz"]
    src = (ROOT / "frontend/src/pages/admin/pharmacy/AnalyticsPanel.jsx").read_text(encoding="utf-8")
    assert "/pharmacy/analytics/sales" in src and "/pharmacy/analytics/summary" in src
    assert "features?.pharmacy" in src
    for k in data["uz"]:
        assert f"'{k}'" in src, k
