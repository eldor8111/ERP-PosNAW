"""P.11 — Dorixona: qadoqli (quti/blister birligi bor) markirovkali dorini dona qilib (`unit_id` siz) sotish.

Bu qutidan bo'lib sotish: kod ixtiyoriy (ko'pi bilan ochilgan quti kodi, holati o'zgarmaydi) — `unit_id` li blister
sotuvidagi (CD.1) qoida bilan bir xil. Avval server dona soniga teng kod talab qilardi (kassada bajarib bo'lmaydi).
Qadoqsiz markirovkali dori, `unit_id` li butun quti va oddiy korxona uchun qoida o'zgarmagan.
"""
from tests.branch_audit.test_CD_1 import (   # noqa: F401  (w — pytest fixture)
    _code, _mcode, _mrow, _pending, _post_sale, _product, _stock, _unit, w,
)


def test_pharmacy_dona_of_boxed_marked_drug_needs_no_codes(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    _unit(db, p, "quti", 20)
    _stock(db, p, w["pwh"], 100)
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 3, "unit_price": 1000}])
    assert r.status_code == 200, r.text


def test_pharmacy_dona_open_box_code_optional_and_stays_in_stock(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    _unit(db, p, "quti", 20)
    b = _stock(db, p, w["pwh"], 100)
    _mcode(db, w["pc"], p, "OB1", w["pwh"], b)
    _mcode(db, w["pc"], p, "OB2", w["pwh"], b)
    r = _post_sale(client, w["padmin"], w["pwh"], [
        {"product_id": p.id, "quantity": 2, "unit_price": 1000, "marking_codes": [_code("OB1")]}])
    assert r.status_code == 200, r.text
    assert _mrow(db, w["pc"], _code("OB1")).status == "in_stock"     # ochilgan quti kodi — sotilgan deb belgilanmaydi
    # 3 dona, 2 kod: na qutidan bo'lib sotish (ko'pi bilan 1), na eski qoida (kod soni = miqdor) — rad
    r = _post_sale(client, w["padmin"], w["pwh"], [
        {"product_id": p.id, "quantity": 3, "unit_price": 1000, "marking_codes": [_code("OB1"), _code("OB2")]}])
    assert r.status_code == 400 and "ochilgan quti kodini" in r.json()["detail"]


def test_pharmacy_unpacked_marked_drug_rule_unchanged(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)                 # qadoq birligi yo'q
    _stock(db, p, w["pwh"], 100)
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 3, "unit_price": 1000}])
    assert r.status_code == 400 and "markirovka talab qilinadi" in r.json()["detail"]


def test_pharmacy_whole_box_still_needs_codes(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    box = _unit(db, p, "quti", 20)
    _stock(db, p, w["pwh"], 100)
    r = _post_sale(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 1, "unit_id": box.id}])
    assert r.status_code == 400 and "1 ta kod" in r.json()["detail"]


def test_regular_company_rule_unchanged(client, db, w):
    p = _product(db, w["nc"], requires_marking=True)
    _unit(db, p, "quti", 20)                                         # oddiy korxonada birlik qo'llanmaydi
    _stock(db, p, w["nwh"], 100)
    r = _post_sale(client, w["nadmin"], w["nwh"], [{"product_id": p.id, "quantity": 3, "unit_price": 1000}])
    assert r.status_code == 400 and "markirovka talab qilinadi" in r.json()["detail"]


def test_pharmacy_confirm_pending_dona_of_boxed_marked_drug(client, db, w):
    p = _product(db, w["pc"], requires_marking=True)
    _unit(db, p, "quti", 20)
    _stock(db, p, w["pwh"], 100)
    sid = _pending(client, w["padmin"], w["pwh"], [{"product_id": p.id, "quantity": 3, "unit_price": 1000}])
    r = client.login(w["padmin"]).put(f"/api/sales/{sid}", json={"status": "completed", "paid_amount": 3000})
    assert r.status_code == 200, r.text
