"""D2.1 — Dori ma'lumotlari modeli va moddalar ma'lumotnomasi.

Qamrov:
 1. Dorixona korxonasida mahsulot yaratish/tahrirlash `pharma` blokini saqlaydi, javobda moddalari bilan qaytadi.
 2. Oddiy korxonada `pharma` e'tiborsiz qoldiriladi, javobda `null` (regressiya), MXIK talab qilinmaydi.
 3. Dorixona rejimida MXIK majburiy (yaratish va tahrirlash, 400); oddiy korxonada majburiy emas.
 4. Ro'yxat endpoint'i N+1 yaratmaydi (pharma/modda so'rovlari mahsulot soniga bog'liq emas).
 5. Moddalar ma'lumotnomasi: umumiy + o'z korxonasi; begona korxona moddasi ko'rinmaydi/o'zgarmaydi;
    umumiy modda o'zgarmaydi; modul o'chiq korxonada 403; seed idempotent (50 ta).
 6. Begona korxona moddasini mahsulotga bog'lab bo'lmaydi (404).
"""
import py_compile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import event

from app.models.billing import CompanyPackage
from app.models.product import Product
from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
from app.routers import pharmacy_catalog
from tests.branch_audit.conftest import engine

PRODUCTS = '/api/products/'
SUBST = '/api/pharmacy/substances'


def _pharmacy_on(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _payload(name, barcode, **kw):
    d = {"name": name, "barcode": barcode, "sale_price": "1000", "mxik_code": "30040000000000000"}
    d.update(kw)
    return d


def _substance(db, name, company=None, lat=None):
    s = PharmaSubstance(company_id=company.id if company else None, name_uz=name, name_lat=lat or name)
    db.add(s)
    db.flush()
    return s


PHARMA = {
    "dosage_form": "tablet", "strength": "500 mg", "pack_qty": 20, "manufacturer": "Nika Pharm",
    "country": "O'zbekiston", "reg_number": "DV/M 01234/01/24", "reg_valid_until": "2030-01-31",
    "atc_code": "N02BE01", "storage": "room", "is_rx": True, "control_class": "potent",
    "max_retail_price": "15000",
}


# ---------------------------------------------------------------- dorixona: yaratish / tahrirlash

def test_pharmacy_create_saves_pharma_with_substances(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    s1 = _substance(db, "Paratsetamol")            # umumiy
    s2 = _substance(db, "Maxsus modda", company=c)  # o'z korxonasi
    cl = client.login(admin)
    r = cl.post(PRODUCTS, json=_payload("Panadol", "4780000000011",
                                        pharma={**PHARMA, "substance_ids": [s1.id, s2.id, s1.id]}))
    assert r.status_code == 201, r.text
    ph = r.json()["pharma"]
    assert ph["dosage_form"] == "tablet" and ph["strength"] == "500 mg" and ph["pack_qty"] == 20
    assert ph["is_rx"] is True and ph["control_class"] == "potent" and ph["storage"] == "room"
    assert ph["reg_valid_until"] == "2030-01-31" and Decimal(ph["max_retail_price"]) == Decimal("15000")
    assert {s["id"] for s in ph["substances"]} == {s1.id, s2.id}
    assert all({"id", "name_uz", "name_ru", "name_lat"} <= set(s) for s in ph["substances"])
    pid = r.json()["id"]
    # GET bitta mahsulot va shtrix-kod bo'yicha ham pharma qaytaradi
    assert cl.get(f"{PRODUCTS}{pid}").json()["pharma"]["atc_code"] == "N02BE01"
    assert cl.get(f"{PRODUCTS}barcode/4780000000011").json()["pharma"]["atc_code"] == "N02BE01"
    assert db.query(ProductSubstance).filter_by(product_id=pid).count() == 2


def test_pharmacy_update_merges_fields_and_replaces_substances(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    s1, s2 = _substance(db, "Modda A"), _substance(db, "Modda B")
    cl = client.login(admin)
    pid = cl.post(PRODUCTS, json=_payload("Dori 1", "4780000000028",
                                          pharma={**PHARMA, "substance_ids": [s1.id]})).json()["id"]
    # faqat bir nechta maydon + moddalarni almashtirish; qolganlari saqlanadi
    r = cl.put(f"{PRODUCTS}{pid}", json={"pharma": {"strength": "250 mg", "substance_ids": [s2.id]}})
    assert r.status_code == 200, r.text
    ph = r.json()["pharma"]
    assert ph["strength"] == "250 mg" and ph["dosage_form"] == "tablet" and ph["is_rx"] is True
    assert [s["id"] for s in ph["substances"]] == [s2.id]
    # substance_ids berilmasa moddalar o'zgarmaydi
    r = cl.put(f"{PRODUCTS}{pid}", json={"pharma": {"country": "Hindiston"}})
    ph = r.json()["pharma"]
    assert ph["country"] == "Hindiston" and [s["id"] for s in ph["substances"]] == [s2.id]
    # bo'sh ro'yxat moddalarni tozalaydi
    r = cl.put(f"{PRODUCTS}{pid}", json={"pharma": {"substance_ids": []}})
    assert r.json()["pharma"]["substances"] == []
    # pharma yuborilmasa blok o'zgarmaydi; 1:1 — bitta qator
    r = cl.put(f"{PRODUCTS}{pid}", json={"min_stock": 3})
    assert r.status_code == 200 and r.json()["pharma"]["country"] == "Hindiston"
    assert db.query(ProductPharma).filter_by(product_id=pid).count() == 1


def test_pharmacy_product_without_pharma_block_is_null(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    r = client.login(admin).post(PRODUCTS, json=_payload("Oddiy tovar", "4780000000035"))
    assert r.status_code == 201, r.text
    assert r.json()["pharma"] is None
    # keyin pharma qo'shsa bo'ladi
    pid = r.json()["id"]
    r = client.login(admin).put(f"{PRODUCTS}{pid}", json={"pharma": {"dosage_form": "syrup"}})
    assert r.json()["pharma"]["dosage_form"] == "syrup"
    assert r.json()["pharma"]["control_class"] == "none" and r.json()["pharma"]["is_rx"] is False


def test_pharma_validation_errors(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    cl = client.login(admin)
    r = cl.post(PRODUCTS, json=_payload("X", "4780000000042", pharma={"dosage_form": "pill"}))
    assert r.status_code == 422
    r = cl.post(PRODUCTS, json=_payload("X", "4780000000042", pharma={"storage": "attic"}))
    assert r.status_code == 422
    r = cl.post(PRODUCTS, json=_payload("X", "4780000000042", pharma={"control_class": "illegal"}))
    assert r.status_code == 422
    r = cl.post(PRODUCTS, json=_payload("X", "4780000000042", pharma={"max_retail_price": "-1"}))
    assert r.status_code == 422
    # bo'sh qator = tanlanmagan
    r = cl.post(PRODUCTS, json=_payload("X", "4780000000042", pharma={"dosage_form": "", "storage": ""}))
    assert r.status_code == 201, r.text
    assert r.json()["pharma"]["dosage_form"] is None


# ---------------------------------------------------------------- MXIK majburiy

def test_pharmacy_requires_mxik_on_create_and_update(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    cl = client.login(admin)
    r = cl.post(PRODUCTS, json={"name": "MXIKsiz", "barcode": "4780000000059", "sale_price": "10"})
    assert r.status_code == 400 and "MXIK" in r.json()["detail"]
    r = cl.post(PRODUCTS, json=_payload("MXIKsiz", "4780000000059", mxik_code="   "))
    assert r.status_code == 400
    assert db.query(Product).filter_by(company_id=c.id).count() == 0

    # eski mahsulot (MXIKsiz) tahrirlanganda ham 400; MXIK berilsa o'tadi
    old = Product(company_id=c.id, name="Eski", barcode="4780000000066", sku="OLD-1", sale_price=10, cost_price=0)
    db.add(old)
    db.flush()
    r = cl.put(f"{PRODUCTS}{old.id}", json={"min_stock": 5})
    assert r.status_code == 400 and "MXIK" in r.json()["detail"]
    r = cl.put(f"{PRODUCTS}{old.id}", json={"min_stock": 5, "mxik_code": "30040000000000000"})
    assert r.status_code == 200, r.text
    # MXIK bor mahsulot keyingi tahrirda MXIK yubormasdan ham o'tadi
    assert cl.put(f"{PRODUCTS}{old.id}", json={"min_stock": 6}).status_code == 200
    # MXIKni bo'shatib bo'lmaydi
    assert cl.put(f"{PRODUCTS}{old.id}", json={"mxik_code": ""}).status_code == 400


# ---------------------------------------------------------------- oddiy korxona (regressiya)

def test_regular_company_pharma_ignored_and_null(client, db, mk):
    c, _, _, admin = mk.tenant()
    s1 = _substance(db, "Umumiy modda")
    cl = client.login(admin)
    # MXIKsiz yaratish avvalgidek mumkin
    r = cl.post(PRODUCTS, json={"name": "Non", "barcode": "4780000000073", "sale_price": "5000"})
    assert r.status_code == 201, r.text
    assert r.json()["pharma"] is None
    # pharma yuborilsa e'tiborsiz qoldiriladi
    r = cl.post(PRODUCTS, json=_payload("Dori emas", "4780000000080", pharma={**PHARMA, "substance_ids": [s1.id]}))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["pharma"] is None
    assert db.query(ProductPharma).count() == 0 and db.query(ProductSubstance).count() == 0
    r = cl.put(f"{PRODUCTS}{pid}", json={"pharma": {"strength": "1 g"}, "min_stock": 2})
    assert r.status_code == 200 and r.json()["pharma"] is None and r.json()["min_stock"] == 2
    assert db.query(ProductPharma).count() == 0
    # ro'yxat va shtrix-kod ham pharma: null
    rows = cl.get(PRODUCTS, params={"limit": 100}).json()
    assert rows and all(row["pharma"] is None for row in rows)
    assert cl.get(f"{PRODUCTS}barcode/4780000000080").json()["pharma"] is None
    # MXIKsiz mahsulotni tahrirlash avvalgidek
    nid = [x for x in rows if x["barcode"] == "4780000000073"][0]["id"]
    assert cl.put(f"{PRODUCTS}{nid}", json={"min_stock": 1}).status_code == 200


def test_module_off_even_with_old_pharma_rows_returns_null(client, db, mk):
    """Modul keyin o'chirilsa, bazadagi dori bloki API'da ko'rinmaydi."""
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    cl = client.login(admin)
    pid = cl.post(PRODUCTS, json=_payload("Dori", "4780000000097", pharma=PHARMA)).json()["id"]
    c.pharmacy_enabled = False
    db.flush()
    assert cl.get(f"{PRODUCTS}{pid}").json()["pharma"] is None


# ---------------------------------------------------------------- N+1

def test_list_has_no_n_plus_one(client, db, mk):
    c, _, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    subs = [_substance(db, f"M{i}") for i in range(3)]
    cl = client.login(admin)

    def make(n):
        for i in range(n):
            code = f"47800001{n:02d}{i:02d}"
            r = cl.post(PRODUCTS, json=_payload(f"Dori {n}-{i}", code,
                                                pharma={**PHARMA, "substance_ids": [s.id for s in subs]}))
            assert r.status_code == 201, r.text

    def count_pharma_queries():
        stmts = []

        def _before(conn, cursor, statement, params, context, executemany):
            low = statement.lower()
            if "from product_pharma" in low or "from product_substances" in low:
                stmts.append(statement)

        event.listen(engine, "before_cursor_execute", _before)
        try:
            r = cl.get(PRODUCTS, params={"limit": 100})
        finally:
            event.remove(engine, "before_cursor_execute", _before)
        assert r.status_code == 200
        return len(stmts), r.json()

    make(2)
    q_small, rows = count_pharma_queries()
    make(6)
    q_big, rows = count_pharma_queries()
    assert len(rows) == 8
    assert q_small == q_big and q_big <= 2
    assert all(len(row["pharma"]["substances"]) == 3 for row in rows)


# ---------------------------------------------------------------- moddalar ma'lumotnomasi

def test_substances_catalog_isolation_and_crud(client, db, mk):
    a, _, _, admin_a = mk.tenant()
    b, _, _, admin_b = mk.tenant()
    _pharmacy_on(db, a)
    _pharmacy_on(db, b)
    common = _substance(db, "Umumiy paratsetamol")
    cl_a, cl_b = client.login(admin_a), None

    r = cl_a.post(SUBST, json={"name_uz": "A moddasi", "name_ru": "Вещество А", "name_lat": "Substantia A"})
    assert r.status_code == 201, r.text
    sa = r.json()
    assert sa["company_id"] == a.id and sa["is_common"] is False

    # A: umumiy + o'ziniki; B: faqat umumiy
    ids_a = {s["id"] for s in cl_a.get(SUBST).json()}
    assert {common.id, sa["id"]} <= ids_a
    cl_b = client.login(admin_b)
    ids_b = {s["id"] for s in cl_b.get(SUBST).json()}
    assert common.id in ids_b and sa["id"] not in ids_b
    assert cl_b.get(SUBST, params={"search": "A moddasi"}).json() == []

    # B begona moddani o'zgartira/o'chira olmaydi
    assert cl_b.put(f"{SUBST}/{sa['id']}", json={"name_uz": "Buzildi"}).status_code == 404
    assert cl_b.delete(f"{SUBST}/{sa['id']}").status_code == 404
    assert db.get(PharmaSubstance, sa["id"]).name_uz == "A moddasi"

    # A: o'zini tahrirlaydi, qidiruv uz/ru/lotin bo'yicha
    cl_a = client.login(admin_a)
    r = cl_a.put(f"{SUBST}/{sa['id']}", json={"name_uz": "A moddasi 2", "name_ru": "Вещество А2", "name_lat": "Subst A2"})
    assert r.status_code == 200 and r.json()["name_uz"] == "A moddasi 2"
    for term in ("moddasi 2", "Вещество", "subst a2"):
        assert [s["id"] for s in cl_a.get(SUBST, params={"search": term}).json()] == [sa["id"]], term
    # '%' maxsus belgi sifatida talqin qilinmaydi
    assert cl_a.get(SUBST, params={"search": "%"}).json() == []

    # umumiy moddani o'zgartirib/o'chirib bo'lmaydi
    assert cl_a.put(f"{SUBST}/{common.id}", json={"name_uz": "Buzildi"}).status_code == 403
    assert cl_a.delete(f"{SUBST}/{common.id}").status_code == 403
    assert db.get(PharmaSubstance, common.id).name_uz == "Umumiy paratsetamol"

    # takroriy nom (umumiy yoki o'zining) — 400
    assert cl_a.post(SUBST, json={"name_uz": "umumiy PARATSETAMOL"}).status_code == 400
    assert cl_a.post(SUBST, json={"name_uz": "a moddasi 2"}).status_code == 400
    assert cl_a.post(SUBST, json={"name_uz": "   "}).status_code == 422
    # B shu nomni o'zi uchun qo'sha oladi (A moddasi unga ko'rinmaydi)
    assert client.login(admin_b).post(SUBST, json={"name_uz": "A moddasi 2"}).status_code == 201

    # ishlatilayotgan moddani o'chirib bo'lmaydi (409); bog'lanish olib tashlangach o'chadi
    cl_a = client.login(admin_a)
    pid = cl_a.post(PRODUCTS, json=_payload("Dori", "4780000000103",
                                            pharma={"substance_ids": [sa["id"]]})).json()["id"]
    assert cl_a.delete(f"{SUBST}/{sa['id']}").status_code == 409
    cl_a.put(f"{PRODUCTS}{pid}", json={"pharma": {"substance_ids": []}})
    assert cl_a.delete(f"{SUBST}/{sa['id']}").status_code == 204
    assert db.get(PharmaSubstance, sa["id"]) is None


def test_foreign_substance_cannot_be_attached(client, db, mk):
    a, _, _, admin_a = mk.tenant()
    b, _, _, _ = mk.tenant()
    _pharmacy_on(db, a)
    foreign = _substance(db, "B moddasi", company=b)
    cl = client.login(admin_a)
    r = cl.post(PRODUCTS, json=_payload("Dori", "4780000000110", pharma={"substance_ids": [foreign.id]}))
    assert r.status_code == 404
    ok = cl.post(PRODUCTS, json=_payload("Dori 2", "4780000000127"))
    pid = ok.json()["id"]
    r = cl.put(f"{PRODUCTS}{pid}", json={"pharma": {"substance_ids": [foreign.id]}})
    assert r.status_code == 404
    assert db.query(ProductSubstance).filter_by(product_id=pid).count() == 0
    assert db.get(PharmaSubstance, foreign.id).name_uz == "B moddasi"


def test_catalog_closed_for_regular_company(client, db, mk):
    c, _, _, admin = mk.tenant()
    _substance(db, "Umumiy")
    cl = client.login(admin)
    assert cl.get(SUBST).status_code == 403
    assert cl.post(SUBST, json={"name_uz": "X"}).status_code == 403
    assert cl.put(f"{SUBST}/1", json={"name_uz": "X"}).status_code == 403
    assert cl.delete(f"{SUBST}/1").status_code == 403


def test_catalog_write_requires_write_role(client, db, mk):
    from app.models.user import UserRole
    c, b, _, admin = mk.tenant()
    _pharmacy_on(db, c)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    cl = client.login(cashier)
    assert cl.get(SUBST).status_code == 200
    assert cl.post(SUBST, json={"name_uz": "X"}).status_code == 403


# ---------------------------------------------------------------- seed va fayllar

def test_seed_is_idempotent_and_has_50_common(db, monkeypatch):
    import app.database as app_database
    from sqlalchemy.orm import sessionmaker
    assert len(pharmacy_catalog.COMMON_SUBSTANCES) == 50
    assert len({lat.lower() for _, _, lat in pharmacy_catalog.COMMON_SUBSTANCES}) == 50
    # seed o'z sessiyasini ochadi va commit qiladi — test tranzaksiyasiga ulaymiz
    monkeypatch.setattr(app_database, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    before = db.query(PharmaSubstance).filter(PharmaSubstance.company_id.is_(None)).count()
    added = pharmacy_catalog.seed_pharma_substances()
    assert added == 50 - before
    total = db.query(PharmaSubstance).filter(PharmaSubstance.company_id.is_(None)).count()
    assert total == before + added
    assert pharmacy_catalog.seed_pharma_substances() == 0
    assert db.query(PharmaSubstance).filter(PharmaSubstance.company_id.is_(None)).count() == total
    names = {s.name_uz for s in db.query(PharmaSubstance).filter(PharmaSubstance.company_id.is_(None)).all()}
    assert "Paratsetamol" in names and "Ibuprofen" in names and "Amoksitsillin" in names


def test_migration_compiles_and_wired():
    py_compile.compile("alembic/versions/d2_1_pharma_catalog.py", doraise=True)
    import importlib.util
    spec = importlib.util.spec_from_file_location("m", "alembic/versions/d2_1_pharma_catalog.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.revision == "d2_1" and m.down_revision == "d1_3"
    from app.main import app
    paths = set(app.openapi()["paths"])
    assert "/api/pharmacy/substances" in paths and "/api/pharmacy/substances/{substance_id}" in paths
