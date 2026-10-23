"""D4.3 — Dorixona defekturasi: GET /api/pharmacy/defektura, ta'minotchi guruhlari, tavsiya, izolyatsiya va regressiya."""
import json
import pathlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import count

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.purchase_order import POItem, POStatus, PurchaseOrder
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.supplier import Supplier
from app.models.user import UserRole
from app.models.warehouse_stock_setting import WarehouseStockSetting

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


def _product(db, company, name, min_stock=0, cost=500, **kw):
    n = next(_n)
    p = Product(name=name, sku=f"SKU{n}", barcode=f"BC{n:08d}", company_id=company.id,
                min_stock=min_stock, cost_price=cost, sale_price=cost * 2, **kw)
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty):
    db.add(StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=qty))
    db.flush()


def _sell(db, company, user, wh, product, qty, days_ago=1, status=SaleStatus.completed, returned=0):
    n = next(_n)
    s = Sale(number=f"S{n:08d}", cashier_id=user.id, total_amount=1000, paid_amount=1000,
             payment_type=PaymentType.cash, status=status, company_id=company.id, warehouse_id=wh.id,
             branch_id=wh.branch_id, created_at=_now() - timedelta(days=days_ago))
    db.add(s)
    db.flush()
    db.add(SaleItem(sale_id=s.id, product_id=product.id, warehouse_id=wh.id, quantity=qty,
                    unit_price=1000, cost_price=500, subtotal=1000, returned_quantity=returned))
    db.flush()


def _supplier(db, company, name):
    s = Supplier(name=name, company_id=company.id)
    db.add(s)
    db.flush()
    return s


def _purchase(db, company, user, wh, supplier, product, cost, status=POStatus.received, days_ago=5):
    n = next(_n)
    po = PurchaseOrder(number=f"PO{n:08d}", supplier_id=supplier.id, warehouse_id=wh.id, company_id=company.id,
                       status=status, created_by=user.id, created_at=_now() - timedelta(days=days_ago))
    db.add(po)
    db.flush()
    db.add(POItem(po_id=po.id, product_id=product.id, qty_ordered=100, qty_received=100, unit_cost=cost))
    db.flush()
    return po


def _setup(db, mk):
    """Dorixona korxonasi: har xil holatdagi dorilar."""
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    s1, s2 = _supplier(db, c, "Alfa Farm"), _supplier(db, c, "Beta Pharm")

    p1 = _product(db, c, "Paratsetamol", min_stock=10)      # past qoldiq
    _stock(db, p1, w, 5)
    _sell(db, c, admin, w, p1, 30)
    _purchase(db, c, admin, w, s1, p1, 1000, days_ago=20)
    _purchase(db, c, admin, w, s2, p1, 1100, days_ago=10)   # oxirgisi — s2
    _purchase(db, c, admin, w, s1, p1, 9999, status=POStatus.draft, days_ago=1)   # qoralama hisobga olinmaydi

    p2 = _product(db, c, "Amoksitsillin")                    # tugagan (qoldiq qatori yo'q)
    _sell(db, c, admin, w, p2, 15)
    _purchase(db, c, admin, w, s1, p2, 2000)

    p3 = _product(db, c, "Vitamin C", min_stock=5)           # yetarli
    _stock(db, p3, w, 100)
    _sell(db, c, admin, w, p3, 30)

    p4 = _product(db, c, "Analgin", min_stock=10)            # kam, lekin sotilmagan
    _stock(db, p4, w, 2)

    p5 = _product(db, c, "Ibuprofen")                        # qoldiq bor, lekin hammasi muddati o'tgan
    _stock(db, p5, w, 20)
    db.add(Batch(product_id=p5.id, warehouse_id=w.id, company_id=c.id, quantity=20, initial_quantity=20,
                 expiry_date=_now() - timedelta(days=3), purchase_price=300))
    _sell(db, c, admin, w, p5, 30)

    p6 = _product(db, c, "Eski sotuv")                       # faqat 60 kun oldin sotilgan
    _sell(db, c, admin, w, p6, 10, days_ago=60)
    db.flush()
    return c, b, w, admin, (s1, s2), (p1, p2, p3, p4, p5, p6)


def _items(data):
    return {i["product_id"]: (g, i) for g in data["groups"] for i in g["items"]}


def test_defektura_recommendation_and_groups(client, db, mk):
    c, b, w, admin, (s1, s2), (p1, p2, p3, p4, p5, p6) = _setup(db, mk)
    r = client.login(admin).get(f"/api/pharmacy/defektura?branch_id={b.id}&days=30&cover_days=14")
    assert r.status_code == 200, r.text
    data = r.json()
    items = _items(data)
    assert set(items) == {p1.id, p2.id, p5.id}      # p3 yetarli, p4 sotilmagan, p6 davrdan tashqari

    g1, i1 = items[p1.id]
    assert g1["supplier_id"] == s2.id and g1["supplier_name"] == "Beta Pharm"   # oxirgi QABUL QILINGAN xarid
    assert i1["status"] == "low" and i1["current_qty"] == 5 and i1["min_stock"] == 10
    assert i1["sold_qty"] == 30 and i1["avg_daily"] == 1.0
    assert i1["recommended_qty"] == 9               # ceil(1.0*14 - 5)
    assert i1["last_cost"] == 1100 and i1["cost_source"] == "purchase"

    g2, i2 = items[p2.id]
    assert g2["supplier_id"] == s1.id
    assert i2["status"] == "out" and i2["current_qty"] == 0
    assert i2["recommended_qty"] == 7               # ceil(0.5*14 - 0)
    assert i2["last_cost"] == 2000

    # muddati o'tgan qoldiq yaroqli hisoblanmaydi; ta'minotchisi yo'q -> alohida guruh, narx mahsulotdan
    g5, i5 = items[p5.id]
    assert g5["supplier_id"] is None
    assert i5["status"] == "out" and i5["total_qty"] == 20 and i5["expired_qty"] == 20 and i5["current_qty"] == 0
    assert i5["recommended_qty"] == 14 and i5["cost_source"] == "product"
    assert data["groups"][-1]["supplier_id"] is None   # ta'minotchisizlar oxirida

    assert g1["total_recommended"] == 9 and g1["estimated_cost"] == 9 * 1100
    assert data["total_items"] == 3
    assert any(x["id"] == w.id for x in data["warehouses"])


def test_defektura_params_days_and_cover(client, db, mk):
    c, b, w, admin, _, (p1, p2, p3, p4, p5, p6) = _setup(db, mk)
    cl = client.login(admin)
    # days=90: eski sotuv ham kiradi (10/90 kunlik, tugagan)
    items = _items(cl.get("/api/pharmacy/defektura?days=90&cover_days=30").json())
    assert p6.id in items
    assert items[p6.id][1]["status"] == "out"
    assert items[p6.id][1]["recommended_qty"] == 4   # ceil(10/90*30) = ceil(3.33)
    # cover_days kichik: p1 uchun tavsiya 0 (yetarli), lekin ro'yxatda qoladi
    items = _items(cl.get("/api/pharmacy/defektura?days=30&cover_days=3").json())
    assert items[p1.id][1]["recommended_qty"] == 0   # ceil(3 - 5) < 0 -> 0
    assert cl.get("/api/pharmacy/defektura?days=0").status_code == 422
    assert cl.get("/api/pharmacy/defektura?cover_days=0").status_code == 422


def test_defektura_warehouse_min_setting_and_returns(client, db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    p = _product(db, c, "Ombor sozlamali", min_stock=0)
    _stock(db, p, w, 8)
    db.add(WarehouseStockSetting(company_id=c.id, warehouse_id=w.id, product_id=p.id, min_qty=10))
    _sell(db, c, admin, w, p, 50, returned=10)
    # qaytarilgan miqdor sotuvdan ayiriladi, bekor qilingan sotuv hisoblanmaydi
    _sell(db, c, admin, w, p, 100, status=SaleStatus.cancelled)
    db.flush()
    r = client.login(admin).get(f"/api/pharmacy/defektura?warehouse_id={w.id}&days=20&cover_days=10")
    assert r.status_code == 200, r.text
    i = _items(r.json())[p.id][1]
    assert i["min_stock"] == 10 and i["sold_qty"] == 40 and i["avg_daily"] == 2.0
    assert i["recommended_qty"] == 12               # ceil(2*10 - 8)


def test_defektura_isolation_between_companies(client, db, mk):
    c, b, w, admin, _, (p1, *_rest) = _setup(db, mk)
    # B korxona ham dorixona, o'z defekturasi bor
    c2, b2, w2, admin2 = mk.tenant()
    _pharmacy(db, c2)
    q = _product(db, c2, "B dori", min_stock=5)
    _stock(db, q, w2, 1)
    _sell(db, c2, admin2, w2, q, 30)

    cl = client.login(admin)
    ids = set(_items(cl.get("/api/pharmacy/defektura").json()))
    assert q.id not in ids and p1.id in ids                         # o'ziniki ishlaydi, begonasi ko'rinmaydi
    assert cl.get(f"/api/pharmacy/defektura?branch_id={b2.id}").status_code == 404
    assert cl.get(f"/api/pharmacy/defektura?warehouse_id={w2.id}").status_code == 404

    ids2 = set(_items(client.login(admin2).get("/api/pharmacy/defektura").json()))
    assert ids2 == {q.id}


def test_defektura_roles_and_branch_scope(client, db, mk):
    c, b, w, admin, _, (p1, *_rest) = _setup(db, mk)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    assert client.login(cashier).get("/api/pharmacy/defektura").status_code == 403
    # boshqa filial xodimi (warehouse roli) o'z filialida cheklangan: begona filial so'ralsa 403
    b3 = mk.branch(c)
    w3 = mk.warehouse(c, b3)
    wh_user = mk.user(c, role=UserRole.warehouse, branch=b3)
    cl = client.login(wh_user)
    assert cl.get(f"/api/pharmacy/defektura?branch_id={b.id}").status_code == 403
    r = cl.get("/api/pharmacy/defektura")
    assert r.status_code == 200
    assert r.json()["groups"] == []                                  # o'z filialida sotuv yo'q


def test_regular_shop_unaffected(client, db, mk):
    """Regressiya: oddiy do'kon — dorixona endpointi yopiq, mavjud endpointlar o'zgarmagan."""
    c, b, w, admin = mk.tenant()
    p = _product(db, c, "Oddiy tovar", min_stock=10)
    _stock(db, p, w, 1)
    _sell(db, c, admin, w, p, 30)
    cl = client.login(admin)
    r = cl.get("/api/pharmacy/defektura")
    assert r.status_code == 403 and "Dorixona" in r.json()["detail"]
    r = cl.get("/api/inventory/stock")
    assert r.status_code == 200
    assert any(row["product_id"] == p.id for row in r.json())
    assert cl.get("/api/companies/me/features").json()["pharmacy"] is False


def test_draft_purchase_from_recommendation(client, db, mk):
    """Frontend shu formatda POST /api/purchase-orders (qoralama) yuboradi — mavjud endpoint o'zgarmagan."""
    c, b, w, admin, (s1, s2), (p1, *_rest) = _setup(db, mk)
    cl = client.login(admin)
    data = cl.get(f"/api/pharmacy/defektura?branch_id={b.id}").json()
    g, i = _items(data)[p1.id]
    payload = {
        "supplier_id": g["supplier_id"], "warehouse_id": data["warehouses"][0]["id"], "status": "draft",
        "note": "Defektura bo'yicha avtomatik qoralama",
        "items": [{"product_id": it["product_id"], "qty_ordered": it["recommended_qty"], "unit_cost": it["last_cost"]}
                  for it in g["items"] if it["recommended_qty"] > 0 and it["product_type"] != "parent"],
    }
    r = cl.post("/api/purchase-orders", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "draft"
    assert any(x["product_id"] == p1.id and Decimal(str(x["qty_ordered"])) == 9 for x in r.json()["items"])


def test_pending_i18n_keys_and_frontend_wiring():
    f = pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D4.3.json"
    data = json.loads(f.read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"]) and data["uz"]
    src = (ROOT / "frontend/src/pages/admin/pharmacy/DefekturaPanel.jsx").read_text(encoding="utf-8")
    assert "/pharmacy/defektura" in src and "/purchase-orders" in src
    for k in data["uz"]:
        assert f"'{k}'" in src, k
