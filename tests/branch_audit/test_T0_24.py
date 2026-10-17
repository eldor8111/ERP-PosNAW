"""T0.24 — Billing: subscribe va activate-my-trial uchun rol tekshiruvi (EDGE-20, EDGE-05)."""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_log import AuditLog
from app.models.billing import BalanceLog, Tariff
from app.models.user import UserRole
from app.routers import billing as billing_router

SUBSCRIBE = "/api/billing/my-company/subscribe"
TRIAL = "/api/billing/activate-my-trial"

OWNER_ROLES = [UserRole.admin, UserRole.director]
OTHER_ROLES = [UserRole.manager, UserRole.accountant, UserRole.warehouse, UserRole.cashier]


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@pytest.fixture
def tariffs(db):
    paid = Tariff(name="Pro", price_per_month=100000, duration_days=30, max_branches=5,
                  is_active=True, min_duration_months=1)
    trial = Tariff(name="Sinov", price_per_month=0, duration_days=7, max_branches=1, is_active=True)
    db.add_all([paid, trial])
    db.flush()
    return paid, trial


def _company_state(db, c):
    db.refresh(c)
    n_logs = db.query(BalanceLog).filter(BalanceLog.company_id == c.id).count()
    return float(c.balance or 0), c.tariff_id, c.subscription_ends_at, n_logs


def _setup(mk, db, role, balance=500000, **company_kw):
    c = mk.company(**company_kw)
    c.balance = balance
    db.flush()
    b = mk.branch(c)
    u = mk.user(c, role=role, branch=b)
    return c, u


# ─── subscribe: rol matritsasi ───────────────────────────────────────────────

@pytest.mark.parametrize("role", OTHER_ROLES)
def test_subscribe_forbidden_for_staff(db, mk, client, tariffs, role):
    paid, _ = tariffs
    c, u = _setup(mk, db, role)
    before = _company_state(db, c)
    r = client.login(u).post(SUBSCRIBE, json={"tariff_id": paid.id, "months": 1})
    assert r.status_code == 403
    assert "Admin" in r.json()["detail"]
    assert _company_state(db, c) == before
    assert db.query(AuditLog).filter(AuditLog.action == "billing.subscribe").count() == 0


@pytest.mark.parametrize("role", OWNER_ROLES)
def test_subscribe_allowed_for_owner_and_audited(db, mk, client, tariffs, role):
    paid, _ = tariffs
    c, u = _setup(mk, db, role)
    r = client.login(u).post(SUBSCRIBE, json={"tariff_id": paid.id, "months": 1})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert float(c.balance) == 400000
    assert c.tariff_id == paid.id
    assert c.is_trial is False
    audit = db.query(AuditLog).filter(AuditLog.action == "billing.subscribe").all()
    assert len(audit) == 1
    assert audit[0].entity_id == c.id and audit[0].user_id == u.id
    assert audit[0].new_values["tariff_id"] == paid.id
    assert audit[0].new_values["months"] == 1


def test_subscribe_expired_company_admin_ok(db, mk, client, tariffs):
    paid, _ = tariffs
    c, u = _setup(mk, db, UserRole.admin,
                  subscription_ends_at=datetime.now(timezone.utc) - timedelta(days=10))
    r = client.login(u).post(SUBSCRIBE, json={"tariff_id": paid.id, "months": 1})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert _utc(c.subscription_ends_at) > datetime.now(timezone.utc)


def test_subscribe_second_request_sees_first_result(db, mk, client, tariffs):
    """Ketma-ket ikkinchi so'rov birinchisining natijasini ko'radi: balans ikki marta yechilmaydi."""
    paid, _ = tariffs
    c, u = _setup(mk, db, UserRole.admin, balance=150000)
    cl = client.login(u)
    assert cl.post(SUBSCRIBE, json={"tariff_id": paid.id, "months": 1}).status_code == 200
    r2 = cl.post(SUBSCRIBE, json={"tariff_id": paid.id, "months": 1})
    assert r2.status_code == 400  # balans yetarli emas
    db.refresh(c)
    assert float(c.balance) == 50000


def test_company_row_locked_for_update():
    """PG da parallel so'rovlar uchun FOR UPDATE ishlatilishi shart (SQLite uni e'tiborsiz qoldiradi)."""
    assert "with_for_update()" in inspect.getsource(billing_router.subscribe_my_company)
    assert "with_for_update()" in inspect.getsource(billing_router.activate_my_trial)


# ─── activate-my-trial ───────────────────────────────────────────────────────

@pytest.mark.parametrize("role", OTHER_ROLES)
def test_trial_forbidden_for_staff(db, mk, client, tariffs, role):
    c, u = _setup(mk, db, role, is_trial=False)
    before = _company_state(db, c)
    r = client.login(u).post(TRIAL)
    assert r.status_code == 403
    assert _company_state(db, c) == before


def test_trial_active_paid_subscription_rejected(db, mk, client, tariffs):
    paid, _ = tariffs
    ends = datetime.now(timezone.utc) + timedelta(days=200)
    c, u = _setup(mk, db, UserRole.admin, is_trial=False, tariff_id=paid.id, subscription_ends_at=ends)
    before = _company_state(db, c)
    r = client.login(u).post(TRIAL)
    assert r.status_code == 400
    assert _company_state(db, c) == before


def test_trial_rejected_if_balance_log_exists(db, mk, client, tariffs):
    c, u = _setup(mk, db, UserRole.director, is_trial=False)
    db.add(BalanceLog(company_id=c.id, amount=-1000, log_type="subscription", note="eski"))
    db.flush()
    before = _company_state(db, c)
    r = client.login(u).post(TRIAL)
    assert r.status_code == 400
    assert "allaqachon" in r.json()["detail"]
    assert _company_state(db, c) == before


def test_trial_already_trial_rejected(db, mk, client, tariffs):
    c, u = _setup(mk, db, UserRole.admin, is_trial=True)
    assert client.login(u).post(TRIAL).status_code == 400


def test_trial_fresh_company_owner_ok(db, mk, client, tariffs):
    _, trial = tariffs
    c, u = _setup(mk, db, UserRole.admin, is_trial=False)
    r = client.login(u).post(TRIAL)
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.is_trial is True and c.tariff_id == trial.id
    assert _utc(c.subscription_ends_at) > datetime.now(timezone.utc)


def test_trial_expired_old_subscription_without_logs_ok(db, mk, client, tariffs):
    """Muddati o'tgan, log yo'q korxona: eski muddat qisqartirilmaydi (u o'tib ketgan), sinov beriladi."""
    c, u = _setup(mk, db, UserRole.admin, is_trial=False,
                  subscription_ends_at=datetime.now(timezone.utc) - timedelta(days=3))
    assert client.login(u).post(TRIAL).status_code == 200


# ─── Korxonalar izolyatsiyasi ────────────────────────────────────────────────

def test_subscribe_affects_only_own_company(db, mk, client, tariffs):
    paid, _ = tariffs
    ca, ua = _setup(mk, db, UserRole.admin)
    cb, ub = _setup(mk, db, UserRole.admin)
    before_b = _company_state(db, cb)
    assert client.login(ua).post(SUBSCRIBE, json={"tariff_id": paid.id, "months": 1}).status_code == 200
    assert _company_state(db, cb) == before_b
    db.refresh(ca)
    assert float(ca.balance) == 400000
