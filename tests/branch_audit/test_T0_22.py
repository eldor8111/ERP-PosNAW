"""T0.22 — API kalitlari korxonaga bog'langan; X-API-Key bilan faqat /reports/1c-export (o'z korxonasi)."""
import hashlib
import itertools
from datetime import datetime, timedelta, timezone

from app.core.security import create_access_token
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.user import UserRole

KEYS = '/api/api-keys/'
EXPORT = '/api/reports/1c-export'
_n = itertools.count(1)


def _raw_key(db, company, user=None, active=True, name='1C'):
    """Bazada kalit yaratadi, xom tokenni qaytaradi."""
    raw = f'tok-{next(_n)}-' + 'x' * 30
    rec = ApiKey(name=name, key_hash=hashlib.sha256(raw.encode()).hexdigest(), is_active=active,
                 company_id=company.id if company else None, created_by=user.id if user else None,
                 key_prefix=raw[:8])
    db.add(rec)
    db.flush()
    return raw, rec


def _sale(db, company, warehouse, cashier, total=100):
    s = Sale(number=f'S{next(_n):06d}', cashier_id=cashier.id, total_amount=total, paid_amount=total,
             payment_type=PaymentType.cash, status=SaleStatus.completed, company_id=company.id,
             warehouse_id=warehouse.id, created_at=datetime.now(timezone.utc))
    db.add(s)
    db.flush()
    return s


def _jwt(user):
    return {'Authorization': 'Bearer ' + create_access_token(
        {'sub': str(user.id), 'company_id': user.company_id, 'role': user.role.value})}


def _csv_numbers(resp):
    lines = resp.content.decode('utf-8-sig').strip().splitlines()
    return [ln.split(',')[0] for ln in lines[1:]]


# ── api-keys router ──────────────────────────────────────────────────────────

def test_create_binds_company_and_hides_hash(client, db, mk):
    ca, _, _, ua = mk.tenant()
    r = client.login(ua).post(KEYS, json={'name': '  1C Integratsiya  '})
    assert r.status_code == 200
    body = r.json()
    assert body['name'] == '1C Integratsiya' and body['token']
    rec = db.get(ApiKey, body['id'])
    assert rec.company_id == ca.id and rec.created_by == ua.id
    assert rec.key_prefix == body['token'][:8]
    assert rec.key_hash == hashlib.sha256(body['token'].encode()).hexdigest()
    assert db.query(AuditLog).filter(AuditLog.action == 'api_key.create', AuditLog.entity_id == rec.id).count() == 1


def test_create_name_validation(client, mk):
    _, _, _, ua = mk.tenant()
    c = client.login(ua)
    assert c.post(KEYS, json={'name': 'a' * 101}).status_code == 422
    assert c.post(KEYS, json={'name': ''}).status_code == 422
    assert c.post(KEYS, json={'name': '   '}).status_code == 422
    assert c.post(KEYS, json={'name': 'a' * 100}).status_code == 200


def test_create_without_company_400(client, db, mk):
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).post(KEYS, json={'name': 'x'})
    assert r.status_code == 400 and r.json()['detail'] == 'Korxona aniqlanmadi'


def test_list_isolated_no_hash(client, db, mk):
    ca, _, _, ua = mk.tenant()
    cb, _, _, ub = mk.tenant()
    _, ka = _raw_key(db, ca, ua, name='A kalit')
    _, kb = _raw_key(db, cb, ub, name='B kalit')
    _raw_key(db, None, name='egasiz')
    r = client.login(ua).get(KEYS)
    assert r.status_code == 200
    items = r.json()
    assert [i['id'] for i in items] == [ka.id]
    assert set(items[0]) == {'id', 'name', 'key_prefix', 'is_active', 'created_at', 'last_used_at'}
    assert 'key_hash' not in items[0]
    assert [i['id'] for i in client.login(ub).get(KEYS).json()] == [kb.id]


def test_list_super_admin_without_company_sees_nothing(client, db, mk):
    ca, _, _, ua = mk.tenant()
    _raw_key(db, ca, ua)
    _raw_key(db, None, name='egasiz')
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).get(KEYS)
    assert r.status_code == 200 and r.json() == []


def test_delete_foreign_404_own_ok(client, db, mk):
    ca, _, _, ua = mk.tenant()
    cb, _, _, ub = mk.tenant()
    _, ka = _raw_key(db, ca, ua)
    _, kb = _raw_key(db, cb, ub)
    _, orphan = _raw_key(db, None)
    c = client.login(ua)
    assert c.delete(f'{KEYS}{kb.id}').status_code == 404
    assert c.delete(f'{KEYS}{orphan.id}').status_code == 404
    assert c.delete(f'{KEYS}999999').status_code == 404
    assert db.get(ApiKey, kb.id) is not None and db.get(ApiKey, orphan.id) is not None
    r = c.delete(f'{KEYS}{ka.id}')
    assert r.status_code == 200
    assert db.get(ApiKey, ka.id) is None
    assert db.query(AuditLog).filter(AuditLog.action == 'api_key.delete').count() == 1


def test_non_admin_cannot_manage_keys(client, db, mk):
    ca, ba, _, _ = mk.tenant()
    cashier = mk.user(ca, role=UserRole.cashier, branch=ba)
    assert client.login(cashier).get(KEYS).status_code == 403
    assert client.login(cashier).post(KEYS, json={'name': 'x'}).status_code == 403


# ── 1c-export: X-API-Key ─────────────────────────────────────────────────────

def test_export_with_key_only_own_company(client, db, mk):
    ca, ba, wa, ua = mk.tenant()
    cb, bb, wb, ub = mk.tenant()
    sa = _sale(db, ca, wa, ua)
    sb = _sale(db, cb, wb, ub)
    raw, _ = _raw_key(db, ca, ua)
    r = client.get(EXPORT, headers={'X-API-Key': raw})
    assert r.status_code == 200
    nums = _csv_numbers(r)
    assert nums == [sa.number] and sb.number not in nums
    # B filiali berilsa ham B ma'lumoti chiqmaydi
    r = client.get(EXPORT, params={'branch_id': bb.id}, headers={'X-API-Key': raw})
    assert r.status_code == 200 and _csv_numbers(r) == []
    r = client.get(EXPORT, params={'branch_id': ba.id, 'format': 'xml'}, headers={'X-API-Key': raw})
    assert r.status_code == 200 and sa.number in r.text and sb.number not in r.text


def test_export_bad_inactive_orphan_key_403(client, db, mk):
    ca, _, _, ua = mk.tenant()
    inactive, _ = _raw_key(db, ca, ua, active=False)
    orphan, _ = _raw_key(db, None)
    for h in ('juda-noto-g-ri-kalit', inactive, orphan):
        assert client.get(EXPORT, headers={'X-API-Key': h}).status_code == 403


def test_export_deleted_key_403(client, db, mk):
    ca, _, _, ua = mk.tenant()
    raw, rec = _raw_key(db, ca, ua)
    assert client.get(EXPORT, headers={'X-API-Key': raw}).status_code == 200
    db.delete(rec)
    db.flush()
    assert client.get(EXPORT, headers={'X-API-Key': raw}).status_code == 403


def test_export_nothing_provided_401(client):
    assert client.get(EXPORT).status_code == 401


def test_invalid_key_with_valid_jwt_no_fallback_403(client, mk):
    _, _, _, ua = mk.tenant()
    h = {**_jwt(ua), 'X-API-Key': 'noto-g-ri'}
    assert client.get(EXPORT, headers=h).status_code == 403


def test_export_inactive_company_and_expired_subscription(client, db, mk):
    ca, _, _, ua = mk.tenant()
    raw, _ = _raw_key(db, ca, ua)
    ca.subscription_ends_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    assert client.get(EXPORT, headers={'X-API-Key': raw}).status_code == 402
    ca.subscription_ends_at = None
    ca.is_active = False
    db.flush()
    assert client.get(EXPORT, headers={'X-API-Key': raw}).status_code == 403
    ca.is_active = True
    db.flush()
    assert client.get(EXPORT, headers={'X-API-Key': raw}).status_code == 200


def test_key_does_not_work_on_other_endpoints(client, db, mk):
    ca, _, _, ua = mk.tenant()
    raw, _ = _raw_key(db, ca, ua)
    h = {'X-API-Key': raw}
    for url in ('/api/sales/', '/api/reports/daily-sales', '/api/reports/top-products', '/api/api-keys/'):
        assert client.get(url, headers=h).status_code in (401, 403), url


def test_last_used_at_updated_once_in_five_minutes(client, db, mk):
    ca, _, _, ua = mk.tenant()
    raw, rec = _raw_key(db, ca, ua)
    assert rec.last_used_at is None
    assert client.get(EXPORT, headers={'X-API-Key': raw}).status_code == 200
    db.refresh(rec)
    first = rec.last_used_at
    assert first is not None
    for _ in range(9):
        assert client.get(EXPORT, headers={'X-API-Key': raw}).status_code == 200
    db.refresh(rec)
    assert rec.last_used_at == first
    # 5 daqiqadan eski bo'lsa — yangilanadi
    old = datetime.utcnow() - timedelta(minutes=6)
    rec.last_used_at = old
    db.flush()
    assert client.get(EXPORT, headers={'X-API-Key': raw}).status_code == 200
    db.refresh(rec)
    assert rec.last_used_at > old + timedelta(minutes=5)


# ── 1c-export: JWT oldingidek ────────────────────────────────────────────────

def test_export_jwt_roles_unchanged(client, db, mk):
    ca, ba, wa, ua = mk.tenant()
    cb, _, wb, ub = mk.tenant()
    sa = _sale(db, ca, wa, ua)
    _sale(db, cb, wb, ub)
    r = client.get(EXPORT, headers=_jwt(ua))
    assert r.status_code == 200 and _csv_numbers(r) == [sa.number]
    cashier = mk.user(ca, role=UserRole.cashier, branch=ba)
    assert client.get(EXPORT, headers=_jwt(cashier)).status_code == 403
    for role in (UserRole.director, UserRole.accountant, UserRole.manager):
        u = mk.user(ca, role=role, branch=ba)
        assert client.get(EXPORT, headers=_jwt(u)).status_code == 200, role


def test_new_key_end_to_end(client, db, mk):
    """Yaratilgan kalit (router orqali) darhol 1c-export bilan ishlaydi."""
    ca, _, wa, ua = mk.tenant()
    s = _sale(db, ca, wa, ua)
    token = client.login(ua).post(KEYS, json={'name': '1C'}).json()['token']
    r = client.get(EXPORT, headers={'X-API-Key': token})
    assert r.status_code == 200 and _csv_numbers(r) == [s.number]
