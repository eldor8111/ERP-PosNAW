"""T0.14 — Pending (ulgurji) sotuvda customer_id korxonaga tekshiriladi (SALES-06, CRM-01)."""
from decimal import Decimal

from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale, SaleStatus
from app.models.user import UserRole


def _product(db, c, n):
    p = Product(name=f"Tovar {n}", sku=f"S{n}-{c.id}", barcode=f"B{n}-{c.id}", company_id=c.id,
                sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _customer(db, c, name):
    cu = Customer(name=name, company_id=c.id, debt_balance=Decimal("0"), debt_balances={})
    db.add(cu)
    db.flush()
    return cu


class World:
    def __init__(self, db, mk):
        self.db = db
        self.ca, self.ba, self.wa, self.ua = mk.tenant(UserRole.cashier)
        self.cb, self.bb, self.wb, self.ub = mk.tenant(UserRole.cashier)
        self.pa = _product(db, self.ca, 1)
        self.cust_a = _customer(db, self.ca, "Mijoz A")
        self.cust_b = _customer(db, self.cb, "Mijoz B Sir")

    def body(self, customer_id, **kw):
        d = {
            "items": [{"product_id": self.pa.id, "quantity": 2, "unit_price": 1000}],
            "payment_type": "debt",
            "paid_amount": 0,
            "customer_id": customer_id,
            "warehouse_id": self.wa.id,
        }
        d.update(kw)
        return d

    def foreign_pending(self, cust):
        """Eski ma'lumot: A korxonasi pending sotuvi, unga B mijozi yozilgan."""
        s = Sale(number=f"T014-{cust.id}-{Sale.__table__.name}", cashier_id=self.ua.id,
                 company_id=self.ca.id, warehouse_id=self.wa.id, customer_id=cust.id,
                 total_amount=Decimal("2000"), paid_amount=Decimal("0"), status=SaleStatus.pending,
                 payment_type="debt")
        self.db.add(s)
        self.db.flush()
        return s


def _n_sales(db):
    return db.query(Sale).count()


def test_pending_foreign_customer_404(db, mk, client):
    w = World(db, mk)
    before = _n_sales(db)
    r = client.login(w.ua).post("/api/sales/pending", json=w.body(w.cust_b.id))
    assert r.status_code == 404, r.text
    assert "Mijoz topilmadi" in r.text
    assert "Mijoz B Sir" not in r.text
    assert _n_sales(db) == before


def test_pending_missing_customer_404(db, mk, client):
    w = World(db, mk)
    r = client.login(w.ua).post("/api/sales/pending", json=w.body(99999999))
    assert r.status_code == 404, r.text
    assert _n_sales(db) == 0


def test_pending_own_customer_ok_and_confirm_adds_debt(db, mk, client):
    w = World(db, mk)
    c = client.login(w.ua)
    r = c.post("/api/sales/pending", json=w.body(w.cust_a.id))
    assert r.status_code == 200, r.text
    assert r.json()["customer_name"] == "Mijoz A"
    sid = r.json()["id"]
    r = c.put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 0})
    assert r.status_code == 200, r.text
    db.refresh(w.cust_a)
    assert Decimal(str(w.cust_a.debt_balance)) == Decimal("2000")
    assert float(w.cust_a.debt_balances.get("UZS", 0)) == 2000.0


def test_confirm_legacy_foreign_customer_409_with_paid_amount(db, mk, client):
    w = World(db, mk)
    s = w.foreign_pending(w.cust_b)
    r = client.login(w.ua).put(f"/api/sales/{s.id}", json={"status": "completed", "paid_amount": 0})
    assert r.status_code == 409, r.text
    db.refresh(w.cust_b)
    assert Decimal(str(w.cust_b.debt_balance)) == 0
    assert not w.cust_b.debt_balances


def test_confirm_legacy_foreign_customer_409_without_paid_amount(db, mk, client):
    w = World(db, mk)
    s = w.foreign_pending(w.cust_b)
    r = client.login(w.ua).put(f"/api/sales/{s.id}", json={"status": "completed"})
    assert r.status_code == 409, r.text
    db.refresh(w.cust_b)
    assert Decimal(str(w.cust_b.debt_balance)) == 0
    assert not w.cust_b.debt_balances


def test_confirm_own_customer_without_paid_amount_adds_debt(db, mk, client):
    w = World(db, mk)
    s = w.foreign_pending(w.cust_a)
    r = client.login(w.ua).put(f"/api/sales/{s.id}", json={"status": "completed"})
    assert r.status_code == 200, r.text
    db.refresh(w.cust_a)
    assert Decimal(str(w.cust_a.debt_balance)) == Decimal("2000")
    assert float(w.cust_a.debt_balances.get("UZS", 0)) == 2000.0


def test_full_edit_foreign_customer_404_nothing_changed(db, mk, client):
    w = World(db, mk)
    c = client.login(w.ua)
    r = c.post("/api/sales/pending", json=w.body(w.cust_a.id))
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    r = c.put(f"/api/sales/{sid}", json={
        "items": [{"product_id": w.pa.id, "quantity": 5, "unit_price": 1000}],
        "customer_id": w.cust_b.id,
        "status": "completed",
        "paid_amount": 0,
    })
    assert r.status_code == 404, r.text
    assert "Mijoz B Sir" not in r.text
    db.expire_all()
    sale = db.query(Sale).filter(Sale.id == sid).one()
    assert sale.customer_id == w.cust_a.id
    assert sale.status == SaleStatus.pending
    assert Decimal(str(sale.total_amount)) == Decimal("2000")
    assert Decimal(str(w.cust_b.debt_balance)) == 0


def test_full_edit_own_customer_ok(db, mk, client):
    w = World(db, mk)
    c = client.login(w.ua)
    r = c.post("/api/sales/pending", json=w.body(w.cust_a.id))
    sid = r.json()["id"]
    r = c.put(f"/api/sales/{sid}", json={
        "items": [{"product_id": w.pa.id, "quantity": 3, "unit_price": 1000}],
        "customer_id": w.cust_a.id,
        "status": "completed",
        "paid_amount": 1000,
        "payment_type": "debt",
    })
    assert r.status_code == 200, r.text
    db.refresh(w.cust_a)
    assert Decimal(str(w.cust_a.debt_balance)) == Decimal("2000")


def test_sale_response_hides_foreign_customer_name(db, mk, client):
    w = World(db, mk)
    s = w.foreign_pending(w.cust_b)
    r = client.login(w.ua).get(f"/api/sales/{s.id}")
    assert r.status_code == 200, r.text
    assert "Mijoz B Sir" not in r.text
    assert r.json().get("customer_name") in (None, "")


def test_partial_return_foreign_customer_debt_unchanged(db, mk, client):
    w = World(db, mk)
    c = client.login(w.ua)
    r = c.post("/api/sales/pending", json=w.body(w.cust_a.id))
    sid = r.json()["id"]
    r = c.put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 0})
    assert r.status_code == 200, r.text
    # eski ma'lumot: sotuvga begona mijoz yozilgan
    sale = db.query(Sale).filter(Sale.id == sid).one()
    sale.customer_id = w.cust_b.id
    w.cust_b.debt_balance = Decimal("5000")
    db.flush()
    item_id = sale.items[0].id
    # Qarzga sotilgan — qaytarish ham qarzdan (naqd bo'lsa T0.31 bo'yicha ochiq kassa shart)
    r = c.post(f"/api/sales/{sid}/return-items",
               json={"items": [{"sale_item_id": item_id, "quantity": 1}], "payment_type": "debt"})
    assert r.status_code == 200, r.text  # qaytarish o'tadi, lekin begona mijoz qarziga tegmaydi
    db.refresh(w.cust_b)
    assert Decimal(str(w.cust_b.debt_balance)) == Decimal("5000")
