"""R5 — Restoran to'lovi va ingredientlarni yechish (R7.1, R7.3).

Qamrov: Sale yaratilishi (taom qoldig'isiz, xizmat haqi qatori, chegirma), aralash to'lov va qaytim, kassa balansi,
ingredientlar oshxona omboridan (to'lovda / yuborishda), bekor qilingan taom chiqimi, yarim tayyor yoyilishi,
taom tannarxi sotuv qatorida, takroriy to'lov, ruxsatlar, umumiy qaytarish/o'chirishdan himoya, fiskal savat.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_R5.py -q -p no:cacheprovider
"""
import os
from decimal import Decimal as D

import pytest

from app.models.inventory import StockLevel, StockMovement
from app.models.moliya import Wallet
from app.models.product import Product
from app.models.restaurant_order import RestaurantOrder
from app.models.sale import Sale, SaleItem
from app.models.user import UserRole, UserWallet
from app.models.warehouse import Warehouse
from app.services import restaurant_orders as svc
from app.services.restaurant import get_kitchen_warehouse
from app.services.restaurant_menu import create_item, save_card
from tests.branch_audit.test_R3 import PIN, R

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
O = "/api/restaurant/orders"


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


@pytest.fixture(autouse=True)
def _reset_pin_fails():
    svc._PIN_FAILS.clear()
    yield


class RP(R):
    """R3 restorani + asosiy ombor, ochiq kassa, qoldiqlar (Guruch 10 kg oshxonada, Cola 50 dona asosiy omborda)."""

    def __init__(self, db, mk, fmt="full_service"):
        super().__init__(db, mk, fmt)
        self.main_wh = Warehouse(name="Asosiy ombor", company_id=self.c.id, branch_id=self.b.id, is_active=True,
                                 is_default=True)
        db.add(self.main_wh)
        db.flush()
        self.kitchen = get_kitchen_warehouse(db, self.c.id, self.b.id)
        self.wallet = Wallet(name="Kassa", type="cash", balance=D(0), company_id=self.c.id, branch_id=self.b.id,
                             is_active=True, is_open=True)
        db.add(self.wallet)
        db.flush()
        for u in (self.admin, self.cashier, self.mgr):
            db.add(UserWallet(user_id=u.id, wallet_id=self.wallet.id, is_default=True, company_id=self.c.id))
        self.stock(self.rice, self.kitchen, 10)
        self.stock(self.cola, self.main_wh, 50)
        db.flush()

    def stock(self, p, wh, qty):
        sl = self.db.query(StockLevel).filter(StockLevel.product_id == p.id, StockLevel.warehouse_id == wh.id).first()
        if sl is None:
            sl = StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty))
            self.db.add(sl)
        else:
            sl.quantity = D(qty)
        self.db.flush()
        return sl

    def qty(self, p, wh):
        v = self.db.query(StockLevel.quantity).filter(StockLevel.product_id == p.id, StockLevel.warehouse_id == wh.id).scalar()
        return D(str(v or 0))

    def ready_check(self, cl, *rows, table=0, send=True):
        oid = self.open(cl, table)["id"]
        self.add(cl, oid, *rows)
        if send:
            assert cl.post(f"{O}/{oid}/send", json={}).status_code == 200
        return oid


@pytest.fixture
def rp(db, mk):
    return RP(db, mk)


def _pay(cl, oid, payments, **kw):
    return cl.post(f"{O}/{oid}/pay", json={"payments": payments, **kw})


# ───────────────────────── asosiy oqim ─────────────────────────

def test_pay_creates_sale_deducts_ingredients_and_closes(rp, client, db):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2}, {"product_id": rp.cola.id})
    # oshxonaga yuborilganda (sukut 'paid' rejimi) hali yechilmaydi
    assert rp.qty(rp.rice, rp.kitchen) == D("10")
    res = _pay(cl, oid, [{"type": "cash", "amount": 150000}], tips=5000)
    assert res.status_code == 200, res.text
    out = res.json()
    # 2*50000 + 10000 = 110000 + 10% xizmat = 121000; qaytim 29000
    assert out["status"] == "paid" and out["total"] == 121000 and out["change"] == 29000 and out["tips_amount"] == 5000
    sale = db.get(Sale, out["sale"]["id"])
    assert float(sale.total_amount) == 121000 and out["sale_id"] == sale.id
    lines = {db.get(Product, si.product_id).name: si for si in db.query(SaleItem).filter(SaleItem.sale_id == sale.id)}
    assert set(lines) == {"Osh", "Cola", "Xizmat haqi"}
    assert float(lines["Xizmat haqi"].unit_price) == 11000
    assert lines["Osh"].cost_price == D("3000.0000")              # 0.15 kg x 20000
    # ingredient oshxona omboridan, tovar asosiy ombordan, taomning o'z qoldig'i yo'q
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700")
    assert rp.qty(rp.cola, rp.main_wh) == D("49")
    assert db.query(StockMovement).filter(StockMovement.product_id == rp.osh.id).count() == 0
    assert db.query(StockLevel).filter(StockLevel.product_id == rp.osh.id).count() == 0
    db.refresh(rp.wallet)
    assert rp.wallet.balance == D("121000")
    st = cl.get("/api/restaurant/tables/status", params={"branch_id": rp.b.id}).json()
    assert st == []                                                  # stol bo'shadi
    # takroriy to'lov
    assert _pay(cl, oid, [{"type": "cash", "amount": 121000}]).status_code == 409


def test_mixed_payment_and_validation(rp, client, db):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.cola.id, "quantity": 2})      # 20000 + 2000 = 22000
    for bad in ([], [{"type": "debt", "amount": 22000}], [{"type": "cash", "amount": 0}],
                [{"type": "card", "amount": 30000}], [{"type": "cash", "amount": 10000}]):
        assert _pay(cl, oid, bad).status_code == 400, bad
    res = _pay(cl, oid, [{"type": "card", "amount": 12000, "reference": "T1"}, {"type": "cash", "amount": 20000}])
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["change"] == 10000
    assert {(p["type"], p["amount"]) for p in out["payments"]} == {("card", 12000), ("cash", 10000)}
    assert db.get(Sale, out["sale"]["id"]).payment_type.value == "mixed"


def test_discount_flows_into_sale(rp, client, db):
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2})
    cl.post(f"{O}/{oid}/discount", json={"pct": 10, "reason": "aksiya"})
    out = _pay(cl, oid, [{"type": "cash", "amount": 99000}]).json()
    sale = db.get(Sale, out["sale"]["id"])
    assert float(sale.discount_amount) == 10000 and float(sale.total_amount) == 99000
    fis = out["fiscal"]
    assert sum(x["discount"] for x in fis["cart"]) == 10000
    assert next(x for x in fis["cart"] if x["name"] == "Xizmat haqi")["unit_price"] == 9000


def test_drafts_block_payment_and_permissions(rp, client, mk):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.cola.id}, send=False)
    res = _pay(cl, oid, [{"type": "cash", "amount": 11000}])
    assert res.status_code == 409 and res.json()["detail"]["code"] == "HAS_DRAFT"
    waiter = mk.user(rp.c, role=UserRole.cashier, branch=rp.b,
                     permissions={"restaurant": {"waiter": True, "take_payment": False}})
    wcl = client.login(waiter)
    woid = rp.ready_check(wcl, {"product_id": rp.cola.id}, table=3)
    assert _pay(wcl, woid, [{"type": "cash", "amount": 11000}]).status_code == 403


def test_empty_and_cancelled_check_cannot_be_paid(rp, client):
    cl = client.login(rp.cashier)
    oid = rp.open(cl)["id"]
    assert _pay(cl, oid, [{"type": "cash", "amount": 1}]).status_code == 400
    cl.post(f"{O}/{oid}/cancel", json={})
    assert _pay(cl, oid, [{"type": "cash", "amount": 1}]).status_code == 409


# ───────────────────────── yechish rejimlari va chiqim ─────────────────────────

def test_cooked_then_cancelled_is_written_off(rp, client, db):
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id}, {"product_id": rp.cola.id})
    items = cl.get(f"{O}/{oid}").json()["items"]
    osh = next(i for i in items if i["name"] == "Osh")
    cl.post(f"{O}/{oid}/items/{osh['id']}/status", json={"status": "ready"})
    cl.post(f"{O}/{oid}/items/{osh['id']}/cancel", json={"reason": "spoiled"})
    assert rp.qty(rp.rice, rp.kitchen) == D("9.850")
    mv = db.query(StockMovement).filter(StockMovement.product_id == rp.rice.id,
                                        StockMovement.reference_type == "rest_writeoff").one()
    assert mv.quantity == D("0.150") and mv.reference_id == oid
    _pay(cl, oid, [{"type": "cash", "amount": 11000}])
    assert rp.qty(rp.rice, rp.kitchen) == D("9.850")                 # qayta yechilmadi


def test_uncooked_cancel_in_paid_mode_does_not_touch_stock(rp, client):
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id})
    iid = cl.get(f"{O}/{oid}").json()["items"][0]["id"]
    cl.post(f"{O}/{oid}/items/{iid}/cancel", json={"reason": "mistake"})
    assert rp.qty(rp.rice, rp.kitchen) == D("10")


def test_sent_mode_deducts_on_send_and_restores_on_cancel(rp, client, db):
    s = dict(rp.c.restaurant_settings)
    s["deduct_stock_on"] = "sent"
    rp.c.restaurant_settings = s
    db.flush()
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id, "quantity": 2}, {"product_id": rp.osh.id, "quantity": 1, "course": 2})
    assert rp.qty(rp.rice, rp.kitchen) == D("9.550")
    items = cl.get(f"{O}/{oid}").json()["items"]
    single = next(i for i in items if i["quantity"] == 1)
    cl.post(f"{O}/{oid}/items/{single['id']}/cancel", json={"reason": "mistake"})
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700")                 # pishmagan: qaytdi
    out = _pay(cl, oid, [{"type": "cash", "amount": 110000}]).json()
    assert out["status"] == "paid"
    assert rp.qty(rp.rice, rp.kitchen) == D("9.700")                 # to'lovda ikkinchi marta yechilmadi
    lines = {db.get(Product, si.product_id).name: si for si in db.query(SaleItem).filter(SaleItem.sale_id == out["sale"]["id"])}
    assert lines["Osh"].cost_price == D("3000.0000")


def test_semi_finished_auto_expand(rp, client, db):
    cid = rp.c.id
    meat = create_item(db, cid, {"name": "Go'sht", "kind": "ingredient", "cost_price": 100000})
    mince = create_item(db, cid, {"name": "Qiyma", "kind": "semi"})
    manti = create_item(db, cid, {"name": "Manti", "kind": "dish", "sale_price": 40000})
    save_card(db, cid, mince, {"output_qty": 1, "items": [{"component_product_id": meat.id, "gross_qty": 1.1}]}, None)
    save_card(db, cid, manti, {"items": [{"component_product_id": mince.id, "gross_qty": 0.2}]}, None)
    rp.stock(meat, rp.kitchen, 5)
    rp.stock(mince, rp.kitchen, 0.1)      # 0.1 kg tayyor qiyma bor, 0.3 kg kerak
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": manti.id, "quantity": 1.5})
    _pay(cl, oid, [{"type": "cash", "amount": 66000}])
    assert rp.qty(mince, rp.kitchen) == D("0")                       # bor qiyma ishlatildi
    assert rp.qty(meat, rp.kitchen) == D("4.780")                    # qolgan 0.2 kg qiyma = 0.22 kg go'sht


def test_card_version_at_order_time_is_used(rp, client, db):
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": rp.osh.id})
    # chek ochilgandan keyin tex karta o'zgardi: eski chek eski versiya bo'yicha yechiladi
    save_card(db, rp.c.id, rp.osh, {"items": [{"component_product_id": rp.rice.id, "gross_qty": 0.5}]}, None)
    _pay(cl, oid, [{"type": "cash", "amount": 55000}])
    assert rp.qty(rp.rice, rp.kitchen) == D("9.850")


# ───────────────────────── himoya ─────────────────────────

def test_generic_return_and_delete_blocked_for_restaurant_sale(rp, client, db):
    cl = client.login(rp.admin)
    oid = rp.ready_check(cl, {"product_id": rp.cola.id})
    sale_id = _pay(cl, oid, [{"type": "cash", "amount": 11000}]).json()["sale"]["id"]
    cola_item = db.query(SaleItem).filter(SaleItem.sale_id == sale_id, SaleItem.product_id == rp.cola.id).one()
    r = cl.post(f"/api/sales/{sale_id}/return-items",
                json={"items": [{"sale_item_id": cola_item.id, "quantity": 1}], "warehouse_id": rp.main_wh.id})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "RESTAURANT_SALE", r.text
    r = cl.post("/api/sales/return", json={"items": [{"product_id": rp.cola.id, "quantity": 1}], "payment_type": "cash",
                                           "paid_amount": 10000, "warehouse_id": rp.main_wh.id,
                                           "original_sale_id": sale_id})
    assert r.status_code == 409, r.text
    r = cl.delete(f"/api/sales/{sale_id}")
    assert r.status_code == 409, r.text
    assert db.get(RestaurantOrder, oid).status == "paid"


def test_free_return_of_dish_blocked(rp, client):
    r = client.login(rp.admin).post("/api/sales/return", json={
        "items": [{"product_id": rp.osh.id, "quantity": 1}], "payment_type": "cash", "paid_amount": 50000,
        "warehouse_id": rp.main_wh.id})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "RESTAURANT_ITEM"


def test_regular_pos_sale_of_dish_does_not_create_dish_stock(rp, client, db):
    """Restoran taomi oddiy POS orqali sotilsa ham taomning o'z qoldig'i yaratilmaydi."""
    r = client.login(rp.admin).post("/api/sales/", json={
        "items": [{"product_id": rp.osh.id, "quantity": 1}], "payment_type": "cash", "paid_amount": 50000,
        "paid_cash": 50000, "warehouse_id": rp.main_wh.id})
    assert r.status_code == 200, r.text
    assert db.query(StockLevel).filter(StockLevel.product_id == rp.osh.id).count() == 0


def test_fiscal_endpoint(rp, client):
    cl = client.login(rp.cashier)
    oid = rp.ready_check(cl, {"product_id": rp.cola.id})
    assert cl.get(f"{O}/{oid}/fiscal").status_code == 409
    _pay(cl, oid, [{"type": "cash", "amount": 11000}])
    f = cl.get(f"{O}/{oid}/fiscal").json()
    assert [x["name"] for x in f["cart"]] == ["Cola", "Xizmat haqi"] and f["payments"][0]["type"] == "cash"


# ───────────────────────── frontend ─────────────────────────

def test_frontend_payment_wired():
    page = _read('frontend/src/pages/admin/restaurant/RestaurantOrders.jsx')
    for token in ("/pay", "fiscalizeAndPrint", "/fiscal", "tips", "change"):
        assert token in page, token


def test_payment_i18n_keys():
    import json
    data = json.load(open(os.path.join(ROOT, 'tests/branch_audit/i18n_pending/R5.json'), encoding='utf-8'))
    for lang in ('uz', 'ru', 'en'):
        d = _read(f'frontend/src/i18n/{lang}.js')
        for k in data['uz']:
            assert d.count(f"'{k}':") == 1, (lang, k)
