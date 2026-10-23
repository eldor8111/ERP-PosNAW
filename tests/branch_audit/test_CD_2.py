"""CD.2 — Dorixona tozalash: frontend qoldiqlari (fayl-matn testlari).

Sotuv tafsiloti (retsept/seriya/birlik), ta'minotchiga qaytarishda partiya tanlash va
Products dorixona filtrlari — hammasi faqat dorixona rejimida (useCompanyFeatures().pharmacy).
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADMIN = ROOT / "frontend" / "src" / "pages" / "admin"


def _src(name):
    return (ADMIN / name).read_text(encoding="utf-8")


def _fn(src, name):
    """Funksiya tanasi: 'function NAME(' dan keyingi birinchi top-level 'function ' gacha."""
    i = src.index(f"function {name}(")
    m = re.search(r"\n(?:export default )?function \w+\(", src[i + 10:])
    return src[i: i + 10 + m.start()] if m else src[i:]


# -- 1. Sotuv tafsiloti (CustomerDetail) -------------------------------------

def test_customer_detail_pharma_blocks_conditional():
    s = _src("CustomerDetail.jsx")
    assert "useCompanyFeatures" in s
    for comp in ("PharmaItemMeta", "PharmaPrescriptions"):
        body = _fn(s, comp)
        assert "features?.pharmacy" in body, comp
        assert "return null" in body, comp          # modul o'chiq - hech narsa chizilmaydi
    # Ikkala tafsilot modalida ham ulangan
    assert s.count("<PharmaItemMeta item={item} />") == 2
    assert s.count("<PharmaPrescriptions sale={saleDetailData} />") == 2


def test_customer_detail_prescription_and_item_fields():
    s = _src("CustomerDetail.jsx")
    for f in ("p.number", "p.issued_at", "p.doctor", "p.clinic", "p.blank_type", "p.reason_without_rx"):
        assert f in s, f
    meta = _fn(s, "PharmaItemMeta")
    for f in ("item.batches", "lot_number", "expiry_date", "unit_name", "unit_qty"):
        assert f in meta, f
    # prescriptions bo'sh bo'lsa blok chizilmaydi
    assert "!list.length" in _fn(s, "PharmaPrescriptions")


# -- 2. Ta'minotchiga qaytarishda partiya tanlash (Operations) ---------------

def test_operations_supplier_return_batch_pick():
    s = _src("Operations.jsx")
    body = _fn(s, "QaytarishCreateView")
    assert "useCompanyFeatures" in s
    assert "const pharmacyOn = !!features?.pharmacy" in body
    assert "showBatchPick = pharmacyOn && !isCustomer" in body
    # so'rov: GET /pharmacy/batches?product_id=&warehouse_id=
    assert "api.get('/pharmacy/batches'" in body
    assert "product_id: sel.id" in body and "params.warehouse_id" in body
    # seriya / muddat / holat / qoldiq ko'rsatiladi
    for f in ("b.lot_number", "b.expiry_date", "b.status", "b.quantity"):
        assert f in body, f
    # batch_id faqat dorixona rejimida va tanlangan bo'lsa yuboriladi
    assert "...(showBatchPick && i.batch_id ? { batch_id: i.batch_id } : {})" in body
    # tanlov faqat dorixonada ko'rinadi
    assert "{showBatchPick && (" in body


def test_operations_customer_return_and_plain_payload_unchanged():
    body = _fn(_src("Operations.jsx"), "QaytarishCreateView")
    # mijozdan qaytarish payloadida batch_id yo'q
    m = re.search(r"const payload = \{\s*customer_id.*?\};", body, re.S)
    assert m and "batch_id" not in m.group(0)
    # asosiy maydonlar saqlangan (oddiy korxona uchun payload avvalgidek)
    assert "unit_cost: i.cost" in body
    assert "quantity: i.qty" in body


# -- 3. Products dorixona filtrlari ------------------------------------------

def test_products_pharma_filters_sent_to_server_only_in_pharmacy():
    s = _src("Products.jsx")
    i = s.index("// D2.2: dori filtrlari")
    block = s[i: i + 600]
    assert "if (pharmacyOn) {" in block
    for p in ("'substance_id'", "'manufacturer'", "'is_rx'", "'control_class'"):
        assert p in block, p
    assert "/products/paginated?" in s
    # filtrlar o'zgarsa ro'yxat qayta yuklanadi va sahifa 1 ga qaytadi
    assert "pharmacyOn, filterSubstance, filterManufacturer, filterRx, filterControl]" in s
    assert "limit, filterSubstance, filterManufacturer, filterRx, filterControl]" in s
    # filtr UI faqat dorixonada
    assert "{pharmacyOn && (\n              <>" in s


# -- i18n (pending fayl) -----------------------------------------------------

def test_pending_i18n_keys_present_and_aligned():
    data = json.loads((ROOT / "tests" / "branch_audit" / "i18n_pending" / "CD.2.json").read_text(encoding="utf-8"))
    assert set(data) == {"uz", "ru", "en"}
    assert set(data["uz"]) == set(data["ru"]) == set(data["en"])
    used = set()
    for name in ("CustomerDetail.jsx", "Operations.jsx"):
        used |= set(re.findall(r"['`\"](pharmaSale\.[\w.]+)['`\"]", _src(name)))
    used |= {f"pharmaSale.{k}" for k in ("rxNumber", "rxDate", "rxDoctor", "rxClinic", "rxBlank", "rxReason")}
    used |= {f"pharmaSale.blank.{b}" for b in ("simple", "form_107", "form_148", "special")}
    assert used <= set(data["uz"]), used - set(data["uz"])
