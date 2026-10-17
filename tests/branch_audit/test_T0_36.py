"""T0.36 — Mir-maza/Telegram buyurtmasini korxonaga to'g'ri bog'lash.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T0_36.py -q -p no:cacheprovider
"""
import itertools
import logging
from decimal import Decimal

import pytest

from app.config import settings
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.marketplace import (
    MarketplaceAgentNotification, MarketplaceAgentTransaction, MarketplaceProduct,
    MarketplaceProductStatus, MarketplaceTransactionType,
)
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.user import UserRole, UserStatus
from app.models.warehouse import WarehouseType
from app.services import marketplace_service as mp_service

KEY = "test-integration-key-T0-36"


# ── Yordamchilar ────────────────────────────────────────────────────────────

@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_API_TOKEN", KEY)
    return KEY


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


@pytest.fixture
def mirmaza(monkeypatch, token):
    """httpx.get/patch mock: `mirmaza.orders` ro'yxatini qaytaradi, PATCH chaqiruvlarini yig'adi."""
    state = {"orders": [], "get_calls": 0, "patches": [], "get_headers": None}

    def fake_get(url, headers=None, timeout=None, **kw):
        state["get_calls"] += 1
        state["get_headers"] = headers
        return _Resp(200, {"orders": state["orders"]})

    def fake_patch(url, json=None, headers=None, timeout=None, **kw):
        state["patches"].append({"url": url, "json": json})
        return _Resp(200, {"ok": True})

    monkeypatch.setattr(mp_service.httpx, "get", fake_get)
    monkeypatch.setattr(mp_service.httpx, "patch", fake_patch)
    return state


def _agent(mk, company):
    return mk.user(company, role=UserRole.marketplace_agent, status=UserStatus.active)


def _mp_product(db, company, agent, price="10000", qty="10"):
    p = MarketplaceProduct(
        company_id=company.id, agent_id=agent.id, name=f"MP tovar {agent.id}",
        price=Decimal(price), qty=Decimal(qty), category_id=777,
        status=MarketplaceProductStatus.approved,
    )
    db.add(p)
    db.flush()
    return p


_seq = itertools.count(1)


def _product(db, company, name="Tovar", price="5000"):
    n = next(_seq)
    p = Product(company_id=company.id, name=f"{name} {n}", sku=f"SKU-{n}", barcode=f"BC-{n}",
                sale_price=Decimal(price))
    db.add(p)
    db.flush()
    return p


def _order(market_id, items, phone="+998 90 123-45-67", name="Ali"):
    return {
        "marketOrderId": market_id,
        "customer": {"name": name, "phone": phone},
        "deliveryAddress": {"address": "Toshkent", "note": "eshik oldiga"},
        "items": items,
    }


def _item(ext_id, qty=1, price=10000):
    return {"externalId": ext_id, "quantity": qty, "price": price, "total": price * qty}


def _mp_tenant(mk, enabled=True):
    c = mk.company(marketplace_agents_enabled=enabled)
    b = mk.branch(c)
    return c, b


# ── 1. Yangi mijoz: TypeError yo'q, customer_type == retail ─────────────────

def test_new_customer_saved_with_customer_type_retail(db, mk, mirmaza):
    c, b = _mp_tenant(mk)
    agent = _agent(mk, c)
    mp = _mp_product(db, c, agent)
    mirmaza["orders"] = [_order(101, [_item(f"ECODE-PROD-{mp.id}", qty=2)])]

    mp_service.pull_mirmaza_orders(db)

    cust = db.query(Customer).filter(Customer.company_id == c.id, Customer.phone == "998901234567").first()
    assert cust is not None
    assert cust.customer_type == "retail"
    orders = db.query(Order).filter(Order.company_id == c.id).all()
    assert len(orders) == 1
    assert orders[0].order_group_id == f"mirmaza-101-c{c.id}"
    assert orders[0].branch_id == b.id
    assert orders[0].customer_id == cust.id
    assert orders[0].status == OrderStatus.pending
    # CONFIRMED PATCH — korxona qo'shimchasisiz externalId
    assert len(mirmaza["patches"]) == 1
    assert mirmaza["patches"][0]["json"] == {"status": "CONFIRMED", "externalId": "mirmaza-101"}
    assert mirmaza["get_headers"]["X-Integration-Key"] == KEY


# ── 2. Ikki korxona: B mahsuloti → hammasi B da, A da hech narsa ─────────────

def test_item_routed_to_owner_company_not_first_company(db, mk, mirmaza):
    a, _ = _mp_tenant(mk)
    bco, bb = _mp_tenant(mk)
    agent_b = _agent(mk, bco)
    mp_b = _mp_product(db, bco, agent_b, qty="10")
    mirmaza["orders"] = [_order(202, [_item(f"ECODE-PROD-{mp_b.id}", qty=3, price=10000)])]

    mp_service.pull_mirmaza_orders(db)

    # A da hech narsa yo'q
    assert db.query(Order).filter(Order.company_id == a.id).count() == 0
    assert db.query(Customer).filter(Customer.company_id == a.id).count() == 0
    assert db.query(MarketplaceAgentTransaction).filter(MarketplaceAgentTransaction.company_id == a.id).count() == 0
    assert db.query(MarketplaceAgentNotification).filter(MarketplaceAgentNotification.company_id == a.id).count() == 0
    assert db.query(Product).filter(Product.company_id == a.id).count() == 0

    # B da hammasi
    o = db.query(Order).filter(Order.company_id == bco.id).one()
    assert o.branch_id == bb.id
    cust = db.query(Customer).get(o.customer_id)
    assert cust.company_id == bco.id
    tx = db.query(MarketplaceAgentTransaction).filter(MarketplaceAgentTransaction.order_id == 202).one()
    assert tx.company_id == bco.id and tx.agent_id == agent_b.id
    assert tx.transaction_type == MarketplaceTransactionType.income
    notif = db.query(MarketplaceAgentNotification).filter(MarketplaceAgentNotification.agent_id == agent_b.id).one()
    assert notif.company_id == bco.id
    prod = db.query(Product).get(o.product_id)
    assert prod.company_id == bco.id
    db.refresh(mp_b)
    assert float(mp_b.qty) == 7.0


# ── 3. PROD-<id> boshqa (modul yoqilmagan) korxona mahsuloti → o'tkazib yuboriladi ──

def test_prod_of_foreign_company_skipped_no_order_no_confirm(db, mk, mirmaza, caplog):
    _mp_tenant(mk)                                   # modul yoqilgan korxona (egasi emas)
    other = mk.company(marketplace_agents_enabled=False)
    mk.branch(other)
    p_other = _product(db, other)
    mirmaza["orders"] = [_order(303, [_item(f"PROD-{p_other.id}")])]

    with caplog.at_level(logging.WARNING):
        mp_service.pull_mirmaza_orders(db)

    assert db.query(Order).count() == 0
    assert db.query(Customer).count() == 0
    assert mirmaza["patches"] == []
    assert any("o'tkazib yuborildi" in r.getMessage() for r in caplog.records)


def test_prod_of_enabled_company_imported(db, mk, mirmaza):
    c, b = _mp_tenant(mk)
    p = _product(db, c)
    mirmaza["orders"] = [_order(304, [_item(f"PROD-{p.id}", qty=2, price=5000)])]

    mp_service.pull_mirmaza_orders(db)

    o = db.query(Order).filter(Order.company_id == c.id).one()
    assert o.product_id == p.id and o.branch_id == b.id and o.quantity == 2
    assert len(mirmaza["patches"]) == 1


# ── 4. Bir buyurtmada A va B mahsulotlari → ikki guruh; qayta tortishda takror yo'q ──

def test_mixed_order_split_into_two_groups_and_idempotent(db, mk, mirmaza):
    a, ab = _mp_tenant(mk)
    bco, bb = _mp_tenant(mk)
    pa = _product(db, a)
    mp_b = _mp_product(db, bco, _agent(mk, bco))
    mirmaza["orders"] = [_order(404, [_item(f"PROD-{pa.id}"), _item(f"ECODE-PROD-{mp_b.id}")])]

    mp_service.pull_mirmaza_orders(db)

    oa = db.query(Order).filter(Order.company_id == a.id).one()
    ob = db.query(Order).filter(Order.company_id == bco.id).one()
    assert oa.order_group_id == f"mirmaza-404-c{a.id}"
    assert ob.order_group_id == f"mirmaza-404-c{bco.id}"
    assert oa.branch_id == ab.id and ob.branch_id == bb.id
    assert len(mirmaza["patches"]) == 1

    # Qayta tortish — takror yaratilmaydi
    mp_service.pull_mirmaza_orders(db)
    assert db.query(Order).count() == 2
    assert db.query(Customer).count() == 2
    assert db.query(MarketplaceAgentTransaction).count() == 1


# ── 5. Filial yo'q korxona: Order yaratilmaydi, branch_id=1 yozilmaydi ───────

def test_company_without_branch_skipped_with_warning(db, mk, mirmaza, caplog):
    # id=1 bo'lgan "begona" filial mavjud bo'lsin
    foreign = mk.company()
    mk.branch(foreign)
    c = mk.company(marketplace_agents_enabled=True)     # filialsiz
    p = _product(db, c)
    mirmaza["orders"] = [_order(505, [_item(f"PROD-{p.id}")])]

    with caplog.at_level(logging.WARNING):
        mp_service.pull_mirmaza_orders(db)

    assert db.query(Order).count() == 0
    assert db.query(Order).filter(Order.branch_id == 1).count() == 0
    assert db.query(Customer).filter(Customer.company_id == c.id).count() == 0
    assert mirmaza["patches"] == []
    assert any("filial topilmadi" in r.getMessage() for r in caplog.records)


def test_inactive_branch_not_used_but_default_branch_is(db, mk, mirmaza):
    c = mk.company(marketplace_agents_enabled=True)
    inactive = mk.branch(c, is_active=False)
    active = mk.branch(c)
    p = _product(db, c)

    # Faqat faol filial tanlanadi (id bo'yicha birinchi faol)
    mirmaza["orders"] = [_order(506, [_item(f"PROD-{p.id}")])]
    mp_service.pull_mirmaza_orders(db)
    o = db.query(Order).filter(Order.company_id == c.id).one()
    assert o.branch_id == active.id and o.branch_id != inactive.id

    # Asosiy filial sozlansa — u ustun
    b2 = mk.branch(c)
    c.marketplace_default_branch_id = b2.id
    db.flush()
    mirmaza["orders"] = [_order(507, [_item(f"PROD-{p.id}")], phone="998911111111")]
    mp_service.pull_mirmaza_orders(db)
    o2 = db.query(Order).filter(Order.order_group_id == f"mirmaza-507-c{c.id}").one()
    assert o2.branch_id == b2.id


def test_customer_branch_preferred_when_same_company(db, mk, mirmaza):
    c = mk.company(marketplace_agents_enabled=True)
    b1 = mk.branch(c)
    b2 = mk.branch(c)
    cust = Customer(company_id=c.id, name="Vali", phone="998933333333", branch_id=b2.id)
    db.add(cust)
    db.flush()
    p = _product(db, c)
    mirmaza["orders"] = [_order(508, [_item(f"PROD-{p.id}")], phone="+998 93 333 33 33")]

    mp_service.pull_mirmaza_orders(db)

    o = db.query(Order).filter(Order.company_id == c.id).one()
    assert o.customer_id == cust.id and o.branch_id == b2.id and o.branch_id != b1.id
    assert db.query(Customer).filter(Customer.company_id == c.id).count() == 1


# ── 6. Bitta buyurtmada istisno → boshqalari saqlanadi (savepoint) ──────────

def test_exception_in_one_order_does_not_block_others(db, mk, mirmaza, monkeypatch, caplog):
    c, b = _mp_tenant(mk)
    p = _product(db, c)
    mirmaza["orders"] = [
        _order(601, [_item(f"PROD-{p.id}")], phone="998901111111"),
        _order(602, [_item(f"PROD-{p.id}")], phone="998902222222"),
        _order(603, [_item(f"PROD-{p.id}")], phone="998903333333"),
    ]
    orig = mp_service._import_mirmaza_group

    def boom(db_, mo, cid, items, gid):
        ok = orig(db_, mo, cid, items, gid)   # mijoz va buyurtma yozilib bo'lgan
        if mo["marketOrderId"] == 602:
            raise RuntimeError("sun'iy xato")
        return ok

    monkeypatch.setattr(mp_service, "_import_mirmaza_group", boom)

    with caplog.at_level(logging.ERROR):
        mp_service.pull_mirmaza_orders(db)

    groups = {o.order_group_id for o in db.query(Order).all()}
    assert groups == {f"mirmaza-601-c{c.id}", f"mirmaza-603-c{c.id}"}
    # 602 ning yarim yozuvlari (mijoz) savepoint bilan bekor bo'lgan
    assert db.query(Customer).filter(Customer.phone == "998902222222").count() == 0
    assert db.query(Customer).count() == 2
    assert [p_["url"].split("/")[-2] for p_ in mirmaza["patches"]] == ["601", "603"]
    assert any("602" in r.getMessage() for r in caplog.records)
    # Sessiya yaroqli
    db.add(Customer(company_id=c.id, name="Keyingi", phone="998904444444"))
    db.flush()
    assert db.query(Customer).filter(Customer.phone == "998904444444").count() == 1


def test_partial_unresolved_item_blocks_confirm(db, mk, mirmaza):
    c, b = _mp_tenant(mk)
    p = _product(db, c)
    mirmaza["orders"] = [_order(604, [_item(f"PROD-{p.id}"), _item("PROD-999999")])]

    mp_service.pull_mirmaza_orders(db)

    # Hal qilingan guruh saqlanadi, lekin CONFIRMED yuborilmaydi
    assert db.query(Order).filter(Order.company_id == c.id).count() == 1
    assert mirmaza["patches"] == []


# ── 7. Qattiq kalit yo'q; token bo'sh bo'lsa so'rov yuborilmaydi ────────────

def test_no_hardcoded_key_in_app():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    hits = [p for p in root.rglob("*.py") if "ecode_secret_key_mirmaza_2026" in p.read_text(encoding="utf-8")]
    assert hits == []


def test_empty_token_sends_no_request(db, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_API_TOKEN", "")
    calls = []
    monkeypatch.setattr(mp_service.httpx, "get", lambda *a, **k: calls.append(("get", a)) or _Resp(200, {"orders": []}))
    monkeypatch.setattr(mp_service.httpx, "patch", lambda *a, **k: calls.append(("patch", a)) or _Resp(200))
    monkeypatch.setattr(mp_service.httpx, "post", lambda *a, **k: calls.append(("post", a)) or _Resp(200))

    assert mp_service._mirmaza_headers() is None
    mp_service.pull_mirmaza_orders(db)
    mp_service.push_courier_status_to_mirmaza(db, "mirmaza-5-c1", 0, "assigned")

    class _P:
        id = 1; images = []; barcode = ""; name = "x"; description = ""; price = 1; qty = 1; category_id = None
        class status:
            value = "approved"

    assert mp_service.push_product_to_mirmaza(_P()) is False
    assert calls == []


# ── 8. get_active_features yo'q; scheduler bloki ishlaydi ───────────────────

def test_get_active_features_not_referenced():
    import pathlib
    import app.core.features as features
    root = pathlib.Path(__file__).resolve().parents[2] / "app"
    # birlashtirishdan keyin jamoa app/core/features.py da yordamchini qayta kiritdi; boshqa joyda ishlatilmasligi kerak
    hits = [p.name for p in root.rglob("*.py") if "get_active_features" in p.read_text(encoding="utf-8")]
    assert hits in ([], ["features.py"])


def test_scheduler_pull_runs_once_in_thread(db, mk, mirmaza):
    """Scheduler bloki mantiqi: modul yoqilgan korxona bo'lsa pull BIR marta, to_thread orqali."""
    import asyncio
    from app.models.company import Company

    _mp_tenant(mk)
    _mp_tenant(mk)   # ikkita yoqilgan korxona — baribir bitta so'rov
    has_mp = db.query(Company.id).filter(
        Company.is_active == True, Company.marketplace_agents_enabled == True,  # noqa: E712
    ).first()
    assert has_mp

    async def run():
        await asyncio.to_thread(mp_service.pull_mirmaza_orders, db)

    asyncio.run(run())
    assert mirmaza["get_calls"] == 1


# ── Kuryer holati: guruh ID dan marketOrderId ajratish ──────────────────────

def test_courier_status_regex_strips_company_suffix(db, mk, mirmaza, monkeypatch):
    urls = []
    monkeypatch.setattr(mp_service.httpx, "patch",
                        lambda url, json=None, headers=None, timeout=None, **k: urls.append(url) or _Resp(200))
    mp_service.push_courier_status_to_mirmaza(db, "mirmaza-777-c12", 0, "on_way")
    mp_service.push_courier_status_to_mirmaza(db, "mirmaza-778", 0, "on_way")
    mp_service.push_courier_status_to_mirmaza(db, "abc-1", 0, "on_way")
    assert urls == [
        "https://mir-maza.uz/api/v1/integration/orders/777/courier",
        "https://mir-maza.uz/api/v1/integration/orders/778/courier",
    ]


# ── 9. Eski endpointlar: boshqa korxona buyurtmasi → 404 ────────────────────

def _legacy_order(db, mk, company, branch):
    cust = Customer(company_id=company.id, name="M", phone=f"99890{company.id:07d}", branch_id=branch.id)
    db.add(cust)
    db.flush()
    p = _product(db, company)
    o = Order(company_id=company.id, customer_id=cust.id, branch_id=branch.id, product_id=p.id,
              quantity=1, unit_price=Decimal("5000"), total_amount=Decimal("5000"), status=OrderStatus.pending)
    db.add(o)
    db.flush()
    return o


def test_confirm_and_delete_cross_tenant_404(db, mk, client):
    a, ab, _, ua = mk.tenant()
    b, bb, _, ub = mk.tenant()
    oa = _legacy_order(db, mk, a, ab)

    r = client.login(ub).put(f"/api/orders/{oa.id}/confirm")
    assert r.status_code == 404 and r.json()["detail"] == "Buyurtma topilmadi"
    r = client.login(ub).delete(f"/api/orders/{oa.id}")
    assert r.status_code == 404 and r.json()["detail"] == "Buyurtma topilmadi"
    db.refresh(oa)
    assert oa.status == OrderStatus.pending

    # O'z korxonasi — ishlaydi
    r = client.login(ua).put(f"/api/orders/{oa.id}/confirm")
    assert r.status_code == 200
    db.refresh(oa)
    assert oa.status == OrderStatus.confirmed


def test_delete_own_order_works(db, mk, client):
    a, ab, _, ua = mk.tenant()
    oa = _legacy_order(db, mk, a, ab)
    r = client.login(ua).delete(f"/api/orders/{oa.id}")
    assert r.status_code == 200
    db.refresh(oa)
    assert oa.status == OrderStatus.cancelled


def test_branch_pending_cross_tenant_404(db, mk, client):
    a, ab, _, ua = mk.tenant()
    b, bb, _, ub = mk.tenant()
    _legacy_order(db, mk, a, ab)

    r = client.login(ub).get(f"/api/orders/branch/{ab.id}/pending")
    assert r.status_code == 404 and r.json()["detail"] == "Filial topilmadi"

    r = client.login(ua).get(f"/api/orders/branch/{ab.id}/pending")
    assert r.status_code == 200 and len(r.json()) == 1


def test_list_and_group_endpoints_use_order_company(db, mk, client):
    a, ab, _, ua = mk.tenant()
    b, bb, _, ub = mk.tenant()
    oa = _legacy_order(db, mk, a, ab)

    assert client.login(ub).get("/api/orders").json() == []
    assert len(client.login(ua).get("/api/orders").json()) == 1
    assert client.login(ub).put(f"/api/orders/group/single-{oa.id}/status", json={"status": "confirmed"}).status_code == 404
    assert client.login(ub).delete(f"/api/orders/group/single-{oa.id}").status_code == 404
    assert client.login(ua).put(f"/api/orders/group/single-{oa.id}/status", json={"status": "confirmed"}).status_code == 200


# ── 10. Migratsiya fayli ────────────────────────────────────────────────────

def test_migration_file_shape():
    import importlib.util
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "t0_36_orders_company_id_mp_default_branch.py"
    spec = importlib.util.spec_from_file_location("t0_36_mig", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "t0_36"
    assert callable(mod.upgrade) and callable(mod.downgrade)
    src = path.read_text(encoding="utf-8")
    assert "ix_orders_company_group" in src and "fk_companies_mp_default_branch" in src


# ── 11. orders.py create_order va shop.py buyurtmalarida company_id ─────────

def test_create_order_sets_company_id(db, mk, client):
    a, ab, _, ua = mk.tenant()
    cust = Customer(company_id=a.id, name="M", phone="998905555555", branch_id=ab.id)
    db.add(cust)
    db.flush()
    p = _product(db, a)
    r = client.login(ua).post("/api/orders", json={"customer_id": cust.id, "product_id": p.id, "quantity": 2})
    assert r.status_code == 201, r.text
    o = db.query(Order).get(r.json()["id"])
    assert o.company_id == a.id


def test_shop_order_sets_company_id(db, mk, client, monkeypatch):
    from app.routers import shop as shop_mod
    a, ab, _wh, ua = mk.tenant()
    # T3.13: buyurtma filialida do'kon (shop) ombori bo'lishi shart
    wh = mk.warehouse(a, ab, name="Do'kon", type=WarehouseType.shop)
    a.tg_bot_token = "123:abc"
    cust = Customer(company_id=a.id, name="M", phone="998906666666", tg_chat_id="42")
    db.add(cust)
    db.flush()
    p = _product(db, a)
    monkeypatch.setattr(shop_mod, "_resolve_shop_context", lambda db_, cid, x, u=None, t=None: (a, cust))

    r = client.post(f"/api/shop/{a.id}/order", json={"items": [{"product_id": p.id, "quantity": 1}]})
    assert r.status_code == 200, r.text
    o = db.query(Order).filter(Order.customer_id == cust.id).one()
    assert o.company_id == a.id and o.branch_id == ab.id


def test_shop_branch_fallback_skips_inactive(db, mk, client, monkeypatch):
    from app.routers import shop as shop_mod
    a = mk.company()
    inactive = mk.branch(a, is_active=False)
    active = mk.branch(a)
    wh = mk.warehouse(a, name="Do'kon", type=WarehouseType.shop)   # filialsiz do'kon ombori (T3.13)
    cust = Customer(company_id=a.id, name="M", phone="998907777777", tg_chat_id="43")
    db.add(cust)
    db.flush()
    p = _product(db, a)
    monkeypatch.setattr(shop_mod, "_resolve_shop_context", lambda db_, cid, x, u=None, t=None: (a, cust))

    r = client.post(f"/api/shop/{a.id}/order", json={"items": [{"product_id": p.id, "quantity": 1}]})
    assert r.status_code == 200, r.text
    o = db.query(Order).filter(Order.customer_id == cust.id).one()
    assert o.branch_id == active.id and o.branch_id != inactive.id


# ── PUT /companies: marketplace_default_branch_id tekshiruvi ────────────────

def test_company_default_branch_validation(db, mk, client):
    a, ab, _, ua = mk.tenant()
    b, bb, _, ub = mk.tenant()
    inactive = mk.branch(a, is_active=False)

    r = client.login(ua).put(f"/api/companies/{a.id}", json={"marketplace_default_branch_id": bb.id})
    assert r.status_code == 400
    r = client.login(ua).put(f"/api/companies/{a.id}", json={"marketplace_default_branch_id": inactive.id})
    assert r.status_code == 400
    r = client.login(ua).put(f"/api/companies/{a.id}", json={"marketplace_default_branch_id": ab.id})
    assert r.status_code == 200, r.text
    assert r.json()["marketplace_default_branch_id"] == ab.id
    assert client.login(ua).get("/api/companies").json()[0]["marketplace_default_branch_id"] == ab.id
    r = client.login(ua).put(f"/api/companies/{a.id}", json={"marketplace_default_branch_id": None})
    assert r.status_code == 200 and r.json()["marketplace_default_branch_id"] is None
