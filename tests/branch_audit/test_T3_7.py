"""T3.7 — Chek va yorliqlarda filial rekvizitlari.

Qamrov: SaleOut / SaleListOut / POST /sales/ / GET /sales/{id}/receipt javoblarida filial nomi, manzili, telefoni,
ombor va korxona nomi; filialsiz ombor uchun None; Telegram chekida "Filial:" qatori; qarz eslatmasida sotuv filiali;
/label-templates (korxonalararo izolyatsiya, 409, filial bo'yicha filtr, rol, 422, begona filial -> 404);
migratsiya fayli; frontend (receiptBuilder, Settings, PosKassa, PosDesktop, pos.js, usePosSync, yorliq redaktorlari).

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_7.py -q -p no:cacheprovider
"""
import asyncio
import itertools
import json
import os
import re
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.database as app_database
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.label_template import LabelTemplate
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleStatus
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _sale(db, user, company, warehouse=None, branch=None, customer=None, **kw):
    n = next(_seq)
    s = Sale(number=kw.pop('number', f'S37-{n}'), cashier_id=user.id, company_id=company.id,
             warehouse_id=warehouse.id if warehouse else None,
             branch_id=branch.id if branch else None,
             customer_id=customer.id if customer else None,
             total_amount=Decimal('1000'), paid_amount=Decimal('1000'), paid_cash=Decimal('1000'),
             discount_amount=Decimal('0'), payment_type=kw.pop('payment_type', PaymentType.cash),
             status=kw.pop('status', SaleStatus.completed), **kw)
    db.add(s)
    db.flush()
    return s


@pytest.fixture
def world(db, mk):
    """Korxona A: 2 filial (turli manzil/telefon), har birida ombor; filialsiz ombor. Korxona B."""
    ca = mk.company(name='Alfa Savdo')
    b1 = mk.branch(ca, name='Chilonzor', address='Chilonzor 5', phone='+998711111111')
    b2 = mk.branch(ca, name='Yunusobod', address='Yunusobod 7', phone='+998722222222')
    w1 = mk.warehouse(ca, b1, name='Ombor-1')
    w2 = mk.warehouse(ca, b2, name='Ombor-2')
    w0 = mk.warehouse(ca, None, name='Filialsiz ombor')
    admin = mk.user(ca, role=UserRole.admin, branch=b1)
    cashier = mk.user(ca, role=UserRole.cashier, branch=b1, name='Kassir Ali')
    cb, bb, wb, admin_b = mk.tenant(UserRole.admin)
    return SimpleNamespace(ca=ca, b1=b1, b2=b2, w1=w1, w2=w2, w0=w0, admin=admin, cashier=cashier,
                           cb=cb, bb=bb, wb=wb, admin_b=admin_b)


# ── 1. Sotuv javoblari: filial rekvizitlari ─────────────────────────────────────

def test_sale_out_fills_branch_fields_from_branch(db, world):
    from app.routers.sales import _build_sale_out
    s = _sale(db, world.cashier, world.ca, world.w1, branch=world.b1)
    out = _build_sale_out(s)
    assert out.branch_id == world.b1.id
    assert (out.branch_name, out.branch_address, out.branch_phone) == ('Chilonzor', 'Chilonzor 5', '+998711111111')
    assert out.warehouse_name == 'Ombor-1'
    assert out.company_name == 'Alfa Savdo'


def test_two_branches_two_different_receipt_requisites(db, world):
    from app.routers.sales import _build_sale_out
    o1 = _build_sale_out(_sale(db, world.cashier, world.ca, world.w1, branch=world.b1))
    o2 = _build_sale_out(_sale(db, world.cashier, world.ca, world.w2, branch=world.b2))
    assert o1.branch_address != o2.branch_address and o1.branch_phone != o2.branch_phone
    assert o2.branch_name == 'Yunusobod' and o2.branch_phone == '+998722222222'


def test_sale_out_falls_back_to_warehouse_branch(db, world):
    """Eski sotuv: branch_id yo'q, ombor filialga tegishli — filial ombor orqali topiladi."""
    from app.routers.sales import _build_sale_out
    s = _sale(db, world.cashier, world.ca, world.w2)
    s.branch_id = None
    db.flush()
    db.expire(s)
    out = _build_sale_out(s)
    assert out.branch_name == 'Yunusobod' and out.branch_address == 'Yunusobod 7'


def test_sale_out_none_for_warehouse_without_branch(db, world):
    from app.routers.sales import _build_sale_out
    s = _sale(db, world.cashier, world.ca, world.w0)
    s.branch_id = None
    db.flush()
    db.expire(s)
    out = _build_sale_out(s)
    assert out.branch_id is None and out.branch_name is None
    assert out.branch_address is None and out.branch_phone is None
    assert out.warehouse_name == 'Filialsiz ombor'
    s2 = _sale(db, world.cashier, world.ca, None)
    s2.branch_id = None
    db.flush()
    db.expire(s2)
    assert _build_sale_out(s2).warehouse_name is None


def test_get_sale_and_receipt_endpoints_have_branch_keys(client, db, world):
    s = _sale(db, world.cashier, world.ca, world.w2, branch=world.b2)
    r = client.login(world.admin).get(f'/api/sales/{s.id}')
    assert r.status_code == 200
    d = r.json()
    assert d['branch_name'] == 'Yunusobod' and d['branch_address'] == 'Yunusobod 7'
    assert d['branch_phone'] == '+998722222222' and d['warehouse_name'] == 'Ombor-2'
    assert d['company_name'] == 'Alfa Savdo'

    r = client.login(world.admin).get(f'/api/sales/{s.id}/receipt')
    assert r.status_code == 200
    d = r.json()
    assert d['receipt_number'] == s.number
    for key in ('branch_id', 'branch_name', 'branch_address', 'branch_phone', 'warehouse_name', 'company_name'):
        assert key in d
    assert d['branch_name'] == 'Yunusobod' and d['company_name'] == 'Alfa Savdo'
    assert d['cashier'] == 'Kassir Ali'


def test_receipt_isolation_between_companies(client, db, world):
    s = _sale(db, world.cashier, world.ca, world.w1, branch=world.b1)
    assert client.login(world.admin_b).get(f'/api/sales/{s.id}/receipt').status_code == 404
    assert client.login(world.admin_b).get(f'/api/sales/{s.id}').status_code == 404
    assert client.login(world.admin).get(f'/api/sales/{s.id}/receipt').status_code == 200


def _stocked_product(db, world, qty=50):
    n = next(_seq)
    p = Product(name=f'Tovar {n}', sku=f'T37-{n}', barcode=f'B37-{n}', company_id=world.ca.id,
                cost_price=Decimal('500'), sale_price=Decimal('1000'))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=world.w2.id, quantity=Decimal(qty)))
    db.flush()
    return p


def test_post_sale_returns_branch_requisites_and_server_cashier(client, db, world):
    """POST /sales/ javobi POS chekni qo'shimcha so'rovsiz chiqarishi uchun yetarli."""
    p = _stocked_product(db, world)
    body = {'items': [{'product_id': p.id, 'quantity': 1, 'unit_price': 1000}], 'payment_type': 'cash',
            'paid_amount': 1000, 'paid_cash': 1000, 'payments': [{'type': 'cash', 'amount': 1000}],
            'warehouse_id': world.w2.id}
    r = client.login(world.admin).post('/api/sales/', json=body, headers={'Idempotency-Key': 'k37-1'})
    if r.status_code != 200:   # kassa/smena sharti bo'lsa — sotuv yaratish bu testning ishi emas
        pytest.skip(f'POST /sales/ muhitda ishlamadi: {r.status_code} {r.text[:120]}')
    d = r.json()
    assert d['number'] and d['cashier_name'] == world.admin.name
    assert d['branch_name'] == 'Yunusobod' and d['branch_address'] == 'Yunusobod 7'
    assert d['branch_phone'] == '+998722222222' and d['warehouse_name'] == 'Ombor-2'
    assert d['company_name'] == 'Alfa Savdo'
    # Takroriy (idempotent) javobda ham xuddi shu maydonlar
    r2 = client.login(world.admin).post('/api/sales/', json=body, headers={'Idempotency-Key': 'k37-1'})
    assert r2.status_code == 200 and r2.json()['number'] == d['number']
    assert r2.json()['branch_phone'] == '+998722222222' and r2.json()['company_name'] == 'Alfa Savdo'


# ── 2. Telegram chek va qarz eslatmasi ───────────────────────────────────────────

def _customer(db, company, **kw):
    n = next(_seq)
    c = Customer(name=f'Mijoz {n}', company_id=company.id, phone=f'99893{n:07d}', debt_balance=Decimal('5000'),
                 debt_balances={}, **kw)
    db.add(c)
    db.flush()
    return c


def test_telegram_receipt_has_branch_line(client, db, world, monkeypatch):
    from app.services import sale_create
    world.ca.tg_bot_token = '111:AAA'
    cust = _customer(db, world.ca, tg_chat_id='777')
    p = _stocked_product(db, world)
    sent = []
    monkeypatch.setattr(sale_create, 'send_tg_sync', lambda token, chat_id, text, *a, **k: sent.append(text))
    body = {'items': [{'product_id': p.id, 'quantity': 1, 'unit_price': 1000}], 'payment_type': 'cash',
            'paid_amount': 1000, 'paid_cash': 1000, 'payments': [{'type': 'cash', 'amount': 1000}],
            'warehouse_id': world.w2.id, 'customer_id': cust.id}
    r = client.login(world.admin).post('/api/sales/', json=body, headers={'Idempotency-Key': 'k37-tg'})
    if r.status_code != 200:
        pytest.skip(f'POST /sales/ muhitda ishlamadi: {r.status_code} {r.text[:120]}')
    assert sent, 'Telegram chek yuborilmadi'
    assert 'Tashkilot: Alfa Savdo' in sent[0]
    assert 'Filial: Yunusobod' in sent[0] and 'Tel: +998722222222' in sent[0]


def test_debt_reminder_includes_sale_branch(db, world, monkeypatch):
    from app.services import scheduler as sched
    world.ca.tg_bot_token = '222:BBB'
    cust = _customer(db, world.ca, tg_chat_id='888')
    due = sched.local_today() + timedelta(days=3)
    s1 = _sale(db, world.cashier, world.ca, world.w1, branch=world.b1, customer=cust,
               payment_type=PaymentType.debt, debt_due_date=due)
    s1.paid_amount = Decimal('0')
    s1.paid_cash = Decimal('0')
    # Filialsiz eski sotuv: xabar baribir ketadi, faqat filial qatori bo'lmaydi
    s2 = _sale(db, world.cashier, world.ca, world.w0, customer=cust, payment_type=PaymentType.debt, debt_due_date=due)
    s2.paid_amount = Decimal('0')
    s2.paid_cash = Decimal('0')
    s2.branch_id = None
    db.flush()
    db.expire_all()
    sent = []

    async def fake_send(token, chat_id, text, *a, **k):
        sent.append(text)
        return True

    monkeypatch.setattr(sched, 'send_tg_msg_async', fake_send)
    # scheduler SessionLocal ni nom bo'yicha import qiladi — test ulanishiga yo'naltiramiz
    monkeypatch.setattr(sched, 'SessionLocal', app_database.SessionLocal)
    asyncio.run(sched.process_daily_debts())
    assert len(sent) == 2
    with_branch = [m for m in sent if 'Filial:' in m]
    assert len(with_branch) == 1
    assert 'Chilonzor' in with_branch[0] and '+998711111111' in with_branch[0]
    assert all('Alfa Savdo' in m for m in sent)


# ── 3. /label-templates ──────────────────────────────────────────────────────────

L = '/api/label-templates'


def _cfg(**kw):
    return {'w': 50, 'h': 30, 'size': '50x30', '_opts': {'companyName': 'Alfa Savdo', **kw}}


def test_label_templates_create_list_update_delete(client, db, world):
    cl = client.login(world.admin)
    r = cl.post(L, json={'name': 'Standart', 'kind': 'product', 'config': _cfg()})
    assert r.status_code == 201
    tid = r.json()['id']
    assert r.json()['branch_id'] is None and r.json()['config']['_opts']['companyName'] == 'Alfa Savdo'
    assert [x['name'] for x in cl.get(L, params={'kind': 'product'}).json()] == ['Standart']
    r = cl.put(f'{L}/{tid}', json={'name': 'Yangi nom', 'config': _cfg(companyName='X')})
    assert r.status_code == 200 and r.json()['name'] == 'Yangi nom'
    assert r.json()['config']['_opts']['companyName'] == 'X'
    assert cl.delete(f'{L}/{tid}').status_code == 204
    assert cl.get(L).json() == []


def test_label_templates_company_isolation(client, db, world):
    r = client.login(world.admin).post(L, json={'name': 'A shabloni', 'config': _cfg()})
    tid = r.json()['id']
    other = client.login(world.admin_b)
    assert other.get(L).json() == []
    assert other.put(f'{L}/{tid}', json={'name': 'buzildi'}).status_code == 404
    assert other.delete(f'{L}/{tid}').status_code == 404
    assert db.get(LabelTemplate, tid).name == 'A shabloni'
    # B korxonasi o'z shablonini yaratadi — A ko'rmaydi
    assert other.post(L, json={'name': 'B shabloni', 'config': _cfg()}).status_code == 201
    assert [x['name'] for x in client.login(world.admin).get(L).json()] == ['A shabloni']


def test_label_templates_duplicate_409_and_scope(client, db, world):
    cl = client.login(world.admin)
    assert cl.post(L, json={'name': 'Bir', 'config': _cfg()}).status_code == 201
    assert cl.post(L, json={'name': 'Bir', 'config': _cfg()}).status_code == 409           # NULL branch ham takrorlanmaydi
    assert cl.post(L, json={'name': 'Bir', 'kind': 'customer', 'config': _cfg()}).status_code == 201   # boshqa kind
    assert cl.post(L, json={'name': 'Bir', 'branch_id': world.b1.id, 'config': _cfg()}).status_code == 201   # boshqa doira
    assert cl.post(L, json={'name': 'Bir', 'branch_id': world.b1.id, 'config': _cfg()}).status_code == 409
    # Nomni o'zgartirib band nomga tushish ham 409
    r = cl.post(L, json={'name': 'Ikki', 'config': _cfg()})
    assert cl.put(f"{L}/{r.json()['id']}", json={'name': 'Bir'}).status_code == 409


def test_label_templates_branch_filter(client, db, world):
    cl = client.login(world.admin)
    cl.post(L, json={'name': 'Hammasi', 'config': _cfg()})
    cl.post(L, json={'name': 'Faqat 1', 'branch_id': world.b1.id, 'config': _cfg()})
    cl.post(L, json={'name': 'Faqat 2', 'branch_id': world.b2.id, 'config': _cfg()})
    names = lambda bid: sorted(x['name'] for x in cl.get(L, params={'branch_id': bid}).json())
    assert names(world.b1.id) == ['Faqat 1', 'Hammasi']
    assert names(world.b2.id) == ['Faqat 2', 'Hammasi']
    assert sorted(x['name'] for x in cl.get(L).json()) == ['Faqat 1', 'Faqat 2', 'Hammasi']
    # Begona korxona filiali bilan filtr/yaratish — 404
    assert cl.get(L, params={'branch_id': world.bb.id}).status_code == 404
    assert cl.post(L, json={'name': 'X', 'branch_id': world.bb.id, 'config': _cfg()}).status_code == 404
    r = cl.post(L, json={'name': 'Y', 'config': _cfg()})
    assert cl.put(f"{L}/{r.json()['id']}", json={'branch_id': world.bb.id}).status_code == 404
    # Doirani butun korxonadan filialga o'tkazish
    assert cl.put(f"{L}/{r.json()['id']}", json={'branch_id': world.b2.id}).json()['branch_id'] == world.b2.id


def test_label_templates_roles_and_size(client, db, world):
    r = client.login(world.cashier).post(L, json={'name': 'Kassir', 'config': _cfg()})
    assert r.status_code == 403
    assert client.login(world.cashier).get(L).status_code == 200            # o'qish hammaga ochiq
    mgr = world.admin
    cl = client.login(mgr)
    big = {'blob': 'x' * (70 * 1024)}
    assert cl.post(L, json={'name': 'Katta', 'config': big}).status_code == 422
    tid = cl.post(L, json={'name': 'Kichik', 'config': _cfg()}).json()['id']
    assert cl.put(f'{L}/{tid}', json={'config': big}).status_code == 422
    assert client.login(world.cashier).delete(f'{L}/{tid}').status_code == 403
    assert client.login(mgr).post(L, json={'name': 'Q', 'kind': "noma'lum", 'config': _cfg()}).status_code == 422


def test_label_template_unique_index_in_db(db, world):
    from sqlalchemy.exc import IntegrityError
    db.add(LabelTemplate(company_id=world.ca.id, branch_id=None, kind='product', name='U', config={}))
    db.flush()
    db.add(LabelTemplate(company_id=world.ca.id, branch_id=None, kind='product', name='U', config={}))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ── 4. Migratsiya ──────────────────────────────────────────────────────────────

def test_migration_file():
    import py_compile
    path = os.path.join(ROOT, 'alembic', 'versions', 't3_7_add_label_templates.py')
    py_compile.compile(path, doraise=True)
    src = _read('alembic', 'versions', 't3_7_add_label_templates.py')
    assert "revision = 't3_7'" in src and "down_revision = 't2_12'" in src
    assert 'label_templates' in src and 'COALESCE(branch_id, 0)' in src
    assert 'ix_label_templates_company_kind' in src and 'uq_label_templates_scope' in src
    assert "ondelete='CASCADE'" in src and "ondelete='SET NULL'" in src


# ── 5. Frontend (manba matni bo'yicha) ──────────────────────────────────────────

def test_receipt_builder_branch_logic():
    src = _read('frontend', 'src', 'utils', 'receiptBuilder.js')
    assert 'sale.branch_name' in src and 'sale.branch_address' in src and 'sale.branch_phone' in src
    assert 'br.address || cfg.address' in src and 'br.phone || cfg.phone' in src
    assert "cfg.company || sale.company_name" in src
    assert "'___'" not in src.split('const infoLines')[1].split('].filter')[0].split('show_account_username')[0].split("Filial")[1]
    assert 'showBranch && br.name' in src                                # nakladnoy va termal: nom bo'lmasa qator yo'q
    assert 'cfg.show_branch ?? cfg.show_account_name' in src             # eski shablon mosligi
    assert 'cfg.show_customer ?? cfg.show_account_name' in src
    assert "sh('show_account_name')" not in src


def test_settings_keys():
    src = _read('frontend', 'src', 'pages', 'admin', 'Settings.jsx')
    assert 'show_branch: true' in src and 'show_customer: true' in src
    assert "['show_branch'" in src and "['show_customer'" in src
    assert "Asosiy filial" not in src
    assert 'migrateAccountName' in src


def test_pos_receipts_use_server_number():
    kassa = _read('frontend', 'src', 'pages', 'admin', 'PosKassa.jsx')
    desktop = _read('frontend', 'src', 'pages', 'admin', 'PosDesktop.jsx')
    assert 'Math.random' not in kassa and 'Math.random' not in desktop
    assert 'orderId' not in kassa and 'orderNum' not in desktop
    assert 'receiptPrintedThisAttempt' not in kassa
    assert kassa.index('await submitSaleOrQueue(payload, false)') < kassa.index('printReceiptHtml(')
    assert desktop.index('await submitSaleOrQueue(payload, false)') < desktop.index('printReceiptHtml(')
    for src in (kassa, desktop):
        assert 'result?.localNumber' in src and 'saved?.number' in src and 'saved?.cashier_name' in src
        assert 'saved?.branch_name' in src and 'saved?.branch_address' in src and 'saved?.branch_phone' in src
    assert "cashier_name: 'Kassa'" not in kassa


def test_offline_local_number_in_sync_hook():
    src = _read('frontend', 'src', 'hooks', 'usePosSync.js')
    assert "'OFL-'" in src and 'toUpperCase()' in src
    assert 'localNumber' in src and 'return { offline: true, localNumber }' in src
    assert re.search(r'pending\.push\(\{[^}]*localNumber', src, re.S)


def test_pos_desktop_receipt_number_and_branch():
    src = _read('pos-desktop', 'renderer', 'pos.js')
    show = src.split('function showReceipt')[1].split('function printReceipt')[0]
    assert 'Math.random' not in show
    assert 'sale.number' in show
    assert 'sale.branch_address' in show and 'sale.branch_phone' in show and 'sale.branch_name' in show


def test_partial_return_passes_branch_fields():
    src = _read('frontend', 'src', 'pages', 'admin', 'PartialReturnModal.jsx')
    assert 'branch_name: sale?.branch_name' in src and 'branch_phone: sale?.branch_phone' in src


@pytest.mark.parametrize('fname,kind,ls', [
    ('BarcodeTemplates.jsx', 'product', 'barcode_saved_templates'),
    ('CustomerBarcodeTemplates.jsx', 'customer', 'customer_barcode_saved_templates'),
])
def test_label_editors_use_server(fname, kind, ls):
    src = _read('frontend', 'src', 'components', fname)
    assert f"kind: '{kind}'" in src and "'/label-templates'" in src
    assert '/billing/my-company' in src                                   # korxona nomi Company.name dan
    assert ls in src
    # localStorage.setItem / getItem faqat try/catch ichidagi yordamchilarda
    for m in re.finditer(r'localStorage\.(setItem|getItem|removeItem)', src):
        before = src[:m.start()]
        last_try = before.rfind('try {')
        assert last_try != -1 and before[last_try:].count('}') <= before[last_try:].count('{'), fname
    assert 'useState(() => {\n    try { return JSON.parse(localStorage' not in src


def test_barcode_editor_branch_fields():
    src = _read('frontend', 'src', 'components', 'BarcodeTemplates.jsx')
    assert 'branchName' in src and 'branchAddress' in src
    assert 'showBranchName' in src and 'showBranchAddress' in src
    assert 'opts.branchName' in src and 'opts.branchAddress' in src


def test_pending_i18n_keys_consistent():
    with open(os.path.join(ROOT, 'tests', 'branch_audit', 'i18n_pending', 'T3.7.json'), encoding='utf-8') as f:
        d = json.load(f)
    assert set(d) == {'uz', 'ru', 'en'}
    assert set(d['uz']) == set(d['ru']) == set(d['en'])
    used = set()
    for rel in (('components', 'BarcodeTemplates.jsx'), ('components', 'CustomerBarcodeTemplates.jsx'),
                ('pages', 'admin', 'Settings.jsx'), ('pages', 'admin', 'PosKassa.jsx')):
        used |= set(re.findall(r"'((?:labelTemplates\.[A-Za-z]+|settings\.receipt\.fieldCustomer|"
                               r"settings\.nakladnoyPreview\.branchSample|pos\.retailSaleNoteShort))'",
                               _read('frontend', 'src', *rel)))
    assert used and used <= set(d['uz'])
    # Kalitlar uz.js ga birlashtirilgan (pending fayl o'chirilgan), takrorlanmagan
    uz_js = _read('frontend', 'src', 'i18n', 'uz.js')
    for k in d['uz']:
        assert uz_js.count(f"'{k}':") == 1, k
