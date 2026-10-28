"""D2.6 — Veb-POS ekranlari (dorixona): PosKassa va UlgurjiSotuv.

Qamrov:
  1. Fayl-matn testlari (frontend): dorixona elementlari FAQAT `pharmacy` (useCompanyFeatures) bo'lganda render bo'ladi;
     savat qatorida muddat belgisi, analoglar, birlik tanlash, butun quti cheklovi, retsept oynasi, markirovka bloki,
     server 400 xatolari oynasi, oflayn rad etilgan sotuvlar sababi; so'rov maydonlari (unit_id, prescriptions,
     rx_override_reason); i18n kalitlari (frontend/src/i18n/pending/D2.6.json — uch tilda bir xil).
  2. Backend shartnomasi (frontend tayanadigan javoblar): dorixona korxonasida pos-list maydonlari
     (nearest_expiry, expiry_warn, is_rx, control_class, units, stock_display, full_boxes), analoglar, rx_required xatosi
     va frontend yuboradigan retsept maydonlari bilan sotuv; oddiy korxonada bularning hech biri yo'q (regressiya).
  3. Ikki korxona izolyatsiyasi (A foydalanuvchisi B mahsuloti analogini ko'ra olmaydi).

Eslatma: so'rovdagi `unit_id` ni server faqat `SaleItemCreate.unit_id` maydoni orqali o'qiydi (sxemada bor —
`test_schema_exposes_unit_id`), aks holda quti jimgina dona deb sotilib ketardi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_D2_6.py -q -p no:cacheprovider
"""
import itertools
import json
import pathlib
import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.models.batch import Batch
from app.models.billing import CompanyPackage
from app.models.inventory import StockLevel
from app.models.moliya import Wallet
from app.models.product import Product
from app.models.product_pharma import PharmaSubstance, ProductPharma, ProductSubstance
from app.models.product_units import ProductUnit
from app.models.sale import Sale
from app.models.user import UserWallet
from app.services.batch_allocator import tashkent_today

ROOT = pathlib.Path(__file__).resolve().parents[2]
FE = ROOT / "frontend" / "src"
POS = (FE / "pages/admin/PosKassa.jsx").read_text(encoding="utf-8")
ULG = (FE / "pages/admin/UlgurjiSotuv.jsx").read_text(encoding="utf-8")
SYNC = (FE / "hooks/usePosSync.js").read_text(encoding="utf-8")
QUEUE = (FE / "utils/posQueue.js").read_text(encoding="utf-8")
PENDING = json.loads((pathlib.Path(__file__).resolve().parent / "i18n_pending" / "D2.6.json").read_text(encoding="utf-8"))
_n = itertools.count(1)


# ───────────────────────── 1. Fayl-matn testlari ─────────────────────────

def test_both_screens_use_company_features_pharmacy_flag():
    for src in (POS, ULG):
        assert "useCompanyFeatures" in src
        assert "const pharmacy = !!features?.pharmacy" in src


def test_poskassa_pharmacy_elements_are_conditionally_rendered():
    # barcha yangi bloklar `pharmacy &&` ostida (oddiy korxonada render bo'lmaydi)
    for marker in (
        "{pharmacy && rxModal && (",
        "{pharmacy && analogModal && (",
        "{pharmacy && saleError && (",
        "{pharmacy && rejectedModal && (",
        "{pharmacy && rejectedSales.length > 0 && (",
    ):
        assert marker in POS, marker
    # savat qatori va mahsulot kartochkasi qo'shimchalari
    cart_idx = POS.index('data-testid="pharmacy-cart-extras"')
    assert "{pharmacy && (" in POS[cart_idx - 120:cart_idx]
    card_idx = POS.index('data-testid="pharmacy-card-extras"')
    assert "{pharmacy && (" in POS[card_idx - 120:card_idx]
    # qatorga dorixona maydonlari faqat dorixonada qo'shiladi
    assert re.search(r"const pharmaCartFields = \(p, unit\) => \{\s*if \(!pharmacy\) return \{\};", POS)
    # stock_display faqat dorixonada
    assert "(pharmacy && p.stock_display) ? p.stock_display" in POS


def test_ulgurji_pharmacy_elements_are_conditionally_rendered():
    for marker in ("{pharmacy && rxModal && (", "{pharmacy && analogModal && (", "{pharmacy && saleError && ("):
        assert marker in ULG, marker
    assert "{pharmacy && (\n                                  <>" in ULG   # savat qatori belgilari
    assert "...(pharmacy ? pharmaFieldsOf(" in ULG
    assert "searchFeatures?.pharmacy ? '/products/pos-list' : '/products'" in ULG   # oddiy korxona avvalgi endpoint


def test_expiry_badge_and_warning_in_cart_row():
    for src in (POS, ULG):
        assert "nearest_expiry" in src and "expiry_warn" in src
        assert "fmtExpiry(" in src
    # P.7: kassada muddat rangi — yashil / sariq / qizil, muddati o'tgan qoldiq qizil miltillaydi
    for cls in ("bg-emerald-100 text-emerald-700", "bg-amber-100 text-amber-800", "bg-red-100 text-red-700",
                "bg-red-600 text-white border border-red-700 animate-pulse"):
        assert cls in POS, cls
    assert "bg-amber-100 text-amber-700" in ULG


def test_server_400_errors_shown_in_dedicated_modal():
    assert "describeRejection(raw)" in POS and "handlePharmacyReject" in POS
    assert "e.response?.status === 400" in POS
    assert "suppressToast: pharmacy" in POS          # interceptor toast'i o'rniga aniq oyna
    assert "_suppressToast: true } : undefined" in ULG
    assert "setSaleError({" in POS and "setSaleError({" in ULG


def test_analogs_button_endpoint_and_auto_suggestion_on_zero_stock():
    for src in (POS, ULG):
        assert "`/products/${pid}/analogs`" in src
        assert "Number(p.stock_quantity) <= 0" in src or "Number(formProduct.stock_quantity) <= 0" in src
        assert "openAnalogs(" in src
    assert "pos.analogs" in POS and "pos.analogs" in ULG


def test_unit_selection_scan_and_request_field():
    # birlik shtrix-kodi skanerlansa birlik o'zi tanlanadi
    assert "x.units.some(u => u.barcode && u.barcode === code)" in POS
    assert "scanned_unit_id" in POS and "scanned_unit_id" in ULG
    # savat qatorida birlik almashtirish -> narx qayta hisoblanadi
    assert "const switchUnit = " in POS and "const switchUnit = " in ULG
    assert "unitLinePrice(" in POS and "unitLinePrice(" in ULG
    # so'rovga unit_id
    assert "unit_id: pharmacy && c.unit_id ? c.unit_id : undefined" in POS
    assert "unit_id: pharmacy && it.unit_id ? it.unit_id : undefined" in ULG
    # birlik qatorlari alohida (bir mahsulot — quti va dona alohida qator)
    assert "(x.unit_id || null) === (unit ? unit.id : null)" in POS


def test_whole_box_not_limited_in_pos_screens():
    """P.13: butun quti soni cheklanmaydi; faqat ochilgan quti bo'lsa skanerda quti sukut bo'yicha tanlanmaydi."""
    for src in (POS, ULG):
        assert "wholeBoxMax(" not in src and "openedBoxOnly(" in src
    assert "_clampWholeBox" not in POS
    assert "parseWholeBoxError(raw)" in POS and "applyBoxFix" in POS
    assert "parseWholeBoxError(detail)" in ULG and "applyBoxFix" in ULG
    assert "export function wholeBoxMax" not in QUEUE and "export const openedBoxOnly" in QUEUE
    assert "export function parseWholeBoxError" in QUEUE and "butun quti" in QUEUE


def test_prescription_modal_and_request_fields():
    """P.13: retsept ixtiyoriy — to'lovdan oldin oyna majburiy ochilmaydi, savatdagi tugma orqali kiritiladi."""
    for src in (POS, ULG):
        assert "buildRxPayload(" in src and "validateRx(" not in src
        assert "rxProductsOf(" in src and "blank_type" in src
        assert "setRxModal({})" in src                                            # savatdagi "Retsept" tugmasi
        assert "const rxMode = 'warn';" in src
    assert "const requestCheckout = () => {\n    setShowCheckout(true);\n  };" in POS and "requestCheckout();" in POS
    assert "info.category === 'rx'" in POS and "info.category === 'rx'" in ULG
    assert "rx_required" in QUEUE and "rx_blank_invalid" in QUEUE
    # so'rov maydonlari: faqat kiritilgan retseptlar yuboriladi
    assert "prescriptions" in QUEUE and "rx_override_reason" in QUEUE
    assert "if (![d.number, d.doctor, d.clinic, d.issued_at].some(v => String(v || '').trim())) continue;" in QUEUE
    assert "...(pharmacy ? buildRxPayload(cart, rxData, rxReason, rxMode) : {})" in POS
    assert "...(pharmacy ? buildRxPayload(cart, rxData, rxReason, rxMode) : {})" in ULG
    assert "pos.rxBlankPick" in POS and "pos.rxNone" in POS and "pos.rxReason" in POS


def test_marking_optional_in_pharmacy_mode():
    # Dorixonada markirovka majburiy emas: to'lovdan oldin kodlar soni tekshirilmaydi, skanerlangan kodlar yuboriladi;
    # oddiy korxonada tekshiruv avvalgidek
    assert not re.search(r"if \(pharmacy\) \{\s*const incomplete = cart\.find\(c => c\.requires_marking", POS)
    assert "!pharmacy && cart.find(c => c.requires_marking && (c.marking_codes || []).length < c.qty_ordered)" in POS
    assert "marking_codes: c.marking_codes && c.marking_codes.length ? c.marking_codes : undefined" in POS
    assert "!pharmacy && cart.find(it => it.requires_marking && (it.marking_codes || []).length < it.qty)" in ULG


def test_offline_rejected_sales_show_reason():
    assert "reason: describeRejection(detail)" in QUEUE            # navbatdagi rad etilgan yozuvga sabab yoziladi
    assert "export function describeRejection" in QUEUE
    assert "describeRejection" in SYNC and "pharmacyRef.current" in SYNC
    assert "[${cat}]" in SYNC                                       # RETSEPT / MUDDAT / MARKIROVKA belgisi
    # oddiy korxona toast'i avvalgidek (dorixonada bo'lmasa eski matn)
    assert "server tomonidan RAD ETILDI va saqlanmadi: ${text}" in SYNC
    # PosKassa: rad etilgan sotuvlar ro'yxati (faqat dorixona)
    assert "REJECTED_SALES_KEY" in POS and "rejectedSales" in POS


def test_shared_helpers_do_not_touch_plain_queue_behaviour():
    # navbat xatti-harakati: faqat rad etilgan yozuvga qo'shimcha `reason` maydoni
    assert re.search(r"rejected\.push\(\{ \.\.\.item, kind, detail, reason: describeRejection\(detail\), rejectedAt: Date\.now\(\) \}\)", QUEUE)
    assert "await api.post(endpoint, item.payload" in QUEUE


def _tf_keys(src):
    return set(re.findall(r"\btfb?\(\s*'([a-zA-Z0-9_.]+)'", src))


def test_i18n_pending_has_same_keys_in_three_languages():
    assert set(PENDING) == {"uz", "ru", "en"}
    assert set(PENDING["uz"]) == set(PENDING["ru"]) == set(PENDING["en"])
    assert all(v.strip() for lang in PENDING.values() for v in lang.values())
    # placeholderlar uch tilda bir xil
    for k, uz in PENDING["uz"].items():
        ph_uz = set(re.findall(r"\{(\w+)\}", uz))
        assert ph_uz == set(re.findall(r"\{(\w+)\}", PENDING["ru"][k])) == set(re.findall(r"\{(\w+)\}", PENDING["en"][k])), k


def test_all_new_tf_keys_exist_in_pending_or_dictionary():
    uz_dict = (FE / "i18n/uz.js").read_text(encoding="utf-8")
    other_pending = {}
    for f in (pathlib.Path(__file__).resolve().parent / "i18n_pending").glob("*.json"):
        if f.name != "D2.6.json":
            other_pending.update(json.loads(f.read_text(encoding="utf-8")).get("uz", {}))
    for src in (POS, ULG):
        for key in _tf_keys(src):
            assert key in PENDING["uz"] or f"'{key}'" in uz_dict or key in other_pending, key
    # yangi kalitlar umumiy lug'atga birlashtirilgan (D-bosqich yakuniy integratsiyasi)
    for key in PENDING["uz"]:
        assert f"'{key}'" in uz_dict or f'"{key}"' in uz_dict, key


# ───────────────────────── 2. Backend shartnomasi ─────────────────────────

def _enable(db, c, **settings):
    c.pharmacy_enabled = True
    if settings:
        c.pharmacy_settings = settings
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
    return w


def _dt(days):
    return datetime.combine(tashkent_today() + timedelta(days=days), time.min)


def _product(db, c, wh, qty=100, expiry_days=200, rx=False, control="none", pharma=True, price=1000, **pharma_kw):
    n = next(_n)
    p = Product(name=f"Dori D26-{n}", sku=f"D26-{n}", barcode=f"BD26-{n:06d}", company_id=c.id,
                cost_price=D("500"), sale_price=D(price))
    db.add(p)
    db.flush()
    if pharma:
        db.add(ProductPharma(product_id=p.id, company_id=c.id, is_rx=rx, control_class=control, **pharma_kw))
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=D(qty)))
    if qty:
        db.add(Batch(product_id=p.id, warehouse_id=wh.id, quantity=D(qty), initial_quantity=D(qty),
                     purchase_price=D("500"), company_id=c.id, expiry_date=_dt(expiry_days)))
    db.flush()
    return p


def _body(lines, wh, **extra):
    total = sum(1000 * q for _, q in lines)
    body = {"items": [{"product_id": p.id, "quantity": q, "unit_price": 1000} for p, q in lines],
            "payment_type": "cash", "paid_amount": total, "paid_cash": total,
            "payments": [{"type": "cash", "amount": total}], "warehouse_id": wh.id}
    body.update(extra)
    return body


@pytest.fixture(autouse=True)
def _no_telegram(monkeypatch):
    import app.routers.sales as sales_router
    monkeypatch.setattr(sales_router, "notify_new_sale", lambda *a, **k: None)


@pytest.fixture
def ph(db, mk):
    """Dorixona yoqilgan korxona A (kassa bilan) va oddiy korxona B."""
    c, b, wh, admin = mk.tenant()
    _wallet(db, c, b, admin)
    _enable(db, c, expiry_warn_days=30)
    c2, b2, wh2, admin2 = mk.tenant()
    _wallet(db, c2, b2, admin2)
    return dict(c=c, b=b, wh=wh, admin=admin, c2=c2, b2=b2, wh2=wh2, admin2=admin2)


def test_pos_list_exposes_fields_used_by_pos_screens(client, db, ph):
    soon = _product(db, ph["c"], ph["wh"], expiry_days=10, rx=True, pack_qty=10)
    late = _product(db, ph["c"], ph["wh"], expiry_days=200, control="psychotropic")
    db.add(ProductUnit(product_id=soon.id, company_id=ph["c"].id, name="quti", ratio=D(10), sale_price=D(9000)))
    db.add(ProductUnit(product_id=soon.id, company_id=ph["c"].id, name="dona", ratio=D(1)))
    db.flush()
    rows = {r["id"]: r for r in client.login(ph["admin"]).get(
        "/api/products/pos-list", params={"warehouse_id": ph["wh"].id}).json()}
    a, b = rows[soon.id], rows[late.id]
    assert a["nearest_expiry"] == (tashkent_today() + timedelta(days=10)).isoformat()
    assert a["expiry_warn"] is True and b["expiry_warn"] is False          # sariq belgi faqat yaqin muddatda
    assert a["is_rx"] is True and b["is_rx"] is False
    assert b["control_class"] == "psychotropic"
    assert {u["name"] for u in a["units"]} == {"quti", "dona"}
    assert all("ratio" in u and "price" in u for u in a["units"])
    assert a["pack_ratio"] == 10 and a["full_boxes"] is not None and a["stock_display"]


def test_pos_list_plain_company_has_no_pharmacy_fields(client, db, ph):
    p = _product(db, ph["c2"], ph["wh2"], pharma=False)
    row = client.login(ph["admin2"]).get("/api/products/pos-list", params={"warehouse_id": ph["wh2"].id}).json()[0]
    assert row["id"] == p.id
    for k in ("nearest_expiry", "expiry_warn", "is_rx", "control_class", "units", "stock_display", "full_boxes",
              "scanned_unit_id", "pack_ratio"):
        assert k not in row, k


def test_analogs_contract_for_cart_button(client, db, ph):
    sub = PharmaSubstance(company_id=ph["c"].id, name_uz="Paratsetamol")
    db.add(sub)
    db.flush()
    src = _product(db, ph["c"], ph["wh"], qty=0, dosage_form="tablet", strength="500 mg")
    alt = _product(db, ph["c"], ph["wh"], qty=20, expiry_days=10, dosage_form="tablet", strength="500 mg",
                   manufacturer="Acme")
    for p in (src, alt):
        db.add(ProductSubstance(product_id=p.id, substance_id=sub.id))
    db.flush()
    r = client.login(ph["admin"]).get(f"/api/products/{src.id}/analogs")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [x["id"] for x in rows] == [alt.id]
    x = rows[0]
    for k in ("name", "sale_price", "in_stock", "valid_quantity", "stock_quantity", "nearest_expiry", "expiry_warn",
              "is_rx", "dosage_form", "strength", "manufacturer"):
        assert k in x, k
    assert x["in_stock"] is True and x["expiry_warn"] is True


def test_analogs_isolation_and_plain_company(client, db, ph):
    other = _product(db, ph["c2"], ph["wh2"])
    mine = _product(db, ph["c"], ph["wh"])
    cl = client.login(ph["admin"])
    assert cl.get(f"/api/products/{mine.id}/analogs").status_code == 200          # o'z resursi
    assert cl.get(f"/api/products/{other.id}/analogs").status_code == 404         # begona korxona mahsuloti
    r = client.login(ph["admin2"]).get(f"/api/products/{other.id}/analogs")
    assert r.status_code == 404                                                   # oddiy korxona: modul o'chiq


def test_rx_drug_sells_without_prescription_and_frontend_payload_works(client, db, ph):
    """P.13: retseptsiz ham sotiladi; frontend (buildRxPayload) yuboradigan maydonlar bilan ham."""
    p = _product(db, ph["c"], ph["wh"], rx=True)
    cl = client.login(ph["admin"])
    r = cl.post("/api/sales/", json=_body([(p, 1)], ph["wh"]))
    assert r.status_code == 200, r.text
    rx = {"product_id": p.id, "number": "AB-1", "issued_at": (tashkent_today() - timedelta(days=1)).isoformat(),
          "doctor": "Karimov A.", "clinic": "3-poliklinika", "blank_type": "simple"}
    ok = cl.post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=[rx]))
    assert ok.status_code == 200, ok.text
    p2 = _product(db, ph["c"], ph["wh"], rx=True)
    ok2 = cl.post("/api/sales/", json=_body([(p2, 1)], ph["wh"], rx_override_reason="Mijoz retseptni olib kelmadi"))
    assert ok2.status_code == 200, ok2.text


def test_controlled_drug_sells_with_any_blank_or_without_prescription(client, db, ph):
    p = _product(db, ph["c"], ph["wh"], control="psychotropic")
    cl = client.login(ph["admin"])
    assert cl.post("/api/sales/", json=_body([(p, 1)], ph["wh"], rx_override_reason="sabab")).status_code == 200
    rx = {"product_id": p.id, "number": "N-1", "issued_at": tashkent_today().isoformat(), "doctor": "A", "clinic": "B",
          "blank_type": "simple"}
    assert cl.post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=[rx])).status_code == 200
    rx["blank_type"] = "form_107"
    assert cl.post("/api/sales/", json=_body([(p, 1)], ph["wh"], prescriptions=[rx])).status_code == 200


def test_expired_batch_sells_with_plain_warning_for_pos(client, db, ph):
    """P.13: muddati o'tgan dori sotiladi; kassa ko'rsatadigan ogohlantirish — oddiy matn."""
    p = _product(db, ph["c"], ph["wh"], expiry_days=-5)
    r = client.login(ph["admin"]).post("/api/sales/", json=_body([(p, 1)], ph["wh"]))
    assert r.status_code == 200, r.text
    w = r.json()["warnings"]
    assert len(w) == 1 and isinstance(w[0]["message"], str) and "muddati o'tgan" in w[0]["message"]


def test_plain_company_sells_rx_flagged_and_expired_as_before(client, db, ph):
    """Regressiya: oddiy do'kon — retsept/muddat qoidalari ishlamaydi, yangi maydonlar e'tiborsiz."""
    p = _product(db, ph["c2"], ph["wh2"], expiry_days=-5, rx=True)
    body = _body([(p, 1)], ph["wh2"], rx_override_reason="ahamiyatsiz")
    r = client.login(ph["admin2"]).post("/api/sales/", json=body)
    assert r.status_code == 200, r.text


def test_schema_exposes_unit_id():
    from app.schemas.sale import SaleItemCreate
    assert "unit_id" in SaleItemCreate.model_fields


def test_unit_id_sale_whole_boxes_not_limited(client, db, ph):
    """P.13: 3 butun quti kerak, omborda 2 butun quti + 15 ochilgan dona — sotuv o'tadi (ochilganidan olinadi)."""
    p = _product(db, ph["c"], ph["wh"], qty=15, pack_qty=10)
    for q in (15, 5):      # jami 35 dona: 10 + 10 butun va 15 ochilgan qutilarda
        db.add(Batch(product_id=p.id, warehouse_id=ph["wh"].id, quantity=D(q), initial_quantity=D(q),
                     purchase_price=D("500"), company_id=ph["c"].id, expiry_date=_dt(200)))
    db.query(StockLevel).filter_by(product_id=p.id).one().quantity = D(35)
    db.flush()
    box = ProductUnit(product_id=p.id, company_id=ph["c"].id, name="quti", ratio=D(10), sale_price=D(9000))
    db.add(box)
    db.flush()
    cl = client.login(ph["admin"])
    body = _body([(p, 3)], ph["wh"])
    body["items"][0].update(unit_id=box.id, unit_price=9000)
    body["paid_amount"] = body["paid_cash"] = 27000
    body["payments"] = [{"type": "cash", "amount": 27000}]
    r = cl.post("/api/sales/", json=body)
    assert r.status_code == 200, r.text
    sl = db.query(StockLevel).filter_by(product_id=p.id).one()
    db.refresh(sl)
    assert D(str(sl.quantity)) == 5          # miqdor asosiy birlikda (3 quti = 30 dona)


# ───────── 3. 2-urinish: pending saqlash, qayta narxlash, birlik narxi (ulgurji) ─────────

def _ulg_block(start: str, end: str) -> str:
    i = ULG.index(start)
    return ULG[i:ULG.index(end, i)]


def test_ulgurji_pending_converts_unit_lines_to_base_unit():
    blk = _ulg_block("const savePendingSale = async", "const activeSaleId")
    # birlik qatori asosiy birlikka o'tkaziladi (pending unit_id ni rad etadi)
    assert "const unitRatio = pharmacy && it.unit_id ? (Number(it.unit_ratio) || 1) : 1;" in blk
    assert "quantity: it.qty * unitRatio, unit_price: it.price / unitRatio" in blk
    assert "unit_id:" not in blk   # so'rovga unit_id yuborilmaydi
    # tab almashtirganda avto-saqlash ham shu funksiya orqali ketadi
    assert "await savePendingSale(true)" in _ulg_block("const handleTabChange", "RENDER")


def test_ulgurji_repricing_handles_unit_lines():
    assert ULG.count("repriceLine(it, newPrice)") == 2     # changePriceType va custId/customers/custPrices effekti
    assert ULG.count("let newPrice = lineBasePrice(it);") == 2
    assert "return { ...it, price: newPrice };" not in ULG   # eski (quti narxini dona narxi bilan almashtiruvchi) yo'l qolmagan


def test_ulgurji_unit_switch_uses_base_price_and_manual_check_handles_missing_unit_price():
    sw = _ulg_block("const switchUnit = useCallback", "const addAnalogToCart")
    assert "lineBasePrice(it)" in sw and "base_price: basePrice" in sw
    assert "/ oldRatio" not in sw        # eski: narx/nisbat bilan siljish
    assert "base_price: basePrice }" in ULG and "...(isPharma ? { ...pharmaFieldsOf(p, scanUnit), base_price: basePrice }" in ULG
    man = _ulg_block("const isPriceManual", "const saveSettings")
    assert "unitLinePrice(base, it.sale_price, un)" in man       # unit.price yo'q bo'lsa asosiy narx * nisbat
    assert "un.price != null && price === Number(un.price)" not in man


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node yo'q")
def test_ulgurji_price_helpers_behaviour_in_node(tmp_path):
    import subprocess
    uni = QUEUE[QUEUE.index("export function unitLinePrice"):]
    uni = uni[:uni.index("\n}\n") + 3].replace("export ", "")
    helpers = _ulg_block("const lineBasePrice", "const fmtPrice")
    js = uni + "\n" + helpers + """
const box = { id: 7, ratio: 10, price: 90000 };
const boxNoPrice = { id: 8, ratio: 10, price: null };
const eq = (a, b, m) => { if (a !== b) { console.log('FAIL ' + m + ' ' + a + ' != ' + b); process.exit(1); } };
// quti (maxsus narx 90000) qatori: base_price 10000 saqlangan
let it = { unit_id: 7, unit_ratio: 10, units: [box], price: 90000, base_price: 10000, sale_price: 10000 };
eq(lineBasePrice(it), 10000, 'base from base_price (not 9000)');
// dona narxi narx turi (ulgurji 8000) bo'yicha qayta narxlansa quti narxi base*ratio
let r = repriceLine(it, 8000);
eq(r.price, 80000, 'box repriced to base*ratio'); eq(r.base_price, 8000, 'base kept');
// asl dona narxiga qaytganda unit.price
eq(repriceLine(it, 10000).price, 90000, 'list price -> unit.price');
// unit.price yo'q birlik
let it2 = { unit_id: 8, unit_ratio: 10, units: [boxNoPrice], price: 100000, base_price: 10000, sale_price: 10000 };
eq(repriceLine(it2, 10000).price, 100000, 'no unit.price -> base*ratio');
// qo'lda o'zgartirilgan quti narxi: base_price emas, narx/nisbat
let it3 = { ...it, price: 85000 };
eq(lineBasePrice(it3), 8500, 'manual price -> price/ratio');
// birliksiz qator: o'zgarishsiz
let plain = { price: 5000, sale_price: 5000 };
eq(lineBasePrice(plain), 5000, 'plain base'); eq(repriceLine(plain, 4000).price, 4000, 'plain reprice');
console.log('OK');
"""
    f = tmp_path / "t.js"
    f.write_text(js, encoding="utf-8")
    out = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0 and "OK" in out.stdout, out.stdout + out.stderr
