"""D4.2 — Dorixona: seriya bo'yicha kuzatish va qaytarib olish (recall).

Qamrov: GET /api/pharmacy/recall (ta'minotchi/xarid, qoldiq omborlar bo'yicha, kimga sotilgan, qaytarishlar),
mijozlar CSV, POST /api/pharmacy/recall/block (barcha filiallar, audit log, Telegram xabari, keyin sotuv rad etiladi),
ikki korxona izolyatsiyasi, filial doirasi, rollar, oddiy do'kon (403 + sotuv avvalgidek), xabar matni escape.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D4_2.py -q -p no:cacheprovider
"""
import itertools
import json
import pathlib
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.admin_tg_bot import notifications
from app.models.audit_log import AuditLog
from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.moliya import Wallet
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.sale import Sale, SaleItem, SaleItemBatch
from app.models.supplier import Supplier
from app.models.user import UserRole, UserWallet
from app.services.batch_allocator import tashkent_today

ROOT = pathlib.Path(__file__).resolve().parents[2]
_n = itertools.count(1)


def _dt(days):
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
    p = Product(name=f"Dori D42-{n}", sku=f"D42-{n}", barcode=f"BD42-{n:06d}", company_id=c.id,
                cost_price=D("500"), sale_price=D("1000"))
    db.add(p)
    db.flush()
    return p


def _stock(db, p, wh, qty):
    sl = StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty))
    db.add(sl)
    db.flush()
    return sl


def _batch(db, p, wh, qty, expiry_days, lot, status=None, po=None):
    b = Batch(product_id=p.id, warehouse_id=wh.id if wh else None, quantity=D(qty), initial_quantity=D(qty),
              purchase_price=D(100), company_id=p.company_id, expiry_date=_dt(expiry_days),
              lot_number=lot, status=status, po_id=po.id if po else None)
    db.add(b)
    db.flush()
    return b


def _sale_body(p, qty, wh, customer_id=None):
    total = 1000 * qty
    body = {"items": [{"product_id": p.id, "quantity": qty, "unit_price": 1000}],
            "payment_type": "cash", "paid_amount": total, "paid_cash": total,
            "payments": [{"type": "cash", "amount": total}], "warehouse_id": wh.id}
    if customer_id:
        body["customer_id"] = customer_id
    return body


@pytest.fixture
def sent(monkeypatch):
    """Telegram xabarini ushlab oladi (haqiqiy yuborilmaydi)."""
    calls = []
    import app.routers.pharmacy_recall as rr
    monkeypatch.setattr(rr, "trigger_batch_recalled", lambda cid, **kw: calls.append((cid, kw)))
    return calls


@pytest.fixture
def ph(db, mk):
    """Dorixona korxonasi A (2 filial, 2 ombor), dorixona korxonasi B va oddiy do'kon S."""
    c, b1, wh1, admin = mk.tenant()
    b2 = mk.branch(c)
    wh2 = mk.warehouse(c, b2)
    _wallet(db, c, b1, admin)
    _enable(db, c)
    p = _product(db, c)
    _stock(db, p, wh1, 100)
    _stock(db, p, wh2, 100)
    sup = Supplier(name="Ta'minotchi <A> & Co", phone="+998901112233", company_id=c.id)
    db.add(sup)
    db.flush()
    po = PurchaseOrder(number=f"PO-D42-{next(_n)}", supplier_id=sup.id, warehouse_id=wh1.id, company_id=c.id,
                       created_by=admin.id, supplier_invoice_number="INV-77")
    db.add(po)
    db.flush()

    cb, bb, whb, adminb = mk.tenant()
    _wallet(db, cb, bb, adminb)
    _enable(db, cb)
    pb = _product(db, cb)
    _stock(db, pb, whb, 100)

    cs, bs, whs, admins = mk.tenant()
    _wallet(db, cs, bs, admins)
    ps = _product(db, cs)
    _stock(db, ps, whs, 100)
    return dict(c=c, b1=b1, b2=b2, wh1=wh1, wh2=wh2, admin=admin, p=p, sup=sup, po=po,
                cb=cb, whb=whb, adminb=adminb, pb=pb, cs=cs, whs=whs, admins=admins, ps=ps)


def _customer(db, c, name="Ali Valiyev", phone="+998901234567"):
    cu = Customer(name=name, phone=phone, company_id=c.id)
    db.add(cu)
    db.flush()
    return cu


# ───────────────────────── Qidiruv ─────────────────────────

def test_lookup_full_picture(client, db, ph):
    p, wh1, wh2 = ph["p"], ph["wh1"], ph["wh2"]
    b1 = _batch(db, p, wh1, 10, 200, "LOT-77", po=ph["po"])
    b2 = _batch(db, p, wh2, 6, 200, "lot-77")                       # boshqa filial, harf registri farqli
    _batch(db, p, wh1, 9, 200, "LOT-770")                           # boshqa seriya (to'liq mos emas)
    cu = _customer(db, ph["c"])
    cl = client.login(ph["admin"])
    r = cl.post("/api/sales/", json=_sale_body(p, 4, wh1, cu.id))
    assert r.status_code == 200, r.text
    # ta'minotchiga qaytarish hujjati (AuditLog)
    db.add(AuditLog(user_id=ph["admin"].id, action="RETURN_TO_SUPPLIER", entity_type="supplier",
                    entity_id=ph["sup"].id,
                    new_values={"movements": [{"batches": [[b2.id, "2"]]}], "reverted": False}))
    db.flush()

    r = cl.get("/api/pharmacy/recall", params={"lot": "LOT-77"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["found"] and {x["batch_id"] for x in d["batches"]} == {b1.id, b2.id}
    first = next(x for x in d["batches"] if x["batch_id"] == b1.id)
    assert first["supplier_name"] == "Ta'minotchi <A> & Co" and first["supplier_phone"] == "+998901112233"
    assert first["po_number"] == ph["po"].number and first["supplier_invoice_number"] == "INV-77"
    # qoldiq omborlar bo'yicha
    stock = {s["warehouse_id"]: s["quantity"] for s in d["stock"]}
    assert stock == {wh1.id: 6.0, wh2.id: 6.0}
    # kimga sotilgan
    assert len(d["sales"]) == 1
    s = d["sales"][0]
    assert s["customer_name"] == "Ali Valiyev" and s["customer_phone"] == "+998901234567"
    assert s["quantity"] == 4 and s["batch_id"] == b1.id and s["branch_name"]
    # ta'minotchiga qaytarish
    assert [(x["batch_id"], x["quantity"]) for x in d["supplier_returns"]] == [(b2.id, 2.0)]
    sm = d["summary"]
    assert sm["received"] == 16 and sm["remaining"] == 12 and sm["sold"] == 4
    assert sm["customers_count"] == 1 and sm["returned_to_supplier"] == 2 and sm["recalled_batches"] == 0


def test_lookup_customer_return_counted(client, db, ph):
    p, wh1 = ph["p"], ph["wh1"]
    _batch(db, p, wh1, 10, 200, "RET-1")
    cl = client.login(ph["admin"])
    sale_id = cl.post("/api/sales/", json=_sale_body(p, 5, wh1, _customer(db, ph["c"]).id)).json()["id"]
    item = db.query(SaleItem).filter_by(sale_id=sale_id).one()
    item.returned_quantity = D(2)
    db.flush()
    d = cl.get("/api/pharmacy/recall", params={"lot": "RET-1"}).json()
    assert d["sales"][0]["returned_quantity"] == 2 and d["summary"]["returned_by_customers"] == 2


def test_lookup_not_found_and_required(client, db, ph):
    cl = client.login(ph["admin"])
    d = cl.get("/api/pharmacy/recall", params={"lot": "YOQ"}).json()
    assert d["found"] is False and d["batches"] == [] and d["sales"] == []
    assert cl.get("/api/pharmacy/recall", params={"lot": "  "}).status_code == 400
    assert cl.get("/api/pharmacy/recall").status_code == 422


def test_lookup_product_filter(client, db, ph):
    p, wh1 = ph["p"], ph["wh1"]
    p_other = _product(db, ph["c"])
    a = _batch(db, p, wh1, 3, 200, "SAME-1")
    _batch(db, p_other, wh1, 4, 200, "SAME-1")
    cl = client.login(ph["admin"])
    assert len(cl.get("/api/pharmacy/recall", params={"lot": "SAME-1"}).json()["batches"]) == 2
    d = cl.get("/api/pharmacy/recall", params={"lot": "SAME-1", "product_id": p.id}).json()
    assert [x["batch_id"] for x in d["batches"]] == [a.id]


def test_lookup_branch_scope(client, db, mk, ph):
    """Filialga biriktirilgan xodim faqat o'z filiali qoldig'ini ko'radi."""
    p, wh1, wh2 = ph["p"], ph["wh1"], ph["wh2"]
    b1 = _batch(db, p, wh1, 10, 200, "SCOPE-1")
    _batch(db, p, wh2, 6, 200, "SCOPE-1")
    mgr = mk.user(ph["c"], role=UserRole.manager, branch=ph["b1"])
    d = client.login(mgr).get("/api/pharmacy/recall", params={"lot": "SCOPE-1"}).json()
    assert [x["batch_id"] for x in d["batches"]] == [b1.id]
    assert {s["warehouse_id"] for s in d["stock"]} == {wh1.id}


def test_lookup_roles(client, db, mk, ph):
    _batch(db, ph["p"], ph["wh1"], 1, 200, "ROLE-1")
    cashier = mk.user(ph["c"], role=UserRole.cashier, branch=ph["b1"])
    assert client.login(cashier).get("/api/pharmacy/recall", params={"lot": "ROLE-1"}).status_code == 403
    assert client.login(cashier).post("/api/pharmacy/recall/block",
                                      json={"lot": "ROLE-1", "reason": "x"}).status_code == 403


# ───────────────────────── Izolyatsiya ─────────────────────────

def test_isolation_between_companies(client, db, ph):
    pa, pb = ph["p"], ph["pb"]
    ba = _batch(db, pa, ph["wh1"], 10, 200, "ISO-1")
    bb = _batch(db, pb, ph["whb"], 10, 200, "ISO-1")                # boshqa korxonada xuddi shu seriya
    # B korxona foydalanuvchisi A ma'lumotini ko'rmaydi, faqat o'zinikini
    d = client.login(ph["adminb"]).get("/api/pharmacy/recall", params={"lot": "ISO-1"}).json()
    assert [x["batch_id"] for x in d["batches"]] == [bb.id]
    # A mahsuloti B uchun topilmaydi
    d2 = client.login(ph["adminb"]).get("/api/pharmacy/recall", params={"lot": "ISO-1", "product_id": pa.id}).json()
    assert d2["found"] is False
    assert client.login(ph["adminb"]).post(
        "/api/pharmacy/recall/block", json={"lot": "ISO-1", "product_id": pa.id, "reason": "x"}).status_code == 404
    db.refresh(ba)
    assert ba.status is None
    # B bloklasa A ga ta'sir qilmaydi
    assert client.login(ph["adminb"]).post(
        "/api/pharmacy/recall/block", json={"lot": "ISO-1", "reason": "B brak"}).status_code == 200
    db.refresh(ba)
    db.refresh(bb)
    assert ba.status is None and bb.status == "recalled"


def test_sales_of_other_company_not_leaked(client, db, ph):
    """B korxonasi sotuvi A seriyasi ro'yxatida chiqmaydi (seriya nomi bir xil bo'lsa ham)."""
    ba = _batch(db, ph["p"], ph["wh1"], 10, 200, "LEAK-1")
    bb = _batch(db, ph["pb"], ph["whb"], 10, 200, "LEAK-1")
    assert client.login(ph["adminb"]).post("/api/sales/", json=_sale_body(ph["pb"], 2, ph["whb"])).status_code == 200
    d = client.login(ph["admin"]).get("/api/pharmacy/recall", params={"lot": "LEAK-1"}).json()
    assert d["sales"] == [] and [x["batch_id"] for x in d["batches"]] == [ba.id]
    d = client.login(ph["adminb"]).get("/api/pharmacy/recall", params={"lot": "LEAK-1"}).json()
    assert len(d["sales"]) == 1 and d["sales"][0]["batch_id"] == bb.id


# ───────────────────────── Bloklash ─────────────────────────

def test_block_all_branches_audit_telegram_and_sale_rejected(client, db, ph, sent):
    p, wh1, wh2 = ph["p"], ph["wh1"], ph["wh2"]
    b1 = _batch(db, p, wh1, 10, 200, "BLK-1")
    b2 = _batch(db, p, wh2, 6, 200, "BLK-1", status="quarantine")
    other = _batch(db, p, wh1, 5, 200, "BLK-2")
    cu = _customer(db, ph["c"])
    cl = client.login(ph["admin"])
    assert cl.post("/api/sales/", json=_sale_body(p, 2, wh1, cu.id)).status_code == 200

    r = cl.post("/api/pharmacy/recall/block", json={"lot": "blk-1", "reason": "Ishlab chiqaruvchi qaytarib oldi"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["blocked_batches"] == 2 and set(j["batch_ids"]) == {b1.id, b2.id}
    assert j["customers_count"] == 1 and j["sales_count"] == 1 and j["remaining_quantity"] == 14
    for b in (b1, b2, other):
        db.refresh(b)
    assert b1.status == "recalled" and b2.status == "recalled" and other.status is None
    assert b1.status_reason == "Ishlab chiqaruvchi qaytarib oldi" and b1.status_changed_by == ph["admin"].id

    logs = db.query(AuditLog).filter(AuditLog.action == "BATCH_STATUS", AuditLog.company_id == ph["c"].id).all()
    assert {lg.entity_id for lg in logs} == {b1.id, b2.id}
    assert next(lg for lg in logs if lg.entity_id == b2.id).old_values == {"status": "quarantine"}
    summary = db.query(AuditLog).filter(AuditLog.action == "PHARMACY_RECALL").one()
    assert summary.new_values["lot"] == "blk-1" and set(summary.new_values["batch_ids"]) == {b1.id, b2.id}

    assert len(sent) == 1
    cid, kw = sent[0]
    assert cid == ph["c"].id and kw["lot"] == "blk-1" and kw["customers_count"] == 1
    assert kw["reason"] == "Ishlab chiqaruvchi qaytarib oldi" and kw["batches_count"] == 2

    # D1.2/D3.3: bloklangan seriya sotilmaydi, boshqa seriya sotiladi (b1/b2 dan boshqa qoldiq yo'q -> faqat `other`)
    r = cl.post("/api/sales/", json=_sale_body(p, 3, wh1, cu.id))
    assert r.status_code == 200, r.text
    db.refresh(b1)
    db.refresh(other)
    assert D(str(b1.quantity)) == 8 and D(str(other.quantity)) == 2        # b1 faqat oldingi sotuvdan kamaygan


def test_sale_rejected_when_only_recalled_lot(client, db, ph, sent):
    p, wh1 = ph["p"], ph["wh1"]
    b = _batch(db, p, wh1, 10, 200, "ONLY-1")
    cl = client.login(ph["admin"])
    assert cl.post("/api/pharmacy/recall/block", json={"lot": "ONLY-1", "reason": "Brak"}).status_code == 200
    r = cl.post("/api/sales/", json=_sale_body(p, 1, wh1))
    assert r.status_code == 400, r.text
    db.refresh(b)
    assert D(str(b.quantity)) == 10
    assert db.query(Sale).filter(Sale.company_id == ph["c"].id).count() == 0


def test_block_validation(client, db, ph, sent):
    _batch(db, ph["p"], ph["wh1"], 10, 200, "VAL-1")
    cl = client.login(ph["admin"])
    assert cl.post("/api/pharmacy/recall/block", json={"lot": "VAL-1", "reason": "  "}).status_code == 400
    assert cl.post("/api/pharmacy/recall/block", json={"lot": " ", "reason": "x"}).status_code == 400
    assert cl.post("/api/pharmacy/recall/block", json={"lot": "YOQ", "reason": "x"}).status_code == 404
    assert cl.post("/api/pharmacy/recall/block", json={"lot": "VAL-1", "reason": "x"}).status_code == 200
    r = cl.post("/api/pharmacy/recall/block", json={"lot": "VAL-1", "reason": "x"})
    assert r.status_code == 400 and "allaqachon" in r.json()["detail"]
    assert len(sent) == 1                                              # xato so'rovlarda xabar yuborilmaydi


def test_block_branch_manager_cannot_cover_other_branch(client, db, mk, ph, sent):
    p = ph["p"]
    mine = _batch(db, p, ph["wh1"], 10, 200, "BR-1")
    theirs = _batch(db, p, ph["wh2"], 6, 200, "BR-1")
    mgr = mk.user(ph["c"], role=UserRole.manager, branch=ph["b1"])
    r = client.login(mgr).post("/api/pharmacy/recall/block", json={"lot": "BR-1", "reason": "x"})
    assert r.status_code == 403
    db.refresh(mine)
    db.refresh(theirs)
    assert mine.status is None and theirs.status is None and not sent
    # faqat o'z filialida bo'lgan seriyani bloklay oladi
    only = _batch(db, p, ph["wh1"], 2, 200, "BR-2")
    assert client.login(mgr).post("/api/pharmacy/recall/block", json={"lot": "BR-2", "reason": "x"}).status_code == 200
    db.refresh(only)
    assert only.status == "recalled"


def test_block_survives_telegram_failure(client, db, ph, monkeypatch):
    import app.routers.pharmacy_recall as rr

    def boom(*a, **k):
        raise RuntimeError("telegram yo'q")
    monkeypatch.setattr(rr, "trigger_batch_recalled", boom)
    b = _batch(db, ph["p"], ph["wh1"], 3, 200, "TG-1")
    r = client.login(ph["admin"]).post("/api/pharmacy/recall/block", json={"lot": "TG-1", "reason": "x"})
    assert r.status_code == 200, r.text
    db.refresh(b)
    assert b.status == "recalled"


# ───────────────────────── Mijozlar eksporti ─────────────────────────

def test_customers_csv(client, db, ph):
    p, wh1 = ph["p"], ph["wh1"]
    _batch(db, p, wh1, 10, 200, "CSV-1")
    cu = _customer(db, ph["c"], name="=HYPERLINK(1)", phone="+998909998877")
    cl = client.login(ph["admin"])
    sale_id = cl.post("/api/sales/", json=_sale_body(p, 3, wh1, cu.id)).json()["id"]
    r = cl.get("/api/pharmacy/recall/customers", params={"lot": "CSV-1"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith(b"\xef\xbb\xbf")
    text = r.content.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0].split(",")[0] == "Mijoz" and len(lines) == 2
    assert "'=HYPERLINK(1)" in lines[1] and "+998909998877" in lines[1] and "CSV-1" in lines[1]
    sale = db.get(Sale, sale_id)
    assert sale.number in lines[1]
    # boshqa korxona foydalanuvchisi bo'sh ro'yxat oladi
    r2 = client.login(ph["adminb"]).get("/api/pharmacy/recall/customers", params={"lot": "CSV-1"})
    assert len(r2.content.decode("utf-8-sig").strip().splitlines()) == 1


# ───────────────────────── Telegram xabari ─────────────────────────

def test_recall_message_is_escaped():
    msg = notifications.build_recall_message(
        lot="<b>X&1", product_names=["A<script>", "B"], reason="<i>brak</i> & zaharli",
        user_name="Ali <admin>", batches_count=2, remaining_qty=D("14"), customers_count=3, sales_count=4)
    assert "<script>" not in msg and "&lt;script&gt;" in msg
    assert "&lt;b&gt;X&amp;1" in msg and "&lt;i&gt;brak&lt;/i&gt; &amp; zaharli" in msg
    assert "Ali &lt;admin&gt;" in msg and "14" in msg and "3 ta mijoz" in msg


def test_trigger_uses_recall_type(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "trigger_instant_notification",
                        lambda cid, text, kind, *a, **k: calls.append((cid, text, kind)))
    notifications.trigger_batch_recalled(7, lot="L1", product_names=["P"], reason="r", user_name="U",
                                         batches_count=1, remaining_qty=5, customers_count=0, sales_count=0)
    assert calls and calls[0][0] == 7 and calls[0][2] == "recall" and "L1" in calls[0][1]


# ───────────────────────── Oddiy do'kon (regressiya) ─────────────────────────

def test_plain_store_forbidden_and_sales_unchanged(client, db, ph):
    ps, whs = ph["ps"], ph["whs"]
    b = _batch(db, ps, whs, 10, -5, "PLAIN-1")                          # muddati o'tgan, status NULL
    cl = client.login(ph["admins"])
    assert cl.get("/api/pharmacy/recall", params={"lot": "PLAIN-1"}).status_code == 403
    assert cl.get("/api/pharmacy/recall/customers", params={"lot": "PLAIN-1"}).status_code == 403
    assert cl.post("/api/pharmacy/recall/block", json={"lot": "PLAIN-1", "reason": "x"}).status_code == 403
    db.refresh(b)
    assert b.status is None
    r = cl.post("/api/sales/", json=_sale_body(ps, 3, whs))
    assert r.status_code == 200, r.text
    db.refresh(b)
    assert D(str(b.quantity)) == 7
    assert db.query(SaleItemBatch).count() >= 1


def test_prepare_send_recall_is_always_sent_kind():
    """'recall' turi tasdiq so'rovi kabi: sozlama (notify_instant_*) talab qilinmaydi, oluvchilar 'finance' qoidasi bilan."""
    src = (ROOT / "app" / "admin_tg_bot" / "notifications.py").read_text(encoding="utf-8")
    assert 'notif_type in ("approval", "recall")' in src
    assert "notif_type == 'sale' and not admin_bot.notify_instant_sales" in src


def test_i18n_pending_keys_cover_panel():
    import re
    data = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D4.2.json").read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    src = (ROOT / "frontend" / "src" / "pages" / "admin" / "pharmacy" / "RecallPanel.jsx").read_text(encoding="utf-8")
    used = set(re.findall(r"tf\(\s*'(pharmacyRecall\.[A-Za-z.]+)'", src))
    used |= {f"pharmacyRecall.sum.{k}" for k in re.findall(r"\['(\w+)',\s*[\"'][^\]]*?sm\.", src)}
    assert used and used <= set(data["uz"]), used - set(data["uz"])
