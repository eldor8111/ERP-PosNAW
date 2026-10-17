"""T3.10 — pos-desktop (Electron) tuzatishlari.

pos-desktop uchun avtomatik test infratuzilmasi yo'q, shu sabab:
  1) Backend shartnomasi (pytest + SQLite): pos-desktop yuboradigan payload'lar va so'rovlar
     mavjud endpointlarda ishlashini tasdiqlaydi (ko'p korxonali login, nasiya, mijoz,
     Idempotency-Key, return-items, type=IN, /shifts/current, ombor bo'yicha qoldiq, shtrix-kod)
     va ikki korxona izolyatsiyasini tekshiradi.
  2) pos.js / index.html statik tekshiruvlari (ko'rsatilgan eski xatolar qaytmasligi uchun).
  3) `node` mavjud bo'lsa — toza funksiyalar (fiscalHeaders, saleKeyFor) ishga tushirib tekshiriladi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T3_10.py -q -p no:cacheprovider
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.moliya import Wallet
from app.models.product import Product
from app.models.sale import Sale, SaleStatus
from app.models.user import UserRole, UserWallet
from app.models.user_company import UserCompany

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
POS_JS = os.path.join(ROOT, 'pos-desktop', 'renderer', 'pos.js')
POS_HTML = os.path.join(ROOT, 'pos-desktop', 'renderer', 'index.html')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


# ───────────────────────────── yordamchilar ─────────────────────────────

_n = [0]


def _product(db, company, price="1000", barcode=None, sku=None, name=None):
    _n[0] += 1
    p = Product(name=name or f"Tovar T310-{_n[0]}", sku=sku or f"T310-{_n[0]}",
                barcode=barcode or f"BC310-{_n[0]:06d}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal(price))
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty):
    sl = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(qty))
    db.add(sl)
    db.flush()
    return sl


def _customer(db, company, name="Mijoz T310", phone="998901112233"):
    c = Customer(name=name, phone=phone, company_id=company.id, debt_balance=Decimal("0"), debt_balances={})
    db.add(c)
    db.flush()
    return c


def _wallet(db, company, branch, user, balance=100000):
    w = Wallet(name=f"Kassa {user.id}", type="cash", balance=Decimal(balance), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(UserWallet(user_id=user.id, wallet_id=w.id, is_default=True, company_id=company.id))
    db.flush()
    return w


@pytest.fixture
def world(db, mk):
    """Ikki mustaqil korxona: A (kassir + kassa + tovar + mijoz), B (begona resurslar)."""
    ca, ba, wa, ua = mk.tenant(UserRole.cashier)
    cb, bb, wb, ub = mk.tenant(UserRole.cashier)
    _wallet(db, ca, ba, ua)
    _wallet(db, cb, bb, ub)
    pa, pb = _product(db, ca), _product(db, cb)
    _stock(db, pa, wa, 100)
    _stock(db, pb, wb, 100)
    return type('W', (), dict(ca=ca, ba=ba, wa=wa, ua=ua, cb=cb, bb=bb, wb=wb, ub=ub, pa=pa, pb=pb,
                              cust_a=_customer(db, ca, "Mijoz A"),
                              cust_b=_customer(db, cb, "Mijoz B Sir", "998905556677")))


def _sale_body(w, **kw):
    """pos.js processSale() yuboradigan payload shakli."""
    d = {
        "items": [{"product_id": w.pa.id, "quantity": 2, "unit_price": 1000, "discount": 0}],
        "payment_type": "cash",
        "paid_amount": 2000,
        "discount_amount": 0,
        "note": "",
        "customer_id": None,
        "warehouse_id": w.wa.id,
    }
    d.update(kw)
    return d


# ───────────────────── 1. Ko'p korxonali login (select-company + refresh) ─────────────────────

def test_multi_company_login_needs_selection_then_tokens(db, mk, client):
    ca, cb = mk.company(), mk.company()
    ba, bb = mk.branch(ca), mk.branch(cb)
    u = mk.user(ca, role=UserRole.admin, branch=ba, hashed_password=hash_password("parol123"))
    db.add_all([
        UserCompany(user_id=u.id, company_id=ca.id, role=UserRole.admin, is_active=True),
        UserCompany(user_id=u.id, company_id=cb.id, role=UserRole.cashier, is_active=True),
    ])
    db.flush()
    # pos.js doLogin: telefon + parol
    r = client.post("/api/auth/login", json={"phone": "+" + u.phone, "password": "parol123"})
    assert r.status_code == 200, r.text
    data = r.json()
    # access_token yo'q — pos.js "Bearer null" yubormasligi uchun needs_company_selection ni qayta ishlaydi
    assert data["needs_company_selection"] is True
    assert not data.get("access_token")
    assert data["temp_token"]
    ids = {c["company_id"] for c in data["companies"]}
    assert ids == {ca.id, cb.id}
    # pos.js selectCompany: {temp_token, company_id}
    r2 = client.post("/api/auth/select-company", json={"temp_token": data["temp_token"], "company_id": cb.id})
    assert r2.status_code == 200, r2.text
    tok = r2.json()
    assert tok["access_token"] and tok["refresh_token"]
    # pos.js tryRefreshToken: {refresh_token} -> yangi access_token
    r3 = client.post("/api/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r3.status_code == 200, r3.text
    assert r3.json()["access_token"]


def test_select_company_foreign_company_403(db, mk, client):
    ca, cb, cc = mk.company(), mk.company(), mk.company()
    u = mk.user(ca, role=UserRole.admin, hashed_password=hash_password("parol123"))
    db.add_all([
        UserCompany(user_id=u.id, company_id=ca.id, role=UserRole.admin, is_active=True),
        UserCompany(user_id=u.id, company_id=cb.id, role=UserRole.admin, is_active=True),
    ])
    db.flush()
    d = client.post("/api/auth/login", json={"phone": "+" + u.phone, "password": "parol123"}).json()
    r = client.post("/api/auth/select-company", json={"temp_token": d["temp_token"], "company_id": cc.id})
    assert r.status_code == 403, r.text


# ───────────────────── 2-4. Mijoz, nasiya, naqd sotuv ─────────────────────

def test_debt_sale_without_customer_is_400(db, world, client):
    """Server ham rad etadi; pos.js esa so'rovni umuman yubormaydi (statik testda)."""
    r = client.login(world.ua).post("/api/sales/", json=_sale_body(world, payment_type="debt", paid_amount=0))
    assert r.status_code == 400, r.text
    assert "mijoz" in r.text.lower()


def test_debt_sale_with_customer_unpaid_remainder_goes_to_debt(db, world, client):
    r = client.login(world.ua).post("/api/sales/", json=_sale_body(
        world, payment_type="debt", paid_amount=0, customer_id=world.cust_a.id))
    assert r.status_code == 200, r.text
    db.refresh(world.cust_a)
    assert Decimal(str(world.cust_a.debt_balance)) == Decimal("2000")


def test_debt_sale_partial_paid_only_remainder_to_debt(db, world, client):
    r = client.login(world.ua).post("/api/sales/", json=_sale_body(
        world, payment_type="debt", paid_amount=500, customer_id=world.cust_a.id, debt_due_date="2030-01-31"))
    assert r.status_code == 200, r.text
    db.refresh(world.cust_a)
    assert Decimal(str(world.cust_a.debt_balance)) == Decimal("1500")


def test_cash_sale_links_customer(db, world, client):
    r = client.login(world.ua).post("/api/sales/", json=_sale_body(world, customer_id=world.cust_a.id))
    assert r.status_code == 200, r.text
    sale = db.query(Sale).filter(Sale.id == r.json()["id"]).one()
    assert sale.customer_id == world.cust_a.id


def test_sale_with_foreign_customer_rejected(db, world, client):
    before = db.query(Sale).count()
    r = client.login(world.ua).post("/api/sales/", json=_sale_body(world, customer_id=world.cust_b.id))
    assert r.status_code in (400, 403, 404), r.text
    assert "Mijoz B Sir" not in r.text
    assert db.query(Sale).count() == before


# ───────────────────── 5. Idempotency-Key ─────────────────────

def test_same_idempotency_key_creates_one_sale(db, world, client):
    h = {"Idempotency-Key": "pos-desktop-key-1"}
    c = client.login(world.ua)
    before = db.query(Sale).count()
    r1 = c.post("/api/sales/", json=_sale_body(world), headers=h)
    r2 = c.post("/api/sales/", json=_sale_body(world), headers=h)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    assert r1.json()["id"] == r2.json()["id"]
    assert db.query(Sale).count() == before + 1
    sl = db.query(StockLevel).filter(StockLevel.product_id == world.pa.id,
                                     StockLevel.warehouse_id == world.wa.id).one()
    assert Decimal(str(sl.quantity)) == Decimal("98")   # zaxira faqat bir marta kamaydi


# ───────────────────── 6. Qaytarish: return-items ─────────────────────

def test_return_items_shape_partial_then_rest_then_overreturn(db, world, client):
    c = client.login(world.ua)
    sale = c.post("/api/sales/", json=_sale_body(world)).json()
    # pos.js selectReturnSale: GET /sales/{id} — qatorda id va returned_quantity bor
    full = c.get(f"/api/sales/{sale['id']}")
    assert full.status_code == 200, full.text
    item = full.json()["items"][0]
    assert "id" in item and Decimal(str(item["returned_quantity"])) == 0

    # SaleReturnRequest shakli: {items:[{sale_item_id, quantity}], payment_type, note}
    body = {"items": [{"sale_item_id": item["id"], "quantity": 1}], "payment_type": "cash", "note": "Qaytarish"}
    r = c.post(f"/api/sales/{sale['id']}/return-items", json=body)
    assert r.status_code == 200, r.text
    st = db.query(Sale).filter(Sale.id == sale["id"]).one()
    assert st.status == SaleStatus.partial_refund

    after = c.get(f"/api/sales/{sale['id']}").json()["items"][0]
    assert Decimal(str(after["returned_quantity"])) == 1
    # qolgan miqdor (quantity - returned_quantity) = 1
    left = Decimal(str(after["quantity"])) - Decimal(str(after["returned_quantity"]))
    assert left == 1
    r2 = c.post(f"/api/sales/{sale['id']}/return-items",
                json={"items": [{"sale_item_id": item["id"], "quantity": float(left)}], "payment_type": "cash"})
    assert r2.status_code == 200, r2.text
    db.refresh(st)
    assert st.status == SaleStatus.refunded

    # allaqachon qaytarilgan miqdor qayta qaytarilmaydi
    r3 = c.post(f"/api/sales/{sale['id']}/return-items",
                json={"items": [{"sale_item_id": item["id"], "quantity": 1}], "payment_type": "cash"})
    assert r3.status_code == 400, r3.text


def test_old_refund_endpoint_does_not_exist(db, world, client):
    c = client.login(world.ua)
    sale = c.post("/api/sales/", json=_sale_body(world)).json()
    r = c.post(f"/api/sales/{sale['id']}/refund", json={})
    assert r.status_code in (404, 405)


def test_return_items_foreign_sale_404(db, world, client):
    sale = client.login(world.ua).post("/api/sales/", json=_sale_body(world)).json()
    item = client.get(f"/api/sales/{sale['id']}").json()["items"][0]
    r = client.login(world.ub).post(f"/api/sales/{sale['id']}/return-items",
                                    json={"items": [{"sale_item_id": item["id"], "quantity": 1}],
                                          "payment_type": "cash"})
    assert r.status_code in (403, 404), r.text
    assert client.login(world.ub).get(f"/api/sales/{sale['id']}").status_code in (403, 404)


# ───────────────────── 7. Kompaniya, filial, chek shabloni ─────────────────────

def test_company_and_branch_endpoints_used_by_pos(db, world, client):
    c = client.login(world.ua)
    r = c.get("/api/billing/my-company")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == world.ca.name and r.json()["org_code"] == world.ca.org_code
    r = c.get(f"/api/branches/{world.ba.id}")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == world.ba.name
    assert "balance" not in r.json()          # shu sabab pos.js filial balansini ko'rsatmaydi
    # GET /companies/{id} yo'q (405) — pos.js endi chaqirmaydi
    assert c.get(f"/api/companies/{world.ca.id}").status_code == 405


def test_branch_of_other_company_not_visible(db, world, client):
    r = client.login(world.ua).get(f"/api/branches/{world.bb.id}")
    assert r.status_code in (403, 404), r.text


def test_receipt_templates_endpoint_returns_own_company_only(db, world, client):
    world.ca.receipt_templates = {"r80": {"company": "A do'koni"}}
    world.cb.receipt_templates = {"r80": {"company": "B sir do'koni"}}
    db.flush()
    r = client.login(world.ua).get("/api/companies/me/receipt_templates")
    assert r.status_code == 200, r.text
    assert r.json()["receipt_templates"]["r80"]["company"] == "A do'koni"
    assert "B sir" not in r.text


# ───────────────────── 8. Ombor bo'yicha qoldiq (pos-list + sotuv) ─────────────────────

def test_pos_list_stock_is_per_selected_warehouse(db, mk, client):
    c = mk.company()
    b1, b2 = mk.branch(c), mk.branch(c)
    w1, w2 = mk.warehouse(c, b1), mk.warehouse(c, b2)
    cashier2 = mk.user(c, role=UserRole.cashier, branch=b2)
    p = _product(db, c)
    _stock(db, p, w1, 40)
    _stock(db, p, w2, 10)
    r = client.login(cashier2).get("/api/products/pos-list", params={"limit": 50, "warehouse_id": w2.id})
    assert r.status_code == 200, r.text
    row = next(x for x in r.json() if x["id"] == p.id)
    assert Decimal(str(row["stock_quantity"])) == Decimal("10")
    # 2-filial kassiri 1-filial omborini so'ray olmaydi
    r = client.login(cashier2).get("/api/products/pos-list", params={"limit": 50, "warehouse_id": w1.id})
    assert r.status_code in (403, 404), r.text


def test_pos_list_foreign_company_warehouse_404(db, world, client):
    r = client.login(world.ua).get("/api/products/pos-list", params={"warehouse_id": world.wb.id})
    assert r.status_code == 404, r.text


def test_sale_deducts_from_sent_warehouse_and_blocks_oversell(db, mk, client):
    c = mk.company()
    c.pos_allow_negative_stock = False
    b = mk.branch(c)
    w1 = mk.warehouse(c, b)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    _wallet(db, c, b, cashier)
    p = _product(db, c)
    _stock(db, p, w1, 10)
    body = {"items": [{"product_id": p.id, "quantity": 15, "unit_price": 1000, "discount": 0}],
            "payment_type": "cash", "paid_amount": 15000, "discount_amount": 0, "note": "",
            "customer_id": None, "warehouse_id": w1.id}
    r = client.login(cashier).post("/api/sales/", json=body)
    assert r.status_code == 400, r.text           # server aniq 400 beradi (ekrandagi 10 ta bo'yicha)
    body["items"][0]["quantity"] = 4
    body["paid_amount"] = 4000
    assert client.login(cashier).post("/api/sales/", json=body).status_code == 200
    sl = db.query(StockLevel).filter(StockLevel.product_id == p.id, StockLevel.warehouse_id == w1.id).one()
    assert Decimal(str(sl.quantity)) == Decimal("6")


# ───────────────────── 9. Shtrix-kod serverdan ─────────────────────

def test_barcode_lookup_server_side_finds_sku_and_isolates(db, world, client):
    c = client.login(world.ua)
    r = c.get(f"/api/products/barcode/{world.pa.barcode}")
    assert r.status_code == 200 and r.json()["id"] == world.pa.id, r.text
    r = c.get(f"/api/products/barcode/{world.pa.sku}")          # SKU/PLU ham topiladi
    assert r.status_code == 200 and r.json()["id"] == world.pa.id, r.text
    # begona korxona shtrix-kodi
    r = c.get(f"/api/products/barcode/{world.pb.barcode}")
    assert r.status_code == 404, r.text


def test_pos_list_server_search_beyond_first_page(db, mk, client):
    """Alifbo bo'yicha 500-dan keyingi tovar: pos.js serverda `search=` bilan topadi."""
    c = mk.company()
    b = mk.branch(c)
    w = mk.warehouse(c, b)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    p = _product(db, c, name="Zzz Yashil choy")
    _stock(db, p, w, 5)
    r = client.login(cashier).get("/api/products/pos-list", params={"limit": 50, "search": "Yashil choy",
                                                                    "warehouse_id": w.id})
    assert r.status_code == 200, r.text
    assert any(x["id"] == p.id for x in r.json())


# ───────────────────── 10. Kirim ro'yxati ─────────────────────

def test_movements_type_IN_purchase_ok_lowercase_422_cashier_403(db, mk, client):
    c, b, w, mgr = mk.tenant(UserRole.manager)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    r = client.login(mgr).get("/api/inventory/movements", params={"type": "IN", "reference_type": "purchase", "limit": 30})
    assert r.status_code == 200, r.text
    assert client.login(mgr).get("/api/inventory/movements", params={"type": "in", "limit": 30}).status_code == 422
    # kassirga yopiq — shu sabab pos.js kassirda Kirim tabini yashiradi va so'rov yubormaydi
    assert client.login(cashier).get("/api/inventory/movements", params={"type": "IN", "limit": 30}).status_code == 403


# ───────────────────── 11. Kassa statistikasi (/shifts/current) ─────────────────────

def test_shifts_current_none_without_shift_and_has_balances_shape(db, world, client):
    c = client.login(world.ua)
    r = c.get("/api/shifts/current")
    assert r.status_code == 200, r.text
    assert r.json() is None                    # pos.js: smena yo'q -> jamlar nol
    r = c.post("/api/shifts/open", json={"note": ""})
    assert r.status_code in (200, 201), r.text
    cur = c.get("/api/shifts/current").json()
    assert cur["id"] and "balances" in cur and "total_sales" in cur
    # savdo qilinsa balansga tushadi
    assert c.post("/api/sales/", json=_sale_body(world)).status_code == 200
    cur = c.get("/api/shifts/current").json()
    assert Decimal(str(cur["balances"]["cash"]["UZS"])) == Decimal("2000")
    z = c.get(f"/api/shifts/{cur['id']}/z-report")
    assert z.status_code == 200, z.text
    assert z.json()["sales"]["count"] == 1 and "returns" in z.json()


def test_shift_of_other_company_not_visible(db, world, client):
    sh = client.login(world.ub).post("/api/shifts/open", json={"note": ""})
    assert sh.status_code in (200, 201), sh.text
    sid = sh.json()["id"]
    assert client.login(world.ua).get("/api/shifts/current").json() is None
    assert client.login(world.ua).get(f"/api/shifts/{sid}/z-report").status_code in (403, 404)


# ───────────────────── Statik tekshiruvlar: pos.js / index.html ─────────────────────

@pytest.fixture(scope="module")
def pos():
    return _read(POS_JS)


@pytest.fixture(scope="module")
def html():
    return _read(POS_HTML)


def _func(src, name):
    """`function name(` / `async function name(` tanasi (qavslar bo'yicha)."""
    m = re.search(r'(?:async\s+)?function\s+' + re.escape(name) + r'\s*\(', src)
    assert m, name
    # parametrlar qavsini (default `= {}` bo'lishi mumkin) o'tkazib, tana `{` ini topamiz
    k, pd = m.end(), 1
    while pd:
        pd += {'(': 1, ')': -1}.get(src[k], 0)
        k += 1
    i = src.index('{', k)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    raise AssertionError(name)


def test_login_handles_company_selection_and_refresh(pos, html):
    assert 'needs_company_selection' in pos and '/api/auth/select-company' in pos
    assert 'temp_token' in pos and 'company_id' in pos
    assert "pos_refresh" in pos and '/api/auth/refresh' in pos
    # api(): 401 da avval refresh urinadi, keyin login oynasi
    api_src = _func(pos, 'api')
    assert 'tryRefreshToken' in api_src and api_src.index('tryRefreshToken') < api_src.index('openLoginModal')
    assert 'id="companyModal"' in html and 'id="companyChoiceList"' in html
    # access_token bo'sh bo'lsa saqlanmaydi (Bearer null bo'lmaydi)
    assert "data.access_token" in _func(pos, 'finishLogin')


def test_company_names_written_with_textcontent(pos):
    src = _func(pos, 'showCompanyChoices')
    assert 'textContent' in src and 'innerHTML' not in src
    assert 'textContent' in _func(pos, 'renderCompanyHeader')
    assert 'innerHTML' not in _func(pos, 'renderCustomerOptions')


def test_process_sale_payload_customer_debt_idempotency_warehouse(pos):
    src = _func(pos, 'processSale')
    assert 'customer_id: customerId ? Number(customerId) : null' in src
    assert "payMethod === 'debt' ? (enteredPaid || 0) : (enteredPaid || total)" in src
    # nasiya + mijozsiz: so'rov yuborilmaydi
    assert "payMethod === 'debt' && !customerId" in src
    assert src.index("payMethod === 'debt' && !customerId") < src.index("api('/sales/'")
    assert 'Nasiya uchun mijoz tanlang' in src
    assert 'debt_due_date' in src and 'warehouse_id: Number(posWarehouseId)' in src
    assert "'Idempotency-Key': saleKeyFor(payload)" in src
    assert "'cash' | 'card' | 'credit'" not in src


def test_returns_use_return_items_not_refund(pos):
    assert '/refund' not in pos
    src = _func(pos, 'processReturn')
    assert "/return-items" in src and 'sale_item_id' in src and 'payment_type' in src and "note: 'Qaytarish'" in src
    assert 'returned_quantity' in _func(pos, '_returnRemaining')
    assert "api('/sales/' + sale.id)" in _func(pos, 'selectReturnSale')


def test_company_info_uses_existing_endpoints_and_no_balance(pos, html):
    src = _func(pos, 'loadCompanyInfo')
    assert '/billing/my-company' in src and '/branches/' in src
    assert 'api(`/companies/${' not in pos and 'branch.balance' not in pos
    assert 'companyBalance' not in pos and 'companyBalance' not in html
    assert 'settBranch' not in html and 'Asosiy filial' not in html


def test_receipt_template_saved_to_localstorage(pos):
    src = _func(pos, 'loadReceiptTemplates')
    assert '/companies/me/receipt_templates' in src
    assert "localStorage.setItem('erp_receipt_settings'" in src and '_company_id' in src
    assert 'loadReceiptTemplates()' in _func(pos, 'loadAllData')


def test_warehouse_selection_and_products_use_warehouse(pos, html):
    assert "'&warehouse_id=' + encodeURIComponent(posWarehouseId)" in _func(pos, 'loadProducts')
    assert "localStorage.setItem('pos_warehouseId'" in pos
    assert 'id="settWarehouse"' in html
    assert 'settWarehouse' in _func(pos, 'renderPosWarehouseSelect')


def test_barcode_falls_back_to_server_and_keeps_scale_logic(pos):
    src = _func(pos, 'saleBarcodeKey')
    assert 'lookupBarcodeOnServer' in src
    assert "startsWith('21')" in src and "startsWith('22')" in src and 'weightGram / 1000' in src
    assert '/products/barcode/' in _func(pos, 'lookupBarcodeOnServer')
    assert '/products/pos-list?limit=50&search=' in _func(pos, 'scheduleServerSearch')


def test_customer_search_debounced_limit_20(pos, html):
    assert '/customers?limit=20&search=' in _func(pos, 'loadCustomers')
    assert 'setTimeout' in _func(pos, 'customerSearchInput') and '300' in _func(pos, 'customerSearchInput')
    assert '/customers/?limit=200' not in pos
    assert 'id="saleCustomerSearch"' in html and 'id="saleCustomerList"' in html
    assert 'id="debtDueInp"' in html


def test_kirim_list_type_IN_and_cashier_hidden(pos):
    src = _func(pos, 'loadKirimList')
    assert "type=IN&reference_type=purchase&limit=30" in src
    assert 'type=in' not in pos and "movements?limit=30" not in pos
    assert 'canSeeKirim' in src
    assert "'cashier'" not in re.search(r"const KIRIM_ROLES = \[[^\]]*\]", pos).group(0)
    assert 'canSeeKirim' in _func(pos, 'switchTab')


def test_kassa_stats_from_current_shift(pos):
    src = _func(pos, 'loadKassaStats')
    assert "api('/shifts/current')" in src and 'z-report' in src
    assert "kassaReturnTotal').textContent = '0" not in src
    assert 'balances' in src


def test_reprint_builds_receipt(pos):
    src = _func(pos, 'reprint')
    assert "api('/sales/'" in src and 'showReceipt(' in src


def test_fiscal_setting_is_persisted_and_header_sent(pos, html):
    assert 'id="settFactoryId"' in html
    assert "pos_fiskalSend" in pos and "pos_fiskalId" in pos
    src = _func(pos, 'fiscalHeaders')
    assert 'X-Hippo-Factory-Id' in src and "'/shifts/close'" in src and "'/sales/'" in src
    assert 'fiscalHeaders(path, opts.method)' in _func(pos, 'api')
    save = _func(pos, 'saveSettings')
    assert 'CFG.fiscal = settingsToggles.fiscal' in save and 'pos_fiskalSend' in save


def test_no_new_unescaped_interpolations_and_no_node_api(pos):
    assert 'require(' not in pos and 'ipcRenderer' not in pos
    # T0.19 bilan mos: qaytarish ro'yxatidagi onclick kodlash saqlangan
    assert ".replace(/'/g, '%27')" in pos


# ───────────────────── node bilan toza funksiyalar ─────────────────────

def _node():
    cand = shutil.which('node') or os.environ.get('NODE_BIN')
    return cand if cand and os.path.exists(cand) else None


@pytest.mark.skipif(_node() is None, reason='node topilmadi')
def test_fiscal_headers_and_sale_key_runtime(pos):
    snippet = _func(pos, 'fiscalHeaders') + '\n' + _func(pos, 'newSaleKey') + '\n' + _func(pos, 'saleKeyFor')
    code = f"""
let CFG = {{ fiscal: true, fiskalId: 'F-77' }};
let _saleKey = {{ sig: '', key: '' }};
{snippet}
const out = {{
  sale: fiscalHeaders('/sales/', 'POST'),
  get: fiscalHeaders('/sales/', 'GET'),
  ret: fiscalHeaders('/sales/5/return-items', 'POST'),
  close: fiscalHeaders('/shifts/close', 'POST'),
  close2: fiscalHeaders('/shifts/12/close', 'POST'),
}};
CFG.fiscal = false;
out.off = fiscalHeaders('/sales/', 'POST');
const k1 = saleKeyFor({{a: 1}}), k2 = saleKeyFor({{a: 1}}), k3 = saleKeyFor({{a: 2}});
out.same = k1 === k2; out.diff = k1 !== k3; out.len = k1.length > 8;
console.log(JSON.stringify(out));
"""
    with tempfile.TemporaryDirectory() as tmp:
        p = subprocess.run([_node(), '-e', code], cwd=tmp, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    res = json.loads(p.stdout.strip().splitlines()[-1])
    assert res['sale'] == {'X-Hippo-Factory-Id': 'F-77'} and res['get'] == {} and res['ret'] == {}
    assert res['close'] == res['close2'] == {'X-Hippo-Factory-Id': 'F-77'}
    assert res['off'] == {}
    assert res['same'] and res['diff'] and res['len']
