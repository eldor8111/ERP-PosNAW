"""Tasnif dori nomidan qisqa tovar nomi (brend + doza + qadoqdagi soni).

Tasnifning rasmiy nomi juda uzun ("Ципрофлоксацин - J01MA02: ЦИПРОФЛОКСАЦИН-АДЖИО (Agio Pharmaceuticals),
Таблеткалар, плёнка билан қопланган 500 мг блистерлар №100(10x10)"); "Dori qo'shish" oynasi va kassadagi
"+ Yangi" nom maydoniga `short_name` yoziladi, to'liq nom va MXIK o'zgarmaydi.
"""
import os

import pytest

from app.models.tovarlar_catalog import TovarlarCatalog
from app.routers.pharmacy_catalog import short_drug_name
from tests.branch_audit.test_P_5 import fake_tasnif, pharm   # noqa: F401  (pytest fixture)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


@pytest.mark.parametrize("name,brand,attribute,want", [
    ("Ципрофлоксацин - J01MA02: ЦИПРОФЛОКСАЦИН-АДЖИО (Agio Pharmaceuticals), Таблеткалар, плёнка билан "
     "қопланган 500 мг блистерлар №100(10x10)", None, None, "Ципрофлоксацин-Аджио 500 мг №100"),
    ('Парацетамол - N02BE01: ПАРАЦЕТАМОЛ (ООО "Фармстандарт-Лексредства", Россия), Таблеткалар 500 мг №10',
     None, None, "Парацетамол 500 мг №10"),
    ("Амброксол - R05CB06: ЛАЗОЛВАН® (Boehringer Ingelheim), Сироп 15 мг/5 мл 100 мл", None, None, "Лазолван 15 мг/5 мл"),
    ("Дротаверин - A03AD02: НО-ШПА (Chinoin), Таблеткалар 40 мг №24", None, None, "НО-ШПА 40 мг №24"),
    ("Ацетилцистеин - R05CB01: АЦЦ 200 (Hexal), Кукун 200 мг №20", None, None, "АЦЦ 200 мг №20"),
    ("x - Y: NUROFEN (Reckitt), Таблеткалар", None, "200 мг №12", "Nurofen 200 мг №12"),
    ("Сулфацетамид - S01AB04: СУЛЬФАЦИЛ (Фармак), Кўз томчилари 200 мг/мл 10мл флаконлар", "СУЛЬФАЦИЛ (Фармак)",
     "Кўз томчилари 200 мг/мл 10мл флаконлар", "Сульфацил 200 мг/мл"),
])
def test_short_drug_name(name, brand, attribute, want):
    assert short_drug_name(name, brand, attribute) == want


def test_non_drug_name_is_not_shortened():
    assert short_drug_name("Бинт стерильный 5м х 10см") is None
    assert short_drug_name("") is None and short_drug_name(None) is None


def test_tasnif_search_and_barcode_return_short_name(client, db, pharm, fake_tasnif):
    _, _, _, u = pharm
    cl = client.login(u)
    (d,) = cl.get('/api/pharmacy/tasnif/search', params={'q': 'эналозид'}).json()
    assert d['short_name'] == 'Эналозид №20' and d['name'].startswith('Эналаприл ва диуретиклар')
    db.add(TovarlarCatalog(barcode='4780000001234', mxik_code='03004001001000005',
                           mxik_name='Парацетамол - N02BE01: Парацетамол (Nika), таблеткалар 500 мг'))
    db.flush()
    r = cl.get('/api/pharmacy/tasnif/barcode/4780000001234')
    assert r.status_code == 200 and r.json()['short_name'] == 'Парацетамол 500 мг'
    r = cl.get('/api/mxik/barcode/4780000001234')
    assert r.status_code == 200 and r.json()['short_name'] == 'Парацетамол 500 мг'
    assert r.json()['mxik_name'].startswith('Парацетамол - N02BE01')   # to'liq nom ham qaytadi


def test_frontend_uses_short_name():
    with open(os.path.join(ROOT, 'frontend/src/components/PharmacyProductModal.jsx'), encoding='utf-8') as f:
        modal = f.read()
    with open(os.path.join(ROOT, 'frontend/src/components/TasnifSearch.jsx'), encoding='utf-8') as f:
        search = f.read()
    assert 'd.short_name || d.name' in modal and 'd.short_name || d.name' in search
