"""D2.3 — Modda bo'yicha qidiruv va analoglar.

Qamrov:
 1. Dorixona rejimida qidiruv (pos-list, paginated, ids) modda nomi uz/ru/lat bo'yicha ham topadi;
    "paratsetamol" == "парацетамол" == "paracetamol"; ko'p so'z (modda + nom) ishlaydi.
 2. Oddiy korxona (regressiya): modda bo'yicha topilmaydi, SQL'da modda jadvali yo'q, javobda yangi maydonlar yo'q.
 3. POS javobida dorixona maydonlari: substances, is_rx, control_class, nearest_expiry, expiry_warn
    (faqat joriy filial omborlaridagi yaroqli partiyalar).
 4. GET /products/{id}/analogs: modda to'plami teng, shakl/doza mos; qoldiqlilar avval, keyin arzonlari;
    boshqa filial/korxona qoldig'i yo'q; modul o'chiq — 404; begona korxona mahsuloti — 404.
 5. So'rovlar soni mahsulotlar soniga bog'liq emas (10 000 mahsulot, SQLite).

Eslatma: SQLite `lower()` faqat ASCII ni kichraytiradi, shuning uchun ruscha nom testda kichik harfda saqlanadi
(PostgreSQL'da ILIKE hamma harfni qamraydi).
"""
import itertools
import py_compile
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D

from sqlalchemy import event

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.branch_price import BranchProductPrice
from app.models.inventory import StockLevel
from app.models.product import Product
from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
from app.models.user import UserRole
from app.services.batch_allocator import tashkent_today

_n = itertools.count(1)


def _pharmacy_on(db, c, settings=None):
    c.pharmacy_enabled = True
    if settings:
        c.pharmacy_settings = settings
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=c.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _dt(days):
    return datetime.combine(tashkent_today() + timedelta(days=days), time(12, 0))


def _substance(db, uz, ru=None, lat=None, company=None):
    s = PharmaSubstance(company_id=company.id if company else None, name_uz=uz, name_ru=ru, name_lat=lat)
    db.add(s)
    db.flush()
    return s


def _drug(db, c, name, substances=(), form="tablet", strength="500 mg", price="1000", is_rx=False,
          control_class="none", **kw):
    n = next(_n)
    p = Product(name=name, sku=f"D23-{n}", barcode=f"BD23-{n:06d}", company_id=c.id,
                cost_price=D("500"), sale_price=D(price), **kw)
    db.add(p)
    db.flush()
    if form is not None or strength is not None or is_rx or control_class != "none":
        db.add(ProductPharma(product_id=p.id, company_id=c.id, dosage_form=form, strength=strength,
                             is_rx=is_rx, control_class=control_class, manufacturer="Nika Pharm"))
    for s in substances:
        db.add(ProductSubstance(product_id=p.id, substance_id=s.id))
    db.flush()
    return p


def _stock(db, p, wh, qty):
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty)))
    db.flush()


def _batch(db, p, wh, qty, expiry_days):
    b = Batch(product_id=p.id, warehouse_id=wh.id, quantity=D(qty), initial_quantity=D(qty),
              purchase_price=D(100), company_id=p.company_id,
              expiry_date=_dt(expiry_days) if expiry_days is not None else None)
    db.add(b)
    db.flush()
    return b


class _SqlLog:
    """Bajarilgan SQL so'rovlarini yig'adi."""

    def __init__(self, db):
        self.engine = db.get_bind().engine  # conftest bilan aynan bir xil engine (modul ikki marta yuklanishi mumkin)
        self.stmts = []

        def _hook(conn, cursor, statement, params, context, executemany):
            self.stmts.append(statement)

        self._hook = _hook

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._hook)
        return self

    def __exit__(self, *a):
        event.remove(self.engine, "before_cursor_execute", self._hook)

    @property
    def count(self):
        return len(self.stmts)


def _setup_pharmacy(db, mk, role=UserRole.admin):
    c, b, w, u = mk.tenant(role=role)
    _pharmacy_on(db, c)
    para = _substance(db, "Paratsetamol", "парацетамол", "Paracetamol")
    asp = _substance(db, "Atsetilsalitsil kislota", "ацетилсалициловая кислота", "Acidum acetylsalicylicum")
    panadol = _drug(db, c, "Panadol", [para])
    efferalgan = _drug(db, c, "Efferalgan", [para])
    aspirin = _drug(db, c, "Aspirin Kardio", [asp])
    vitamin = _drug(db, c, "Vitamin C", [], form=None, strength=None)
    return c, b, w, u, para, panadol, efferalgan, aspirin, vitamin


# ------------------------------------------------------------------ 1. qidiruv (dorixona)

def test_pharmacy_search_by_substance_in_all_languages(client, db, mk):
    c, b, w, u, para, panadol, efferalgan, aspirin, vitamin = _setup_pharmacy(db, mk)
    cl = client.login(u)
    expected = {panadol.id, efferalgan.id}
    for q in ("paratsetamol", "парацетамол", "paracetamol", "Paracetamol", "ПАРАЦЕТАМОЛ", "PARATSETAMOL"):
        ids = {x["id"] for x in cl.get("/api/products/pos-list", params={"search": q}).json()}
        assert ids == expected, (q, ids)
        ids2 = set(cl.get("/api/products/ids", params={"search": q}).json())
        assert ids2 == expected, (q, ids2)
        pag = cl.get("/api/products/paginated", params={"search": q}).json()
        assert {x["id"] for x in pag["items"]} == expected and pag["total"] == 2, q
    # boshqa modda boshqa mahsulotni topadi; nom bo'yicha qidiruv avvalgidek
    got = {x["id"] for x in cl.get("/api/products/pos-list", params={"search": "acetylsalicyl"}).json()}
    assert got == {aspirin.id}
    got = {x["id"] for x in cl.get("/api/products/pos-list", params={"search": "panadol"}).json()}
    assert got == {panadol.id}


def test_pharmacy_search_multiword_substance_plus_name(client, db, mk):
    c, b, w, u, para, panadol, efferalgan, aspirin, vitamin = _setup_pharmacy(db, mk)
    cl = client.login(u)
    got = {x["id"] for x in cl.get("/api/products/pos-list", params={"search": "paratsetamol panadol"}).json()}
    assert got == {panadol.id}
    got = {x["id"] for x in cl.get("/api/products/pos-list", params={"search": "парацетамол effer"}).json()}
    assert got == {efferalgan.id}
    # modda + mavjud bo'lmagan so'z -> hech narsa
    assert cl.get("/api/products/pos-list", params={"search": "paratsetamol yoq-nom"}).json() == []


def test_pharmacy_search_ignores_foreign_company_substance(client, db, mk):
    c, b, w, u, *_ = _setup_pharmacy(db, mk)
    c2, _, _, u2 = mk.tenant()
    _pharmacy_on(db, c2)
    own = _substance(db, "Maxsusmodda", "максусмодда", "Maxsusmodda", company=c2)
    p2 = _drug(db, c2, "B-korxona dorisi", [own])
    # A korxona B ning moddasini ko'rmaydi (va mahsulotini ham)
    assert client.login(u).get("/api/products/pos-list", params={"search": "maxsusmodda"}).json() == []
    # B o'z moddasi bo'yicha topadi
    got = client.login(u2).get("/api/products/pos-list", params={"search": "maxsusmodda"}).json()
    assert [x["id"] for x in got] == [p2.id]
    # A korxonasidagi mahsulotga B ning moddasi bog'langan bo'lsa ham, A qidiruvida topilmaydi
    pa = _drug(db, c, "A dorisi", [own])
    assert client.login(u).get("/api/products/pos-list", params={"search": "maxsusmodda"}).json() == []
    assert pa.id  # bog'lanish mavjud, lekin modda A uchun ko'rinmaydi


# ------------------------------------------------------------------ 2. oddiy korxona (regressiya)

def test_regular_company_search_unchanged(client, db, mk):
    c, b, w, u = mk.tenant()
    para = _substance(db, "Paratsetamol", "парацетамол", "Paracetamol")
    p = _drug(db, c, "Panadol", [para])
    q = _drug(db, c, "Un Turon", [], form=None, strength=None)
    cl = client.login(u)
    with _SqlLog(db) as log:
        r = cl.get("/api/products/pos-list", params={"search": "paratsetamol"})
    assert r.status_code == 200 and r.json() == []  # modda bo'yicha topilmaydi (modul o'chiq)
    assert not any("pharma_substances" in s or "product_substances" in s for s in log.stmts)
    with _SqlLog(db) as log:
        rows = cl.get("/api/products/pos-list", params={"search": "panadol"}).json()
    assert [x["id"] for x in rows] == [p.id]
    assert not any("pharma_substances" in s or "product_pharma" in s or "FROM batches" in s for s in log.stmts)
    for k in ("substances", "is_rx", "control_class", "nearest_expiry", "expiry_warn"):
        assert k not in rows[0]
    assert [x["id"] for x in cl.get("/api/products/pos-list", params={"search": "turon"}).json()] == [q.id]
    pag = cl.get("/api/products/paginated", params={"search": "paratsetamol"}).json()
    assert pag["items"] == [] and pag["total"] == 0
    assert cl.get("/api/products/ids", params={"search": "paratsetamol"}).json() == []


def test_regular_company_analogs_404(client, db, mk):
    c, b, w, u = mk.tenant()
    para = _substance(db, "Paratsetamol")
    p = _drug(db, c, "Panadol", [para])
    r = client.login(u).get(f"/api/products/{p.id}/analogs")
    assert r.status_code == 404


# ------------------------------------------------------------------ 3. POS qo'shimcha maydonlar

def test_pos_list_pharmacy_fields(client, db, mk):
    c, b, w, u, para, panadol, efferalgan, aspirin, vitamin = _setup_pharmacy(db, mk, role=UserRole.cashier)
    pharma = db.query(ProductPharma).filter_by(product_id=panadol.id).one()
    pharma.is_rx = True
    pharma.control_class = "potent"
    w2 = mk.warehouse(c, mk.branch(c))  # boshqa filial ombori
    c.pharmacy_settings = {"expiry_warn_days": 60, "expiry_block_days": 10}
    db.flush()
    _stock(db, panadol, w, 30)
    _batch(db, panadol, w, 5, -3)     # muddati o'tgan — hisobga olinmaydi
    _batch(db, panadol, w, 5, 5)      # P.13: expiry_block_days sotuvni bloklamaydi — eng yaqin yaroqli shu
    _batch(db, panadol, w, 10, 40)
    _batch(db, panadol, w, 10, 200)
    _batch(db, panadol, w2, 10, 15)   # boshqa filial — hisobga olinmaydi
    _batch(db, panadol, w, 0, 20)     # qoldig'i 0 — hisobga olinmaydi
    _stock(db, efferalgan, w, 5)
    _batch(db, efferalgan, w, 5, 300)  # uzoq muddat — warn yo'q
    _stock(db, aspirin, w, 5)
    _batch(db, aspirin, w, 5, None)    # muddatsiz partiya — nearest_expiry yo'q

    rows = {x["id"]: x for x in client.login(u).get("/api/products/pos-list", params={"limit": 50}).json()}
    r = rows[panadol.id]
    assert r["is_rx"] is True and r["control_class"] == "potent"
    assert r["nearest_expiry"] == (tashkent_today() + timedelta(days=5)).isoformat()
    assert r["expiry_warn"] is True
    assert [s["name_uz"] for s in r["substances"]] == ["Paratsetamol"]
    assert {"id", "name_uz", "name_ru", "name_lat"} <= set(r["substances"][0])
    e = rows[efferalgan.id]
    assert e["is_rx"] is False and e["control_class"] == "none"
    assert e["nearest_expiry"] == (tashkent_today() + timedelta(days=300)).isoformat() and e["expiry_warn"] is False
    a = rows[aspirin.id]
    assert a["nearest_expiry"] is None and a["expiry_warn"] is False
    v = rows[vitamin.id]  # pharma bloki yo'q mahsulot
    assert v["substances"] == [] and v["is_rx"] is False and v["control_class"] == "none"
    assert v["nearest_expiry"] is None and v["expiry_warn"] is False


# ------------------------------------------------------------------ 4. analoglar

def test_analogs_match_order_and_scope(client, db, mk):
    c, b, w, u, para, panadol, efferalgan, aspirin, vitamin = _setup_pharmacy(db, mk, role=UserRole.cashier)
    other_branch = mk.branch(c)
    w2 = mk.warehouse(c, other_branch)
    ibuprofen = _substance(db, "Ibuprofen", "ибупрофен", "Ibuprofen")
    # panadol (paratsetamol, tablet, 500 mg) analoglari
    cheap_nostock = _drug(db, c, "Paratsetamol arzon", [para], price="500")
    mid_stock = _drug(db, c, "Paratsetamol o'rta", [para], strength="500mg", price="1500")      # doza yozuvi boshqacha
    dear_stock = _drug(db, c, "Paratsetamol qimmat", [para], strength="500 MG", price="3000")
    only_expired = _drug(db, c, "Paratsetamol muddati o'tgan", [para], price="400")
    only_other_branch = _drug(db, c, "Paratsetamol boshqa filialda", [para], price="300")
    wrong_dose = _drug(db, c, "Paratsetamol 250", [para], strength="250 mg")
    wrong_form = _drug(db, c, "Paratsetamol sirop", [para], form="syrup")
    extra_substance = _drug(db, c, "Paratsetamol + ibuprofen", [para, ibuprofen])
    only_ibu = _drug(db, c, "Ibuprofen", [ibuprofen])
    no_substance = _drug(db, c, "Moddasiz", [])
    inactive = _drug(db, c, "Paratsetamol nofaol", [para])
    inactive.status = "inactive"
    deleted = _drug(db, c, "Paratsetamol o'chirilgan", [para])
    deleted.is_deleted = True
    db.flush()

    _stock(db, mid_stock, w, 10)
    _batch(db, mid_stock, w, 10, 100)
    _stock(db, dear_stock, w, 4)
    _batch(db, dear_stock, w, 4, None)
    _stock(db, only_expired, w, 7)
    _batch(db, only_expired, w, 7, -2)
    _stock(db, only_other_branch, w2, 50)       # boshqa filial qoldig'i
    _batch(db, only_other_branch, w2, 50, 100)
    _stock(db, efferalgan, w, 3)
    _batch(db, efferalgan, w, 3, 100)
    db.add(BranchProductPrice(company_id=c.id, branch_id=b.id, product_id=dear_stock.id,
                              sale_price=D("2500")))
    db.flush()

    cl = client.login(u)
    r = cl.get(f"/api/products/{panadol.id}/analogs")
    assert r.status_code == 200, r.text
    items = r.json()
    names = [i["name"] for i in items]
    # qoldiqlilar avval (arzoni birinchi), keyin qoldiqsizlar (arzoni birinchi)
    assert names == [
        "Efferalgan",                      # 1000, qoldiq 3
        "Paratsetamol o'rta",              # 1500, qoldiq 10
        "Paratsetamol qimmat",             # filial narxi 2500, qoldiq 4
        "Paratsetamol boshqa filialda",    # 300, bu filialda 0
        "Paratsetamol muddati o'tgan",     # 400, yaroqli 0
        "Paratsetamol arzon",              # 500, qoldiq 0
    ], names
    by = {i["name"]: i for i in items}
    assert panadol.id not in {i["id"] for i in items}
    assert by["Paratsetamol qimmat"]["sale_price"] == 2500.0 and by["Paratsetamol qimmat"]["price_source"] == "branch"
    assert by["Paratsetamol o'rta"]["price_source"] == "product"
    assert by["Paratsetamol o'rta"]["stock_quantity"] == 10.0 and by["Paratsetamol o'rta"]["valid_quantity"] == 10.0
    assert by["Paratsetamol o'rta"]["in_stock"] is True
    assert by["Paratsetamol o'rta"]["nearest_expiry"] == (tashkent_today() + timedelta(days=100)).isoformat()
    assert by["Paratsetamol qimmat"]["nearest_expiry"] is None and by["Paratsetamol qimmat"]["in_stock"] is True
    # boshqa filial qoldig'i ko'rinmaydi
    assert by["Paratsetamol boshqa filialda"]["stock_quantity"] == 0.0
    assert by["Paratsetamol boshqa filialda"]["in_stock"] is False
    # muddati o'tgan partiya yaroqli qoldiqqa kirmaydi
    assert by["Paratsetamol muddati o'tgan"]["stock_quantity"] == 7.0
    assert by["Paratsetamol muddati o'tgan"]["valid_quantity"] == 0.0
    assert by["Paratsetamol muddati o'tgan"]["in_stock"] is False
    for k in ("dosage_form", "strength", "manufacturer", "is_rx", "control_class", "expiry_warn", "unit",
              "barcode", "sale_currency"):
        assert k in items[0]
    # limit
    assert len(cl.get(f"/api/products/{panadol.id}/analogs", params={"limit": 2}).json()) == 2
    # boshqa mahsulotlar: faqat ibuprofen -> 'Ibuprofen' ning analogi yo'q (to'plam teng emas)
    assert cl.get(f"/api/products/{only_ibu.id}/analogs").json() == []
    # moddasiz mahsulot -> bo'sh
    assert cl.get(f"/api/products/{no_substance.id}/analogs").json() == []
    # ibuprofen+paratsetamol to'plamining analogi yo'q
    assert cl.get(f"/api/products/{extra_substance.id}/analogs").json() == []


def test_analogs_isolation_between_companies(client, db, mk):
    c, b, w, u, para, panadol, efferalgan, aspirin, vitamin = _setup_pharmacy(db, mk)
    c2, b2, w2, u2 = mk.tenant()
    _pharmacy_on(db, c2)
    # B korxonasida ayni umumiy moddali mahsulotlar va qoldig'i
    b_drug = _drug(db, c2, "B Panadol", [para])
    b_analog = _drug(db, c2, "B analog", [para])
    _stock(db, b_analog, w2, 99)
    _batch(db, b_analog, w2, 99, 100)
    _stock(db, efferalgan, w, 1)
    # A foydalanuvchisi o'z analoglarini ko'radi, B nikini emas
    items = client.login(u).get(f"/api/products/{panadol.id}/analogs").json()
    assert [i["id"] for i in items] == [efferalgan.id]
    assert items[0]["stock_quantity"] == 1.0
    # A -> B mahsulotining analogi: 404
    assert client.login(u).get(f"/api/products/{b_drug.id}/analogs").status_code == 404
    # B -> A mahsuloti: 404
    assert client.login(u2).get(f"/api/products/{panadol.id}/analogs").status_code == 404
    # B o'z analogini ko'radi
    items = client.login(u2).get(f"/api/products/{b_drug.id}/analogs").json()
    assert [i["id"] for i in items] == [b_analog.id] and items[0]["stock_quantity"] == 99.0
    # mavjud bo'lmagan mahsulot
    assert client.login(u).get("/api/products/99999999/analogs").status_code == 404


# ------------------------------------------------------------------ 5. so'rovlar soni (N+1 emas)

def _bulk_products(db, c, n, substance, start=0):
    rows = [dict(name=f"Mass dori {start + i}", sku=f"MS-{start + i}", barcode=f"BMS-{start + i:07d}",
                 company_id=c.id, cost_price=D("100"), sale_price=D(1000 + i)) for i in range(n)]
    db.bulk_insert_mappings(Product, rows)
    db.flush()
    ids = [r[0] for r in db.query(Product.id).filter(Product.company_id == c.id,
                                                      Product.sku.like("MS-%")).all()]
    return ids


def test_query_count_not_n_plus_one(client, db, mk):
    c, b, w, u, para, panadol, efferalgan, aspirin, vitamin = _setup_pharmacy(db, mk)
    cl = client.login(u)

    def run():
        with _SqlLog(db) as log:
            r1 = cl.get("/api/products/pos-list", params={"search": "paratsetamol", "limit": 50})
            r2 = cl.get(f"/api/products/{panadol.id}/analogs", params={"limit": 50})
        assert r1.status_code == 200 and r2.status_code == 200
        return log.count, len(r1.json()), len(r2.json())

    small, n1, n2 = run()
    assert n1 == 2 and n2 == 1

    # 10 000 mahsulot: 2000 tasi paratsetamol (analog, tablet 500 mg)
    ids = _bulk_products(db, c, 10000, para)
    assert len(ids) == 10000
    db.bulk_insert_mappings(ProductPharma, [
        dict(product_id=i, company_id=c.id, dosage_form="tablet", strength="500 mg", is_rx=False,
             control_class="none") for i in ids[:2000]])
    db.bulk_insert_mappings(ProductSubstance, [dict(product_id=i, substance_id=para.id) for i in ids[:2000]])
    db.bulk_insert_mappings(StockLevel, [dict(product_id=i, warehouse_id=w.id, quantity=D(3)) for i in ids[:500]])
    db.bulk_insert_mappings(Batch, [dict(product_id=i, warehouse_id=w.id, quantity=D(3), initial_quantity=D(3),
                                         purchase_price=D(1), company_id=c.id, expiry_date=_dt(90))
                                    for i in ids[:500]])
    db.flush()
    big, n1, n2 = run()
    assert n1 == 50 and n2 == 50          # limit bo'yicha kesiladi
    assert small >= 5, small              # hisoblagich ishlayotganini tekshirish
    assert big == small, (small, big)     # so'rovlar soni mahsulotlar soniga bog'liq emas
    assert big <= 40
    # yaroqli qoldiqlilar avval keladi
    items = cl.get(f"/api/products/{panadol.id}/analogs", params={"limit": 200}).json()
    assert len(items) == 200
    flags = [i["in_stock"] for i in items]
    assert flags == sorted(flags, reverse=True) and flags[0] is True


def test_translit_substance_variants_and_compile():
    from app.utils.translit import substance_variants
    a = set(substance_variants("paratsetamol"))
    b = set(substance_variants("парацетамол"))
    c = set(substance_variants("paracetamol"))
    assert a == b == c
    assert {"paratsetamol", "paracetamol", "парацетамол"} <= a
    for f in ("app/routers/product_search.py", "app/utils/translit.py"):
        py_compile.compile(f, doraise=True)
