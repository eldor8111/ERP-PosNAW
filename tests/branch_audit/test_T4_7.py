"""T4.7 - Filial rejasi, KPI, ish soati/komissiya va distribyutor hududi.

Qamrov: `PUT /branch-plans/targets` (upsert, validatsiya, 404/400/403), `GET /branch-plans/progress`
(fakt = sotuv - qaytarish, bekor/kutilayotgan kirmaydi, cashier-report bilan mos, foiz/prognoz/reyting,
rejasiz filial), `/branch-plans/sellers`, menejer filial cheklovi, ikki korxona izolyatsiyasi,
`/staff-reports/work-hours` (yopiq/ochiq/uzun smena), `/staff-reports/commissions` + `commission-rates`,
`_check_territory_free` (region bilan), `GET /dashboard/summary` dagi `plan`, frontend i18n kalitlari.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T4_7.py -q -p no:cacheprovider
"""
import itertools
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.customer import Customer
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.sales_target import SalesTarget
from app.models.shift import Shift
from app.models.user import UserRole
from app.routers import branch_plans as bp
from app.routers.customers import _check_territory_free

_seq = itertools.count(1)
MONTH = "2026-09"            # o'tgan oy (to'liq): prognoz = fakt
IN_MONTH = datetime(2026, 9, 15, 12, 0)


def _sale(db, user, company, warehouse, amount, refund=False, status=None, at=IN_MONTH):
    n = next(_seq)
    st = status or (SaleStatus.refunded if refund else SaleStatus.completed)
    s = Sale(number=f"{'R' if refund else 'S'}T47-{n}", cashier_id=user.id, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None, total_amount=Decimal(amount),
             paid_amount=Decimal(amount), payment_type=PaymentType.cash, status=st, created_at=at)
    db.add(s)
    db.flush()
    return s


def _shift(db, user, branch, opened, closed=None, status=None):
    s = Shift(cashier_id=user.id, branch_id=branch.id, company_id=user.company_id, opened_at=opened,
              closed_at=closed, status=status or ("closed" if closed else "open"))
    db.add(s)
    db.flush()
    return s


def _put(client, user, **body):
    return client.login(user).put("/api/branch-plans/targets", json=body)


def _row(rows, branch_id):
    return next(r for r in rows if r["branch_id"] == branch_id)


# ─── Rejani kiritish ─────────────────────────────────────────────────────────

def test_put_target_and_progress_percent(client, db, mk):
    c, b, w, admin = mk.tenant()
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    _sale(db, cashier, c, w, 200_000_000)
    _sale(db, cashier, c, w, 50_000_000, refund=True)  # qaytarish ayriladi
    r = _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=300_000_000)
    assert r.status_code == 200, r.text
    assert r.json()["month"] == MONTH and r.json()["revenue_target"] == 300_000_000
    rows = client.get(f"/api/branch-plans/progress?month={MONTH}").json()
    row = _row(rows, b.id)
    assert row["target"] == 300_000_000
    assert row["fact"] == 150_000_000
    assert row["percent"] == 50.0
    assert row["remaining"] == 150_000_000
    assert row["rank"] == 1
    assert row["days_left"] == 0
    assert row["forecast"] == 150_000_000  # o'tgan oy: butun oy o'tgan


def test_second_put_updates_not_inserts(client, db, mk):
    c, b, w, admin = mk.tenant()
    assert _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=100).status_code == 200
    first = client.get(f"/api/branch-plans/targets?month={MONTH}").json()
    assert _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=500).status_code == 200
    rows = client.get(f"/api/branch-plans/targets?month={MONTH}").json()
    assert len(rows) == 1 and rows[0]["id"] == first[0]["id"] and rows[0]["revenue_target"] == 500
    assert db.query(SalesTarget).filter(SalesTarget.branch_id == b.id).count() == 1


def test_unique_index_race_falls_back_to_update(client, db, mk, monkeypatch):
    """Parallel so'rov oldin yozib qo'ygan: unikal indeks buzilsa 500 emas, mavjudi yangilanadi."""
    c, b, w, admin = mk.tenant()
    db.add(SalesTarget(company_id=c.id, branch_id=b.id, period_month=date(2026, 9, 1), revenue_target=Decimal(10)))
    db.flush()
    orig = bp.SalesTarget
    calls = {"n": 0}
    real_query = db.query

    # birinchi `_find()` hech narsa topmaganday ko'rinsin (poyga), keyingisi haqiqiy natija qaytarsin
    class _Empty:
        def filter(self, *a, **k):
            return self

        def first(self):
            return None

    def fake_query(*a, **k):
        if a and a[0] is orig and calls["n"] == 0:
            calls["n"] += 1
            return _Empty()
        return real_query(*a, **k)

    monkeypatch.setattr(db, "query", fake_query)
    r = _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=777)
    assert r.status_code == 200, r.text
    monkeypatch.setattr(db, "query", real_query)
    assert db.query(SalesTarget).filter(SalesTarget.branch_id == b.id).count() == 1
    assert float(db.query(SalesTarget).filter(SalesTarget.branch_id == b.id).one().revenue_target) == 777


@pytest.mark.parametrize("body", [
    {"month": "2026-9", "revenue_target": 1},
    {"month": "2026-13", "revenue_target": 1},
    {"month": "oktyabr", "revenue_target": 1},
    {"month": MONTH, "revenue_target": -5},
])
def test_put_validation_422(client, mk, body):
    c, b, w, admin = mk.tenant()
    r = _put(client, admin, branch_id=b.id, **body)
    assert r.status_code == 422


def test_seller_target_requires_user_in_branch(client, db, mk):
    c, b, w, admin = mk.tenant()
    b2 = mk.branch(c)
    seller = mk.user(c, role=UserRole.cashier, branch=b)
    r = _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=10, user_id=seller.id)
    assert r.status_code == 200 and r.json()["user_id"] == seller.id
    # ikkinchi filialda ishlamaydi -> 400
    assert _put(client, admin, branch_id=b2.id, month=MONTH, revenue_target=10, user_id=seller.id).status_code == 400
    # filial rejasi va sotuvchi rejasi alohida qatorlar
    assert _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=99).status_code == 200
    assert len(client.get(f"/api/branch-plans/targets?month={MONTH}").json()) == 2


def test_delete_target(client, db, mk):
    c, b, w, admin = mk.tenant()
    tid = _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=5).json()["id"]
    assert client.delete(f"/api/branch-plans/targets/{tid}").status_code == 204
    assert client.delete(f"/api/branch-plans/targets/{tid}").status_code == 404


# ─── Fakt hisobi ─────────────────────────────────────────────────────────────

def test_fact_excludes_cancelled_pending_and_matches_cashier_report(client, db, mk):
    c, b, w, admin = mk.tenant()
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    _sale(db, cashier, c, w, 1_000)
    _sale(db, cashier, c, w, 2_000, status=SaleStatus.partial_refund)  # haqiqiy sotuv bo'lib qoladi
    _sale(db, cashier, c, w, 400, refund=True)
    _sale(db, cashier, c, w, 9_999, status=SaleStatus.cancelled)
    _sale(db, cashier, c, w, 7_777, status=SaleStatus.pending)
    _sale(db, cashier, c, w, 5_555, at=datetime(2026, 8, 20, 12, 0))  # boshqa oy
    _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=10_000)
    fact = _row(client.get(f"/api/branch-plans/progress?month={MONTH}").json(), b.id)["fact"]
    assert fact == 2_600
    rep = client.get(f"/api/reports/cashier-report?date_from=2026-09-01&date_to=2026-09-30&branch_id={b.id}").json()
    assert sum(sum(e["total_amount"].values()) for e in rep) == fact


def test_branch_without_target_has_null_percent(client, db, mk):
    c, b, w, admin = mk.tenant()
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    _sale(db, cashier, c, w, 100)
    _sale(db, cashier, c, w2, 900)
    _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=200)
    rows = client.get(f"/api/branch-plans/progress?month={MONTH}").json()
    no_plan = _row(rows, b2.id)
    assert no_plan["target"] is None and no_plan["percent"] is None and no_plan["rank"] is None
    assert no_plan["remaining"] is None and no_plan["fact"] == 900
    assert _row(rows, b.id)["rank"] == 1


def test_rank_orders_by_percent(client, db, mk):
    c, b1, w1, admin = mk.tenant()
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    cashier = mk.user(c, role=UserRole.cashier, branch=b1)
    _sale(db, cashier, c, w1, 50)    # 50%
    _sale(db, cashier, c, w2, 180)   # 90%
    _put(client, admin, branch_id=b1.id, month=MONTH, revenue_target=100)
    _put(client, admin, branch_id=b2.id, month=MONTH, revenue_target=200)
    rows = client.get(f"/api/branch-plans/progress?month={MONTH}").json()
    assert [r["branch_id"] for r in rows[:2]] == [b2.id, b1.id]
    assert (rows[0]["rank"], rows[1]["rank"]) == (1, 2)
    assert rows[0]["percent"] == 90.0


def test_forecast_current_month(client, db, mk, monkeypatch):
    c, b, w, admin = mk.tenant()
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    _sale(db, cashier, c, w, 1_000, at=datetime(2026, 10, 3, 12, 0))
    monkeypatch.setattr(bp, "local_today", lambda: date(2026, 10, 10))
    _put(client, admin, branch_id=b.id, month="2026-10", revenue_target=100_000)
    row = _row(client.get("/api/branch-plans/progress?month=2026-10").json(), b.id)
    assert row["days_left"] == 21
    assert row["forecast"] == round(1_000 / 10 * 31, 2)


def test_sellers_plan_and_fact(client, db, mk):
    c, b, w, admin = mk.tenant()
    s1 = mk.user(c, role=UserRole.cashier, branch=b)
    s2 = mk.user(c, role=UserRole.cashier, branch=b)
    _sale(db, s1, c, w, 600)
    _sale(db, s2, c, w, 100)
    _sale(db, s2, c, w, 30, refund=True)
    _put(client, admin, branch_id=b.id, month=MONTH, revenue_target=1_000, user_id=s1.id)
    rows = client.get(f"/api/branch-plans/sellers?month={MONTH}&branch_id={b.id}").json()
    r1 = next(r for r in rows if r["user_id"] == s1.id)
    r2 = next(r for r in rows if r["user_id"] == s2.id)
    assert (r1["target"], r1["fact"], r1["percent"]) == (1_000, 600, 60.0)
    assert (r2["target"], r2["fact"], r2["percent"]) == (None, 70, None)


# ─── Rol va izolyatsiya ──────────────────────────────────────────────────────

def test_manager_cannot_write_and_sees_only_own_branch(client, db, mk):
    c, b1, w1, admin = mk.tenant()
    b2 = mk.branch(c)
    mk.warehouse(c, b2)
    mgr = mk.user(c, role=UserRole.manager, branch=b1)
    _put(client, admin, branch_id=b1.id, month=MONTH, revenue_target=10)
    _put(client, admin, branch_id=b2.id, month=MONTH, revenue_target=20)
    assert _put(client, mgr, branch_id=b1.id, month=MONTH, revenue_target=1).status_code == 403
    rows = client.login(mgr).get(f"/api/branch-plans/progress?month={MONTH}").json()
    assert [r["branch_id"] for r in rows] == [b1.id]
    assert client.get(f"/api/branch-plans/progress?month={MONTH}&branch_id={b2.id}").status_code == 403
    assert client.get(f"/api/branch-plans/targets?month={MONTH}&branch_id={b2.id}").status_code == 403
    own = client.get(f"/api/branch-plans/targets?month={MONTH}").json()
    assert [t["branch_id"] for t in own] == [b1.id]
    tid = client.login(admin).get(f"/api/branch-plans/targets?month={MONTH}&branch_id={b2.id}").json()[0]["id"]
    assert client.login(mgr).delete(f"/api/branch-plans/targets/{tid}").status_code == 403


def test_cross_company_isolation(client, db, mk):
    cA, bA, wA, adminA = mk.tenant()
    cB, bB, wB, adminB = mk.tenant()
    sellerB = mk.user(cB, role=UserRole.cashier, branch=bB)
    _put(client, adminB, branch_id=bB.id, month=MONTH, revenue_target=500)
    _sale(db, sellerB, cB, wB, 123)
    tid = client.get(f"/api/branch-plans/targets?month={MONTH}").json()[0]["id"]
    # A korxona foydalanuvchisi B resursiga
    assert _put(client, adminA, branch_id=bB.id, month=MONTH, revenue_target=1).status_code == 404
    assert _put(client, adminA, branch_id=bA.id, month=MONTH, revenue_target=1, user_id=sellerB.id).status_code == 404
    assert client.delete(f"/api/branch-plans/targets/{tid}").status_code == 404
    assert client.get(f"/api/branch-plans/progress?month={MONTH}&branch_id={bB.id}").status_code == 404
    rows = client.get(f"/api/branch-plans/progress?month={MONTH}").json()
    assert [r["branch_id"] for r in rows] == [bA.id] and rows[0]["fact"] == 0
    assert client.get(f"/api/branch-plans/targets?month={MONTH}").json() == []
    assert client.get(f"/api/branch-plans/sellers?month={MONTH}").json() == []


# ─── Ish soati ───────────────────────────────────────────────────────────────

def test_work_hours_closed_open_and_long(client, db, mk):
    c, b, w, admin = mk.tenant()
    k1 = mk.user(c, role=UserRole.cashier, branch=b)
    k2 = mk.user(c, role=UserRole.cashier, branch=b)
    base = datetime(2026, 9, 10, 8, 0)
    _shift(db, k1, b, base, base + timedelta(hours=9, minutes=30))                 # 9.5 soat
    _shift(db, k1, b, base + timedelta(days=1), base + timedelta(days=1, hours=20))  # 20 soat - uzun
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _shift(db, k2, b, now - timedelta(hours=3))                                      # ochiq, 3 soat
    r = client.login(admin).get("/api/staff-reports/work-hours?date_from=2026-09-01&date_to=2026-12-31").json()
    e1 = next(x for x in r if x["cashier_id"] == k1.id)
    assert e1["shifts_count"] == 2 and e1["total_hours"] == 29.5 and e1["avg_shift_hours"] == 14.75
    assert [s["hours"] for s in e1["long_shifts"]] == [20.0] and e1["open_shift"] is None
    # kun chegarasi Toshkent vaqti: 9.5 soatlik smena alohida tekshiriladi
    only = client.get(f"/api/staff-reports/work-hours?date_from=2026-09-10&date_to=2026-09-10&cashier_id={k1.id}").json()
    assert only[0]["shifts_count"] == 1 and only[0]["total_hours"] == 9.5
    e2 = next(x for x in r if x["cashier_id"] == k2.id)
    assert e2["open_shift"] is not None and abs(e2["open_shift"]["hours"] - 3.0) < 0.05
    assert e2["long_shifts"] == []


def test_work_hours_open_shift_capped_and_flagged(client, db, mk):
    c, b, w, admin = mk.tenant()
    k = mk.user(c, role=UserRole.cashier, branch=b)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    _shift(db, k, b, now - timedelta(hours=60))
    r = client.login(admin).get("/api/staff-reports/work-hours").json()
    assert r[0]["total_hours"] == 24.0
    assert len(r[0]["long_shifts"]) == 1 and r[0]["long_shifts"][0]["is_open"] is True


def test_work_hours_branch_scope_and_company_isolation(client, db, mk):
    cA, bA, wA, adminA = mk.tenant()
    bA2 = mk.branch(cA)
    cB, bB, wB, adminB = mk.tenant()
    kA = mk.user(cA, role=UserRole.cashier, branch=bA)
    kA2 = mk.user(cA, role=UserRole.cashier, branch=bA2)
    kB = mk.user(cB, role=UserRole.cashier, branch=bB)
    t0 = datetime(2026, 9, 10, 8, 0)
    for k, br in ((kA, bA), (kA2, bA2), (kB, bB)):
        _shift(db, k, br, t0, t0 + timedelta(hours=8))
    mgr = mk.user(cA, role=UserRole.manager, branch=bA)
    rows = client.login(mgr).get("/api/staff-reports/work-hours?date_from=2026-09-01&date_to=2026-09-30").json()
    assert [x["cashier_id"] for x in rows] == [kA.id]
    assert client.get(f"/api/staff-reports/work-hours?branch_id={bA2.id}").status_code == 403
    rows = client.login(adminA).get("/api/staff-reports/work-hours?date_from=2026-09-01&date_to=2026-09-30").json()
    assert sorted(x["cashier_id"] for x in rows) == sorted([kA.id, kA2.id])  # kB ko'rinmaydi
    assert client.get(f"/api/staff-reports/work-hours?branch_id={bB.id}").status_code == 404


# ─── Komissiya ───────────────────────────────────────────────────────────────

def test_commission_net_of_returns(client, db, mk):
    c, b, w, admin = mk.tenant()
    seller = mk.user(c, role=UserRole.cashier, branch=b)
    _sale(db, seller, c, w, 12_000_000)
    _sale(db, seller, c, w, 2_000_000, refund=True)
    r = client.login(admin).put(f"/api/staff-reports/commission-rates/{seller.id}", json={"percent": 1})
    assert r.status_code == 200 and r.json()["percent"] == 1
    rows = client.get("/api/staff-reports/commissions?date_from=2026-09-01&date_to=2026-09-30").json()
    e = next(x for x in rows if x["user_id"] == seller.id)
    assert e["net_sales"] == 10_000_000 and e["percent"] == 1 and e["commission"] == 100_000
    assert e["by_currency"]["UZS"]["commission"] == 100_000
    # foiz yangilanadi (yangi qator emas)
    client.put(f"/api/staff-reports/commission-rates/{seller.id}", json={"percent": 2.5})
    e = client.get("/api/staff-reports/commissions?date_from=2026-09-01&date_to=2026-09-30").json()[0]
    assert e["percent"] == 2.5 and e["commission"] == 250_000


def test_commission_percent_validation_and_roles(client, db, mk):
    c, b, w, admin = mk.tenant()
    seller = mk.user(c, role=UserRole.cashier, branch=b)
    for bad in (-1, 100.01, 101):
        assert client.login(admin).put(f"/api/staff-reports/commission-rates/{seller.id}",
                                       json={"percent": bad}).status_code == 422
    assert client.put(f"/api/staff-reports/commission-rates/{seller.id}", json={"percent": 0}).status_code == 200
    assert client.put(f"/api/staff-reports/commission-rates/{seller.id}", json={"percent": 100}).status_code == 200
    mgr = mk.user(c, role=UserRole.manager, branch=b)
    assert client.login(mgr).put(f"/api/staff-reports/commission-rates/{seller.id}",
                                 json={"percent": 5}).status_code == 403


def test_commission_cross_company_and_branch_scope(client, db, mk):
    cA, bA, wA, adminA = mk.tenant()
    bA2 = mk.branch(cA)
    wA2 = mk.warehouse(cA, bA2)
    cB, bB, wB, adminB = mk.tenant()
    sA = mk.user(cA, role=UserRole.cashier, branch=bA)
    sA2 = mk.user(cA, role=UserRole.cashier, branch=bA2)
    sB = mk.user(cB, role=UserRole.cashier, branch=bB)
    _sale(db, sA, cA, wA, 100)
    _sale(db, sA2, cA, wA2, 200)
    _sale(db, sB, cB, wB, 999)
    assert client.login(adminA).put(f"/api/staff-reports/commission-rates/{sB.id}",
                                    json={"percent": 5}).status_code == 404
    rows = client.get("/api/staff-reports/commissions?date_from=2026-09-01&date_to=2026-09-30").json()
    assert sorted(x["user_id"] for x in rows) == sorted([sA.id, sA2.id])
    one = client.get(f"/api/staff-reports/commissions?date_from=2026-09-01&date_to=2026-09-30&branch_id={bA2.id}").json()
    assert [x["user_id"] for x in one] == [sA2.id]
    mgr = mk.user(cA, role=UserRole.manager, branch=bA)
    rows = client.login(mgr).get("/api/staff-reports/commissions?date_from=2026-09-01&date_to=2026-09-30").json()
    assert [x["user_id"] for x in rows] == [sA.id]


# ─── Distribyutor hududi ─────────────────────────────────────────────────────

def _dist(db, c, name, territory, region=None, active=True):
    d = Customer(name=name, company_id=c.id, customer_type="distributor", territory=territory,
                 region=region, is_active=active)
    db.add(d)
    db.flush()
    return d


def test_territory_same_region_conflicts(db, mk):
    c = mk.company()
    _dist(db, c, "D1", "Markaziy bozor", "Toshkent")
    with pytest.raises(HTTPException) as ei:
        _check_territory_free(db, c.id, "distributor", "markaziy BOZOR", region="toshkent")
    assert ei.value.status_code == 409 and "(toshkent)" in ei.value.detail


def test_territory_different_region_allowed(db, mk):
    c = mk.company()
    _dist(db, c, "D1", "Markaziy bozor", "Toshkent")
    _check_territory_free(db, c.id, "distributor", "Markaziy bozor", region="Samarqand")


def test_territory_one_side_empty_region_conflicts(db, mk):
    c = mk.company()
    _dist(db, c, "D1", "Markaziy bozor", None)
    with pytest.raises(HTTPException):  # mavjudning viloyati bo'sh
        _check_territory_free(db, c.id, "distributor", "Markaziy bozor", region="Samarqand")
    _dist(db, c, "D2", "Yangi bozor", "Toshkent")
    with pytest.raises(HTTPException):  # yangining viloyati bo'sh
        _check_territory_free(db, c.id, "distributor", "Yangi bozor", region=None)
    with pytest.raises(HTTPException):
        _check_territory_free(db, c.id, "distributor", "Yangi bozor", region="  ")


def test_territory_both_empty_conflicts_and_exclude(db, mk):
    c = mk.company()
    d = _dist(db, c, "D1", "Chilonzor", None)
    with pytest.raises(HTTPException) as ei:
        _check_territory_free(db, c.id, "distributor", "Chilonzor")
    assert ei.value.status_code == 409
    _check_territory_free(db, c.id, "distributor", "Chilonzor", exclude_id=d.id)   # o'zini tahrirlash
    _check_territory_free(db, c.id, "distributor", "Chilonzor", region="Toshkent", exclude_id=d.id)
    _check_territory_free(db, c.id, "customer", "Chilonzor")                        # distribyutor emas
    _check_territory_free(db, mk.company().id, "distributor", "Chilonzor")          # boshqa korxona


def test_territory_inactive_ignored(db, mk):
    c = mk.company()
    _dist(db, c, "D1", "Markaziy bozor", "Toshkent", active=False)
    _check_territory_free(db, c.id, "distributor", "Markaziy bozor", region="Toshkent")


def test_create_distributor_api_region_rule(client, db, mk):
    c, b, w, admin = mk.tenant()
    _dist(db, c, "D1", "Markaziy bozor", "Toshkent")
    cl = client.login(admin)
    ok = cl.post("/api/customers", json={"name": "D2", "customer_type": "distributor",
                                         "territory": "Markaziy bozor", "region": "Samarqand"})
    assert ok.status_code in (200, 201), ok.text
    bad = cl.post("/api/customers", json={"name": "D3", "customer_type": "distributor",
                                          "territory": "Markaziy bozor", "region": "Toshkent"})
    assert bad.status_code == 409 and "Toshkent" in bad.json()["detail"]


# ─── Dashboard va frontend ───────────────────────────────────────────────────

def test_dashboard_summary_has_plan_and_keeps_keys(client, db, mk):
    c, b, w, admin = mk.tenant()
    first = date.today().replace(day=1)
    db.add(SalesTarget(company_id=c.id, branch_id=b.id, period_month=first, revenue_target=Decimal(1000)))
    db.flush()
    r = client.login(admin).get("/api/dashboard/summary")
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("period", "sales", "cash_balance", "cash_balance_by_currency", "cash_balance_scope",
                "low_stock_count", "top_products"):
        assert key in body
    assert body["plan"] == {"target": 1000, "fact": 0, "percent": 0.0}
    assert set(body["plan"]) == {"target", "fact", "percent"}


def test_dashboard_plan_without_target(client, db, mk):
    c, b, w, admin = mk.tenant()
    body = client.login(admin).get("/api/dashboard/summary").json()
    assert body["plan"] == {"target": None, "fact": 0, "percent": None}


def test_frontend_i18n_keys_pending_consistent():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = os.path.join(root, "tests", "branch_audit", "i18n_pending", "T4.7.json")
    data = json.load(open(path, encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"]) and data["uz"]
    for lang in data.values():
        assert all(isinstance(v, str) and v for v in lang.values())


def test_frontend_used_keys_are_in_pending():
    """Frontend fayllarda ishlatilgan yangi kalitlar (plan.*, staff.*, distributor.territoryRegionHint) pending faylda bor."""
    import re
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    pending = json.load(open(os.path.join(root, "tests", "branch_audit", "i18n_pending", "T4.7.json"), encoding="utf-8"))
    files = ["BranchPlans.jsx", "Shifts.jsx", "Reports.jsx", "Filiallar.jsx", "Customers.jsx"]
    used = set()
    for f in files:
        src = open(os.path.join(root, "frontend", "src", "pages", "admin", f), encoding="utf-8").read()
        used |= set(re.findall(r"'((?:plan|staff\.hours|staff\.commission)\.[A-Za-z.]+|distributor\.territoryRegionHint)'", src))
    assert used
    assert used <= set(pending["uz"]), used - set(pending["uz"])
