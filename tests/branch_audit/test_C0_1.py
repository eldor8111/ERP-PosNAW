"""C0.1 — 0-bosqich tozalash: backend qoldiqlari.

Qamrov: SaleOut/SaleListOut da original_sale_id; UserOut.tg_linked; sale_update da naqd
bo'lmagan to'lovga Transaction yozilmasligi va resolve_tx_branch; lock_customer (arxivlangan
mijozga o'tish 400); telegram/field_staff da arxivlangan mijoz chiqmasligi; users limitida
marketplace_agent sanalmasligi; purge da orders bevosita company_id bo'yicha; skriptlar va
.env.example; ikki korxona izolyatsiyasi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_C0_1.py -q -p no:cacheprovider
"""
import importlib.util
import itertools
import os
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.customer import Customer
from app.models.inventory import StockLevel
from app.models.moliya import KassaSession, Transaction, Wallet
from app.models.product import Product
from app.models.sale import PaymentType, Sale, SaleItem, SaleStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.sale import SaleCreate, SaleOut, SaleListOut, SaleUpdate
from app.schemas.user import UserOut
from app.services.customer_service import ARCHIVED_DETAIL
from app.services.sale_create import create_sale
from app.services.sale_update import update_sale, reassign_sale_customer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_seq = itertools.count(1)


# ── Yordamchilar ─────────────────────────────────────────────────────────────

def _wallet(db, company, branch):
    w = Wallet(name=f"Kassa {next(_seq)}", type="cash", balance=Decimal("0"),
               company_id=company.id, branch_id=branch.id, is_active=True, is_open=True)
    db.add(w)
    db.flush()
    db.add(KassaSession(wallet_id=w.id, company_id=company.id, status="open"))
    db.flush()
    return w


def _cust(db, company, **kw):
    n = next(_seq)
    c = Customer(name=kw.pop("name", f"Mijoz {n}"), company_id=company.id,
                 phone=kw.pop("phone", f"99890{n:07d}"), **kw)
    db.add(c)
    db.flush()
    return c


def _product(db, company, wh, qty=100):
    n = next(_seq)
    p = Product(name=f"Tovar {n}", sku=f"C01-{n}", barcode=f"BC01-{n}", company_id=company.id,
                cost_price=Decimal("500"), sale_price=Decimal("1000"))
    db.add(p)
    db.flush()
    db.add(StockLevel(product_id=p.id, warehouse_id=wh.id, quantity=Decimal(qty)))
    db.flush()
    return p


def _sale_data(prod, wh, price=1000, qty=1, payments=None, payment_type="cash", customer_id=None):
    body = dict(items=[{"product_id": prod.id, "quantity": qty, "unit_price": price}],
                payment_type=payment_type, warehouse_id=wh.id, customer_id=customer_id)
    if payments is not None:
        body["payments"] = payments
    body["paid_amount"] = sum((Decimal(str(p["amount"])) for p in (payments or [])
                               if p["type"] not in ("debt", "cashback", "mixed")), Decimal("0"))
    return SaleCreate(**body)


def _txs(db, sale):
    return db.query(Transaction).filter(
        Transaction.reference_type == "sale", Transaction.reference_id == sale.id,
    ).all()


@pytest.fixture
def w(db, mk):
    """Korxona A (admin, agent, kassa, mijoz, mahsulot) va korxona B (admin, agent, mijoz)."""
    ca, ba, wha, admin = mk.tenant(UserRole.admin)
    ca.distribution_enabled = True
    agent = mk.user(ca, role=UserRole.agent, branch=ba)
    wallet = _wallet(db, ca, ba)
    cust = _cust(db, ca)
    prod = _product(db, ca, wha)
    cb, bb, whb, admin_b = mk.tenant(UserRole.admin)
    cb.distribution_enabled = True
    agent_b = mk.user(cb, role=UserRole.agent, branch=bb)
    cust_b = _cust(db, cb)
    db.flush()
    return dict(ca=ca, ba=ba, wha=wha, admin=admin, agent=agent, wallet=wallet, cust=cust, prod=prod,
                cb=cb, bb=bb, whb=whb, admin_b=admin_b, agent_b=agent_b, cust_b=cust_b)


# ── 6-band: SaleOut.original_sale_id ─────────────────────────────────────────

def test_sale_out_has_original_sale_id(db, w, client):
    from app.routers.sales import _build_sale_out, _build_sale_list_out

    orig = create_sale(db, _sale_data(w["prod"], w["wha"], payments=[{"type": "cash", "amount": 1000}]), w["admin"])
    ret = Sale(number=f"R{next(_seq):06d}", cashier_id=w["admin"].id, company_id=w["ca"].id,
               warehouse_id=w["wha"].id, total_amount=Decimal("1000"), paid_amount=Decimal("1000"),
               payment_type=PaymentType.cash, status=SaleStatus.refunded, original_sale_id=orig.id)
    db.add(ret)
    db.flush()
    db.add(SaleItem(sale_id=ret.id, product_id=w["prod"].id, warehouse_id=w["wha"].id, quantity=Decimal("1"),
                    unit_price=Decimal("1000"), cost_price=Decimal("500"), discount=Decimal("0"),
                    subtotal=Decimal("1000")))
    db.flush()
    db.refresh(ret)
    db.refresh(orig)

    out = _build_sale_out(ret)
    assert isinstance(out, SaleOut) and out.original_sale_id == orig.id
    assert _build_sale_out(orig).original_sale_id is None
    lst = _build_sale_list_out(ret)
    assert isinstance(lst, SaleListOut) and lst.original_sale_id == orig.id
    assert "original_sale_id" in SaleOut.model_fields and "original_sale_id" in SaleListOut.model_fields

    # Endpoint orqali ham chiqadi
    r = client.login(w["admin"]).get(f"/api/sales/{ret.id}")
    assert r.status_code == 200, r.text
    assert r.json()["original_sale_id"] == orig.id


# ── 7-band: UserOut.tg_linked ────────────────────────────────────────────────

def test_user_out_tg_linked(db, mk, w):
    u_no = w["admin"]
    u_yes = mk.user(w["ca"], role=UserRole.manager, tg_chat_id="777")
    assert UserOut.model_validate(u_no).tg_linked is False
    assert UserOut.model_validate(u_yes).tg_linked is True
    # tg_chat_id ning o'zi javobga chiqmaydi
    assert "tg_chat_id" not in UserOut.model_validate(u_yes).model_dump()
    # dict yo'li ham ishlaydi; ORM obyekti o'zgartirilmaydi
    d = UserOut.model_validate(u_yes).model_dump()
    assert UserOut(**d).tg_linked is True
    assert "tg_linked" not in u_yes.__dict__
    # Dinamik is_shared belgisi (T0.38) saqlanadi
    u_yes.is_shared = True
    assert UserOut.model_validate(u_yes).is_shared is True


def test_users_me_endpoint_returns_tg_linked(client, mk, w):
    u = mk.user(w["ca"], role=UserRole.manager, tg_chat_id="888")
    r = client.login(w["admin"]).get(f"/api/users/{u.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tg_linked"] is True and "tg_chat_id" not in body


# ── 1/2-band: sale_update — resolve_tx_branch va naqd bo'lmagan to'lov ───────

def test_update_sale_noncash_payment_has_no_transaction(db, w):
    sale = create_sale(db, _sale_data(w["prod"], w["wha"], payments=[{"type": "cash", "amount": 1000}],
                                      customer_id=w["cust"].id), w["admin"])
    assert len(_txs(db, sale)) == 1

    upd = SaleUpdate(items=[{"product_id": w["prod"].id, "quantity": 2, "unit_price": 1000}],
                     payment_type="mixed", paid_amount=Decimal("400"),
                     payments=[{"type": "cash", "amount": 400}, {"type": "debt", "amount": 1600}],
                     customer_id=w["cust"].id)
    update_sale(db, sale.id, upd, w["admin"])

    txs = _txs(db, sale)
    assert all(t.payment_type not in ("debt", "cashback", "mixed") for t in txs)
    # Faol (sof) kirim: faqat naqd 400 (eski 1000 teskari qilingan)
    income = sum(Decimal(str(t.amount)) for t in txs if t.type == "income")
    expense = sum(Decimal(str(t.amount)) for t in txs if t.type == "expense")
    assert income - expense == Decimal("400")
    # Har tranzaksiya filiali bor (resolve_tx_branch None qaytarmaydi)
    assert all(t.branch_id == w["ba"].id for t in txs)
    db.refresh(w["cust"])
    assert Decimal(str(w["cust"].debt_balance)) == Decimal("1600")


def test_update_sale_paid_delta_debt_type_recorded_as_cash(db, w):
    sale = create_sale(db, _sale_data(w["prod"], w["wha"], payments=[{"type": "debt", "amount": 1000}],
                                      payment_type="debt", customer_id=w["cust"].id), w["admin"])
    assert _txs(db, sale) == []
    update_sale(db, sale.id, SaleUpdate(paid_amount=Decimal("1000")), w["admin"])
    txs = _txs(db, sale)
    assert len(txs) == 1 and txs[0].payment_type == "cash" and txs[0].branch_id == w["ba"].id


def test_update_sale_without_branch_400(db, mk):
    """Filialsiz korxonada resolve_tx_branch 400 beradi (jim 0/None emas)."""
    c = mk.company()
    wh = mk.warehouse(c)
    admin = mk.user(c, role=UserRole.admin)
    prod = _product(db, c, wh)
    with pytest.raises(HTTPException) as ei:
        create_sale(db, _sale_data(prod, wh, payments=[{"type": "cash", "amount": 1000}]), admin)
    assert ei.value.status_code == 400


# ── 3-band: lock_customer — arxivlangan mijoz ────────────────────────────────

def test_update_sale_to_archived_customer_400(db, w):
    sale = create_sale(db, _sale_data(w["prod"], w["wha"], payments=[{"type": "cash", "amount": 1000}],
                                      customer_id=w["cust"].id), w["admin"])
    archived = _cust(db, w["ca"], is_active=False)
    upd = SaleUpdate(items=[{"product_id": w["prod"].id, "quantity": 1, "unit_price": 1000}],
                     paid_amount=Decimal("1000"), payments=[{"type": "cash", "amount": 1000}],
                     customer_id=archived.id)
    with pytest.raises(HTTPException) as ei:
        update_sale(db, sale.id, upd, w["admin"])
    assert ei.value.status_code == 400 and ei.value.detail == ARCHIVED_DETAIL
    db.rollback()


def test_reassign_sale_to_archived_customer_400_and_active_ok(db, w):
    sale = create_sale(db, _sale_data(w["prod"], w["wha"], payments=[{"type": "debt", "amount": 1000}],
                                      payment_type="debt", customer_id=w["cust"].id), w["admin"])
    archived = _cust(db, w["ca"], is_active=False)
    with pytest.raises(HTTPException) as ei:
        reassign_sale_customer(db, sale.id, archived.id, w["admin"], commit=False)
    assert ei.value.status_code == 400 and ei.value.detail == ARCHIVED_DETAIL

    other = _cust(db, w["ca"])
    reassign_sale_customer(db, sale.id, other.id, w["admin"], commit=False)
    db.flush()
    db.refresh(w["cust"]); db.refresh(other)
    assert Decimal(str(w["cust"].debt_balance)) == Decimal("0")
    assert Decimal(str(other.debt_balance)) == Decimal("1000")


def test_update_sale_existing_archived_customer_still_editable(db, w):
    """Sotuvdagi mijoz keyin arxivlansa ham to'lov qo'shish ishlaydi (allow_inactive)."""
    sale = create_sale(db, _sale_data(w["prod"], w["wha"], payments=[{"type": "debt", "amount": 1000}],
                                      payment_type="debt", customer_id=w["cust"].id), w["admin"])
    w["cust"].is_active = False
    db.flush()
    update_sale(db, sale.id, SaleUpdate(paid_amount=Decimal("1000")), w["admin"])
    db.refresh(w["cust"])
    assert Decimal(str(w["cust"].debt_balance)) == Decimal("0")


# ── 4-band: telegram — arxivlangan mijoz ─────────────────────────────────────

def test_telegram_find_customer_by_chat_skips_archived(db, mk):
    from app.routers.telegram import _find_customer_by_chat

    c = mk.company(tg_bot_token=f"tok-{next(_seq)}")
    active = _cust(db, c, tg_chat_id="5001")
    _cust(db, c, tg_chat_id="5002", is_active=False)
    company, found = _find_customer_by_chat(db, c.tg_bot_token, "5001")
    assert company.id == c.id and found.id == active.id
    company, found = _find_customer_by_chat(db, c.tg_bot_token, "5002")
    assert company.id == c.id and found is None


# ── 5-band: field_staff — arxivlangan mijoz ──────────────────────────────────

def test_field_staff_assign_skips_archived_and_counts_active_only(client, db, w):
    active = _cust(db, w["ca"])
    archived = _cust(db, w["ca"], is_active=False)
    c = client.login(w["admin"])
    r = c.post(f"/api/field-staff/agents/{w['agent'].id}/customers", json={"add": [active.id, archived.id]})
    assert r.status_code == 200, r.text
    assert r.json() == {"added": 1, "removed": 0, "total": 1}
    db.refresh(active); db.refresh(archived)
    assert active.agent_id == w["agent"].id and archived.agent_id is None

    # Biriktirilgan mijoz keyin arxivlansa — hisobga kirmaydi
    active.is_active = False
    db.flush()
    r = c.get("/api/field-staff/users")
    assert r.status_code == 200, r.text
    row = next(u for u in r.json() if u["id"] == w["agent"].id)
    assert row["customers_count"] == 0


def test_field_staff_other_company_agent_404(client, w):
    """Izolyatsiya: A admini B agentiga mijoz biriktira olmaydi, B mijozini A agentiga ham."""
    c = client.login(w["admin"])
    r = c.post(f"/api/field-staff/agents/{w['agent_b'].id}/customers", json={"add": [w["cust"].id]})
    assert r.status_code == 404
    r = c.post(f"/api/field-staff/agents/{w['agent'].id}/customers", json={"add": [w["cust_b"].id]})
    assert r.status_code == 200 and r.json()["added"] == 0


def test_sale_update_other_company_404(db, w):
    """Izolyatsiya: A admini B sotuvini tahrirlay olmaydi."""
    sale_b = Sale(number=f"B{next(_seq):06d}", cashier_id=w["admin_b"].id, company_id=w["cb"].id,
                  warehouse_id=w["whb"].id, total_amount=Decimal("1000"), paid_amount=Decimal("1000"),
                  payment_type=PaymentType.cash, status=SaleStatus.completed)
    db.add(sale_b)
    db.flush()
    with pytest.raises(HTTPException) as ei:
        update_sale(db, sale_b.id, SaleUpdate(note="x"), w["admin"])
    assert ei.value.status_code == 404
    # O'z sotuvi ishlaydi
    update_sale(db, sale_b.id, SaleUpdate(note="ok"), w["admin_b"])
    assert sale_b.note == "ok"


# ── 8-band: users limiti — marketplace_agent sanalmaydi ──────────────────────

def _user_body(role="cashier"):
    n = next(_seq)
    return {"name": f"Yangi {n}", "phone": f"9989{n:08d}", "password": "secret123", "role": role}


def test_user_limit_ignores_marketplace_agents(client, db, mk):
    c = mk.company()           # tarif yo'q -> limit 5
    admin = mk.user(c, role=UserRole.admin)
    for _ in range(3):
        mk.user(c, role=UserRole.cashier)
    for _ in range(3):
        mk.user(c, role=UserRole.marketplace_agent)
    # 4 ta xodim + 3 marketplace agent: eski hisobda 7 >= 5 edi, endi 4 < 5
    r = client.login(admin).post("/api/users/", json=_user_body())
    assert r.status_code == 201, r.text
    # Endi 5 ta xodim — keyingisi limitga uriladi
    r = client.login(admin).post("/api/users/", json=_user_body())
    assert r.status_code == 403
    assert "maksimal xodimlar soni" in r.json()["detail"]


# ── 9-band: purge — orders bevosita company_id bo'yicha ──────────────────────

def test_purge_owner_sql_uses_orders_company_id(db, mk):
    from app.services.company_purge import _Purger, OWNER_VIA

    c = mk.company()
    p = _Purger(db, c.id)
    assert p.has_cid("orders")
    assert p._owner_sql("orders").startswith("COALESCE(r.company_id")
    assert "orders" in OWNER_VIA  # faqat ustunsiz (eski) baza uchun zaxira


# ── 10-band: sale_create — resolve_cashier_wallet_id ─────────────────────────

def test_sale_create_uses_resolve_cashier_wallet_id(db, w, monkeypatch):
    # T1.10: kassa tanlash yagona `resolve_wallet` (kassirning default kassasi birinchi) orqali
    import app.services.sale_create as sc

    called = {}
    orig = sc.resolve_wallet

    def _spy(db_, user, *a, **kw):
        called["user"] = user.id
        return orig(db_, user, *a, **kw)

    monkeypatch.setattr(sc, "resolve_wallet", _spy)
    sale = create_sale(db, _sale_data(w["prod"], w["wha"], payments=[{"type": "cash", "amount": 1000}]), w["admin"])
    assert called["user"] == w["admin"].id
    assert _txs(db, sale)[0].wallet_id == w["wallet"].id


# ── 11/12-band: skriptlar va .env.example ────────────────────────────────────

def _load_script(name):
    path = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reconcile_shift_handover_script_dry_run_and_apply(db, mk, monkeypatch, capsys):
    from app.models.moliya import CashTransfer, KassaMovement
    from app.models.shift import Shift
    from app.models.user import UserWallet

    mod = _load_script("reconcile_shift_handover.py")
    c, b, wh, admin = mk.tenant(UserRole.admin)
    cashier = mk.user(c, role=UserRole.cashier, branch=b)
    src = _wallet(db, c, b)
    tgt = _wallet(db, c, b)
    src.balance = Decimal("5000"); tgt.balance = Decimal("5000")
    db.add(UserWallet(user_id=cashier.id, wallet_id=src.id, is_default=True))
    sh = Shift(cashier_id=cashier.id, branch_id=b.id, company_id=c.id, status="closed")
    db.add(sh)
    db.flush()
    tx = Transaction(branch_id=b.id, company_id=c.id, type="income", amount=Decimal("3000"), payment_type="cash",
                     wallet_id=tgt.id, reference_type="shift", reference_id=sh.id, description="eski")
    db.add(tx)
    db.flush()
    tx_id = tx.id

    # Dry-run: hech narsa o'zgarmaydi
    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr("sys.argv", ["x", "--company-id", str(c.id)])
    mod.main()
    out = capsys.readouterr().out
    assert "dry-run" in out and "Jami 1 ta yozuv" in out
    assert db.get(Transaction, tx_id) is not None

    # --apply faqat --shift-ids bilan
    monkeypatch.setattr("sys.argv", ["x", "--apply"])
    with pytest.raises(SystemExit):
        mod.main()

    monkeypatch.setattr("sys.argv", ["x", "--apply", "--shift-ids", str(sh.id)])
    mod.main()
    assert db.get(Transaction, tx_id) is None
    ct = db.query(CashTransfer).filter(CashTransfer.sender_wallet_id == src.id, CashTransfer.receiver_wallet_id == tgt.id).one()
    assert Decimal(str(ct.amount)) == Decimal("3000") and ct.status == "completed"
    mvs = db.query(KassaMovement).filter(KassaMovement.reference_id == ct.id).all()
    assert {(m.wallet_id, m.direction, m.reference_type) for m in mvs} == {
        (src.id, "out", "transfer_out"), (tgt.id, "in", "transfer_in")}
    db.refresh(src); db.refresh(tgt)
    assert Decimal(str(src.balance)) == Decimal("2000") and Decimal(str(tgt.balance)) == Decimal("5000")

    # Takror ishga tushirish — yozuv qolmagan
    monkeypatch.setattr("sys.argv", ["x", "--company-id", str(c.id)])
    mod.main()
    assert "topilmadi" in capsys.readouterr().out


def test_report_noncash_script_is_read_only(db, mk, monkeypatch, capsys):
    mod = _load_script("report_noncash_transactions.py")
    c, b, wh, admin = mk.tenant(UserRole.admin)
    for ptype, amt in (("debt", "100"), ("debt", "250"), ("cashback", "50"), ("cash", "999")):
        db.add(Transaction(branch_id=b.id, company_id=c.id, type="income", amount=Decimal(amt), payment_type=ptype))
    db.flush()
    before = db.query(Transaction).count()
    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr("sys.argv", ["x", "--company-id", str(c.id), "--by-type"])
    mod.main()
    out = capsys.readouterr().out
    assert "debt" in out and "cashback" in out and "cash " not in out.split("Jami")[0].replace("cashback", "")
    assert "Jami: 3 ta yozuv, summa 400" in out
    assert db.query(Transaction).count() == before


def test_env_example_has_marketplace_token():
    with open(os.path.join(ROOT, ".env.example"), encoding="utf-8") as f:
        text = f.read()
    assert "MARKETPLACE_API_TOKEN=" in text and "Mir-maza" in text
