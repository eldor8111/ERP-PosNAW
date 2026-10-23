"""D3.2 — Markirovka kodlari: kirimda qabul, sotuvda tekshirish, qaytarishda holat (dorixona rejimi).

Qamrov: GS1 Data Matrix tahlili (qavsli / FNC1-GS / kripto dum / oy oxiri), kirimda kodlarni yozish (servis va
`POST /api/pharmacy/marking/receive`), GTIN/seriya/muddat/son ogohlantirishlari, sotuvda in_stock tekshiruvi va
`sold` holati, takror sotuv 400, qaytarishda `in_stock`, oddiy korxona (regressiya), ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D3_2.py -q -p no:cacheprovider
"""
import itertools
import json
import pathlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.marking_code import MarkingCode
from app.models.moliya import Wallet
from app.models.product import Product
from app.models.sale import SaleItem
from app.models.supplier import Supplier
from app.models.user import UserWallet
from app.routers.pharmacy_marking import canonical_code, parse_gs1
from app.services.document_numbers import tashkent_today
from app.services.purchase_order_service import receive_purchase_order

ROOT = pathlib.Path(__file__).resolve().parents[2]
_n = itertools.count(1)
GS = "\x1d"
GTIN = "04600000000017"          # 13 raqam + nazorat raqami (mod 10) to'g'ri
EAN = "4600000000017"            # shu GTIN'ning EAN-13 ko'rinishi (mahsulot shtrix-kodi)
LOT = "LOT-A1"


def _gtin_with_check(body13: str) -> str:
    digits = [int(c) for c in body13]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return body13 + str((10 - total % 10) % 10)


# ─── yordamchilar ───

def _enable(db, c):
    c.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _wallet(db, c, b, user):
    w = Wallet(name=f"Kassa {next(_n)}", type="cash", balance=D(0), company_id=c.id, branch_id=b.id,
               is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(UserWallet(user_id=user.id, wallet_id=w.id, is_default=True, company_id=c.id))
    db.flush()


def _supplier(db, c):
    s = Supplier(name=f"Taminotchi {c.id}-{next(_n)}", company_id=c.id, is_active=True,
                 debt_balance=D(0), debt_balances={})
    db.add(s)
    db.flush()
    return s


def _product(db, c, marking=True, barcode=EAN):
    n = next(_n)
    p = Product(name=f"Dori M{n}", sku=f"M32-{n}", barcode=barcode if barcode != EAN else f"{EAN[:-3]}{n:03d}"[:13],
                company_id=c.id, cost_price=D("500"), sale_price=D("1000"), requires_marking=marking)
    db.add(p)
    db.flush()
    return p


def _gs_code(serial, gtin=GTIN, lot=LOT, expiry=None, tail=True):
    """FNC1 (GS) ajratgichli xom Data Matrix: 01 GTIN 21 serial GS [17 muddat 10 seriya GS] [91 kalit GS 92 imzo]."""
    s = f"01{gtin}21{serial}{GS}"
    if expiry:
        s += f"17{expiry}"
    if lot:
        s += f"10{lot}{GS}"
    if tail:
        s += f"91EE11{GS}92ABCDEFGH"
    return s


def _exp_days(days):
    d = tashkent_today() + timedelta(days=days)
    return d, d.strftime("%y%m%d")


def _po(client, user, wh, sup, product, qty):
    r = client.login(user).post('/api/purchase-orders', json={
        'supplier_id': sup.id, 'warehouse_id': wh.id, 'status': 'sent',
        'items': [{'product_id': product.id, 'qty_ordered': qty, 'unit_cost': 500}]})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _receive_api(client, user, po, qty, expiry_days=400):
    d, _ = _exp_days(expiry_days)
    return client.login(user).post(f"/api/purchase-orders/{po['id']}/receive", json={'items': [{
        'po_item_id': po['items'][0]['id'], 'qty_received': qty, 'lot_number': LOT,
        'expiry_date': d.isoformat() + 'T00:00:00'}]})


def _sale_body(p, qty, wh, codes=None):
    total = 1000 * qty
    item = {"product_id": p.id, "quantity": qty, "unit_price": 1000}
    if codes is not None:
        item["marking_codes"] = codes
    return {"items": [item], "payment_type": "cash", "paid_amount": total, "paid_cash": total,
            "payments": [{"type": "cash", "amount": total}], "warehouse_id": wh.id}


def _rows(db, company, **flt):
    return db.query(MarkingCode).filter_by(company_id=company.id, **flt).order_by(MarkingCode.id).all()


@pytest.fixture
def w(db, mk):
    """P — dorixona (admin, kassa, ta'minotchi), Q — boshqa dorixona, A — oddiy korxona."""
    p_c, p_b, p_wh, p_admin = mk.tenant()
    q_c, q_b, q_wh, q_admin = mk.tenant()
    a_c, a_b, a_wh, a_admin = mk.tenant()
    for c, b, u in ((p_c, p_b, p_admin), (q_c, q_b, q_admin), (a_c, a_b, a_admin)):
        _wallet(db, c, b, u)
    _enable(db, p_c)
    _enable(db, q_c)
    return dict(pc=p_c, pwh=p_wh, padmin=p_admin, psup=_supplier(db, p_c),
                qc=q_c, qwh=q_wh, qadmin=q_admin, qsup=_supplier(db, q_c),
                ac=a_c, awh=a_wh, aadmin=a_admin, asup=_supplier(db, a_c))


@pytest.fixture
def received(client, db, w):
    """Dorixonada markirovkali dori: 5 ta qabul qilindi, 3 ta kod (A1..A3) kirimda yozildi."""
    prod = _product(db, w['pc'])
    po = _po(client, w['padmin'], w['pwh'], w['psup'], prod, 5)
    assert _receive_api(client, w['padmin'], po, 5).status_code == 200
    _, yymmdd = _exp_days(400)
    codes = [_gs_code(f"SER{i:04d}", expiry=yymmdd) for i in (1, 2, 3)]
    r = client.login(w['padmin']).post('/api/pharmacy/marking/receive', json={
        'po_id': po['id'], 'items': [{'po_item_id': po['items'][0]['id'], 'marking_codes': codes}]})
    assert r.status_code == 200, r.text
    return dict(prod=prod, po=po, codes=codes, resp=r.json())


# ───────────────────────── 1. GS1 tahlili ─────────────────────────

def test_parse_parenthesized():
    p = parse_gs1(f"(01){GTIN}(21)ABC123(17)261231(10)LOT9")
    assert p["valid"] and p["gtin"] == GTIN and p["serial"] == "ABC123"
    assert p["expiry_date"] == "2026-12-31" and p["lot"] == "LOT9"
    assert p["code"] == f"01{GTIN}21ABC123" and p["errors"] == []


def test_parse_fnc1_with_crypto_tail_and_symbology_prefix():
    raw = "]d2" + _gs_code("SER0001", expiry="270630")
    p = parse_gs1(raw)
    assert p["valid"] and p["serial"] == "SER0001" and p["lot"] == LOT
    assert p["expiry_date"] == "2027-06-30"
    assert p["ais"]["91"] == "EE11" and p["ais"]["92"] == "ABCDEFGH"
    # kripto dumsiz qisqa kod ham bir xil kalitga keladi
    assert canonical_code(f"01{GTIN}21SER0001")[0] == p["code"]


def test_parse_day_zero_is_end_of_month_and_bad_date_warns():
    assert parse_gs1(f"(01){GTIN}(21)S1(17)280200")["expiry_date"] == "2028-02-29"
    bad = parse_gs1(f"(01){GTIN}(21)S1(17)261399")
    assert bad["expiry_date"] is None and bad["warnings"] and bad["valid"]


def test_parse_invalid_inputs_never_raise():
    for raw in ("", "   ", "ABC", "01123", f"(01)123(21)X", f"01{GTIN}", "99"):
        p = parse_gs1(raw)
        assert p["valid"] is False and p["errors"], raw
    # to'g'ri GTIN, lekin nazorat raqami xato — ogohlantirish, kod yaroqli
    p = parse_gs1("(01)04600000000018(21)S1")
    assert p["valid"] and any("nazorat" in x for x in p["warnings"])


def test_parse_endpoint_pharmacy_ok_plain_forbidden(client, w):
    r = client.login(w['padmin']).post('/api/pharmacy/marking/parse', json={'code': f"(01){GTIN}(21)Z9(10)L1"})
    assert r.status_code == 200, r.text
    assert r.json()['serial'] == 'Z9' and r.json()['lot'] == 'L1' and r.json()['valid'] is True
    r = client.login(w['aadmin']).post('/api/pharmacy/marking/parse', json={'code': f"(01){GTIN}(21)Z9"})
    assert r.status_code == 403


# ───────────────────────── 2. Kirim ─────────────────────────

def test_receive_registers_codes_in_stock_and_links_batch(client, db, w, received):
    rows = _rows(db, w['pc'])
    assert len(rows) == 3 and all(r.status == "in_stock" for r in rows)
    assert {r.serial for r in rows} == {"SER0001", "SER0002", "SER0003"}
    assert all(r.code == f"01{GTIN}21{r.serial}" and r.gtin == GTIN and r.lot_number == LOT for r in rows)
    batch = db.query(Batch).filter_by(product_id=received['prod'].id).one()
    assert all(r.batch_id == batch.id and r.received_po_id == received['po']['id'] and r.warehouse_id == w['pwh'].id
               for r in rows)
    assert all(r.expiry_date == tashkent_today() + timedelta(days=400) for r in rows)
    # 3 ta kod, lekin 5 ta qabul qilingan va GTIN mahsulot shtrix-kodiga mos emas -> ogohlantirishlar (rad etilmaydi)
    warns = " ".join(received['resp']['warnings'])
    assert "teng emas" in warns and "GTIN" in warns
    assert received['resp']['registered'] == 3 and received['resp']['already'] == 0


def test_receive_resend_is_idempotent(client, db, w, received):
    r = client.login(w['padmin']).post('/api/pharmacy/marking/receive', json={
        'po_id': received['po']['id'],
        'items': [{'po_item_id': received['po']['items'][0]['id'], 'marking_codes': received['codes']}]})
    assert r.status_code == 200, r.text
    assert r.json()['registered'] == 0 and r.json()['already'] == 3
    assert len(_rows(db, w['pc'])) == 3


def test_receive_matching_gtin_and_count_gives_no_warnings(client, db, w):
    gt = _gtin_with_check("0461111111111")
    prod = _product(db, w['pc'], barcode="461111111111" + gt[-2:-1] + gt[-1:])
    prod.barcode = gt[1:]                                    # EAN-13 = GTIN-14 dan boshidagi 0 tashlangan
    db.flush()
    po = _po(client, w['padmin'], w['pwh'], w['psup'], prod, 2)
    assert _receive_api(client, w['padmin'], po, 2).status_code == 200
    _, yymmdd = _exp_days(400)
    codes = [_gs_code(f"G{i}", gtin=gt, expiry=yymmdd) for i in (1, 2)]
    r = client.login(w['padmin']).post('/api/pharmacy/marking/receive', json={
        'po_id': po['id'], 'items': [{'po_item_id': po['items'][0]['id'], 'marking_codes': codes}]})
    assert r.status_code == 200, r.text
    assert r.json()['warnings'] == [] and r.json()['registered'] == 2


def test_receive_warns_on_lot_and_expiry_mismatch(client, db, w):
    prod = _product(db, w['pc'])
    po = _po(client, w['padmin'], w['pwh'], w['psup'], prod, 1)
    assert _receive_api(client, w['padmin'], po, 1).status_code == 200
    code = _gs_code("X1", lot="OTHER", expiry=_exp_days(30)[1])
    r = client.login(w['padmin']).post('/api/pharmacy/marking/receive', json={
        'po_id': po['id'], 'items': [{'po_item_id': po['items'][0]['id'], 'marking_codes': [code]}]})
    assert r.status_code == 200, r.text
    warns = " ".join(r.json()['warnings'])
    assert "seriyasi" in warns and "muddati" in warns
    assert len(_rows(db, w['pc'])) == 1


def test_receive_rejects_duplicates_and_known_codes(client, db, w, received):
    prod2 = _product(db, w['pc'])
    po2 = _po(client, w['padmin'], w['pwh'], w['psup'], prod2, 1)
    assert _receive_api(client, w['padmin'], po2, 1).status_code == 200
    item = po2['items'][0]['id']
    cl = client.login(w['padmin'])
    # so'rovning o'zida takror
    dup = _gs_code("DUP1")
    r = cl.post('/api/pharmacy/marking/receive', json={'po_id': po2['id'], 'items': [
        {'po_item_id': item, 'marking_codes': [dup, dup]}]})
    assert r.status_code == 400 and "takrorlangan" in r.json()['detail']
    # allaqachon boshqa mahsulot/xaridda ro'yxatda
    r = cl.post('/api/pharmacy/marking/receive', json={'po_id': po2['id'], 'items': [
        {'po_item_id': item, 'marking_codes': [received['codes'][0]]}]})
    assert r.status_code == 400 and "allaqachon" in r.json()['detail']
    assert len(_rows(db, w['pc'])) == 3     # rad etilganda hech narsa yozilmadi


def test_receive_requires_received_goods_and_marked_product(client, db, w):
    prod = _product(db, w['pc'])
    po = _po(client, w['padmin'], w['pwh'], w['psup'], prod, 1)
    cl = client.login(w['padmin'])
    r = cl.post('/api/pharmacy/marking/receive', json={'po_id': po['id'], 'items': [
        {'po_item_id': po['items'][0]['id'], 'marking_codes': [_gs_code("N1")]}]})
    assert r.status_code == 400 and "qabul" in r.json()['detail']
    plain = _product(db, w['pc'], marking=False)
    po2 = _po(client, w['padmin'], w['pwh'], w['psup'], plain, 1)
    assert _receive_api(client, w['padmin'], po2, 1).status_code == 200
    r = cl.post('/api/pharmacy/marking/receive', json={'po_id': po2['id'], 'items': [
        {'po_item_id': po2['items'][0]['id'], 'marking_codes': [_gs_code("N2")]}]})
    assert r.status_code == 400 and "markirovka talab qilmaydi" in r.json()['detail']


def test_receive_service_accepts_marking_codes_in_receive_payload(client, db, w):
    """receive_purchase_order qatordagi `marking_codes` ni qabul bilan birga yozadi (sxemaga maydon qo'shilgach API ham)."""
    prod = _product(db, w['pc'])
    po = _po(client, w['padmin'], w['pwh'], w['psup'], prod, 2)
    d, yymmdd = _exp_days(300)
    codes = [_gs_code("S1", expiry=yymmdd), _gs_code("S2", expiry=yymmdd)]
    data = SimpleNamespace(note=None, items=[SimpleNamespace(
        po_item_id=po['items'][0]['id'], qty_received=D(2), lot_number=LOT, expiry_date=datetime(d.year, d.month, d.day),
        manufacture_date=None, lots=None, marking_codes=codes)])
    res = receive_purchase_order(db, po['id'], data, w['padmin'])
    rows = _rows(db, w['pc'])
    assert len(rows) == 2 and all(r.status == "in_stock" and r.batch_id for r in rows)
    assert res.receive_warnings and "GTIN" in " ".join(res.receive_warnings)   # shtrix-kod GTIN ga mos emas


def test_plain_company_receive_ignores_marking_codes(client, db, w):
    prod = _product(db, w['ac'])
    po = _po(client, w['aadmin'], w['awh'], w['asup'], prod, 2)
    data = SimpleNamespace(note=None, items=[SimpleNamespace(
        po_item_id=po['items'][0]['id'], qty_received=D(2), lot_number=None, expiry_date=None,
        manufacture_date=None, lots=None, marking_codes=[_gs_code("P1"), _gs_code("P2")])])
    res = receive_purchase_order(db, po['id'], data, w['aadmin'])
    assert res.status.value == "received" and list(res.receive_warnings) == []
    assert db.query(MarkingCode).count() == 0
    # API: dorixona endpointlari oddiy korxonada yopiq
    r = client.login(w['aadmin']).post('/api/pharmacy/marking/receive', json={'po_id': po['id'], 'items': []})
    assert r.status_code == 403


# ───────────────────────── 3. Sotuv ─────────────────────────

def test_sale_marks_codes_sold_and_links_sale_item(client, db, w, received):
    prod, codes = received['prod'], received['codes']
    r = client.login(w['padmin']).post('/api/sales/', json=_sale_body(prod, 2, w['pwh'], codes[:2]))
    assert r.status_code == 200, r.text
    item = db.query(SaleItem).filter_by(sale_id=r.json()['id']).one()
    assert item.marking_codes == codes[:2]                           # fiskal uzatish uchun xom kodlar saqlanadi
    rows = {x.serial: x for x in _rows(db, w['pc'])}
    assert rows["SER0001"].status == rows["SER0002"].status == "sold"
    assert rows["SER0001"].sale_item_id == rows["SER0002"].sale_item_id == item.id
    assert rows["SER0003"].status == "in_stock" and rows["SER0003"].sale_item_id is None


def test_sale_accepts_short_code_without_crypto_tail(client, db, w, received):
    short = f"01{GTIN}21SER0003"
    r = client.login(w['padmin']).post('/api/sales/', json=_sale_body(received['prod'], 1, w['pwh'], [short]))
    assert r.status_code == 200, r.text
    assert [x.status for x in _rows(db, w['pc'], serial="SER0003")] == ["sold"]


def test_second_sale_of_same_code_is_400(client, db, w, received):
    prod, codes = received['prod'], received['codes']
    cl = client.login(w['padmin'])
    assert cl.post('/api/sales/', json=_sale_body(prod, 1, w['pwh'], [codes[0]])).status_code == 200
    r = cl.post('/api/sales/', json=_sale_body(prod, 1, w['pwh'], [codes[0]]))
    assert r.status_code == 400 and "allaqachon sotilgan" in r.json()['detail']
    sl = db.query(StockLevel).filter_by(product_id=prod.id, warehouse_id=w['pwh'].id).one()
    assert D(str(sl.quantity)) == 4                                   # ikkinchi sotuv ombordan ayirmadi


def test_sale_with_unknown_code_is_400_and_writes_nothing(client, db, w, received):
    prod = received['prod']
    r = client.login(w['padmin']).post('/api/sales/', json=_sale_body(prod, 1, w['pwh'], [_gs_code("NOPE")]))
    assert r.status_code == 400 and "topilmadi" in r.json()['detail']
    sl = db.query(StockLevel).filter_by(product_id=prod.id, warehouse_id=w['pwh'].id).one()
    assert D(str(sl.quantity)) == 5
    assert all(x.status == "in_stock" for x in _rows(db, w['pc']))


def test_sale_duplicate_code_within_one_receipt_is_400(client, db, w, received):
    c = received['codes'][0]
    r = client.login(w['padmin']).post('/api/sales/', json=_sale_body(received['prod'], 2, w['pwh'], [c, c]))
    assert r.status_code == 400 and "takrorlangan" in r.json()['detail']
    assert all(x.status == "in_stock" for x in _rows(db, w['pc']))


def test_sale_count_rule_still_enforced(client, db, w, received):
    r = client.login(w['padmin']).post('/api/sales/', json=_sale_body(received['prod'], 2, w['pwh'], received['codes'][:1]))
    assert r.status_code == 400 and "markirovka talab qilinadi" in r.json()['detail']


def test_other_company_cannot_sell_foreign_code(client, db, w, received):
    """Q dorixonasi P kodini sota olmaydi (Q'da bu kod yo'q); Q o'z mahsuloti bilan ham."""
    prod_q = _product(db, w['qc'])
    po = _po(client, w['qadmin'], w['qwh'], w['qsup'], prod_q, 1)
    assert _receive_api(client, w['qadmin'], po, 1).status_code == 200
    r = client.login(w['qadmin']).post('/api/sales/', json=_sale_body(prod_q, 1, w['qwh'], [received['codes'][0]]))
    assert r.status_code == 400 and "topilmadi" in r.json()['detail']
    assert [x.status for x in _rows(db, w['pc'], serial="SER0001")] == ["in_stock"]


def test_code_belonging_to_other_product_is_400(client, db, w, received):
    prod2 = _product(db, w['pc'])
    po = _po(client, w['padmin'], w['pwh'], w['psup'], prod2, 1)
    assert _receive_api(client, w['padmin'], po, 1).status_code == 200
    r = client.login(w['padmin']).post('/api/sales/', json=_sale_body(prod2, 1, w['pwh'], [received['codes'][0]]))
    assert r.status_code == 400 and "boshqa mahsulotga" in r.json()['detail']


def test_same_code_can_exist_in_two_companies(client, db, w, received):
    prod_q = _product(db, w['qc'])
    po = _po(client, w['qadmin'], w['qwh'], w['qsup'], prod_q, 1)
    assert _receive_api(client, w['qadmin'], po, 1).status_code == 200
    r = client.login(w['qadmin']).post('/api/pharmacy/marking/receive', json={
        'po_id': po['id'], 'items': [{'po_item_id': po['items'][0]['id'], 'marking_codes': [received['codes'][0]]}]})
    assert r.status_code == 200, r.text
    assert len(_rows(db, w['qc'])) == 1 and len(_rows(db, w['pc'])) == 3


# ───────────────────────── 4. Qaytarish ─────────────────────────

def _return(client, user, wh, prod, qty, sale_id, codes=None):
    item = {"product_id": prod.id, "quantity": qty}
    if codes is not None:
        item["marking_codes"] = codes
    return client.login(user).post("/api/sales/return", json={
        "items": [item], "payment_type": "cash", "paid_amount": qty * 1000, "paid_cash": qty * 1000,
        "warehouse_id": wh.id, "original_sale_id": sale_id})


def test_return_puts_codes_back_in_stock_and_they_can_be_resold(client, db, w, received):
    prod, codes = received['prod'], received['codes']
    cl = client.login(w['padmin'])
    sale = cl.post('/api/sales/', json=_sale_body(prod, 2, w['pwh'], codes[:2])).json()
    # kodsiz qaytarish: asl qatorning sotilgan kodlaridan miqdorcha
    r = _return(client, w['padmin'], w['pwh'], prod, 1, sale['id'])
    assert r.status_code == 200, r.text
    st = {x.serial: x for x in _rows(db, w['pc'])}
    assert st["SER0001"].status == "in_stock" and st["SER0001"].sale_item_id is None
    assert st["SER0001"].warehouse_id == w['pwh'].id
    assert st["SER0002"].status == "sold"
    # qaytgan kod qayta sotiladi
    assert cl.post('/api/sales/', json=_sale_body(prod, 1, w['pwh'], [codes[0]])).status_code == 200
    assert [x.status for x in _rows(db, w['pc'], serial="SER0001")] == ["sold"]


def test_return_with_explicit_code(client, db, w, received):
    prod, codes = received['prod'], received['codes']
    sale = client.login(w['padmin']).post('/api/sales/', json=_sale_body(prod, 2, w['pwh'], codes[:2])).json()
    r = _return(client, w['padmin'], w['pwh'], prod, 1, sale['id'], codes=[codes[1]])
    assert r.status_code == 200, r.text
    st = {x.serial: x.status for x in _rows(db, w['pc'])}
    assert st == {"SER0001": "sold", "SER0002": "in_stock", "SER0003": "in_stock"}


def test_return_of_unsold_code_is_400(client, db, w, received):
    prod, codes = received['prod'], received['codes']
    sale = client.login(w['padmin']).post('/api/sales/', json=_sale_body(prod, 1, w['pwh'], [codes[0]])).json()
    r = _return(client, w['padmin'], w['pwh'], prod, 1, sale['id'], codes=[codes[2]])    # SER0003 sotilmagan
    assert r.status_code == 400 and "sotilmagan" in r.json()['detail']
    assert {x.serial: x.status for x in _rows(db, w['pc'])}["SER0001"] == "sold"


# ───────────────────────── 5. Oddiy korxona (regressiya) ─────────────────────────

def test_plain_company_sale_and_return_unchanged(client, db, w):
    prod = _product(db, w['ac'])
    db.add(StockLevel(product_id=prod.id, warehouse_id=w['awh'].id, quantity=D(10)))
    db.flush()
    codes = [_gs_code("P1"), _gs_code("P2")]
    cl = client.login(w['aadmin'])
    # kod bazada yo'q — oddiy do'kon bloklanmaydi, faqat soni tekshiriladi (avvalgidek)
    r = cl.post('/api/sales/', json=_sale_body(prod, 2, w['awh'], codes))
    assert r.status_code == 200, r.text
    item = db.query(SaleItem).filter_by(sale_id=r.json()['id']).one()
    assert item.marking_codes == codes
    assert db.query(MarkingCode).count() == 0
    assert cl.post('/api/sales/', json=_sale_body(prod, 2, w['awh'], codes[:1])).status_code == 400
    # takror sotuv oddiy do'konda 400 emas (kuzatuv faqat dorixonada)
    assert cl.post('/api/sales/', json=_sale_body(prod, 2, w['awh'], codes)).status_code == 200
    # qaytarish: kod holati yo'q, SaleItem.marking_codes yozilmaydi
    r = _return(client, w['aadmin'], w['awh'], prod, 1, r.json()['id'])
    assert r.status_code == 200, r.text
    ret_item = db.query(SaleItem).filter_by(sale_id=r.json()['id']).one()
    assert ret_item.marking_codes is None
    assert db.query(MarkingCode).count() == 0


def test_plain_company_pharmacy_module_off_after_expiry_not_blocked(client, db, w):
    """Dorixona paketi tugagan korxona ham oddiy do'kondek: kodlar bazada bo'lmasa ham sotuv o'tadi."""
    for pkg in db.query(CompanyPackage).filter_by(company_id=w['qc'].id):
        pkg.ends_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    prod = _product(db, w['qc'])
    db.add(StockLevel(product_id=prod.id, warehouse_id=w['qwh'].id, quantity=D(5)))
    db.flush()
    r = client.login(w['qadmin']).post('/api/sales/', json=_sale_body(prod, 1, w['qwh'], [_gs_code("E1")]))
    assert r.status_code == 200, r.text


# ───────────────────────── 6. Izolyatsiya va ro'yxat ─────────────────────────

def test_cross_company_receive_endpoint_is_404(client, db, w, received):
    r = client.login(w['qadmin']).post('/api/pharmacy/marking/receive', json={
        'po_id': received['po']['id'],
        'items': [{'po_item_id': received['po']['items'][0]['id'], 'marking_codes': [_gs_code("HACK")]}]})
    assert r.status_code == 404
    assert db.query(MarkingCode).filter_by(company_id=w['qc'].id).count() == 0


def test_list_shows_only_own_company_and_filters(client, db, w, received):
    prod = received['prod']
    sale = client.login(w['padmin']).post('/api/sales/', json=_sale_body(prod, 1, w['pwh'], [received['codes'][0]]))
    assert sale.status_code == 200
    r = client.login(w['padmin']).get('/api/pharmacy/marking')
    assert r.status_code == 200 and len(r.json()) == 3
    r = client.login(w['padmin']).get('/api/pharmacy/marking', params={'status': 'sold'})
    assert [x['serial'] for x in r.json()] == ['SER0001']
    r = client.login(w['padmin']).get('/api/pharmacy/marking', params={'code': received['codes'][1]})
    assert [x['serial'] for x in r.json()] == ['SER0002']
    assert client.login(w['qadmin']).get('/api/pharmacy/marking').json() == []
    assert client.login(w['aadmin']).get('/api/pharmacy/marking').status_code == 403


# ───────────────────────── 7. Frontend / migratsiya ─────────────────────────

def test_frontend_wiring_and_i18n_keys():
    pending = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D3.2.json").read_text(encoding='utf-8'))
    assert set(pending) == {'uz', 'ru', 'en'}
    assert set(pending['uz']) == set(pending['ru']) == set(pending['en']) and pending['uz']
    src = (ROOT / 'frontend' / 'src' / 'pages' / 'admin' / 'Purchases.jsx').read_text(encoding='utf-8')
    assert "/pharmacy/marking/parse" in src and "/pharmacy/marking/receive" in src and "marking_codes" in src
    assert all(k in src for k in pending['uz'])


def test_migration_matches_model():
    src = (ROOT / 'alembic' / 'versions' / 'd3_2_marking_codes.py').read_text(encoding='utf-8')
    assert "revision: str = 'd3_2'" in src and "down_revision" in src and "= 'd2_5'" in src
    for col in MarkingCode.__table__.columns:
        assert col.name in src, col.name
    assert "uq_marking_codes_company_code" in src
