"""T0.19 — XSS: chek HTML, shablon ruxsati/sxemasi, Telegram ismi, pos-desktop.

Backend qismi pytest bilan (SQLite muhit); frontend/pos-desktop qismi `node` orqali
(node topilmasa, tegishli testlar o'tkazib yuboriladi) va statik tekshiruvlar bilan.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

from app.models.company import Company
from app.models.user import UserRole

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
RECEIPT_JS = os.path.join(ROOT, 'frontend', 'src', 'utils', 'receiptBuilder.js')
POS_JS = os.path.join(ROOT, 'pos-desktop', 'renderer', 'pos.js')
POS_HTML = os.path.join(ROOT, 'pos-desktop', 'renderer', 'index.html')
MAIN_JS = os.path.join(ROOT, 'pos-desktop', 'main.js')
PRELOAD_JS = os.path.join(ROOT, 'pos-desktop', 'preload.js')

XSS = '<img src=x onerror=alert(1)>'
URL = '/api/companies/me/receipt_templates'


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _node():
    cand = shutil.which('node') or os.environ.get('NODE_BIN')
    if cand and os.path.exists(cand):
        return cand
    return None


needs_node = pytest.mark.skipif(_node() is None, reason='node topilmadi')


def _run_node(code, cwd):
    p = subprocess.run([_node(), '--input-type=module', '-e', code], cwd=cwd,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


# ───────────────────────── Backend: shablon ruxsati va sxema ─────────────────────────

GOOD = {'r80': {'company': 'A&B do\'koni', 'address': 'Toshkent', 'show_qr': True,
                'logo': 'data:image/png;base64,iVBORw0KGgo=', 'logo_size': 40, 'copies': '1'}}


def test_cashier_cannot_save_template_403(client, mk):
    c, b, w, cashier = mk.tenant(role=UserRole.cashier)
    r = client.login(cashier).put(URL, json={'receipt_templates': GOOD})
    assert r.status_code == 403, r.text


def test_courier_cannot_save_template_403(client, mk):
    c, b, w, courier = mk.tenant(role=UserRole.courier)
    r = client.login(courier).put(URL, json={'receipt_templates': GOOD})
    assert r.status_code == 403, r.text


@pytest.mark.parametrize('role', [UserRole.admin, UserRole.director])
def test_admin_and_director_can_save(client, mk, db, role):
    c, b, w, u = mk.tenant(role=role)
    r = client.login(u).put(URL, json={'receipt_templates': GOOD})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.receipt_templates['r80']['company'] == "A&B do'koni"


def test_cashier_can_still_read_template(client, mk, db):
    c, b, w, admin = mk.tenant(role=UserRole.admin)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    assert client.login(admin).put(URL, json={'receipt_templates': GOOD}).status_code == 200
    r = client.login(cashier).get(URL)
    assert r.status_code == 200
    assert r.json()['receipt_templates']['r80']['address'] == 'Toshkent'


def test_two_companies_isolated(client, mk, db):
    c1, b1, w1, a1 = mk.tenant()
    c2, b2, w2, a2 = mk.tenant()
    assert client.login(a1).put(URL, json={'receipt_templates': {'r58': {'company': 'Birinchi'}}}).status_code == 200
    assert client.login(a2).put(URL, json={'receipt_templates': {'r58': {'company': 'Ikkinchi'}}}).status_code == 200
    db.refresh(c1)
    db.refresh(c2)
    assert c1.receipt_templates['r58']['company'] == 'Birinchi'
    assert c2.receipt_templates['r58']['company'] == 'Ikkinchi'
    assert client.login(a1).get(URL).json()['receipt_templates']['r58']['company'] == 'Birinchi'


@pytest.mark.parametrize('payload', [
    {'zzz': {'company': 'x'}},                                   # noma'lum shablon
    {'r58': {'evil_key': 'x'}},                                  # noma'lum kalit
    {'r58': {'company': 'x' * 501}},                             # juda uzun
    {'r58': {'logo': 'javascript:alert(1)'}},                    # noto'g'ri logo
    {'r58': {'logo': 'http://evil/x.png'}},                      # http ruxsat emas
    {'r58': {'logo': 'https://x/a.png" onerror="alert(1)'}},     # atribut inyeksiyasi
    {'r58': {'logo': 'data:text/html;base64,PHNjcmlwdD4='}},     # rasm emas
    {'r58': {'logo_size': 'katta'}},                             # son emas
    {'r58': {'company': {'a': 1}}},                              # matn emas
    {'r58': 'matn'},                                             # obyekt emas
])
def test_invalid_template_422(client, mk, payload):
    c, b, w, admin = mk.tenant()
    r = client.login(admin).put(URL, json={'receipt_templates': payload})
    assert r.status_code == 422, r.text


def test_script_text_in_fields_is_stored_as_text(client, mk, db):
    """Matn maydonlariga <script> yozish mumkin (escape chekda qilinadi) — lekin logo'ga emas."""
    c, b, w, admin = mk.tenant()
    r = client.login(admin).put(URL, json={'receipt_templates': {'nak': {'company': XSS, 'footer_note': '<script>1</script>'}}})
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.receipt_templates['nak']['company'] == XSS


def test_full_settings_payload_from_ui_accepted(client, mk):
    """Settings.jsx yuboradigan haqiqiy kalitlar to'plami 422 bermasligi kerak."""
    c, b, w, admin = mk.tenant()
    r58 = {'company': 'K', 'address': 'a', 'phone': '+998', 'inn': '1', 'logo': '', 'logo_size': 40,
           'header': '', 'footer': 'rahmat', 'show_number': True, 'show_debt': False, 'copies': '1', 'show_qr': False}
    nak = {'company': 'K', 'inn': '1', 'address': 'a', 'phone': 'p', 'logo': '', 'logo_size': 50,
           'logo_position': 'center', 'bank': 'b', 'account': '1', 'mfo': '2', 'director': 'd',
           'accountant': 'a', 'storekeeper': 's', 'footer_note': 'n', 'show_director': True, 'show_sku': False}
    r = client.login(admin).put(URL, json={'receipt_templates': {'r58': r58, 'r80': r58, 'nak': nak}})
    assert r.status_code == 200, r.text


# ───────────────────────── Backend: Telegram ismi ─────────────────────────

def test_telegram_clean_name_and_escape():
    from app.routers.telegram import _clean_name, _h
    assert '<' not in _clean_name(XSS) and '>' not in _clean_name(XSS)
    assert _clean_name('  Ali   Vali  ') == 'Ali Vali'
    assert len(_clean_name('a' * 500)) == 200
    assert _clean_name('<>') == ''
    assert _h('<b>&') == '&lt;b&gt;&amp;'
    assert _h(None) == ''


# ───────────────────────── Frontend: chek HTML (node orqali) ─────────────────────────

def _receipt_runner(tmp, body):
    shutil.copy(RECEIPT_JS, os.path.join(tmp, 'rb.mjs'))
    return _run_node("import * as rb from './rb.mjs';\n" + body, tmp)


@needs_node
def test_thermal_receipt_escapes_everything():
    with tempfile.TemporaryDirectory() as tmp:
        out = _receipt_runner(tmp, f"""
const X = {json.dumps(XSS)};
const sale = {{ number: X, id: 1, cashier_name: X, customer_name: X, note: X, status: X,
  contractor_contacts: [X], total_amount: 1000, paid_amount: 1000,
  items: [{{ product_name: X, quantity: 1, unit_price: 1000, subtotal: 1000, unit: X, currency_code: 'UZS' }}] }};
const cfg = {{ company: X, address: X, phone: X, inn: X, footer: X, logo: 'javascript:alert(1)',
  show_note: true, show_status: true, show_unit: true, show_account_name: true, show_contractor_contact: true }};
console.log(JSON.stringify(rb.buildReceiptHtml(sale, '80', cfg)));
""")
    assert '<img' not in out
    assert 'onerror=alert' not in out.replace('&lt;img src=x onerror=alert(1)&gt;', '')
    assert '&lt;img src=x onerror=alert(1)&gt;' in out
    assert 'javascript:' not in out


@needs_node
def test_nakladnoy_escapes_everything():
    with tempfile.TemporaryDirectory() as tmp:
        out = _receipt_runner(tmp, f"""
const X = {json.dumps(XSS)};
const sale = {{ number: X, id: 1, cashier_name: X, customer_name: X, note: X, status: X, account_name: X,
  account_username: X, employee_name: X, total_amount: 1000, paid_amount: 500, total_national: X, percent_discount: X,
  payment_currencies: [{{ type: X, currency: 'UZS', amount: 500 }}],
  items: [{{ product_name: X, quantity: 1, unit_price: 1000, subtotal: 1000, measurement_name: X, warehouse_name: X, sku: X }}] }};
const cfg = {{ company: X, address: X, phone: X, inn: X, bank: X, account: X, mfo: X, director: X, accountant: X,
  storekeeper: X, footer_note: X, logo: 'https://x/a.png" onerror="alert(1)', show_note: true, show_status: true,
  show_account_username: true, show_contractor_contacts: true, show_accountant: true, show_storekeeper: true,
  show_measurement: true, show_warehouse: true, show_sku: true, show_total_national: true, show_percent_discount: true }};
console.log(JSON.stringify(rb.buildReceiptHtml(sale, 'nak', cfg)));
""")
    assert '<img' not in out
    assert '&lt;img src=x onerror=alert(1)&gt;' in out
    assert 'onerror="alert' not in out


@needs_node
def test_logo_allowed_only_safe_urls():
    with tempfile.TemporaryDirectory() as tmp:
        res = _receipt_runner(tmp, """
const ok1 = rb.safeUrl('data:image/png;base64,iVBORw0KGgo=');
const ok2 = rb.safeUrl('https://cdn.example.com/a.png');
const bad = ['javascript:alert(1)', 'http://x/a.png', 'data:text/html;base64,AAAA', 'https://x/a" onerror="1', '', null,
  'data:image/png;base64,AA" onerror="alert(1)'].map(rb.safeUrl);
const html = rb.buildReceiptHtml({ number: 1, items: [] }, '80', { logo: 'data:image/png;base64,iVBORw0KGgo=' });
console.log(JSON.stringify({ ok1, ok2, bad, hasLogo: html.includes('<img src="data:image/png;base64,iVBORw0KGgo="') }));
""")
    assert res['ok1'].startswith('data:image/png') and res['ok2'].startswith('https://')
    assert res['bad'] == [''] * 7
    assert res['hasLogo'] is True


@needs_node
def test_esc_function():
    with tempfile.TemporaryDirectory() as tmp:
        res = _receipt_runner(tmp, """
console.log(JSON.stringify([rb.esc('<a href="x">&\\'</a>'), rb.esc(null), rb.esc(5), rb.esc(undefined)]));
""")
    assert res == ['&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;', '', '5', '']


@needs_node
def test_sale_number_with_script_end_does_not_break_script_block():
    """4-mezon: sale.number da </script> bo'lsa, <script> bloki buzilmaydi; barcode/QR skriptlari saqlanadi."""
    with tempfile.TemporaryDirectory() as tmp:
        out = _receipt_runner(tmp, """
const N = '</script><script>alert(1)</script>';
const html = rb.buildReceiptHtml({ number: N, id: 1, total_amount: 5, paid_amount: 5, items: [] }, '80',
  { show_barcode: true, show_qr: true });
console.log(JSON.stringify(html));
""")
    # faqat 3 ta <script ...> ochilishi: jsbarcode, qrcode, inline
    assert out.count('<script') == 3
    assert out.count('</script>') == 3
    assert 'jsbarcode@3.11.6' in out and 'qrcode-generator@1.4.4' in out      # 7-mezon: kutubxonalar saqlanadi
    assert 'JsBarcode(' in out and 'qrcode(0' in out
    assert '\\u003c/script>' in out or '\\\\u003c/script>' in out


# ───────────────────────── Frontend: boshqa HTML yozuvchilar ─────────────────────────

def test_ai_copilot_render_text_escapes():
    src = _read(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'AICopilot.jsx'))
    m = re.search(r'function renderText\(text\) \{(.*?)\n\}', src, re.S)
    assert m
    body = m.group(1)
    assert body.index("&lt;") < body.index('<strong>')          # avval escape, keyin teg qo'shiladi


def test_warehouse_print_table_escapes():
    src = _read(os.path.join(ROOT, 'frontend', 'src', 'pages', 'admin', 'Warehouse.jsx'))
    assert 'const esc = ' in src
    assert '<title>${esc(title)}</title>' in src
    assert '${esc(cell ?? ' in src
    assert '<title>${title}</title>' not in src


# ───────────────────────── pos-desktop ─────────────────────────

def test_electron_window_hardened():
    main = _read(MAIN_JS)
    assert 'nodeIntegration: false' in main
    assert 'contextIsolation: true' in main
    assert 'sandbox: true' in main
    assert "path.join(__dirname, 'preload.js')" in main
    assert 'nodeIntegration: true' not in main


def test_preload_exposes_only_window_controls():
    pre = _read(PRELOAD_JS)
    assert "contextBridge.exposeInMainWorld('posWin'" in pre
    for cmd in ('minimize', 'maximize', 'close'):
        assert f"'{cmd}'" in pre
    assert "ipcRenderer.send('win-' + cmd)" in pre


def test_renderer_has_no_node_api_and_uses_preload():
    pos = _read(POS_JS)
    assert "require(" not in pos and 'ipcRenderer' not in pos
    assert 'window.posWin.send(cmd)' in pos


def test_csp_present_in_index_html():
    html = _read(POS_HTML)
    m = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', html)
    assert m
    csp = m.group(1)
    assert "default-src 'self'" in csp and "object-src 'none'" in csp


def test_pos_innerhtml_interpolations_are_escaped():
    """Server qiymatlari (name/sku/phone/...) esc() siz `${...}` ichida qolmasligi kerak."""
    pos = _read(POS_JS)
    risky = re.compile(r'\$\{(?!esc\(|prodImgSrc|safeUrl)[A-Za-z_.?\[\]]*\.(name|sku|phone|message|number|cashier_name|'
                       r'product_name|category_name|reason|address|image_url|unit|terminal|type)\b(?!\s*\?)')
    bad = [ln for ln in pos.splitlines() if risky.search(ln) and not ln.lstrip().startswith('//')]
    # toast()/textContent chaqiruvlari `${}` ishlatmaydi; qolganlari bo'sh bo'lishi kerak
    assert bad == [], bad


def test_return_sale_onclick_encoding_escapes_single_quote():
    pos = _read(POS_JS)
    assert ".replace(/'/g, '%27')" in pos


@needs_node
def test_pos_esc_and_safe_url_runtime():
    pos = _read(POS_JS)
    start = pos.index('const esc = ')
    end = pos.index("const PRODUCTION_API")
    snippet = pos[start:end]
    with tempfile.TemporaryDirectory() as tmp:
        code = f"""
const CFG = {{ apiUrl: 'https://savdo.e-code.uz' }};
{snippet}
console.log(JSON.stringify({{
  e: esc('<img src=x onerror="a">'),
  a: safeUrl('javascript:alert(1)'),
  b: safeUrl('https://savdo.e-code.uz/static/a.png'),
  c: prodImgSrc('/static/a.png'),
  d: prodImgSrc('x" onerror="alert(1)'),
  f: safeUrl('//evil.com/x.png'),
}}));
"""
        res = _run_node(code, tmp)
    assert res['e'] == '&lt;img src=x onerror=&quot;a&quot;&gt;'
    assert res['a'] == '' and res['d'] == '' and res['f'] == ''
    assert res['b'] == 'https://savdo.e-code.uz/static/a.png'
    assert res['c'] == 'https://savdo.e-code.uz/static/a.png'
