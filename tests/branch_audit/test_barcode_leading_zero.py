"""Shtrix-kod boshidagi 0 lar farqi (dorixona).

Skaner 12 xonali UPC-A ni EAN-13 qilib boshiga "0" qo'shadi; Excel importi boshidagi 0 ni o'chiradi —
kassada "shtrix-kod boshiga raqam qo'shilib, dori topilmaydi". GET /products/barcode/{kod} dorixonada
8-14 xonali raqamli kodni nollarsiz ham solishtiradi. Oddiy korxona va qisqa kodlar o'zgarishsiz.
"""
from app.models.product import Product
from tests.branch_audit.test_P_5 import pharm   # noqa: F401  (pytest fixture)


def _p(db, c, barcode, n, extra=None):
    p = Product(name=f"Dori {n}", sku=f"Z-{c.id}-{n}", barcode=barcode, company_id=c.id, sale_price=1000,
                extra_barcodes=extra)
    db.add(p)
    db.flush()
    return p


def test_pharmacy_scan_with_extra_or_missing_leading_zero(client, db, pharm):
    c, _, _, u = pharm
    upc = _p(db, c, "123456789012", 1)                 # 12 xonali UPC-A bazada
    excel = _p(db, c, "12345678905", 2)                # Excel boshidagi 0 ni o'chirgan
    full = _p(db, c, "0712345678901", 3)              # 13 xonali, boshida 0
    ext = _p(db, c, "4780000000011", 4, extra='["03600029145"]')
    db.commit()
    cl = client.login(u)
    assert cl.get('/api/products/barcode/0123456789012').json()["id"] == upc.id     # skaner "0" qo'shgan
    assert cl.get('/api/products/barcode/012345678905').json()["id"] == excel.id
    assert cl.get('/api/products/barcode/712345678901').json()["id"] == full.id     # skaner 0 siz yuborgan
    assert cl.get('/api/products/barcode/0003600029145').json()["id"] == ext.id     # qo'shimcha shtrix-kod
    assert cl.get('/api/products/barcode/1123456789012').status_code == 404          # boshqa raqam — topilmaydi


def test_regular_company_and_short_codes_unchanged(client, db, mk, pharm):
    c, _, _, u = mk.tenant()
    _p(db, c, "123456789012", 1)
    pc, _, _, pu = pharm
    _p(db, pc, "1234567", 2)                           # EAN-8 "01234567" dan Excel 0 ni o'chirgan — topiladi
    _p(db, pc, "12345", 3)                             # qisqa ichki kod (5 xona) — nollarsiz moslashtirilmaydi
    db.commit()
    assert client.login(u).get('/api/products/barcode/0123456789012').status_code == 404
    assert client.login(pu).get('/api/products/barcode/01234567').status_code == 200
    assert client.login(pu).get('/api/products/barcode/00012345').status_code == 404
