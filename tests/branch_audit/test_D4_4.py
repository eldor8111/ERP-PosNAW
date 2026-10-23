"""D4.4 — Nazoratdagi dorilar harakati jurnali va retsept jurnali (dorixona rejimi)."""
import json
import pathlib
import re
from datetime import date, datetime, timedelta, timezone
from itertools import count

from app.models.billing import CompanyPackage
from app.models.inventory import MovementType, StockLevel, StockMovement
from app.models.prescription import SalePrescription
from app.models.product import Product
from app.models.product_pharma import ProductPharma
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import UserRole

ROOT = pathlib.Path(__file__).resolve().parents[2]
_n = count(1)
MONTH = "2026-03"
URL = "/api/pharmacy/journals/controlled"
RX_URL = "/api/pharmacy/journals/prescriptions"


def _pharmacy(db, company):
    company.pharmacy_enabled = True
    now = datetime.now(timezone.utc)
    db.add(CompanyPackage(company_id=company.id, package_code="pharmacy", is_active=True,
                          starts_at=now, ends_at=now + timedelta(days=30)))
    db.flush()


def _product(db, company, name, control="none"):
    n = next(_n)
    p = Product(name=name, sku=f"J44-{n}", barcode=f"BJ44-{n:08d}", company_id=company.id,
                cost_price=500, sale_price=1000)
    db.add(p)
    db.flush()
    db.add(ProductPharma(product_id=p.id, company_id=company.id, control_class=control))
    db.flush()
    return p


def _mv(db, product, wh, mtype, before, after, at, ref_type=None, ref_id=None, reason=None, user=None):
    m = StockMovement(product_id=product.id, warehouse_id=wh.id, type=mtype, qty_before=before,
                      qty_after=after, quantity=abs(after - before), reference_type=ref_type,
                      reference_id=ref_id, reason=reason, user_id=user.id if user else None,
                      created_at=at)
    db.add(m)
    db.flush()
    return m


def _stock(db, product, wh, qty):
    db.add(StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=qty))
    db.flush()


def _sale(db, company, user, wh, product, qty, at, status=SaleStatus.completed):
    n = next(_n)
    s = Sale(number=f"J44S{n:06d}", cashier_id=user.id, total_amount=1000 * qty, paid_amount=1000 * qty,
             payment_type=PaymentType.cash, status=status, company_id=company.id, warehouse_id=wh.id,
             branch_id=wh.branch_id, created_at=at)
    db.add(s)
    db.flush()
    it = SaleItem(sale_id=s.id, product_id=product.id, warehouse_id=wh.id, quantity=qty,
                  unit_price=1000, cost_price=500, subtotal=1000 * qty)
    db.add(it)
    db.flush()
    return s, it


def _rx(db, company, sale, item, product, number="RX-1", doctor="Dr. Aliyev", clinic="Shifo",
        reason=None, patient="Bemor"):
    r = SalePrescription(sale_id=sale.id, sale_item_id=item.id, product_id=product.id, company_id=company.id,
                         number=number, issued_at=date(2026, 3, 9) if number else None,
                         doctor=doctor if number else None, clinic=clinic if number else None,
                         patient=patient if number else None, blank_type="form_107" if number else None,
                         reason_without_rx=reason)
    db.add(r)
    db.flush()
    return r


def _setup(db, mk):
    """Narkotik dori: fevral oxirida 20; mart: kirim +10, sotuv -5 (retsept), qaytarish +1,
    hisobdan chiqarish -2, transfer -4; aprelda -3 (mart oxiri qoldig'i 20 bo'lishi kerak)."""
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    narc = _product(db, c, "Morfin", control="narcotic")
    plain = _product(db, c, "Analgin", control="none")
    d = lambda day: datetime(2026, 3, day, 10, 0)  # noqa: E731
    _mv(db, narc, w, MovementType.IN, 0, 20, datetime(2026, 2, 15, 9, 0), "purchase_order", 1)
    _mv(db, narc, w, MovementType.IN, 20, 30, d(3), "purchase_order", 2)
    sale, item = _sale(db, c, admin, w, narc, 5, d(10))
    _rx(db, c, sale, item, narc, number="RX-777")
    _mv(db, narc, w, MovementType.OUT, 30, 25, d(10), "sale", sale.id, user=admin)
    rsale, _ = _sale(db, c, admin, w, narc, 1, d(11))
    _mv(db, narc, w, MovementType.RETURN, 25, 26, d(11), "sale_refund", rsale.id)
    _mv(db, narc, w, MovementType.EXPIRED, 26, 24, d(15), "batch_write_off", 5)
    _mv(db, narc, w, MovementType.TRANSFER_OUT, 24, 20, d(20), "transfer_out", 3)
    _mv(db, narc, w, MovementType.OUT, 20, 17, datetime(2026, 4, 2, 9, 0), "sale", 999)
    _stock(db, narc, w, 17)
    # Nazoratda bo'lmagan dori harakati jurnalga kirmasligi kerak
    _mv(db, plain, w, MovementType.IN, 0, 50, d(4), "purchase_order", 4)
    _stock(db, plain, w, 50)
    return c, b, w, admin, narc, plain, sale


# ─── Nazoratdagi dorilar jurnali ─────────────────────────────────────────────

def test_controlled_journal_movements_and_balances(client, db, mk):
    c, b, w, admin, narc, plain, sale = _setup(db, mk)
    r = client.login(admin).get(f"{URL}?month={MONTH}")
    assert r.status_code == 200
    data = r.json()
    assert data["month"] == MONTH and data["from"] == "2026-03-01" and data["to"] == "2026-03-31"
    assert [x["product_id"] for x in data["products"]] == [narc.id]  # oddiy dori kirmaydi
    p = data["products"][0]
    assert (p["opening"], p["receipts"], p["issues"], p["closing"]) == (20, 11, 11, 20)
    assert p["control_class"] == "narcotic"

    kinds = [row["kind"] for row in data["rows"]]
    assert kinds == ["receipt", "sale", "return_customer", "write_off", "transfer_out"]
    assert [row["balance_after"] for row in data["rows"]] == [30, 25, 26, 24, 20]
    assert data["rows"][0]["in_qty"] == 10 and data["rows"][1]["out_qty"] == 5
    # sotuv — retsept raqami va hujjat raqami bilan
    s = data["rows"][1]
    assert s["rx_number"] == "RX-777" and s["document_number"] == sale.number
    assert s["prescriptions"][0]["doctor"] == "Dr. Aliyev" and s["rx_missing"] is False
    assert data["rows"][0]["rx_number"] is None
    assert "tahrirlanmaydi" in data["note"]


def test_controlled_sale_without_rx_is_flagged(client, db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    p = _product(db, c, "Tramadol", control="psychotropic")
    _stock(db, p, w, 9)
    _mv(db, p, w, MovementType.OUT, 10, 9, datetime(2026, 3, 5, 12, 0), "sale", 12345)
    rows = client.login(admin).get(f"{URL}?month={MONTH}").json()["rows"]
    assert rows[0]["kind"] == "sale" and rows[0]["rx_missing"] is True and rows[0]["rx_number"] is None


def test_controlled_product_filter_and_empty_month(client, db, mk):
    c, b, w, admin, narc, plain, sale = _setup(db, mk)
    cl = client.login(admin)
    assert len(cl.get(f"{URL}?month={MONTH}&product_id={narc.id}").json()["rows"]) == 5
    # oddiy dori bo'yicha — bo'sh
    assert cl.get(f"{URL}?month={MONTH}&product_id={plain.id}").json()["rows"] == []
    # harakatsiz oy: faqat qoldiq (opening == closing), qatorlar yo'q
    may = cl.get(f"{URL}?month=2026-05").json()
    assert may["rows"] == []
    assert may["products"][0]["opening"] == may["products"][0]["closing"] == 17
    # noto'g'ri oy formati
    assert cl.get(f"{URL}?month=2026-13").status_code == 422


def test_controlled_csv_and_pdf(client, db, mk):
    c, b, w, admin, narc, plain, sale = _setup(db, mk)
    cl = client.login(admin)
    r = cl.get(f"{URL}?month={MONTH}&format=csv")
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    text = r.content.decode("utf-8-sig")
    assert "RX-777" in text and "Morfin" in text and "Oy oxiri qoldiq" in text
    r = cl.get(f"{URL}?month={MONTH}&format=pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert "pdf" in r.headers["content-type"]


def test_journal_is_read_only(client, db, mk):
    """Jurnal tahrirlanmaydi: yozuvchi metodlar yo'q."""
    c, b, w, admin, *_ = _setup(db, mk)
    cl = client.login(admin)
    for path in (URL, RX_URL):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(cl, method)(path).status_code == 405, (method, path)


def test_controlled_company_isolation(client, db, mk):
    c, b, w, admin, narc, plain, sale = _setup(db, mk)
    c2, b2, w2, admin2 = mk.tenant()
    _pharmacy(db, c2)
    other = _product(db, c2, "B dori", control="narcotic")
    _stock(db, other, w2, 3)
    _mv(db, other, w2, MovementType.IN, 0, 3, datetime(2026, 3, 6, 9, 0), "purchase_order", 77)

    cl2 = client.login(admin2)
    # B korxona A'ning dorisi/filialini ko'ra olmaydi
    assert cl2.get(f"{URL}?month={MONTH}&product_id={narc.id}").status_code == 404
    assert cl2.get(f"{URL}?month={MONTH}&branch_id={b.id}").status_code == 404
    mine = cl2.get(f"{URL}?month={MONTH}").json()
    assert [x["product_id"] for x in mine["products"]] == [other.id]
    assert [x["product_id"] for x in mine["rows"]] == [other.id]
    # o'z resursi ishlaydi
    assert client.login(admin).get(f"{URL}?month={MONTH}&product_id={narc.id}").status_code == 200


def test_controlled_branch_scope(client, db, mk):
    c, b1, w1, admin = mk.tenant()
    b2 = mk.branch(c)
    w2 = mk.warehouse(c, b2)
    _pharmacy(db, c)
    p = _product(db, c, "Kodein", control="narcotic")
    _stock(db, p, w1, 5)
    _stock(db, p, w2, 7)
    _mv(db, p, w1, MovementType.IN, 0, 5, datetime(2026, 3, 5, 9, 0), "purchase_order", 1)
    _mv(db, p, w2, MovementType.IN, 0, 7, datetime(2026, 3, 6, 9, 0), "purchase_order", 2)
    mgr = mk.user(c, role=UserRole.manager, branch=b1)

    all_rows = client.login(admin).get(f"{URL}?month={MONTH}").json()
    assert len(all_rows["rows"]) == 2 and all_rows["products"][0]["closing"] == 12
    only2 = client.login(admin).get(f"{URL}?month={MONTH}&branch_id={b2.id}").json()
    assert [r["warehouse_id"] for r in only2["rows"]] == [w2.id] and only2["products"][0]["closing"] == 7

    cl = client.login(mgr)
    mine = cl.get(f"{URL}?month={MONTH}").json()
    assert [r["warehouse_id"] for r in mine["rows"]] == [w1.id] and mine["products"][0]["closing"] == 5
    assert cl.get(f"{URL}?month={MONTH}&branch_id={b2.id}").status_code == 403
    assert client.login(mk.user(c, role=UserRole.cashier, branch=b1)).get(f"{URL}?month={MONTH}").status_code == 403


# ─── Retseptli sotuvlar jurnali ──────────────────────────────────────────────

def _rx_setup(db, mk):
    c, b, w, admin = mk.tenant()
    _pharmacy(db, c)
    narc = _product(db, c, "Morfin", control="narcotic")
    abx = _product(db, c, "Amoksitsillin")
    s1, i1 = _sale(db, c, admin, w, narc, 2, datetime(2026, 3, 10, 10, 0))
    _rx(db, c, s1, i1, narc, number="RX-1", doctor="Dr. Aliyev", clinic="Shifo markazi")
    s2, i2 = _sale(db, c, admin, w, abx, 1, datetime(2026, 3, 12, 10, 0))
    _rx(db, c, s2, i2, abx, number="RX-2", doctor="Dr. Karimov", clinic="Med plus")
    s3, i3 = _sale(db, c, admin, w, abx, 1, datetime(2026, 3, 14, 10, 0))
    _rx(db, c, s3, i3, abx, number=None, reason="Shoshilinch holat")
    # davrdan tashqari va bekor qilingan sotuv
    s4, i4 = _sale(db, c, admin, w, abx, 1, datetime(2026, 1, 5, 10, 0))
    _rx(db, c, s4, i4, abx, number="RX-OLD")
    s5, i5 = _sale(db, c, admin, w, abx, 1, datetime(2026, 3, 15, 10, 0), status=SaleStatus.cancelled)
    _rx(db, c, s5, i5, abx, number="RX-CANCEL")
    return c, b, w, admin, narc, abx, (s1, s2, s3)


def test_rx_journal_rows_and_modes(client, db, mk):
    c, b, w, admin, narc, abx, (s1, s2, s3) = _rx_setup(db, mk)
    cl = client.login(admin)
    q = f"{RX_URL}?from=2026-03-01&to=2026-03-31"
    data = cl.get(q).json()
    assert [r["number"] for r in data["rows"]] == ["RX-1", "RX-2", None]
    assert data["summary"] == {"total": 3, "with_rx": 2, "without_rx": 1}
    first = data["rows"][0]
    assert first["sale_number"] == s1.number and first["doctor"] == "Dr. Aliyev"
    assert first["control_class"] == "narcotic" and first["quantity"] == 2 and first["has_rx"] is True

    wo = cl.get(q + "&mode=without").json()
    assert len(wo["rows"]) == 1 and wo["rows"][0]["reason_without_rx"] == "Shoshilinch holat"
    assert wo["rows"][0]["has_rx"] is False and wo["rows"][0]["sale_number"] == s3.number
    assert [r["number"] for r in cl.get(q + "&mode=with").json()["rows"]] == ["RX-1", "RX-2"]
    assert cl.get(q + "&mode=zzz").status_code == 422


def test_rx_journal_filters(client, db, mk):
    c, b, w, admin, *_ = _rx_setup(db, mk)
    cl = client.login(admin)
    q = f"{RX_URL}?from=2026-03-01&to=2026-03-31"
    assert [r["number"] for r in cl.get(q + "&doctor=karim").json()["rows"]] == ["RX-2"]
    assert [r["number"] for r in cl.get(q + "&clinic=shifo").json()["rows"]] == ["RX-1"]
    assert cl.get(q + "&doctor=nomalum").json()["rows"] == []
    # keng davr eski retseptni ham oladi
    wide = cl.get(f"{RX_URL}?from=2026-01-01&to=2026-03-31").json()
    assert "RX-OLD" in [r["number"] for r in wide["rows"]]
    assert cl.get(f"{RX_URL}?from=2026-04-01&to=2026-03-01").status_code == 400
    r = cl.get(q + "&format=csv")
    assert r.status_code == 200 and "RX-1" in r.content.decode("utf-8-sig")


def test_rx_journal_isolation_and_scope(client, db, mk):
    c, b1, w1, admin, narc, abx, _ = _rx_setup(db, mk)
    c2, b2, w2, admin2 = mk.tenant()
    _pharmacy(db, c2)
    q = f"{RX_URL}?from=2026-01-01&to=2026-12-31"
    cl2 = client.login(admin2)
    assert cl2.get(q).json()["rows"] == []
    assert cl2.get(q + f"&branch_id={b1.id}").status_code == 404
    assert len(client.login(admin).get(q).json()["rows"]) == 4

    # filialga biriktirilgan xodim boshqa filial sotuvini ko'rmaydi
    b3 = mk.branch(c)
    mgr3 = mk.user(c, role=UserRole.manager, branch=b3)
    mk.warehouse(c, b3)
    assert client.login(mgr3).get(q).json()["rows"] == []
    assert client.login(mgr3).get(q + f"&branch_id={b1.id}").status_code == 403


# ─── Regressiya: oddiy do'kon ────────────────────────────────────────────────

def test_plain_store_forbidden_and_unchanged(client, db, mk):
    c, b, w, admin = mk.tenant()  # modul yoqilmagan
    p = _product(db, c, "Narkotik belgili", control="narcotic")
    _stock(db, p, w, 4)
    _mv(db, p, w, MovementType.IN, 0, 4, datetime(2026, 3, 5, 9, 0), "purchase_order", 1)
    cl = client.login(admin)
    assert cl.get(f"{URL}?month={MONTH}").status_code == 403
    assert cl.get(RX_URL).status_code == 403
    # mavjud inventar endpointi o'zgarmagan
    assert cl.get("/api/inventory/warehouses").status_code == 200


# ─── i18n va PDF ─────────────────────────────────────────────────────────────

def test_pending_i18n_keys_match():
    d = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D4.4.json").read_text(encoding="utf-8"))
    assert set(d) == {"uz", "ru", "en"}
    assert set(d["uz"]) == set(d["ru"]) == set(d["en"])
    src = (ROOT / "frontend" / "src" / "pages" / "admin" / "pharmacy" / "JournalsPanel.jsx").read_text(encoding="utf-8")
    used = set(re.findall(r"tf\('(pharmJournals\.[A-Za-z0-9.]+)'", src))
    assert used and used <= set(d["uz"])


def test_pdf_fallback_without_unicode_font(monkeypatch):
    from app.routers import pharmacy_journals as pj
    monkeypatch.setattr(pj, "_first_existing", lambda paths: None)
    data = {
        "month": "2026-03", "from": "2026-03-01", "to": "2026-03-31",
        "products": [{"product_id": 1, "name": "Морфин", "control_class": "narcotic", "unit": "dona",
                      "opening": 1, "receipts": 2, "issues": 1, "closing": 2}],
        "rows": [{"product_id": 1, "date": "2026-03-02T10:00:00", "kind_label": "Kirim", "document_number": None,
                  "document_type": "purchase_order", "document_id": 1, "rx_number": None, "warehouse_name": "Ombor",
                  "in_qty": 2.0, "out_qty": 0.0, "balance_after": 3.0}],
    }
    out = pj.build_controlled_pdf(company_name="Дорихона", data=data)
    assert out[:5] == b"%PDF-"
