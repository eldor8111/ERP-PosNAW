"""C4.4 — Mobil (kuryer/Flutter) va deploy fayllari qoldiqlari.

Qamrov:
  1  CourierRoute.jsx: to'xtov kartochkasida "Olib ketish: filial, manzil" (logistics.pickupBranch);
  2  Cash.jsx: kassa ro'yxatida filial va "(yopiq)", boshqa filial tasdig'i + confirm_other_branch, topshirishni bekor qilish;
     backend shartnomasi (wallets tartibi/maydonlari, 409, bekor qilish, begona korxona 404);
  3-5 deploy: erppos-worker.service, install_worker.sh, deploy_erppos.sh (erppos-worker restart);
  6  edit_product_screen.dart: "Topshirish ombori" dropdown + PUT preferred_warehouse_id;
  7  my_products_screen.dart: "Qabul qilindi: {warehouse_name}".

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_C4_4.py -q -p no:cacheprovider
"""
import itertools
import json
import os
import re
from decimal import Decimal

import pytest

from app.models.moliya import CashTransfer, Wallet
from app.models.user import UserRole
from app.services import cash_service
from app.services.mobile_service import ensure_personal_wallet, personal_cash_balance

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read().replace('\r\n', '\n')


# ───────────────────── 1. CourierRoute.jsx ─────────────────────

def test_courier_route_shows_pickup_branch():
    src = _read('frontend', 'src', 'mobile', 'courier', 'CourierRoute.jsx')
    assert 'stop.pickup_branch_name &&' in src
    assert "t('logistics.pickupBranch')" in src and 'stop.pickup_address' in src
    # manzil qatoridan keyin turadi
    assert src.index('logistics.noAddress') < src.index('stop.pickup_branch_name')


# ───────────────────── 2. Cash.jsx ─────────────────────

def test_cash_screen_branch_closed_confirm_cancel():
    src = _read('frontend', 'src', 'mobile', 'screens', 'Cash.jsx')
    assert 'w.branch_name' in src and "t('m.walletClosedSuffix')" in src and 'w.is_open === false' in src
    assert "window.confirm(t('m.handoverOtherBranch'))" in src
    assert 'confirm_other_branch: true' in src
    assert re.search(r"api\.post\(`/mobile/cash/handover/\$\{id\}/cancel`\)", src)
    assert "t('m.handoverCancel')" in src and 'cancelHandover(h.id)' in src
    # handover hamon offline outbox orqali ketadi
    assert "enqueue({" in src and "url: '/mobile/cash/handover'" in src


def test_outbox_does_not_retry_409():
    """409 (boshqa filial) outbox'da qayta-urinilmaydi: 'failed' bo'lib foydalanuvchiga ko'rinadi."""
    src = _read('frontend', 'src', 'mobile', 'offline', 'outbox.js')
    assert 'status >= 500' in src and 'status === 409' not in src
    assert "state: 'failed'" in src


def test_i18n_keys_exist_in_all_languages():
    keys = ['logistics.pickupBranch', 'm.walletClosedSuffix', 'm.handoverOtherBranch', 'm.handoverCancel']
    for lang in ('uz', 'ru', 'en'):
        src = _read('frontend', 'src', 'i18n', f'{lang}.js')
        for k in keys:
            assert f"'{k}':" in src, (lang, k)
    # yangi kalit kiritilmagan: pending fayl bo'lsa uchala tilda bir xil bo'lsin
    p = os.path.join(ROOT, 'frontend', 'src', 'i18n', 'pending', 'C4.4.json')
    if os.path.exists(p):
        d = json.load(open(p, encoding='utf-8'))
        assert set(d['uz']) == set(d['ru']) == set(d['en'])


def _wallet(db, company, branch=None, *, is_open=True, name=None):
    w = Wallet(name=name or f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"), company_id=company.id,
               branch_id=branch.id if branch else None, is_active=True, is_open=is_open, is_personal=False)
    db.add(w)
    db.flush()
    return w


@pytest.fixture
def env(mk, db):
    a = mk.company("A")
    a1, a2 = mk.branch(a, "Chilonzor"), mk.branch(a, "Yunusobod")
    b = mk.company("B")
    b1 = mk.branch(b, "B filial")
    cu = mk.user(a, role=UserRole.courier, branch=a1)
    w = ensure_personal_wallet(db, cu)
    cash_service.post_cash(db, user=cu, wallet=w, direction="in", amount=Decimal("1000"), payment_type="cash",
                           reference_type="sale", reference_id=0, description="test", with_transaction=False)
    db.flush()
    return dict(a=a, a1=a1, a2=a2, b=b, b1=b1, cu=cu, pw=w)


def test_cash_api_contract_for_screen(client, db, env):
    """Ekran tayanadigan maydonlar: branch_id/branch_name/is_open; birinchi kassa o'z filialiniki."""
    other = _wallet(db, env['a'], env['a2'], name="Z-Yunusobod")
    own = _wallet(db, env['a'], env['a1'], is_open=False, name="A-Chilonzor")
    foreign = _wallet(db, env['b'], env['b1'])
    j = client.login(env['cu']).get("/api/mobile/cash").json()
    ids = [x['id'] for x in j['wallets']]
    assert foreign.id not in ids  # begona korxona kassasi ko'rinmaydi
    assert ids[0] == own.id and j['wallets'][0]['branch_id'] == env['a1'].id
    byid = {x['id']: x for x in j['wallets']}
    assert byid[own.id]['is_open'] is False and byid[own.id]['branch_name'] == "Chilonzor"
    assert byid[other.id]['branch_name'] == "Yunusobod"


def test_handover_409_confirm_and_cancel_and_isolation(client, db, env):
    other = _wallet(db, env['a'], env['a2'])
    foreign = _wallet(db, env['b'], env['b1'])
    c = client.login(env['cu'])
    r = c.post("/api/mobile/cash/handover", json={"wallet_id": other.id, "amount": 100})
    assert r.status_code == 409
    r = c.post("/api/mobile/cash/handover", json={"wallet_id": other.id, "amount": 100, "confirm_other_branch": True})
    assert r.status_code == 200, r.text
    tid = r.json()['transfer_id']
    j = c.get("/api/mobile/cash").json()
    assert [h['id'] for h in j['pending_handovers']] == [tid]  # bekor qilish tugmasi shu ro'yxatga bog'langan
    r = c.post(f"/api/mobile/cash/handover/{tid}/cancel")
    assert r.status_code == 200 and r.json()['balance'] == 1000.0
    assert db.get(CashTransfer, tid).status == "rejected"
    assert personal_cash_balance(db, env['pw']) == Decimal("1000")
    assert c.get("/api/mobile/cash").json()['pending_handovers'] == []
    # begona korxona kassasi: 404
    assert c.post("/api/mobile/cash/handover",
                  json={"wallet_id": foreign.id, "amount": 10, "confirm_other_branch": True}).status_code == 404


# ───────────────────── 3-5. deploy ─────────────────────

def test_worker_service_unit():
    s = _read('deploy', 'erppos-worker.service')
    assert 'ExecStart=@PYTHON@ -m app.worker' in s
    for ph in ('@MAIN_UNIT@', '@USER@', '@WORKDIR@', '@ENV_FILE_LINE@'):
        assert ph in s, ph
    assert 'PartOf=@MAIN_UNIT@.service' in s and 'Restart=always' in s
    assert '@CPU_' not in s


def test_install_worker_script():
    s = _read('deploy', 'install_worker.sh')
    assert s.startswith('#!/usr/bin/env bash') and 'set -euo pipefail' in s
    assert 'erppos-worker.service' in s and 'systemctl enable "$WORKER_UNIT"' in s
    for ph in ('@MAIN_UNIT@', '@USER@', '@WORKDIR@', '@PYTHON@', '@ENV_FILE_LINE@'):
        assert ph in s, ph
    assert 'RUN_BACKGROUND_JOBS=0' in s
    # web'ga RUN_BACKGROUND_JOBS=0 ishchi ishga tushganini tekshirgandan KEYIN qo'yiladi
    assert s.index('is-active --quiet "$WORKER_UNIT"') < s.index('Environment=RUN_BACKGROUND_JOBS=0')


def test_install_worker_template_vars_all_substituted():
    """Shablondagi har bir @VAR@ skriptdagi sed bilan almashtiriladi."""
    tpl = _read('deploy', 'erppos-worker.service')
    sh = _read('deploy', 'install_worker.sh')
    for var in set(re.findall(r'@[A-Z_]+@', tpl)):
        assert f's|{var}|' in sh, var


def test_deploy_script_restarts_worker():
    s = _read('deploy', 'deploy_erppos.sh')
    assert 'systemctl is-enabled --quiet erppos-worker' in s
    assert 'systemctl restart erppos-worker' in s
    assert s.index('erppos-bgworker') < s.index('erppos-worker') < s.index('sleep 12')


def test_worker_module_exists():
    assert os.path.exists(os.path.join(ROOT, 'app', 'worker.py'))
    from app.services.background_jobs import background_jobs_enabled  # noqa: F401


# ───────────────────── 6-7. Flutter ─────────────────────

def test_edit_product_screen_preferred_warehouse():
    s = _read('mobile', 'lib', 'screens', 'edit_product_screen.dart')
    assert "'/mobile/marketplace/warehouses'" in s
    assert "p['preferred_warehouse_id'] as int?" in s
    assert "'preferred_warehouse_id': _preferredWarehouseId" in s
    assert "Topshirish ombori (ixtiyoriy)" in s and 'DropdownButtonFormField<int?>' in s


def test_my_products_screen_shows_warehouse_name():
    s = _read('mobile', 'lib', 'screens', 'my_products_screen.dart')
    assert "status == 'approved' && product['warehouse_name'] != null" in s
    assert "Qabul qilindi: ${product['warehouse_name']}" in s
