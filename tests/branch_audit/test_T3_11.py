"""T3.11 — Web POS: oflayn sotuv vaqti chegarasi, pos-list sahifalash, frontend yordamchilari.

Qamrov: create_sale created_at oralig'i (2 soat OK, 73 soat / +10 daqiqa 400, None o'zgarmagan),
OFFLINE_SALE_SYNCED audit, smenaga bog'lash, POST /sales/ 400 detail, /products/pos-list skip/limit
(takrorlanmaydi, limit=5001 -> 422, korxonalar izolyatsiyasi), config qiymatlari,
frontend manba tekshiruvlari (posQueue, usePosSync, PosLogin, PosReturn, AdminLayout, PosKassa, i18n).

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_11.py -q -p no:cacheprovider
"""
import itertools
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models.audit_log import AuditLog
from app.models.inventory import StockLevel
from app.models.moliya import KassaSession, Wallet
from app.models.product import Product
from app.models.sale import Sale
from app.models.shift import Shift
from app.models.user import UserRole, UserWallet
from app.schemas.sale import SaleCreate
from app.services.sale_create import OFFLINE_SALE_TIME_DETAIL, _to_naive_utc, create_sale

_seq = itertools.count(1)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _wallet(db, company, branch):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _product(db, company, wh=None, qty=100, name=None):
    n = next(_seq)
    p = Product(name=name or f"Tovar {n}", sku=f"T311-{n}", barcode=f"B311-{n:06d}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    if wh is not None:
        db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
        db.flush()
    return p


def _body(p, **extra):
    body = {"items": [{"product_id": p.id, "quantity": 1, "unit_price": 1000}], "payment_type": "cash",
            "paid_amount": 1000, "paid_cash": 1000, "payments": [{"type": "cash", "amount": 1000}]}
    body.update(extra)
    return body


@pytest.fixture
def w(db, mk):
    ca, ba, wa, admin = mk.tenant(UserRole.admin)
    wallet = _wallet(db, ca, ba)
    db.add(UserWallet(user_id=admin.id, wallet_id=wallet.id, is_default=True, company_id=ca.id))
    db.flush()
    cb, bb, wb, admin_b = mk.tenant(UserRole.admin)
    return dict(ca=ca, ba=ba, wa=wa, admin=admin, cb=cb, bb=bb, wb=wb, admin_b=admin_b)


def _iso(dt):
    return dt.isoformat().replace('+00:00', 'Z')


def _now():
    return datetime.now(timezone.utc)


def _audit(db, sale_id, action="OFFLINE_SALE_SYNCED"):
    return db.query(AuditLog).filter(AuditLog.action == action, AuditLog.entity_id == sale_id).all()


# ── Sotuv vaqti chegarasi (create_sale) ──────────────────────────────────────

def test_config_defaults():
    assert settings.POS_OFFLINE_MAX_AGE_HOURS == 72
    assert settings.POS_FUTURE_TOLERANCE_MINUTES == 5


def test_created_at_two_hours_ok_and_audited(db, w):
    p = _product(db, w["ca"], w["wa"])
    cat = _now() - timedelta(hours=2)
    sale = create_sale(db, SaleCreate(**_body(p, created_at=_iso(cat), local_id="abc-1")), w["admin"])
    assert sale.id is not None
    # asl qiymat yoziladi — taxminan 2 soat oldin (sinxron vaqti emas)
    saved = sale.created_at if sale.created_at.tzinfo else sale.created_at.replace(tzinfo=timezone.utc)
    assert abs((saved - cat).total_seconds()) < 2
    logs = _audit(db, sale.id)
    assert len(logs) == 1
    assert logs[0].company_id == w["ca"].id


def test_created_at_73_hours_rejected(db, w):
    p = _product(db, w["ca"], w["wa"])
    cat = _now() - timedelta(hours=73)
    with pytest.raises(HTTPException) as e:
        create_sale(db, SaleCreate(**_body(p, created_at=_iso(cat))), w["admin"])
    assert e.value.status_code == 400
    assert e.value.detail == "Sotuv vaqti ruxsat etilgan oraliqdan tashqarida" == OFFLINE_SALE_TIME_DETAIL
    assert db.query(Sale).filter(Sale.company_id == w["ca"].id).count() == 0


def test_created_at_future_10_min_rejected(db, w):
    p = _product(db, w["ca"], w["wa"])
    with pytest.raises(HTTPException) as e:
        create_sale(db, SaleCreate(**_body(p, created_at=_iso(_now() + timedelta(minutes=10)))), w["admin"])
    assert e.value.status_code == 400


def test_created_at_small_future_tolerated_and_not_audited(db, w):
    p = _product(db, w["ca"], w["wa"])
    sale = create_sale(db, SaleCreate(**_body(p, created_at=_iso(_now() + timedelta(minutes=2)))), w["admin"])
    assert sale.id is not None
    assert _audit(db, sale.id) == []          # farq 10 daqiqadan kam — audit yo'q


def test_created_at_none_unchanged(db, w):
    p = _product(db, w["ca"], w["wa"])
    sale = create_sale(db, SaleCreate(**_body(p)), w["admin"])
    assert sale.id is not None and sale.created_at is not None
    assert _audit(db, sale.id) == []


def test_naive_created_at_treated_as_utc(db, w):
    p = _product(db, w["ca"], w["wa"])
    naive = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(tzinfo=None)
    sale = create_sale(db, SaleCreate(**_body(p, created_at=naive.isoformat())), w["admin"])
    assert len(_audit(db, sale.id)) == 1


def test_to_naive_utc_helper():
    aware = datetime(2026, 1, 1, 12, 0, tzinfo=timezone(timedelta(hours=5)))
    assert _to_naive_utc(aware) == datetime(2026, 1, 1, 7, 0)
    assert _to_naive_utc(None) is None
    n = datetime(2026, 1, 1, 7, 0)
    assert _to_naive_utc(n) == n


def test_offline_sale_bound_to_open_shift_covering_time(db, w):
    p = _product(db, w["ca"], w["wa"])
    shift = Shift(cashier_id=w["admin"].id, branch_id=w["ba"].id, company_id=w["ca"].id, status="open",
                  opened_at=(datetime.now(timezone.utc) - timedelta(hours=5)).replace(tzinfo=None))
    db.add(shift)
    db.flush()
    sale = create_sale(db, SaleCreate(**_body(p, created_at=_iso(_now() - timedelta(hours=2)))), w["admin"])
    assert sale.shift_id == shift.id


def test_config_limit_is_respected(db, w, monkeypatch):
    p = _product(db, w["ca"], w["wa"])
    monkeypatch.setattr(settings, "POS_OFFLINE_MAX_AGE_HOURS", 1)
    with pytest.raises(HTTPException) as e:
        create_sale(db, SaleCreate(**_body(p, created_at=_iso(_now() - timedelta(hours=2)))), w["admin"])
    assert e.value.status_code == 400


def test_post_sales_endpoint_400_detail(client, db, w):
    p = _product(db, w["ca"], w["wa"])
    r = client.login(w["admin"]).post("/api/sales/", json=_body(p, created_at=_iso(_now() - timedelta(hours=73))))
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Sotuv vaqti ruxsat etilgan oraliqdan tashqarida"
    r = client.login(w["admin"]).post("/api/sales/", json=_body(p, created_at=_iso(_now() - timedelta(hours=2))))
    assert r.status_code in (200, 201), r.text


def test_sale_other_company_product_not_allowed(db, w):
    pb = _product(db, w["cb"], w["wb"])
    with pytest.raises(HTTPException) as e:
        create_sale(db, SaleCreate(**_body(pb, created_at=_iso(_now() - timedelta(hours=2)))), w["admin"])
    assert e.value.status_code in (400, 403, 404)


# ── /products/pos-list sahifalash ────────────────────────────────────────────

def _page(client, user, **params):
    r = client.login(user).get("/api/products/pos-list", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_pos_list_paging_three_pages(client, db, w):
    made = [_product(db, w["ca"], w["wa"], name=f"Mahsulot {i:02d}") for i in range(7)]
    _product(db, w["cb"], w["wb"], name="Mahsulot BEGONA")
    seen = []
    for skip in (0, 3, 6):
        rows = _page(client, w["admin"], limit=3, skip=skip)
        seen.extend(r["id"] for r in rows)
    assert len(seen) == len(set(seen)) == 7
    assert set(seen) == {p.id for p in made}
    names = [r["name"] for r in _page(client, w["admin"], limit=10)]
    assert names == sorted(names)
    assert _page(client, w["admin"], limit=3, skip=7) == []


def test_pos_list_limit_bounds(client, db, w):
    _product(db, w["ca"], w["wa"])
    assert client.login(w["admin"]).get("/api/products/pos-list", params={"limit": 5001}).status_code == 422
    assert client.login(w["admin"]).get("/api/products/pos-list", params={"limit": 0}).status_code == 422
    assert client.login(w["admin"]).get("/api/products/pos-list", params={"skip": -1}).status_code == 422
    assert client.login(w["admin"]).get("/api/products/pos-list", params={"limit": 5000}).status_code == 200


def test_pos_list_company_isolation(client, db, w):
    pa = _product(db, w["ca"], w["wa"], name="A tovar")
    pb = _product(db, w["cb"], w["wb"], name="B tovar")
    ids_a = {r["id"] for r in _page(client, w["admin"], limit=100)}
    ids_b = {r["id"] for r in _page(client, w["admin_b"], limit=100)}
    assert pa.id in ids_a and pb.id not in ids_a
    assert pb.id in ids_b and pa.id not in ids_b


# ── Frontend manba tekshiruvlari ─────────────────────────────────────────────

def test_pos_queue_module_shape():
    src = _read("frontend/src/utils/posQueue.js")
    for name in ("export function getPending", "export function setPending", "export function getPendingPosCount",
                 "export function flushPosQueue", "export function migrateLegacyQueue", "export function queueKey"):
        assert name in src, name
    assert "`${base}:${companyId}`" in src          # pos_pending_sales:<companyId>
    assert "pos_pending_sales" in src and "pos_pending_returns" in src


def test_use_pos_sync_queues_created_at_and_company():
    src = _read("frontend/src/hooks/usePosSync.js")
    assert "created_at: new Date().toISOString()" in src
    assert "local_id: idemKey" in src
    assert "user_id" in src and "company_id" in src
    assert "raw.company_id !== getCurrentUser()?.company_id" in src      # loadFromCache
    assert "fetchAllPages" in src and "skip: page * PRODUCTS_PAGE_SIZE" in src
    assert "PRODUCTS_MAX_PAGES = 20" in src
    assert "image_url" in src and "catch" in src                          # kvota -> image_url siz qayta yozish
    assert "flushPosQueue" in src


def test_auth_context_keeps_queue_and_has_select_company():
    src = _read("frontend/src/context/AuthContext.jsx")
    keys_block = src[src.index("const POS_CACHE_KEYS"):src.index("function clearPosCache")]
    assert "pos_pending" not in keys_block            # navbat logout/login da o'chmaydi
    assert "selectCompany" in src and "/auth/select-company" in src
    assert "temp_token: tempToken" in src and "company_id: companyId" in src


def test_pos_login_fields_and_routes():
    src = _read("frontend/src/pages/PosLogin.jsx")
    assert "pos-desktop" not in src
    assert src.count("/admin/pos-kassa") == 2
    assert "company.id" not in src and "company.name" not in src and "company.address" not in src
    assert "company.company_id" in src and "company.company_name" in src
    assert "needs_company_selection" in src and "temp_token" in src
    assert "active_company_id" not in src


def test_pos_return_route():
    src = _read("frontend/src/pages/admin/PosReturn.jsx")
    assert "/admin/pos-desktop" not in src
    assert "/admin/pos-kassa" in src
    assert 'path="pos-kassa"' in _read("frontend/src/App.jsx")


def test_admin_layout_logout_guard():
    src = _read("frontend/src/components/AdminLayout.jsx")
    body = src[src.index("const handleLogout"):src.index("// Rebuild navGroups")]
    assert "getPendingPosCount()" in body and "flushPosQueue(api)" in body
    assert "window.confirm" in body and "pos.logoutPendingConfirm" in body
    assert "toast.error" in body and "pos.logoutBlockedPending" in body
    assert body.index("navigator.onLine") < body.index("flushPosQueue")


def test_pos_kassa_pending_badge_and_barcode_lookup():
    src = _read("frontend/src/pages/admin/PosKassa.jsx")
    assert "syncing, pendingCount" in src
    assert "pos.pendingBadge" in src
    assert "/products/barcode/' + encodeURIComponent(code)" in src
    assert "status === 404" in src


def test_i18n_pending_keys_parity():
    with open(os.path.join(ROOT, "tests/branch_audit/i18n_pending/T3.11.json"), encoding="utf-8") as f:
        data = json.load(f)
    assert set(data) == {"uz", "ru", "en"}
    keys = set(data["uz"])
    assert {"pos.logoutPendingConfirm", "pos.logoutBlockedPending", "pos.pendingBadge"} <= keys
    assert set(data["ru"]) == keys and set(data["en"]) == keys
    assert "{count}" in data["uz"]["pos.logoutPendingConfirm"]


def test_package_json_has_vitest():
    pkg = json.loads(_read("frontend/package.json"))
    assert pkg["scripts"].get("test") == "vitest run"
    assert "vitest" in pkg["devDependencies"]
