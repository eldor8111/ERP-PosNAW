"""T1.12 — Filial hayot sikli: is_active tekshiruvi va arxivlash.

Qamrov: har bir bloker turi (ochiq smena, kassa, balans, qoldiq, transfer, buyurtma, PO, inventarizatsiya,
ishlab chiqarish, faol xodim, kutilayotgan sotuv) PATCH/DELETE da 409; muvaffaqiyatli arxiv (closed_*,
omborlar/kassalar, xodimlarni ko'chirish) va reopen (tarif limiti 403); default_branch_id va fallback'lar
nofaol filialni tashlab ketishi; resolve_branch_id (409) va create_sale (400) nofaol filial uchun;
ombor DELETE/PATCH qoldiq bilan 409, branch_id=null; qoldiq jami arxivlangan omborni hisobga olmaydi;
Company.is_active=false -> 403 (billing yo'li o'tadi); ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T1_12.py -q -p no:cacheprovider
"""
import itertools
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.audit_log import AuditLog
from app.models.billing import Tariff
from app.models.bom import BOM
from app.models.branch import Branch
from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.inventory_count import CountStatus, InventoryCount
from app.models.moliya import Wallet
from app.models.order import Order, OrderStatus
from app.models.product import Product
from app.models.production_order import ProductionOrder, ProductionOrderStatus
from app.models.purchase_order import POStatus, PurchaseOrder
from app.models.sale import Sale, SaleStatus
from app.models.shift import Shift
from app.models.supplier import Supplier
from app.models.transfer import StockTransfer, TransferStatus
from app.models.user import UserRole, UserStatus
from app.models.user_branch import UserBranch
from app.models.user_company import UserCompany
from app.models.warehouse import Warehouse
from app.schemas.sale import SaleCreate
from app.services.branch_helpers import (
    archive_branch, BranchCloseBlocked, branch_close_blockers, default_branch_id,
    fallback_active_branch_id, fallback_active_branch_id_or_400, reopen_branch,
)
from app.services.sale_create import create_sale
from app.services.sale_helpers import resolve_branch_id

_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _tariff(db, company, max_branches=10):
    t = Tariff(name="Test tarif", max_branches=max_branches, price_per_month=100000)
    db.add(t)
    db.flush()
    company.tariff_id = t.id
    company.subscription_ends_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.flush()
    return t


def _product(db, company):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"T112-{n}", barcode=f"B112-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _stock(db, product, wh, qty=10):
    s = StockLevel(product_id=product.id, warehouse_id=wh.id, quantity=Decimal(qty))
    db.add(s)
    db.flush()
    return s


def _wallet(db, company, branch, balance=0, is_open=False):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal(balance), company_id=company.id,
               branch_id=branch.id, is_active=True, is_open=is_open)
    db.add(w)
    db.flush()
    return w


@pytest.fixture
def w(db, mk):
    """A korxona: admin (filialsiz), a1 (ombor wh1, kassir), a2 (zaxira filial); B korxona: admin + filial."""
    ca = mk.company()
    _tariff(db, ca)
    a1 = mk.branch(ca, "Filial A1")
    a2 = mk.branch(ca, "Filial A2")
    wh1 = mk.warehouse(ca, a1, name="Ombor A1")
    wh2 = mk.warehouse(ca, a2, name="Ombor A2")
    admin = mk.user(ca, role=UserRole.admin)
    cashier = mk.user(ca, role=UserRole.cashier, branch=a1)
    cb, b1, whb, admin_b = mk.tenant(UserRole.admin)
    _tariff(db, cb)
    return dict(ca=ca, a1=a1, a2=a2, wh1=wh1, wh2=wh2, admin=admin, cashier=cashier,
                cb=cb, b1=b1, whb=whb, admin_b=admin_b)


def _close_check(client, admin, branch):
    r = client.login(admin).get(f"/api/branches/{branch.id}/close-check")
    assert r.status_code == 200, r.text
    return r.json()


def _assert_blocked(client, admin, branch, key):
    """Bloker `key` close-check da ko'rinadi, PATCH va DELETE esa 409 (detail — matn, blockers bilan)."""
    chk = _close_check(client, admin, branch)
    assert chk["can_close"] is False
    val = chk["blockers"][key]
    assert (len(val) if isinstance(val, list) else val) > 0, chk
    cl = client.login(admin)
    r = cl.patch(f"/api/branches/{branch.id}", json={"is_active": False})
    assert r.status_code == 409, r.text
    body = r.json()
    assert isinstance(body["detail"], str) and body["detail"].startswith("Filialni yopib bo'lmaydi")
    assert body["blockers"][key]
    r = cl.delete(f"/api/branches/{branch.id}")
    assert r.status_code == 409, r.text


# ── 1. Har bir bloker turi ───────────────────────────────────────────────────

def _free_branch(db, mk, w, name="Yopiladigan"):
    """Xodimsiz, omborsiz toza filial (faqat tekshirilayotgan bloker qo'shiladi)."""
    return mk.branch(w["ca"], name)


def test_blocker_open_shift(db, mk, client, w):
    b = _free_branch(db, mk, w)
    cashier = mk.user(w["ca"], role=UserRole.cashier)   # filialsiz xodim: faol xodim bloker emas
    db.add(Shift(cashier_id=cashier.id, branch_id=b.id, company_id=w["ca"].id, status="open"))
    db.flush()
    _assert_blocked(client, w["admin"], b, "open_shifts")


def test_blocker_open_kassa_and_balance(db, mk, client, w):
    b = _free_branch(db, mk, w)
    _wallet(db, w["ca"], b, balance=0, is_open=True)
    _assert_blocked(client, w["admin"], b, "open_kassa")

    b2 = _free_branch(db, mk, w, "Boshqa")
    wl = _wallet(db, w["ca"], b2, balance=4_000_000, is_open=False)
    _assert_blocked(client, w["admin"], b2, "wallets_with_balance")
    assert _close_check(client, w["admin"], b2)["blockers"]["wallets_with_balance"][0]["id"] == wl.id


def test_blocker_stock_including_negative(db, mk, client, w):
    b = _free_branch(db, mk, w)
    wh = mk.warehouse(w["ca"], b, name="Qoldiqli")
    _stock(db, _product(db, w["ca"]), wh, qty=-3)       # manfiy ham bloker
    _assert_blocked(client, w["admin"], b, "stock")
    st = _close_check(client, w["admin"], b)["blockers"]["stock"][0]
    assert st["warehouse_id"] == wh.id and st["qty"] == -3.0


def test_blocker_pending_transfer(db, mk, client, w):
    b = _free_branch(db, mk, w)
    wh = mk.warehouse(w["ca"], b)
    db.add(StockTransfer(number=f"TR-{next(_seq)}", from_warehouse_id=wh.id, to_warehouse_id=w["wh2"].id,
                         status=TransferStatus.pending, created_by=w["admin"].id))
    db.flush()
    _assert_blocked(client, w["admin"], b, "pending_transfers")


def test_blocker_open_order(db, mk, client, w):
    b = _free_branch(db, mk, w)
    p = _product(db, w["ca"])
    cust = Customer(name="Mijoz", phone="998900000001", company_id=w["ca"].id)
    db.add(cust)
    db.flush()
    db.add(Order(company_id=w["ca"].id, customer_id=cust.id, branch_id=b.id, product_id=p.id, quantity=1,
                 unit_price=Decimal("1000"), total_amount=Decimal("1000"), status=OrderStatus.pending))
    db.flush()
    _assert_blocked(client, w["admin"], b, "open_orders")


def test_blocker_purchase_order(db, mk, client, w):
    b = _free_branch(db, mk, w)
    wh = mk.warehouse(w["ca"], b)
    sup = Supplier(name="Ta'minotchi", company_id=w["ca"].id)
    db.add(sup)
    db.flush()
    db.add(PurchaseOrder(number=f"PO-{next(_seq)}", supplier_id=sup.id, warehouse_id=wh.id,
                         company_id=w["ca"].id, status=POStatus.sent, created_by=w["admin"].id))
    db.flush()
    _assert_blocked(client, w["admin"], b, "open_purchase_orders")


def test_blocker_inventory_count(db, mk, client, w):
    b = _free_branch(db, mk, w)
    wh = mk.warehouse(w["ca"], b)
    db.add(InventoryCount(number=f"IC-{next(_seq)}", warehouse_id=wh.id, status=CountStatus.in_progress,
                          created_by=w["admin"].id))
    db.flush()
    _assert_blocked(client, w["admin"], b, "open_counts")


def test_blocker_production(db, mk, client, w):
    b = _free_branch(db, mk, w)
    wh = mk.warehouse(w["ca"], b)
    p = _product(db, w["ca"])
    bom = BOM(product_id=p.id, name="Retsept")
    db.add(bom)
    db.flush()
    db.add(ProductionOrder(number=f"PR-{next(_seq)}", bom_id=bom.id, product_id=p.id,
                           planned_quantity=Decimal("5"), warehouse_id=w["wh2"].id, target_warehouse_id=wh.id,
                           status=ProductionOrderStatus.in_progress, company_id=w["ca"].id,
                           created_by=w["admin"].id))
    db.flush()
    _assert_blocked(client, w["admin"], b, "open_production")


def test_blocker_pending_sale(db, mk, client, w):
    b = _free_branch(db, mk, w)
    wh = mk.warehouse(w["ca"], b)
    db.add(Sale(number=f"S-{next(_seq)}", cashier_id=w["admin"].id, total_amount=Decimal("1000"),
                paid_amount=Decimal("0"), payment_type="cash", status=SaleStatus.pending,
                company_id=w["ca"].id, warehouse_id=wh.id, branch_id=b.id))
    db.flush()
    _assert_blocked(client, w["admin"], b, "pending_sales")


def test_blocker_active_users_and_reassign_makes_it_closable(db, mk, client, w):
    # a1 da kassir bor -> faol xodim bloker
    _assert_blocked(client, w["admin"], w["a1"], "active_users")
    # xodimlar boshqa filialga ko'chirilsa bloker yo'q
    r = client.login(w["admin"]).get(
        f"/api/branches/{w['a1'].id}/close-check", params={"reassign_users_to_branch_id": w["a2"].id})
    assert r.json()["can_close"] is True


def test_inactive_user_and_inactive_warehouse_do_not_block(db, mk, client, w):
    b = _free_branch(db, mk, w)
    mk.user(w["ca"], role=UserRole.cashier, branch=b, status=UserStatus.inactive)
    wh = mk.warehouse(w["ca"], b, is_active=False)
    _stock(db, _product(db, w["ca"]), wh, qty=5)     # nofaol ombor qoldig'i yopishni abadiy to'smaydi
    assert _close_check(client, w["admin"], b)["can_close"] is True


# ── 2. Muvaffaqiyatli arxiv ──────────────────────────────────────────────────

def test_archive_success_cascade_and_reassign(db, mk, client, w):
    a1, a2, ca = w["a1"], w["a2"], w["ca"]
    wh_empty = w["wh1"]
    wh_second = mk.warehouse(ca, a1, name="Ikkinchi")
    wallet_closed = _wallet(db, ca, a1, balance=0, is_open=False)
    multi = mk.user(ca, role=UserRole.manager, branch=a1)
    db.add(UserCompany(user_id=multi.id, company_id=ca.id, role=UserRole.manager, branch_id=a1.id, is_active=True))
    db.add(UserBranch(user_id=multi.id, company_id=ca.id, branch_id=a1.id))
    db.flush()

    r = client.login(w["admin"]).post(
        f"/api/branches/{a1.id}/archive",
        json={"reason": "Ijara tugadi", "reassign_users_to_branch_id": a2.id})
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False and r.json()["close_reason"] == "Ijara tugadi"

    db.refresh(a1)
    assert a1.is_active is False and a1.closed_at is not None
    assert a1.closed_by == w["admin"].id and a1.close_reason == "Ijara tugadi"
    for wh in (wh_empty, wh_second):
        db.refresh(wh)
        assert wh.is_active is False
    db.refresh(wallet_closed)
    assert wallet_closed.is_active is False
    # xodimlar ko'chdi
    db.refresh(w["cashier"])
    db.refresh(multi)
    assert w["cashier"].branch_id == a2.id and multi.branch_id == a2.id
    uc = db.query(UserCompany).filter_by(user_id=multi.id, company_id=ca.id).one()
    assert uc.branch_id == a2.id
    assert db.query(UserBranch).filter_by(user_id=multi.id).one().branch_id == a2.id
    # audit
    assert db.query(AuditLog).filter(AuditLog.action == "ARCHIVE", AuditLog.entity_id == a1.id).count() == 1


def test_archive_via_patch_and_delete(db, mk, client, w):
    b = _free_branch(db, mk, w, "P1")
    cl = client.login(w["admin"])
    r = cl.patch(f"/api/branches/{b.id}", json={"is_active": False})
    assert r.status_code == 200, r.text
    db.refresh(b)
    assert b.is_active is False and b.closed_at is not None
    b2 = _free_branch(db, mk, w, "P2")
    assert cl.delete(f"/api/branches/{b2.id}").status_code == 204
    db.refresh(b2)
    assert b2.is_active is False and b2.closed_at is not None


def test_archive_with_open_wallet_balance_keeps_nothing_changed(db, mk, client, w):
    b = _free_branch(db, mk, w)
    wh = mk.warehouse(w["ca"], b)
    _wallet(db, w["ca"], b, balance=100, is_open=False)
    r = client.login(w["admin"]).post(f"/api/branches/{b.id}/archive", json={})
    assert r.status_code == 409
    db.refresh(b)
    db.refresh(wh)
    assert b.is_active is True and b.closed_at is None and wh.is_active is True


def test_archive_reassign_validation(db, mk, client, w):
    b = _free_branch(db, mk, w)
    cl = client.login(w["admin"])
    assert cl.post(f"/api/branches/{b.id}/archive", json={"reassign_users_to_branch_id": b.id}).status_code == 400
    # begona korxona filiali -> 404
    assert cl.post(f"/api/branches/{b.id}/archive",
                   json={"reassign_users_to_branch_id": w["b1"].id}).status_code == 404
    # nofaol filial -> 400
    dead = mk.branch(w["ca"], "O'lik", is_active=False)
    assert cl.post(f"/api/branches/{b.id}/archive",
                   json={"reassign_users_to_branch_id": dead.id}).status_code == 400


def test_archive_reason_too_long_is_422(db, mk, client, w):
    b = _free_branch(db, mk, w)
    r = client.login(w["admin"]).post(f"/api/branches/{b.id}/archive", json={"reason": "x" * 300})
    assert r.status_code == 422


# ── 3. Reopen ────────────────────────────────────────────────────────────────

def test_reopen_clears_closed_fields_and_lists_inactive_assets(db, mk, client, w):
    b = _free_branch(db, mk, w, "Qayta")
    wh = mk.warehouse(w["ca"], b, name="Eski ombor")
    cl = client.login(w["admin"])
    assert cl.post(f"/api/branches/{b.id}/archive", json={"reason": "vaqtincha"}).status_code == 200
    r = cl.post(f"/api/branches/{b.id}/reopen")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_active"] is True and body["closed_at"] is None and body["close_reason"] is None
    assert [x["id"] for x in body["inactive_warehouses"]] == [wh.id]     # avto-yoqilmaydi
    db.refresh(wh)
    assert wh.is_active is False
    db.refresh(b)
    assert b.closed_by is None
    assert db.query(AuditLog).filter(AuditLog.action == "REOPEN", AuditLog.entity_id == b.id).count() == 1
    # allaqachon faol -> 400
    assert cl.post(f"/api/branches/{b.id}/reopen").status_code == 400


def test_reopen_and_patch_true_respect_tariff_limit(db, mk, client):
    c, b1, wh, admin = mk.tenant()
    _tariff(db, c, max_branches=1)          # b1 faol -> limit to'lgan
    dead = mk.branch(c, "Nofaol", is_active=False)
    cl = client.login(admin)
    r = cl.post(f"/api/branches/{dead.id}/reopen")
    assert r.status_code == 403, r.text
    assert "maksimal filiallar soni" in r.json()["detail"]
    assert cl.patch(f"/api/branches/{dead.id}", json={"is_active": True}).status_code == 403
    db.refresh(dead)
    assert dead.is_active is False
    # limit oshirilsa PATCH ham, reopen ham o'tadi
    c.tariff.max_branches = 5
    db.flush()
    assert cl.patch(f"/api/branches/{dead.id}", json={"is_active": True}).status_code == 200


def test_list_branches_include_inactive(db, mk, client, w):
    dead = mk.branch(w["ca"], "Arxiv", is_active=False)
    cl = client.login(w["admin"])
    ids = {x["id"] for x in cl.get("/api/branches").json()}
    assert dead.id not in ids and w["a1"].id in ids
    ids_all = {x["id"] for x in cl.get("/api/branches", params={"include_inactive": "true"}).json()}
    assert dead.id in ids_all and w["a1"].id in ids_all
    assert w["b1"].id not in ids_all        # begona korxona filiali hech qachon


# ── 4. Korxonalararo izolyatsiya ─────────────────────────────────────────────

def test_cross_company_isolation(db, mk, client, w):
    a_admin, b_branch = w["admin"], w["b1"]
    cl = client.login(a_admin)
    assert cl.get(f"/api/branches/{b_branch.id}/close-check").status_code == 404
    assert cl.post(f"/api/branches/{b_branch.id}/archive", json={}).status_code == 404
    assert cl.post(f"/api/branches/{b_branch.id}/reopen").status_code == 404
    assert cl.delete(f"/api/branches/{b_branch.id}").status_code == 404
    db.refresh(b_branch)
    assert b_branch.is_active is True
    # ijobiy yo'l: o'z filiali ishlaydi
    own = _free_branch(db, mk, w)
    assert cl.get(f"/api/branches/{own.id}/close-check").json()["can_close"] is True


def test_non_admin_cannot_archive(db, mk, client, w):
    b = _free_branch(db, mk, w)
    cl = client.login(w["cashier"])
    assert cl.get(f"/api/branches/{b.id}/close-check").status_code == 403
    assert cl.post(f"/api/branches/{b.id}/archive", json={}).status_code == 403
    assert cl.post(f"/api/branches/{b.id}/reopen").status_code == 403


# ── 5. default_branch_id va fallback'lar ─────────────────────────────────────

def test_default_branch_id_skips_inactive_and_orders_by_id(db, mk):
    c = mk.company()
    dead = mk.branch(c, "Birinchi lekin nofaol", is_active=False)
    live2 = mk.branch(c, "Ikkinchi")
    live3 = mk.branch(c, "Uchinchi")
    assert default_branch_id(db, c.id) == live2.id
    live2.is_active = False
    db.flush()
    assert default_branch_id(db, c.id) == live3.id
    live3.is_active = False
    db.flush()
    assert default_branch_id(db, c.id) is None
    assert dead.id < live2.id


def test_fallback_active_branch_never_picks_archived(db, mk):
    c = mk.company()
    main = mk.branch(c, "Asosiy", is_main=True)
    other = mk.branch(c, "Boshqa")
    u = mk.user(c, role=UserRole.manager)
    assert fallback_active_branch_id(db, u) == main.id
    main.is_active = False
    db.flush()
    assert fallback_active_branch_id(db, u) == other.id        # arxivlangan asosiy filial tanlanmaydi
    other.is_active = False
    db.flush()
    assert fallback_active_branch_id(db, u) is None
    with pytest.raises(HTTPException) as e:
        fallback_active_branch_id_or_400(db, u)
    assert e.value.status_code == 400 and e.value.detail == "Faol filial topilmadi"


def test_kassa_expense_without_branch_uses_active_branch(db, mk, client):
    c = mk.company()
    dead = mk.branch(c, "Arxiv", is_active=False)
    live = mk.branch(c, "Faol")
    wallet = Wallet(name="Umumiy", type="cash", balance=Decimal("1000"), company_id=c.id, is_active=True,
                    is_open=True)
    db.add(wallet)
    db.flush()
    admin = mk.user(c, role=UserRole.admin)
    from app.models.moliya import ExpenseCategory, Expense
    cat = ExpenseCategory(name="Kategoriya", company_id=c.id)
    db.add(cat)
    db.flush()
    r = client.login(admin).post("/api/kassa/do-expense", json={
        "wallet_id": wallet.id, "category_id": cat.id, "amount": 100, "payment_type": "cash"})
    assert r.status_code in (200, 201), r.text
    exp = db.query(Expense).filter(Expense.company_id == c.id).one()
    assert exp.branch_id == live.id and exp.branch_id != dead.id


def test_kassa_expense_400_when_no_active_branch(db, mk, client):
    c = mk.company()
    mk.branch(c, "Arxiv", is_active=False)
    wallet = Wallet(name="Umumiy", type="cash", balance=Decimal("1000"), company_id=c.id, is_active=True,
                    is_open=True)
    db.add(wallet)
    db.flush()
    admin = mk.user(c, role=UserRole.admin)
    from app.models.moliya import ExpenseCategory
    cat = ExpenseCategory(name="Kategoriya", company_id=c.id)
    db.add(cat)
    db.flush()
    r = client.login(admin).post("/api/kassa/do-expense", json={
        "wallet_id": wallet.id, "category_id": cat.id, "amount": 100, "payment_type": "cash"})
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "Faol filial topilmadi"


def test_marketplace_default_branch_must_be_active(db, mk):
    from app.services.marketplace_service import _resolve_mirmaza_branch_id
    c = mk.company()
    dead = mk.branch(c, "Arxiv", is_active=False)
    live = mk.branch(c, "Faol")
    c.marketplace_default_branch_id = dead.id
    db.flush()
    assert _resolve_mirmaza_branch_id(db, c.id, None) == live.id
    live.is_active = False
    db.flush()
    assert _resolve_mirmaza_branch_id(db, c.id, None) is None      # `1` ga tushmaydi, buyurtma o'tkaziladi


# ── 6. resolve_branch_id va sotuv ────────────────────────────────────────────

def test_resolve_branch_id_409_for_user_of_closed_branch(db, mk, w):
    w["a1"].is_active = False
    db.flush()
    with pytest.raises(HTTPException) as e:
        resolve_branch_id(db, w["cashier"], None)
    assert e.value.status_code == 409
    assert e.value.detail == "Filialingiz yopilgan. Administrator bilan bog'laning."


def test_resolve_branch_id_skips_inactive_warehouse_branch(db, mk, w):
    # filialsiz admin: yopilgan filial ombori o'tkazib yuboriladi, faol filialga tushadi
    w["a1"].is_active = False
    db.flush()
    got = resolve_branch_id(db, w["admin"], w["wh1"].id)
    assert got is not None and got != w["a1"].id
    assert db.get(Branch, got).is_active is True


def _sale_data(product, wh_id=None):
    return SaleCreate(items=[{"product_id": product.id, "quantity": 1, "unit_price": 1000}],
                      payment_type="cash", warehouse_id=wh_id,
                      payments=[{"type": "cash", "amount": 1000}], paid_amount=Decimal("1000"))


def test_create_sale_closed_branch_user_409_and_closed_warehouse_400(db, mk, w):
    p = _product(db, w["ca"])
    _stock(db, p, w["wh1"], 10)
    _stock(db, p, w["wh2"], 10)
    # ijobiy yo'l: faol filial ombori
    sale = create_sale(db, _sale_data(p, w["wh2"].id), w["admin"])
    assert sale.id and sale.branch_id == w["a2"].id

    # filialsiz admin yopilgan filial omboridan sota olmaydi -> 400
    w["a1"].is_active = False
    db.flush()
    with pytest.raises(HTTPException) as e:
        create_sale(db, _sale_data(p, w["wh1"].id), w["admin"])
    assert e.value.status_code == 400 and e.value.detail == "Ombor filiali yopilgan"
    st = db.query(StockLevel).filter_by(product_id=p.id, warehouse_id=w["wh1"].id).one()
    assert st.quantity == 10          # qoldiq yechilmadi

    # yopilgan filial xodimi (ko'chirilmagan) -> 409
    with pytest.raises(HTTPException) as e:
        create_sale(db, _sale_data(p, w["wh2"].id), w["cashier"])
    assert e.value.status_code == 409 and "Filialingiz yopilgan" in e.value.detail


# ── 7. Ombor: DELETE/PATCH qoldiq bilan, branch_id=null ──────────────────────

def test_warehouse_delete_blocked_by_stock_then_ok(db, mk, client, w):
    wh = mk.warehouse(w["ca"], w["a2"], name="Qoldiqli")
    st = _stock(db, _product(db, w["ca"]), wh, qty=7)
    cl = client.login(w["admin"])
    r = cl.delete(f"/api/warehouses/{wh.id}")
    assert r.status_code == 409 and r.json()["detail"] == "Omborda qoldiq bor: 1 ta mahsulot"
    r = cl.patch(f"/api/warehouses/{wh.id}", json={"is_active": False})
    assert r.status_code == 409 and r.json()["detail"].startswith("Omborda qoldiq bor")
    db.refresh(wh)
    assert wh.is_active is True
    st.quantity = Decimal("0")
    db.flush()
    assert cl.delete(f"/api/warehouses/{wh.id}").status_code == 204
    db.refresh(wh)
    assert wh.is_active is False


def test_warehouse_negative_stock_and_open_documents_block(db, mk, client, w):
    cl = client.login(w["admin"])
    wh = mk.warehouse(w["ca"], w["a2"], name="Manfiy")
    s = _stock(db, _product(db, w["ca"]), wh, qty=-1)
    assert cl.delete(f"/api/warehouses/{wh.id}").status_code == 409
    s.quantity = Decimal("0")
    db.flush()
    db.add(StockTransfer(number=f"TR-{next(_seq)}", from_warehouse_id=wh.id, to_warehouse_id=w["wh2"].id,
                         status=TransferStatus.in_transit, created_by=w["admin"].id))
    db.flush()
    r = cl.patch(f"/api/warehouses/{wh.id}", json={"is_active": False})
    assert r.status_code == 409 and "ochiq hujjatlar" in r.json()["detail"]


def test_warehouse_patch_branch_null_detaches_and_validates(db, mk, client, w):
    wh = mk.warehouse(w["ca"], w["a2"], name="Ajratiladigan")
    cl = client.login(w["admin"])
    r = cl.patch(f"/api/warehouses/{wh.id}", json={"branch_id": None})
    assert r.status_code == 200, r.text
    db.refresh(wh)
    assert wh.branch_id is None
    # begona korxona va nofaol filialga biriktirish rad etiladi
    assert cl.patch(f"/api/warehouses/{wh.id}", json={"branch_id": w["b1"].id}).status_code == 400
    dead = mk.branch(w["ca"], "Arxiv2", is_active=False)
    assert cl.patch(f"/api/warehouses/{wh.id}", json={"branch_id": dead.id}).status_code == 400
    assert cl.patch(f"/api/warehouses/{wh.id}", json={"branch_id": w["a1"].id}).status_code == 200


def test_warehouse_cross_company_isolation(db, mk, client, w):
    r = client.login(w["admin"]).delete(f"/api/warehouses/{w['whb'].id}")
    assert r.status_code == 404
    db.refresh(w["whb"])
    assert w["whb"].is_active is True


def test_super_admin_warehouse_requires_branch(db, mk, client):
    sa = mk.user(None, role=UserRole.super_admin)
    r = client.login(sa).post("/api/warehouses", json={"name": "Yetim"})
    assert r.status_code == 400
    assert db.query(Warehouse).filter(Warehouse.name == "Yetim").count() == 0


# ── 8. Arxivlangan ombor qoldig'i jamga qo'shilmaydi ─────────────────────────

def test_product_list_totals_exclude_archived_warehouse(db, mk, client, w):
    p = _product(db, w["ca"])
    _stock(db, p, w["wh1"], 5)
    wh_dead = mk.warehouse(w["ca"], w["a1"], name="Arxiv ombor", is_active=False)
    _stock(db, p, wh_dead, 100)
    cl = client.login(w["admin"])
    r = cl.get("/api/products", params={"limit": 50})
    assert r.status_code == 200, r.text
    row = next(x for x in (r.json() if isinstance(r.json(), list) else r.json()["items"]) if x["id"] == p.id)
    assert Decimal(str(row["stock_quantity"])) == Decimal("5")
    assert all(ws["warehouse_id"] != wh_dead.id for ws in row.get("warehouse_stocks", []))


# ── 9. Company.is_active ─────────────────────────────────────────────────────

def test_company_inactive_blocks_everything_except_billing_dependency(db, mk):
    from app.core.dependencies import _check_company_subscription
    c, b, wh, user = mk.tenant(UserRole.admin)
    _check_company_subscription(user, db)            # faol -> o'tadi
    c.is_active = None                               # NULL o'tadi (qat'iy `is False`)
    db.flush()
    _check_company_subscription(user, db)
    c.is_active = False
    db.flush()
    with pytest.raises(HTTPException) as e:
        _check_company_subscription(user, db)
    assert e.value.status_code == 403 and e.value.detail == "Korxona bloklangan"
    # super_admin ta'sirlanmaydi
    sa = mk.user(c, role=UserRole.super_admin)
    _check_company_subscription(sa, db)


def test_company_inactive_get_current_user_403_but_allow_expired_passes(db, mk):
    from fastapi.security import HTTPAuthorizationCredentials
    from starlette.requests import Request
    from app.core.dependencies import get_current_user, get_current_user_allow_expired
    from app.core.security import create_access_token

    c, b, wh, user = mk.tenant(UserRole.admin)
    c.is_active = False
    db.flush()
    token = create_access_token({"sub": str(user.id), "company_id": c.id, "role": user.role.value})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    req = Request({"type": "http", "method": "GET", "path": "/api/branches", "headers": [], "query_string": b""})
    with pytest.raises(HTTPException) as e:
        get_current_user(req, creds, db)
    assert e.value.status_code == 403 and e.value.detail == "Korxona bloklangan"
    # billing yo'li (allow_expired) bloklanmaydi
    got = get_current_user_allow_expired(req, creds, db)
    assert got.id == user.id


# ── 10. Blokerlar to'g'ridan-to'g'ri ─────────────────────────────────────────

def test_blockers_function_clean_branch_and_message(db, mk, w):
    b = _free_branch(db, mk, w)
    assert branch_close_blockers(db, b)["active_users"] == 0
    mk.user(w["ca"], role=UserRole.cashier, branch=b)
    bl = branch_close_blockers(db, b)
    assert bl["active_users"] == 1
    with pytest.raises(BranchCloseBlocked) as e:
        archive_branch(db, b, w["admin"])
    assert e.value.detail == "Filialni yopib bo'lmaydi: 1 ta faol xodim"
    # reassign bilan o'tadi, reopen esa tarif limitini tekshiradi
    archive_branch(db, b, w["admin"], reason=" sabab ", reassign_to=w["a2"].id)
    assert b.close_reason == "sabab"
    out = reopen_branch(db, b, w["admin"])
    assert b.is_active is True and out["inactive_warehouses"] == []
