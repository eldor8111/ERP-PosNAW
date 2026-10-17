"""T0.25 — Korxonani o'chirish (purge) boshqa korxona yozuvlariga tegmasligi (MODEL-01).

X korxonasi filiali (bx) ga Y korxonasining xarajat/tranzaksiya/buyurtmalari bog'langan holat:
Y qatorlari o'chmasligi va ularning filiali Y ning birinchi filialiga ko'chishi kerak.
"""
import pytest

from app.models.company import Company
from app.models.customer import Customer
from app.models.moliya import Expense, ExpenseCategory, Transaction, Wallet
from app.models.order import Order
from app.models.product import Product
from app.models.user import UserRole
from app.services import company_purge
from app.services.company_purge import PurgeError, _Purger, preview_company_purge, preview_company_purge_ex, purge_company

N_FOREIGN_EXP = 4


def _product(db, c, n):
    p = Product(name=f"Tovar {n}", sku=f"S{n}-{c.id}", barcode=f"B{n}-{c.id}", company_id=c.id)
    db.add(p)
    db.flush()
    return p


def _order(db, cust, br, prod):
    o = Order(customer_id=cust.id, branch_id=br.id, product_id=prod.id, quantity=1, unit_price=10, total_amount=10)
    db.add(o)
    db.flush()
    return o


class World:
    """X (o'chiriladi) va Y (saqlanadi). Y yozuvlari X ning bx filialiga yozilgan."""

    def __init__(self, db, mk, y_second_branch=True):
        self.db, self.mk = db, mk
        self.x = mk.company()
        self.y = mk.company()
        self.bx = mk.branch(self.x)
        self.by1 = mk.branch(self.y)
        self.by2 = mk.branch(self.y) if y_second_branch else None
        mk.user(self.x, role=UserRole.admin, branch=self.bx)
        mk.user(self.y, role=UserRole.admin, branch=self.by1)
        self.wx = Wallet(name="WX", company_id=self.x.id, branch_id=self.bx.id)
        self.wy = Wallet(name="WY", company_id=self.y.id, branch_id=self.by1.id)
        db.add_all([self.wx, self.wy])
        db.flush()
        self.cat_x = ExpenseCategory(name="KX", company_id=self.x.id)
        self.cat_y = ExpenseCategory(name="KY", company_id=self.y.id)
        db.add_all([self.cat_x, self.cat_y])
        db.flush()
        self.cx = Customer(name="Mijoz X", company_id=self.x.id)
        self.cy = Customer(name="Mijoz Y", company_id=self.y.id)
        db.add_all([self.cx, self.cy])
        db.flush()
        self.px, self.py = _product(db, self.x, 1), _product(db, self.y, 2)

        # Y ning begona yozuvlari (X filialida)
        self.y_exp = [Expense(branch_id=self.bx.id, category_id=self.cat_y.id, amount=5, company_id=self.y.id)
                      for _ in range(N_FOREIGN_EXP)]
        db.add_all(self.y_exp)
        self.y_tx_cid = Transaction(branch_id=self.bx.id, type="expense", amount=5, company_id=self.y.id)
        # company_id yo'q, lekin Y hamyoni orqali Y niki
        self.y_tx_wallet = Transaction(branch_id=self.bx.id, type="expense", amount=5, wallet_id=self.wy.id)
        db.add_all([self.y_tx_cid, self.y_tx_wallet])
        self.y_order = _order(db, self.cy, self.bx, self.py)
        # X ning o'z yozuvlari
        self.x_exp = Expense(branch_id=self.bx.id, category_id=self.cat_x.id, amount=7, company_id=self.x.id)
        self.x_tx_cid = Transaction(branch_id=self.bx.id, type="income", amount=1, company_id=self.x.id)
        self.x_tx_wallet = Transaction(branch_id=self.bx.id, type="income", amount=1, wallet_id=self.wx.id)
        db.add_all([self.x_exp, self.x_tx_cid, self.x_tx_wallet])
        self.x_order = _order(db, self.cx, self.bx, self.px)
        db.commit()   # setup commit: PurgeError dagi rollback sozlamani yo'qotmasin

    def count(self, model, **flt):
        return self.db.query(model).filter_by(**flt).count()

    def y_snapshot(self):
        return {
            "expenses": self.count(Expense, company_id=self.y.id),
            "orders": self.count(Order, customer_id=self.cy.id),
            "customers": self.count(Customer, company_id=self.y.id),
            "wallets": self.count(Wallet, company_id=self.y.id),
            "tx": self.db.query(Transaction).filter(
                Transaction.id.in_([self.y_tx_cid.id, self.y_tx_wallet.id])).count(),
            "products": self.count(Product, company_id=self.y.id),
        }


@pytest.fixture(params=["oddiy", "tez"])
def mode(request, monkeypatch):
    """Oddiy rejim va tez rejim (_try_fast=True: _verify ham ishlaydi) ikkala yo'l."""
    monkeypatch.setattr(_Purger, "_try_fast", lambda self: request.param == "tez")
    return request.param


@pytest.fixture
def notnull_tx_branch(monkeypatch):
    """Prod'dagi holat: transactions.branch_id NOT NULL (modelda nullable) — reflection natijasini almashtiramiz."""
    orig = _Purger._reflect

    def _reflect(self):
        orig(self)
        for e in self.rev.get("branches", []):
            if e.child == "transactions" and e.col == "branch_id":
                e.nullable = False

    monkeypatch.setattr(_Purger, "_reflect", _reflect)


# ─── Asosiy: begona qatorlar saqlanadi va ko'chiriladi ───────────────────────

def test_foreign_rows_survive_and_move_to_owner_branch(db, mk, mode, notnull_tx_branch):
    w = World(db, mk)
    before = w.y_snapshot()
    counts = purge_company(db, w.x.id)
    assert counts  # X ma'lumotlari o'chdi

    # Y qatorlari soni o'zgarmagan
    assert w.y_snapshot() == before
    assert w.count(Company, id=w.y.id) == 1
    assert w.count(Company, id=w.x.id) == 0
    # ... va filiali Y ning birinchi filialiga ko'chgan
    for r in [*w.y_exp, w.y_tx_cid, w.y_tx_wallet, w.y_order]:
        db.refresh(r)
        assert r.branch_id == w.by1.id
    # X ning o'z yozuvlari o'chgan
    assert w.count(Expense, id=w.x_exp.id) == 0
    assert w.count(Order, id=w.x_order.id) == 0
    assert db.query(Transaction).filter(Transaction.id.in_([w.x_tx_cid.id, w.x_tx_wallet.id])).count() == 0
    assert w.count(Customer, id=w.cx.id) == 0


def test_tx_nullable_branch_is_detached_not_deleted(db, mk, mode):
    """Modeldagi (nullable) transactions.branch_id: begona tranzaksiya o'chmaydi, faqat bog'lanish uziladi."""
    w = World(db, mk)
    purge_company(db, w.x.id)
    for t in (w.y_tx_cid, w.y_tx_wallet):
        db.refresh(t)
        assert t.branch_id is None
    assert w.count(Transaction, id=w.x_tx_cid.id) == 0
    assert w.count(Transaction, id=w.x_tx_wallet.id) == 0


def test_moves_to_lowest_branch_id_of_owner(db, mk, mode):
    w = World(db, mk)
    purge_company(db, w.x.id)
    db.refresh(w.y_order)
    assert w.y_order.branch_id == min(w.by1.id, w.by2.id)


def _drop_y_branch(db, w):
    """Y da faqat X filialiga yozilgan qatorlar qolsin: Y ning o'z filiali yo'q."""
    from app.models.branch import Branch
    from app.models.user import User
    db.query(User).filter(User.company_id == w.y.id).update({"branch_id": None})
    db.query(Wallet).filter(Wallet.company_id == w.y.id).update({"branch_id": None})
    db.query(Branch).filter(Branch.id == w.by1.id).delete()
    db.commit()


# ─── Y da boshqa filial yo'q ─────────────────────────────────────────────────

def test_blocked_when_owner_has_no_other_branch(db, mk, mode):
    w = World(db, mk, y_second_branch=False)
    _drop_y_branch(db, w)
    snap = w.y_snapshot()
    x_exp = w.count(Expense, company_id=w.x.id)
    with pytest.raises(PurgeError) as ei:
        purge_company(db, w.x.id)
    assert f"id={w.y.id}" in str(ei.value)
    assert "filial" in str(ei.value)
    with pytest.raises(PurgeError):
        preview_company_purge_ex(db, w.x.id)
    # hech narsa o'chmagan va o'zgarmagan
    assert w.count(Company, id=w.x.id) == 1
    assert w.y_snapshot() == snap
    assert w.count(Expense, company_id=w.x.id) == x_exp
    db.refresh(w.y_order)
    assert w.y_order.branch_id == w.bx.id


# ─── Ko'rib chiqish ──────────────────────────────────────────────────────────

def test_preview_moved_counts_match(db, mk):
    w = World(db, mk)
    res = preview_company_purge_ex(db, w.x.id)
    assert res["moved"]["expenses"] == N_FOREIGN_EXP
    assert res["moved"]["orders"] == 1
    # begona qatorlar o'chirish to'plamida emas
    assert res["counts"]["expenses"] == 1
    assert res["counts"]["orders"] == 1
    # preview hech narsani o'zgartirmaydi
    assert w.count(Expense, company_id=w.y.id) == N_FOREIGN_EXP
    assert w.count(Company, id=w.x.id) == 1


def test_preview_moved_includes_notnull_transactions(db, mk, notnull_tx_branch):
    w = World(db, mk)
    res = preview_company_purge_ex(db, w.x.id)
    assert res["moved"]["transactions"] == 2
    assert res["counts"]["transactions"] == 2      # faqat X ning


def test_preview_backward_compatible_signature(db, mk):
    w = World(db, mk)
    counts = preview_company_purge(db, w.x.id)
    assert isinstance(counts, dict) and counts["expenses"] == 1


def test_clean_company_counts_unchanged(db, mk):
    """Ifloslanish yo'q: moved bo'sh, counts to'liq o'z qatorlari."""
    x, bx, _, _ = mk.tenant()
    cat = ExpenseCategory(name="K", company_id=x.id)
    db.add(cat)
    db.flush()
    db.add_all([Expense(branch_id=bx.id, category_id=cat.id, amount=1, company_id=x.id) for _ in range(3)])
    db.commit()
    res = preview_company_purge_ex(db, x.id)
    assert res["moved"] == {}
    assert res["counts"]["expenses"] == 3
    assert res["counts"] == preview_company_purge(db, x.id)
    purge_company(db, x.id)
    assert db.query(Expense).count() == 0


def test_unattributed_transactions_reported(db, mk):
    x, bx, _, _ = mk.tenant()
    db.add(Transaction(branch_id=bx.id, type="income", amount=1))          # egasi noaniq
    db.add(Transaction(branch_id=bx.id, type="income", amount=1, company_id=x.id))
    db.commit()
    res = preview_company_purge_ex(db, x.id)
    assert res["counts"]["transactions"] == 2
    assert res["counts"]["transactions_unattributed"] == 1
    purge_company(db, x.id)
    assert db.query(Transaction).count() == 0     # hozirgidek filial egasiniki sifatida o'chadi


# ─── Ikki korxona izolyatsiyasi (API) ────────────────────────────────────────

def test_delete_preview_endpoint_super_admin_only(db, mk, client):
    w = World(db, mk)
    su = mk.user(None, role=UserRole.super_admin)
    db.commit()
    r = client.login(su).get(f"/api/super-admin/companies/{w.x.id}/delete-preview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["moved"]["expenses"] == N_FOREIGN_EXP
    assert body["moved"]["orders"] == 1
    assert body["total"] == sum(body["counts"].values())
    # korxona foydalanuvchisi (A) boshqa korxona (B) ni ko'ra olmaydi
    admin_y = mk.user(w.y, role=UserRole.admin, branch=w.by1)
    db.commit()
    assert client.login(admin_y).get(f"/api/super-admin/companies/{w.x.id}/delete-preview").status_code == 403
    assert client.login(admin_y).get(f"/api/super-admin/companies/{w.y.id}/delete-preview").status_code == 403


def test_delete_preview_endpoint_400_when_no_branch(db, mk, client):
    w = World(db, mk, y_second_branch=False)
    _drop_y_branch(db, w)
    su = mk.user(None, role=UserRole.super_admin)
    db.commit()
    r = client.login(su).get(f"/api/super-admin/companies/{w.x.id}/delete-preview")
    assert r.status_code == 400
    assert f"id={w.y.id}" in r.json()["detail"]


# ─── Boshqa NOT NULL (filial bo'lmagan) bog'lanish: begona qator bo'lsa to'xtaydi ─

def test_foreign_row_on_non_branch_notnull_edge_blocks(db, mk):
    """Y buyurtmasi X tovariga (orders.product_id NOT NULL) bog'langan: jimgina o'chirmaslik, PurgeError."""
    w = World(db, mk)
    bad = _order(db, w.cy, w.by1, w.px)
    db.commit()
    with pytest.raises(PurgeError) as ei:
        purge_company(db, w.x.id)
    assert "orders.product_id" in str(ei.value)
    assert w.count(Order, id=bad.id) == 1
    assert w.count(Company, id=w.x.id) == 1
