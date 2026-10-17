"""T0.4 — Foydalanuvchi-kassa (user_wallets) endpointlarini himoyalash.

Ikki korxona (A, B): kassir rol bo'yicha 403, begona foydalanuvchi/kassa 404,
set-default demotion (bir korxonada bitta default), create_sale / _resolve_wallet
ko'p korxonali foydalanuvchi uchun faqat joriy korxona kassasini tanlaydi,
ensure_personal_wallet har korxona uchun alohida, migratsiya SQL idempotent,
/kassa/user-wallets va /kassa/assign-wallet yo'llari o'chirilgan.
"""
import importlib.util
import os
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.moliya import KassaMovement, Wallet
from app.models.product import Product
from app.models.user import UserRole, UserWallet
from app.models.user_company import UserCompany

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
USER_404 = "Foydalanuvchi topilmadi"
WALLET_404 = "Kassa (hamyon) topilmadi"
MIG_PATH = os.path.join(ROOT, 'alembic', 'versions', 's0_04_user_wallets_company.py')


# ─── Yordamchilar ────────────────────────────────────────────────────────────

def _wallet(db, company, branch=None, name=None, is_active=True, is_open=True, balance=0):
    w = Wallet(name=name or f"Kassa {company.id}", type="cash", balance=Decimal(balance),
               company_id=company.id, branch_id=branch.id if branch else None,
               is_active=is_active, is_open=is_open)
    db.add(w)
    db.flush()
    return w


def _links(db, user_id):
    """{wallet_id: (is_default, company_id)}"""
    rows = db.execute(text("SELECT wallet_id, is_default, company_id FROM user_wallets WHERE user_id=:u"),
                      {"u": user_id}).fetchall()
    return {int(r[0]): (bool(r[1]), r[2]) for r in rows}


def _defaults_in(db, user_id, company):
    return db.execute(text(
        "SELECT count(*) FROM user_wallets uw JOIN wallets w ON w.id = uw.wallet_id "
        "WHERE uw.user_id=:u AND uw.is_default AND w.company_id=:c"), {"u": user_id, "c": company.id}).scalar()


def _link(db, user, wallet, is_default=False, company_id=None):
    db.add(UserWallet(user_id=user.id, wallet_id=wallet.id, is_default=is_default,
                      company_id=wallet.company_id if company_id is None else company_id))
    db.flush()


def _member(db, user, company, role=UserRole.cashier):
    db.add(UserCompany(user_id=user.id, company_id=company.id, role=role, is_active=True))
    db.flush()


def _product(db, company, n=1):
    p = Product(name=f"Tovar {n}", sku=f"T04-{n}-{company.id}", barcode=f"B04-{n}-{company.id}",
                company_id=company.id, sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    return p


def _load_migration():
    spec = importlib.util.spec_from_file_location("s0_04_user_wallets_company", MIG_PATH)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    return mig


def _bal(db, wallet):
    db.refresh(wallet)
    return Decimal(str(wallet.balance or 0))


@pytest.fixture
def two(db, mk):
    """A va B korxonalar: admin, kassir (A), kassalar wa/wa2 (A) va wb (B)."""
    ca, ba, wha, ua = mk.tenant()
    cb, bb, whb, ub = mk.tenant()
    cash_a = mk.user(ca, role=UserRole.cashier, branch=ba)
    wa = _wallet(db, ca, ba, "Kassa A")
    wa2 = _wallet(db, ca, ba, "Kassa A2")
    wb = _wallet(db, cb, bb, "Kassa B")
    return dict(ca=ca, ba=ba, wha=wha, ua=ua, cash_a=cash_a, wa=wa, wa2=wa2,
                cb=cb, bb=bb, whb=whb, ub=ub, wb=wb)


# ─── 1. Rol: kassir 403, o'z GET ishlaydi ───────────────────────────────────

def test_cashier_403_on_assign_remove_set_default(client, db, two):
    t = two
    c = client.login(t['cash_a'])
    uid, wid = t['cash_a'].id, t['wa'].id
    r = c.post(f'/api/users/{uid}/wallets', json={"wallet_id": wid, "is_default": True})
    assert r.status_code == 403 and "ruxsat yo'q" in r.json()['detail']
    r = c.post(f'/api/users/{uid}/wallets/{wid}/set-default')
    assert r.status_code == 403
    r = c.delete(f'/api/users/{uid}/wallets/{wid}')
    assert r.status_code == 403
    assert _links(db, uid) == {}


def test_cashier_own_get_ok_other_user_403(client, db, two):
    t = two
    _link(db, t['cash_a'], t['wa'], is_default=True)
    r = client.login(t['cash_a']).get(f'/api/users/{t["cash_a"].id}/wallets')
    assert r.status_code == 200, r.text
    assert r.json() == [{"id": t['wa'].id, "name": "Kassa A", "type": "cash", "is_default": True}]
    # Boshqa xodimning ro'yxati — kassir uchun 403
    r = client.login(t['cash_a']).get(f'/api/users/{t["ua"].id}/wallets')
    assert r.status_code == 403


def test_get_wallets_admin_own_company_ok_foreign_404(client, db, two):
    t = two
    _link(db, t['cash_a'], t['wa'])
    r = client.login(t['ua']).get(f'/api/users/{t["cash_a"].id}/wallets')
    assert r.status_code == 200 and [w['id'] for w in r.json()] == [t['wa'].id]
    r = client.login(t['ub']).get(f'/api/users/{t["cash_a"].id}/wallets')
    assert r.status_code == 404 and r.json()['detail'] == USER_404


# ─── 2. Korxona: begona foydalanuvchi yoki kassa 404 ────────────────────────

def test_assign_cross_company_404(client, db, two):
    t = two
    uid = t['cash_a'].id
    # A admin: A xodimini B kassasiga
    r = client.login(t['ua']).post(f'/api/users/{uid}/wallets', json={"wallet_id": t['wb'].id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    # B admin: A xodimini (begona) B kassasiga
    r = client.login(t['ub']).post(f'/api/users/{uid}/wallets', json={"wallet_id": t['wb'].id})
    assert r.status_code == 404 and r.json()['detail'] == USER_404
    # A admin: B xodimini A kassasiga
    r = client.login(t['ua']).post(f'/api/users/{t["ub"].id}/wallets', json={"wallet_id": t['wa'].id})
    assert r.status_code == 404 and r.json()['detail'] == USER_404
    # Mavjud bo'lmagan foydalanuvchi
    r = client.login(t['ua']).post('/api/users/99999999/wallets', json={"wallet_id": t['wa'].id})
    assert r.status_code == 404
    assert _links(db, uid) == {} and _links(db, t['ub'].id) == {}


def test_assign_own_ok_company_id_written_and_default_demoted(client, db, two):
    t = two
    uid = t['cash_a'].id
    c = client.login(t['ua'])
    r = c.post(f'/api/users/{uid}/wallets', json={"wallet_id": t['wa'].id, "is_default": True})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _links(db, uid) == {t['wa'].id: (True, t['ca'].id)}
    # Ikkinchi kassa default bilan — birinchisi bekor bo'ladi
    r = c.post(f'/api/users/{uid}/wallets', json={"wallet_id": t['wa2'].id, "is_default": True})
    assert r.status_code == 200
    assert _links(db, uid) == {t['wa'].id: (False, t['ca'].id), t['wa2'].id: (True, t['ca'].id)}
    assert _defaults_in(db, uid, t['ca']) == 1
    # Nofaol kassaga biriktirib bo'lmaydi
    inactive = _wallet(db, t['ca'], name="Nofaol A", is_active=False)
    r = c.post(f'/api/users/{uid}/wallets', json={"wallet_id": inactive.id})
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404


def test_remove_cross_company_404_own_ok(client, db, two):
    t = two
    uid = t['cash_a'].id
    _link(db, t['cash_a'], t['wa'], is_default=True)
    r = client.login(t['ub']).delete(f'/api/users/{uid}/wallets/{t["wa"].id}')
    assert r.status_code == 404 and r.json()['detail'] == USER_404
    r = client.login(t['ua']).delete(f'/api/users/{uid}/wallets/{t["wb"].id}')
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    assert _links(db, uid) == {t['wa'].id: (True, t['ca'].id)}
    r = client.login(t['ua']).delete(f'/api/users/{uid}/wallets/{t["wa"].id}')
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _links(db, uid) == {}
    # Nofaol kassa biriktirmasi ham olib tashlanadi (require_active=False)
    inactive = _wallet(db, t['ca'], name="Nofaol A", is_active=False)
    _link(db, t['cash_a'], inactive)
    r = client.login(t['ua']).delete(f'/api/users/{uid}/wallets/{inactive.id}')
    assert r.status_code == 200
    assert _links(db, uid) == {}


# ─── 3. set-default: bitta default, partial unique indeks buzilmaydi ─────────

def test_set_default_demotes_others_and_respects_unique_index(client, db, two):
    t = two
    mig = _load_migration()
    db.execute(text(mig.SQL_UNIQUE_DEFAULT_INDEX))  # uq_user_wallets_default_per_company
    uid = t['cash_a'].id
    c = client.login(t['ua'])
    _link(db, t['cash_a'], t['wa'])
    _link(db, t['cash_a'], t['wa2'])
    r = c.post(f'/api/users/{uid}/wallets/{t["wa"].id}/set-default')
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert _links(db, uid)[t['wa'].id] == (True, t['ca'].id)
    assert _defaults_in(db, uid, t['ca']) == 1
    # Ikkinchi default — indeksni buzmaydi, birinchisi bekor bo'ladi
    r = c.post(f'/api/users/{uid}/wallets/{t["wa2"].id}/set-default')
    assert r.status_code == 200, r.text
    links = _links(db, uid)
    assert links[t['wa'].id][0] is False and links[t['wa2'].id][0] is True
    assert _defaults_in(db, uid, t['ca']) == 1
    # Takroriy chaqiruv idempotent
    r = c.post(f'/api/users/{uid}/wallets/{t["wa2"].id}/set-default')
    assert r.status_code == 200 and _defaults_in(db, uid, t['ca']) == 1
    # Begona kassa / begona admin — 404, holat o'zgarmaydi
    r = c.post(f'/api/users/{uid}/wallets/{t["wb"].id}/set-default')
    assert r.status_code == 404 and r.json()['detail'] == WALLET_404
    r = client.login(t['ub']).post(f'/api/users/{uid}/wallets/{t["wb"].id}/set-default')
    assert r.status_code == 404 and r.json()['detail'] == USER_404
    assert _links(db, uid) == links
    # Kassir o'zini begona kassaga default qila olmaydi (SALES-02 ssenariysi)
    r = client.login(t['cash_a']).post(f'/api/users/{uid}/wallets/{t["wb"].id}/set-default')
    assert r.status_code == 403


def test_set_default_multi_company_user_one_default_per_company(client, db, two):
    """Ko'p korxonali xodim: A va B da alohida default; B admin A biriktirmasini bekor qilmaydi."""
    t = two
    mig = _load_migration()
    db.execute(text(mig.SQL_UNIQUE_DEFAULT_INDEX))
    su = t['cash_a']
    _member(db, su, t['cb'])
    r = client.login(t['ua']).post(f'/api/users/{su.id}/wallets/{t["wa"].id}/set-default')
    assert r.status_code == 200
    r = client.login(t['ub']).post(f'/api/users/{su.id}/wallets/{t["wb"].id}/set-default')
    assert r.status_code == 200, r.text
    assert _links(db, su.id) == {t['wa'].id: (True, t['ca'].id), t['wb'].id: (True, t['cb'].id)}
    # B admin faqat B kassasini ko'radi
    r = client.login(t['ub']).get(f'/api/users/{su.id}/wallets')
    assert r.status_code == 200 and [w['id'] for w in r.json()] == [t['wb'].id]


# ─── 4. create_sale va _resolve_wallet — joriy korxona kassasi ──────────────

def _sale_data(product, warehouse):
    from app.schemas.sale import SaleCreate
    return SaleCreate(items=[{"product_id": product.id, "quantity": 1, "unit_price": 1000}],
                      payment_type="cash", paid_amount=Decimal("1000"), paid_cash=Decimal("1000"),
                      warehouse_id=warehouse.id)


def test_create_sale_multi_company_user_uses_current_company_wallet(db, two):
    from app.services.sale_create import create_sale
    t = two
    su = t['cash_a']
    _member(db, su, t['cb'])
    _link(db, su, t['wa'], is_default=True)
    _link(db, su, t['wb'], is_default=True)
    pb = _product(db, t['cb'], 1)
    su.company_id = t['cb'].id  # token orqali B korxonaga o'tdi (dependencies.get_current_user)
    sale = create_sale(db, _sale_data(pb, t['whb']), su)
    mv = db.query(KassaMovement).filter(KassaMovement.reference_type == "sale",
                                        KassaMovement.reference_id == sale.id).all()
    assert len(mv) == 1 and mv[0].wallet_id == t['wb'].id and mv[0].company_id == t['cb'].id
    assert _bal(db, t['wb']) == Decimal(1000)
    assert _bal(db, t['wa']) == Decimal(0)


def test_create_sale_only_foreign_binding_falls_back_to_own_company_wallet(db, two):
    from app.services.sale_create import create_sale
    t = two
    su = t['cash_a']
    _member(db, su, t['cb'])
    _link(db, su, t['wa'], is_default=True)   # faqat A kassasi biriktirilgan
    pb = _product(db, t['cb'], 2)
    su.company_id = t['cb'].id
    sale = create_sale(db, _sale_data(pb, t['whb']), su)
    mv = db.query(KassaMovement).filter(KassaMovement.reference_id == sale.id,
                                        KassaMovement.reference_type == "sale").one()
    assert mv.wallet_id == t['wb'].id          # B ning ochiq kassasi, A kassasi emas
    assert _bal(db, t['wa']) == Decimal(0)


def test_create_sale_skips_inactive_bound_wallet(db, two):
    from app.services.sale_create import create_sale
    t = two
    inactive = _wallet(db, t['ca'], t['ba'], "Nofaol A", is_active=False)
    _link(db, t['cash_a'], inactive, is_default=True)
    _link(db, t['cash_a'], t['wa2'])
    pa = _product(db, t['ca'], 3)
    sale = create_sale(db, _sale_data(pa, t['wha']), t['cash_a'])
    mv = db.query(KassaMovement).filter(KassaMovement.reference_id == sale.id,
                                        KassaMovement.reference_type == "sale").one()
    assert mv.wallet_id == t['wa2'].id         # faol biriktirilgan kassa (default emas bo'lsa ham)
    assert _bal(db, inactive) == Decimal(0)


def test_order_to_sale_resolve_wallet_by_company(db, two):
    from app.services.order_to_sale import _resolve_wallet
    t = two
    su = t['cash_a']
    _member(db, su, t['cb'])
    _link(db, su, t['wa'], is_default=True)
    _link(db, su, t['wb'], is_default=True)
    assert _resolve_wallet(db, su).id == t['wa'].id
    su.company_id = t['cb'].id
    assert _resolve_wallet(db, su).id == t['wb'].id
    # B biriktirmasi olib tashlansa — B ning ochiq kassasiga tushadi (A emas)
    db.execute(text("DELETE FROM user_wallets WHERE user_id=:u AND wallet_id=:w"), {"u": su.id, "w": t['wb'].id})
    assert _resolve_wallet(db, su).id == t['wb'].id


# ─── 5. ensure_personal_wallet — har korxona uchun alohida ──────────────────

def test_ensure_personal_wallet_per_company(db, mk, two):
    from app.services.mobile_service import ensure_personal_wallet
    t = two
    cur = mk.user(t['ca'], role=UserRole.courier, branch=t['ba'])
    _member(db, cur, t['cb'])
    pa = ensure_personal_wallet(db, cur)
    assert pa.company_id == t['ca'].id and _links(db, cur.id) == {pa.id: (True, t['ca'].id)}
    assert ensure_personal_wallet(db, cur).id == pa.id      # takror — yangi kassa yaratilmaydi
    cur.company_id = t['cb'].id
    pb = ensure_personal_wallet(db, cur)
    assert pb.id != pa.id and pb.company_id == t['cb'].id
    assert ensure_personal_wallet(db, cur).id == pb.id
    links = _links(db, cur.id)
    assert links == {pa.id: (True, t['ca'].id), pb.id: (True, t['cb'].id)}  # A default saqlanib qoldi
    assert _defaults_in(db, cur.id, t['ca']) == 1 and _defaults_in(db, cur.id, t['cb']) == 1
    # Eski (company_id NULL) default qator ham korxona ichida topiladi
    cur2 = mk.user(t['ca'], role=UserRole.agent, branch=t['ba'])
    _link(db, cur2, t['wa'], is_default=True, company_id=None)
    db.execute(text("UPDATE user_wallets SET company_id = NULL WHERE user_id=:u"), {"u": cur2.id})
    assert ensure_personal_wallet(db, cur2).id == t['wa'].id


# ─── 6. Migratsiya SQL: to'ldirish, dedupe, indekslar — idempotent ──────────

def test_migration_sql_idempotent(db, mk, two):
    t = two
    mig = _load_migration()
    assert mig.revision == 't0_4' and mig.down_revision == 't0_3'
    assert 'IF NOT EXISTS' in mig.SQL_ADD_COLUMN_PG and 'IF NOT EXISTS' in mig.SQL_UNIQUE_DEFAULT_INDEX
    u = t['cash_a']
    wa3 = _wallet(db, t['ca'], name="Kassa A3")
    # Eski holat: company_id NULL, A korxonada 3 ta default; B da 1 ta default
    for w in (t['wa'], t['wa2'], wa3, t['wb']):
        _link(db, u, w, is_default=True, company_id=None)
    db.execute(text("UPDATE user_wallets SET company_id = NULL WHERE user_id=:u"), {"u": u.id})

    for _ in range(2):  # ikki marta ketma-ket — xato bermasligi kerak
        for stmt in mig.UPGRADE_SQL:
            db.execute(text(stmt))
    links = _links(db, u.id)
    assert links[t['wa'].id] == (False, t['ca'].id)
    assert links[t['wa2'].id] == (False, t['ca'].id)
    assert links[wa3.id] == (True, t['ca'].id)          # eng katta wallet_id qoldi
    assert links[t['wb'].id] == (True, t['cb'].id)      # B korxonasi default saqlandi
    assert db.execute(text("SELECT count(*) FROM user_wallets WHERE company_id IS NULL")).scalar() == 0
    names = {r[1] for r in db.execute(text("PRAGMA index_list('user_wallets')")).fetchall()}
    assert {'uq_user_wallets_default_per_company', 'ix_user_wallets_company'} <= names
    # Indeks ishlaydi: shu korxonada ikkinchi default to'g'ridan-to'g'ri yozilsa — xato
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text("UPDATE user_wallets SET is_default = true WHERE user_id=:u AND wallet_id=:w"),
                       {"u": u.id, "w": t['wa'].id})


# ─── 7. /kassa dublikat endpointlari o'chirilgan ────────────────────────────

def test_kassa_user_wallet_routes_removed(client, two):
    from app.main import app
    paths = {getattr(r, 'path', '') for r in app.routes}
    assert not any(p.endswith('/kassa/user-wallets') or p.endswith('/kassa/assign-wallet') for p in paths), paths
    t = two
    c = client.login(t['ua'])
    assert c.get('/api/kassa/user-wallets', params={"user_id": t['cash_a'].id}).status_code in (404, 405, 422)
    r = c.post('/api/kassa/assign-wallet', json={"user_id": t['cash_a'].id, "wallet_id": t['wb'].id})
    assert r.status_code in (404, 405, 422)
    src = open(os.path.join(ROOT, 'app', 'routers', 'kassa.py'), encoding='utf-8').read()
    assert 'user_wallets' not in src and 'AssignWalletIn' not in src
