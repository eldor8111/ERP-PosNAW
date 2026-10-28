"""P.7 — Web kassa (dorixona): shtrix-kod skanerlanganda quti / blister / dona tanlash va yaroqlilik muddati ranglari.

Qamrov:
 1. Backend: /products/pos-list dorixonada `expired_qty` (shu omborlardagi muddati o'tgan qoldiq) qaytaradi;
    `nearest_expiry` faqat yaroqli partiyadan; oddiy korxona javobi o'zgarmagan.
 2. PosKassa.jsx: skanerda eng katta mavjud birlik o'zi (`scanAdd`: quti -> blister -> dona), kartochka bosilganda
    `pickOrAdd` (dorixonada tanlash oynasi, aks holda avvalgidek savatga); tanlash oynasi faqat `pharmacy && unitPick`;
    oyna ochiqligida skaner kodi tanlov bo'lib ketmaydi; "Sotuv" (UlgurjiSotuv) skaneri ham `defaultScanUnit`;
    muddat ranglari yashil / sariq / qizil, muddati o'tgan — qizil miltillaydi.
 3. i18n (i18n_pending/P.7.json).
"""
import json
import os
import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.product_pharma import ProductPharma
from app.services.batch_allocator import tashkent_today

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
POS = 'frontend/src/pages/admin/PosKassa.jsx'
PENDING = 'tests/branch_audit/i18n_pending/P.7.json'


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


def _pharmacy_on(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code='pharmacy', is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _dt(days):
    return datetime.combine(tashkent_today() + timedelta(days=days), time.min)


def _drug(db, c, wh, batches, name='Dori P7'):
    """batches: [(miqdor, muddatgacha kun)]."""
    p = Product(name=name, sku='SKU-' + name[-6:], barcode='B' + name[-6:], company_id=c.id,
                cost_price=D('500'), sale_price=D('1000'))
    db.add(p)
    db.flush()
    db.add(ProductPharma(product_id=p.id, company_id=c.id))
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(sum(q for q, _ in batches))))
    for q, days in batches:
        db.add(Batch(product_id=p.id, warehouse_id=wh.id, quantity=D(q), initial_quantity=D(q),
                     purchase_price=D('500'), company_id=c.id, expiry_date=_dt(days)))
    db.flush()
    return p


def _pos_row(client, u, wh, pid):
    r = client.login(u).get('/api/products/pos-list', params={'warehouse_id': wh.id, 'limit': 100})
    assert r.status_code == 200, r.text
    rows = r.json() if isinstance(r.json(), list) else r.json().get('items', [])
    return next(x for x in rows if x['id'] == pid)


# ───────────────────────── 1. Backend ─────────────────────────

def test_pos_list_returns_expired_qty_and_nearest_valid_expiry(client, db, mk):
    c, _, wh, u = mk.tenant()
    _pharmacy_on(db, c)
    p = _drug(db, c, wh, [(5, -3), (7, -1), (20, 200)], name='Dori P7-000001')
    row = _pos_row(client, u, wh, p.id)
    assert row['expired_qty'] == 12                                  # 5 + 7 muddati o'tgan
    assert row['nearest_expiry'] == (tashkent_today() + timedelta(days=200)).isoformat()
    only_ok = _drug(db, c, wh, [(10, 90)], name='Dori P7-000002')
    assert _pos_row(client, u, wh, only_ok.id)['expired_qty'] == 0


def test_pos_list_plain_company_unchanged(client, db, mk):
    c, _, wh, u = mk.tenant()                                        # dorixona yoqilmagan
    p = _drug(db, c, wh, [(5, -3)], name='Dori P7-000003')
    row = _pos_row(client, u, wh, p.id)
    assert 'expired_qty' not in row and 'nearest_expiry' not in row


# ───────────────────────── 2. PosKassa.jsx ─────────────────────────

def test_scan_picks_largest_unit_card_click_uses_picker():
    s = _read(POS)
    # skaner: asosiy shtrix-kod va serverdan topilgan tovar -> scanAdd (quti -> blister -> dona, tanlash oynasisiz)
    body = s[s.index('const handleScannedCode = (code) => {'):s.index('const scanRef = useRef(null);')]
    assert 'scanAdd(p);' in body and 'scanAdd(r.data)' in body and 'pickOrAdd(' not in body
    scan = s[s.index('const scanAdd = (p) => {'):s.index('const confirmUnitPick')]
    assert "pharmacy ? unitOptions(p).find(x => x.unit && !x.skip) : null" in scan     # P.13: skip — faqat ochilgan quti
    ulg = _read('frontend/src/pages/admin/UlgurjiSotuv.jsx')
    assert "prod._scanUnit = defaultScanUnit(prod);" in ulg and "const defaultScanUnit = (p) =>" in ulg
    # birlik shtrix-kodi (quti/blister kodi) — tanlovsiz, to'g'ridan-to'g'ri o'sha birlik
    assert "addToCart(up, undefined, up.units.find(u => u.barcode === code));" in body
    assert 'scanRef.current(code);' in s
    # kartochka bosilganda ham
    assert "pickOrAdd(p);   // P.7: dorixonada quti / blister / dona tanlanadi" in s
    # oddiy korxonada (pharmacy=false) avvalgidek savatga
    pick = s[s.index('const pickOrAdd = (p, qty) => {'):s.index('const confirmUnitPick')]
    assert 'const opts = pharmacy ? unitOptions(p) : [];' in pick
    # oyna faqat quti + blister bo'lgan dorida (variantlar: quti, blister, dona); donalab / blistersiz — avvalgidek savatga
    assert 'if (opts.length < 3) { addToCart(p, qty); return; }' in pick
    # oyna faqat dorixonada
    assert re.search(r"\{pharmacy && unitPick && \(\(\) => \{", s)
    # holat global tinglovchidan OLDIN e'lon qilingan (TDZ yo'q) va tinglovchi oyna ochiqligida skanni o'tkazib yuboradi
    assert s.index('const [unitPick, setUnitPick] = useState(null);') < s.index('// Global Skaner Listener')
    assert 'rejectedModal || unitPick) return;' in s


def test_unit_picker_options_keyboard_and_scan_while_open():
    s = _read(POS)
    opts = s[s.index('const unitOptions = (p) => {'):s.index('const pickOrAdd')]
    # quti (eng katta) birinchi, oxirida dona; P.13: hech bir birlik bloklanmaydi, faqat ochilgan quti bo'lsa quti
    # sukut bo'yicha tanlanmaydi (skip)
    assert '.sort((a, b) => Number(b.ratio) - Number(a.ratio))' in opts
    assert "{ unit: null, name: p.unit || 'dona', ratio: 1, price: base, disabled: false, skip: false }" in opts
    assert 'disabled: false, skip: openedOnly && Number(u.ratio) >= Number(p.pack_ratio)' in opts
    keys = s[s.index("if (!unitPick) return undefined;"):s.index('// P.7: yaroqlilik muddati rangi')]
    assert "e.key === 'Escape'" in keys and "e.key === 'ArrowDown'" in keys and "e.key === 'Enter'" in keys
    # oyna ochiqligida kelgan skaner kodi: joriy tanlov qo'shiladi, yangi kod odatdagidek qayta ishlanadi
    assert 'confirmUnitPick();' in keys and 'if (code.length >= 3) setTimeout(() => scanRef.current && scanRef.current(code), 0);' in keys
    assert not re.search(r"e\.key === '[1-9]'", keys)                 # raqam tugmalari yo'q (skaner raqamlari)


def _level(days, warn=30):
    """expiryLevel ning Python nusxasi."""
    red = max(1, warn or 30)
    if days is None:
        return None
    if days < 0:
        return 'expired'
    if days <= red:
        return 'red'
    if days <= red * 3:
        return 'yellow'
    return 'green'


def test_expiry_colors():
    assert [_level(d) for d in (-1, 0, 30, 31, 90, 91, 400)] == ['expired', 'red', 'red', 'yellow', 'yellow', 'green', 'green']
    assert _level(50, warn=60) == 'red' and _level(None) is None
    s = _read(POS)
    lvl = s[s.index('const expiryLevel = (days) => {'):s.index('const EXPIRY_CLS')]
    for token in ("if (days < 0) return 'expired';", "if (days <= red) return 'red';",
                  "if (days <= red * 3) return 'yellow';", "return 'green';",
                  "Number(features?.pharmacy_settings?.expiry_warn_days) || 30"):
        assert token in lvl, token
    assert "expired: 'bg-red-600 text-white border border-red-700 animate-pulse'" in s     # miltillaydi
    # kartochka, savat, analoglar va tanlash oynasida
    assert s.count('expiryBadges(') == 4          # savat, kartochka, analoglar, tanlash oynasi
    assert "expired_qty: Number(p.expired_qty) || 0," in s


# ───────────────────────── 3. i18n ─────────────────────────

def test_i18n_p7():
    with open(os.path.join(ROOT, PENDING), encoding='utf-8') as f:
        data = json.load(f)
    assert set(data['uz']) == set(data['ru']) == set(data['en'])
    used = set(re.findall(r"tf\('(pos\.(?:unitPick\w*|noWholeBox|expiryDaysLeft|expired\w*))'", _read(POS)))
    assert used == set(data['uz']), used ^ set(data['uz'])
    for lang in ('uz', 'ru', 'en'):
        txt = _read(f'frontend/src/i18n/{lang}.js')
        for k in data[lang]:
            assert len(re.findall(r"^\s*['\"]" + re.escape(k) + r"['\"]\s*:", txt, re.M)) == 1, (lang, k)
