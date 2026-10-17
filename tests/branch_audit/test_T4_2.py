"""T4.2 — Filial sozlamalari va fiskal rekvizitlar.

Qamrov (qabul mezonlari):
 1. STIR: 8/10 xonali -> 422; 9 va 14 xonali saqlanadi. tax_regime, working_hours validatsiyasi.
 2. Filial kodi korxona ichida noyob (katta-kichik harfsiz) -> 409; boshqa korxonada ruxsat.
 3. PATCH `exclude_unset`: null yuborilsa maydon bo'shaydi, yuborilmagani o'zgarmaydi.
 4. Boshqa korxona filiali -> 404 (PATCH, receipt_templates).
 5. Filial chek shablonlari: PUT (admin/director), GET (kassir ham), bo'sh = NULL (korxona shabloni).
 6. SaleOut / receipt javobida branch_legal_name, branch_stir, branch_address, branch_phone.
 7. PATCH /sales/{id}/fiscal fiscal_factory_id ni saqlaydi.
 8. GET /fiscal/coverage: filial va modul bo'yicha fiskallangan/fiskallanmagan, qaytarish hujjatlari alohida;
    GET /fiscal/unfiscalized; rol va korxona izolyatsiyasi.
 9. QQS belgilanmagan mahsulot uchun ogohlantirish logi (xatti-harakat o'zgarmaydi).
 + migratsiya <-> model mosligi, i18n pending kalitlari.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T4_2.py -q -p no:cacheprovider
"""
import itertools
import json
import logging
import os
import py_compile
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.branch import Branch
from app.models.fiscal_device import FiscalDevice
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole

_seq = itertools.count(1)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _product(db, company):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T42-{n}", barcode=f"B42-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _sale(db, user, company, warehouse, branch=None, refund=False, fiscal=None, with_item=None, status=None):
    """fiscal: factory_id -> fiscal_sign + fiscal_factory_id yoziladi; None -> fiskallanmagan."""
    n = next(_seq)
    s = Sale(number=f"{'R' if refund else 'S'}T42-{n}", cashier_id=user.id, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None, branch_id=branch.id if branch else None,
             total_amount=Decimal(1000), paid_amount=Decimal(1000), payment_type=PaymentType.cash,
             status=status or (SaleStatus.refunded if refund else SaleStatus.completed))
    if fiscal:
        s.fiscal_sign = f"SIGN{n}"
        s.fiscal_factory_id = fiscal
        s.fiscal_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(s)
    db.flush()
    if with_item is not None:
        db.add(SaleItem(sale_id=s.id, product_id=with_item.id, quantity=Decimal(1), unit_price=Decimal(1000),
                        cost_price=Decimal(500), subtotal=Decimal(1000), currency_code="UZS", exchange_rate=1))
        db.flush()
    return s


def _two(mk):
    """Ikki korxona: (A tenant, B tenant)."""
    return mk.tenant(), mk.tenant()


@pytest.fixture(autouse=True)
def _no_tariff_limit(monkeypatch):
    """Sinov tarifi 1 ta filialga ruxsat beradi; bu testlar tarif limitini emas, rekvizitlarni tekshiradi."""
    from app.routers import branches as branches_router
    monkeypatch.setattr(branches_router, 'check_branch_limit', lambda *a, **k: None)


def _post_branch(client, user, **body):
    body.setdefault('name', f'Yangi filial {next(_seq)}')
    body.setdefault('create_warehouse', False)
    body.setdefault('create_wallet', False)
    return client.login(user).post('/api/branches', json=body)


# ── 1. STIR / soliq rejimi / ish vaqti validatsiyasi ─────────────────────────

@pytest.mark.parametrize('stir', ['12345678', '1234567890', '12345678901234567', 'abcdefghi', '12345 789'])
def test_stir_wrong_length_or_chars_422(mk, client, stir):
    _, _, _, admin = mk.tenant()
    assert _post_branch(client, admin, stir=stir).status_code == 422


@pytest.mark.parametrize('stir', ['123456789', '12345678901234'])
def test_stir_9_and_14_saved(mk, client, db, stir):
    _, _, _, admin = mk.tenant()
    r = _post_branch(client, admin, stir=stir, legal_name='  Andijon YaTT  ', tax_regime='turnover')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['stir'] == stir
    assert body['legal_name'] == 'Andijon YaTT'
    assert body['tax_regime'] == 'turnover'
    assert db.get(Branch, body['id']).stir == stir


def test_stir_validated_on_patch_too(mk, client):
    _, b, _, admin = mk.tenant()
    c = client.login(admin)
    assert c.patch(f'/api/branches/{b.id}', json={'stir': '12345678'}).status_code == 422
    r = c.patch(f'/api/branches/{b.id}', json={'stir': '123456789'})
    assert r.status_code == 200 and r.json()['stir'] == '123456789'


def test_tax_regime_allowed_values(mk, client):
    _, b, _, admin = mk.tenant()
    c = client.login(admin)
    assert c.patch(f'/api/branches/{b.id}', json={'tax_regime': 'xyz'}).status_code == 422
    for ok in ('vat', 'turnover'):
        r = c.patch(f'/api/branches/{b.id}', json={'tax_regime': ok})
        assert r.status_code == 200 and r.json()['tax_regime'] == ok


def test_working_hours_validation_and_save(mk, client):
    _, b, _, admin = mk.tenant()
    c = client.login(admin)
    good = {'mon': {'open': '09:00', 'close': '18:00', 'closed': False}, 'sun': {'closed': True}}
    r = c.patch(f'/api/branches/{b.id}', json={'working_hours': good})
    assert r.status_code == 200, r.text
    assert r.json()['working_hours']['mon'] == {'open': '09:00', 'close': '18:00', 'closed': False}
    assert r.json()['working_hours']['sun']['closed'] is True
    for bad in ({'xxx': {'open': '09:00', 'close': '18:00'}},
                {'mon': {'open': '9am', 'close': '18:00'}},
                {'mon': {'open': '19:00', 'close': '18:00'}},
                ['mon']):
        assert c.patch(f'/api/branches/{b.id}', json={'working_hours': bad}).status_code == 422


# ── 2. Kod noyobligi ─────────────────────────────────────────────────────────

def test_code_unique_per_company_case_insensitive(mk, client):
    (ca, ba, _, adm_a), (cb, bb, _, adm_b) = _two(mk)
    assert _post_branch(client, adm_a, code='AND-01').status_code == 200
    r = _post_branch(client, adm_a, code='and-01')
    assert r.status_code == 409
    # boshqa korxonada shu kod ruxsat
    assert _post_branch(client, adm_b, code='AND-01').status_code == 200
    # PATCH orqali to'qnashuv
    other = mk.branch(ca)
    r = client.login(adm_a).patch(f'/api/branches/{other.id}', json={'code': 'And-01'})
    assert r.status_code == 409
    # o'z kodini qayta yuborish to'qnashuv emas
    r = client.login(adm_a).patch(f'/api/branches/{other.id}', json={'code': 'XYZ'})
    assert r.status_code == 200
    r = client.login(adm_a).patch(f'/api/branches/{other.id}', json={'code': 'XYZ'})
    assert r.status_code == 200


def test_blank_code_not_unique_restricted(mk, client):
    _, _, _, admin = mk.tenant()
    assert _post_branch(client, admin, code='').status_code == 200
    assert _post_branch(client, admin, code='   ').status_code == 200
    assert _post_branch(client, admin).status_code == 200


# ── 3. exclude_unset: maydonni bo'shatish ────────────────────────────────────

def test_patch_can_clear_field_and_keeps_unsent(mk, client):
    _, b, _, admin = mk.tenant()
    c = client.login(admin)
    r = c.patch(f'/api/branches/{b.id}', json={'stir': '123456789', 'legal_name': 'MCHJ', 'address': 'Toshkent'})
    assert r.status_code == 200
    r = c.patch(f'/api/branches/{b.id}', json={'stir': None})
    assert r.status_code == 200
    body = r.json()
    assert body['stir'] is None
    assert body['legal_name'] == 'MCHJ' and body['address'] == 'Toshkent'   # yuborilmagani o'zgarmadi
    r = c.patch(f'/api/branches/{b.id}', json={'legal_name': ''})           # bo'sh satr ham bo'shatadi
    assert r.json()['legal_name'] is None and r.json()['address'] == 'Toshkent'


# ── 4. Korxona izolyatsiyasi ─────────────────────────────────────────────────

def test_other_company_branch_404(mk, client):
    (ca, ba, _, adm_a), (cb, bb, _, adm_b) = _two(mk)
    c = client.login(adm_a)
    assert c.patch(f'/api/branches/{bb.id}', json={'stir': '123456789'}).status_code == 404
    assert c.get(f'/api/branches/{bb.id}/receipt_templates').status_code == 404
    assert c.put(f'/api/branches/{bb.id}/receipt_templates', json={'r80': {'company': 'x'}}).status_code == 404
    # o'z filiali ishlaydi
    assert c.get(f'/api/branches/{ba.id}/receipt_templates').status_code == 200


# ── 5. Filial chek shablonlari ───────────────────────────────────────────────

def test_branch_receipt_templates_roundtrip(mk, client, db):
    c_, b, _, admin = mk.tenant()
    r = client.login(admin).get(f'/api/branches/{b.id}/receipt_templates')
    assert r.status_code == 200 and r.json()['receipt_templates'] == {}      # bo'sh = korxona shabloni
    body = {'r58': {}, 'r80': {'company': 'Filial MCHJ', 'show_branch': True}, 'nak': {}}
    r = client.login(admin).put(f'/api/branches/{b.id}/receipt_templates', json=body)
    assert r.status_code == 200, r.text
    assert r.json()['receipt_templates'] == {'r80': {'company': 'Filial MCHJ', 'show_branch': True}}
    assert db.get(Branch, b.id).receipt_templates['r80']['company'] == 'Filial MCHJ'
    r = client.login(admin).get(f'/api/branches/{b.id}/receipt_templates')
    assert r.json()['receipt_templates']['r80']['company'] == 'Filial MCHJ'
    assert r.json()['branch']['id'] == b.id
    # ro'yxatda faqat bayroq
    lst = client.login(admin).get('/api/branches').json()
    assert [x for x in lst if x['id'] == b.id][0]['has_receipt_templates'] is True
    # bo'shatish -> NULL
    r = client.login(admin).put(f'/api/branches/{b.id}/receipt_templates', json={'r58': {}, 'r80': {}, 'nak': {}})
    assert r.status_code == 200 and r.json()['receipt_templates'] == {}
    db.expire_all()
    assert db.get(Branch, b.id).receipt_templates is None


def test_branch_receipt_templates_roles_and_validation(mk, client):
    c_, b, _, admin = mk.tenant()
    cashier = mk.user(c_, role=UserRole.cashier, branch=b)
    # kassir o'qiydi (POS), yoza olmaydi
    assert client.login(cashier).get(f'/api/branches/{b.id}/receipt_templates').status_code == 200
    assert client.login(cashier).put(f'/api/branches/{b.id}/receipt_templates', json={'r80': {}}).status_code == 403
    director = mk.user(c_, role=UserRole.director)
    assert client.login(director).put(f'/api/branches/{b.id}/receipt_templates',
                                      json={'r80': {'company': 'X'}}).status_code == 200
    r = client.login(admin).put(f'/api/branches/{b.id}/receipt_templates', json={'r80': {'noma_lum_kalit': 1}})
    assert r.status_code == 422


# ── 6. Sotuv javobida filial rekvizitlari ────────────────────────────────────

def test_sale_out_has_branch_requisites(mk, client, db):
    c, b, wh, admin = mk.tenant()
    b.legal_name, b.stir, b.address, b.phone = 'Chilonzor MCHJ', '123456789', 'Chilonzor 5', '+998901112233'
    db.flush()
    p = _product(db, c)
    s = _sale(db, admin, c, wh, branch=b, with_item=p)
    cl = client.login(admin)
    out = cl.get(f'/api/sales/{s.id}').json()
    assert out['branch_name'] == b.name
    assert out['branch_legal_name'] == 'Chilonzor MCHJ'
    assert out['branch_stir'] == '123456789'
    assert out['branch_address'] == 'Chilonzor 5' and out['branch_phone'] == '+998901112233'
    rc = cl.get(f'/api/sales/{s.id}/receipt').json()
    assert rc['branch_legal_name'] == 'Chilonzor MCHJ' and rc['branch_stir'] == '123456789'
    assert rc['branch_name'] == b.name


def test_sale_out_branch_from_warehouse_when_no_snapshot(mk, client, db):
    c, b, wh, admin = mk.tenant()
    b.stir = '12345678901234'
    db.flush()
    s = _sale(db, admin, c, wh, branch=None, with_item=_product(db, c))
    s.branch_id = None
    db.flush()
    db.expire(s)
    out = client.login(admin).get(f'/api/sales/{s.id}').json()
    assert out['branch_stir'] == '12345678901234'


# ── 7. PATCH /sales/{id}/fiscal -> fiscal_factory_id ─────────────────────────

def test_patch_sale_fiscal_saves_factory_id(mk, client, db):
    c, b, wh, admin = mk.tenant()
    s = _sale(db, admin, c, wh, branch=b, with_item=_product(db, c))
    r = client.login(admin).patch(f'/api/sales/{s.id}/fiscal',
                                  json={'fiscal_sign': 'ABC123', 'fiscal_factory_id': 'HP-001'})
    assert r.status_code == 200, r.text
    assert r.json()['fiscal_factory_id'] == 'HP-001'
    db.expire_all()
    assert db.get(Sale, s.id).fiscal_factory_id == 'HP-001'


# ── 8. Fiskal qamrov hisoboti ────────────────────────────────────────────────

def _coverage_setup(mk, db):
    c, b1, w1, admin = mk.tenant()
    b2 = mk.branch(c, name='Ikkinchi filial')
    w2 = mk.warehouse(c, b2)
    db.add(FiscalDevice(company_id=c.id, branch_id=b1.id, factory_id='HP-1', label='Kassa 1', is_active=True))
    db.flush()
    # b1: 3 sotuv (2 ta HP-1 da fiskallangan, 1 ta yo'q) + 1 qaytarish hujjati (hisobga olinmaydi)
    _sale(db, admin, c, w1, b1, fiscal='HP-1')
    _sale(db, admin, c, w1, b1, fiscal='HP-1')
    _sale(db, admin, c, w1, b1)
    _sale(db, admin, c, w1, b1, refund=True)
    # b2: 2 sotuv, ikkalasi fiskallanmagan; bekor qilingan sotuv hisoblanmaydi
    _sale(db, admin, c, w2, b2)
    _sale(db, admin, c, w2, b2)
    _sale(db, admin, c, w2, b2, status=SaleStatus.cancelled)
    return c, b1, b2, admin


def test_coverage_counts_by_branch_and_terminal(mk, client, db):
    c, b1, b2, admin = _coverage_setup(mk, db)
    r = client.login(admin).get('/api/fiscal/coverage')
    assert r.status_code == 200, r.text
    rows = r.json()
    by = {(x['branch_id'], x['factory_id']): x for x in rows}
    fisc = by[(b1.id, 'HP-1')]
    assert (fisc['total_sales'], fisc['fiscalized'], fisc['unfiscalized']) == (2, 2, 0)
    assert fisc['terminal_id'] is not None and fisc['branch_name'] == b1.name
    nof = by[(b1.id, None)]
    assert (nof['total_sales'], nof['fiscalized'], nof['unfiscalized']) == (1, 0, 1)
    assert nof['terminal_id'] is None
    assert nof['returns'] == 1                       # qaytarish hujjati alohida
    other = by[(b2.id, None)]
    assert (other['total_sales'], other['fiscalized'], other['unfiscalized']) == (2, 0, 2)
    # jami fiskallanmagan sotuv = 3 (qaytarish va bekor qilingan kirmaydi)
    assert sum(x['unfiscalized'] for x in rows) == 3


def test_coverage_branch_filter_and_foreign_branch(mk, client, db):
    c, b1, b2, admin = _coverage_setup(mk, db)
    _, bb, _, adm_b = mk.tenant()
    rows = client.login(admin).get('/api/fiscal/coverage', params={'branch_id': b2.id}).json()
    assert {x['branch_id'] for x in rows} == {b2.id}
    assert client.login(admin).get('/api/fiscal/coverage', params={'branch_id': bb.id}).status_code == 404


def test_coverage_date_filter(mk, client, db):
    c, b1, b2, admin = _coverage_setup(mk, db)
    rows = client.login(admin).get('/api/fiscal/coverage',
                                   params={'date_from': '2000-01-01', 'date_to': '2000-01-02'}).json()
    assert rows == []
    assert client.login(admin).get('/api/fiscal/coverage', params={'date_from': 'xx'}).status_code == 400


def test_coverage_company_isolation_and_roles(mk, client, db):
    c, b1, b2, admin = _coverage_setup(mk, db)
    cb, bb, wb, adm_b = mk.tenant()
    assert client.login(adm_b).get('/api/fiscal/coverage').json() == []          # A ma'lumoti B ga ko'rinmaydi
    assert client.login(adm_b).get('/api/fiscal/unfiscalized').json() == []
    cashier = mk.user(c, role=UserRole.cashier, branch=b1)
    assert client.login(cashier).get('/api/fiscal/coverage').status_code == 403
    assert client.login(cashier).get('/api/fiscal/unfiscalized').status_code == 403
    acc = mk.user(c, role=UserRole.accountant)
    assert client.login(acc).get('/api/fiscal/coverage').status_code == 200
    director = mk.user(c, role=UserRole.director)
    assert client.login(director).get('/api/fiscal/unfiscalized').status_code == 200


def test_unfiscalized_list(mk, client, db):
    c, b1, b2, admin = _coverage_setup(mk, db)
    cl = client.login(admin)
    r = cl.get('/api/fiscal/unfiscalized')
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3 and r.headers['X-Total-Count'] == '3'
    assert all(i['number'].startswith('S') for i in items)             # qaytarish hujjati yo'q
    only_b2 = cl.get('/api/fiscal/unfiscalized', params={'branch_id': b2.id}).json()
    assert len(only_b2) == 2 and {i['branch_id'] for i in only_b2} == {b2.id}
    page = cl.get('/api/fiscal/unfiscalized', params={'skip': 1, 'limit': 1})
    assert len(page.json()) == 1 and page.headers['X-Total-Count'] == '3'


# ── 9. QQS belgilanmagan mahsulot: ogohlantirish (xatti-harakat o'zgarmaydi) ─

def test_vat_none_warns_but_keeps_12(caplog):
    from app.services import hippo_fiscalize
    p = Product(id=7, name='QQSsiz', vat_rate_type=None)
    with caplog.at_level(logging.WARNING, logger='hippo.fiscalize'):
        assert hippo_fiscalize._vat_percent(p) == 12
    assert any('vat_rate_type belgilanmagan' in r.getMessage() for r in caplog.records)


# ── Migratsiya <-> model ─────────────────────────────────────────────────────

def test_migration_matches_model():
    path = os.path.join(ROOT, 'alembic', 'versions', 't4_2_branch_settings.py')
    py_compile.compile(path, doraise=True)
    src = open(path, encoding='utf-8').read()
    assert "revision = 't4_2'" in src and "down_revision = 't4_1'" in src
    for col in ('code', 'legal_name', 'stir', 'tax_regime', 'working_hours', 'receipt_templates'):
        assert f"'{col}'" in src
        assert col in Branch.__table__.c
    assert 'uq_branches_company_code' in src
    assert any(i.name == 'uq_branches_company_code' for i in Branch.__table__.indexes)


# ── i18n pending kalitlari ───────────────────────────────────────────────────

def test_i18n_pending_keys():
    import re
    pend = json.load(open(os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T4.2.json'), encoding='utf-8'))
    assert set(pend) == {'uz', 'ru', 'en'}
    assert set(pend['uz']) == set(pend['ru']) == set(pend['en'])
    assert all(v.strip() for lang in pend.values() for v in lang.values())
    # yakuniy birlashtirishdan keyin: kalitlar uchala lug'atda bor
    for lang in ('uz', 'ru', 'en'):
        existing = open(os.path.join(ROOT, 'frontend', 'src', 'i18n', f'{lang}.js'), encoding='utf-8').read()
        assert not [k for k in pend['uz'] if f"'{k}'" not in existing]
    # komponentlarda ishlatilgan tf('...') kalitlari pending faylda bor
    used = set()
    for rel in ('pages/admin/FiscalCoverage.jsx', 'pages/admin/Settings.jsx'):
        src = open(os.path.join(ROOT, 'frontend', 'src', *rel.split('/')), encoding='utf-8').read()
        used |= set(re.findall(r"tf\('((?:fiscalCoverage|branchSettings)\.[A-Za-z.]+)'", src))
    used |= {f'branchSettings.day.{d}' for d in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')}
    assert used and used <= set(pend['uz']), used - set(pend['uz'])
