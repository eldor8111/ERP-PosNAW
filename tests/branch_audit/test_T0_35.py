"""T0.35 — Kassalararo o'tkazma: ikki bosqich, qulf va moliya jurnali.

/kassa/{id}/transfer/out va out-batch o'tkazmani `pending` yaratadi (pul yuboruvchidan darhol chiqadi),
transfer/in qabul qiluvchiga yozadi, transfer/reject yuboruvchiga qaytaradi. Qayta ishlangan
o'tkazma -> 409. Huquq: admin/director/manager yoki user_wallets biriktirilgan foydalanuvchi.
(Parallel FOR UPDATE Postgres talab qiladi; bu yerda ketma-ket qayta chaqiruv 409 tekshiriladi.)
"""
from decimal import Decimal

import pytest

from app.models.audit_log import AuditLog
from app.models.moliya import CashTransfer, KassaMovement, Wallet
from app.models.user import UserRole, UserWallet
from app.services.wallet_access import user_can_use_wallet

R = UserRole


def _wallet(db, company, branch=None, name=None, is_active=True, is_open=True):
    w = Wallet(name=name or f"Kassa {company.id}-{id(object())}", type="cash", balance=Decimal(0),
               company_id=company.id, branch_id=branch.id if branch else None,
               is_active=is_active, is_open=is_open)
    db.add(w)
    db.flush()
    return w


def _fund(db, w, amount, payment_type="cash", currency="UZS"):
    db.add(KassaMovement(wallet_id=w.id, company_id=w.company_id, direction="in",
                         payment_type=payment_type, amount=Decimal(amount), currency=currency,
                         reference_type="invest"))
    if currency == "UZS":
        w.balance = Decimal(w.balance or 0) + Decimal(amount)
    db.flush()


def _movements(db, w, **kw):
    return db.query(KassaMovement).filter_by(wallet_id=w.id, **kw).all()


@pytest.fixture
def env(mk, db):
    comp = mk.company()
    ba, bb = mk.branch(comp), mk.branch(comp)
    admin = mk.user(comp, role=R.admin, branch=ba)
    wa = _wallet(db, comp, ba, "A kassa")
    wb = _wallet(db, comp, bb, "B kassa")
    _fund(db, wa, 1_000_000)
    _fund(db, wa, 50, "cash", "USD")
    db.commit()
    return comp, ba, bb, admin, wa, wb


def _out(c, wa, wb, **kw):
    body = {"receiver_wallet_id": wb.id, "amount": 100000}
    body.update(kw)
    return c.post(f"/api/kassa/{wa.id}/transfer/out", json=body)


def _count(db):
    return db.query(CashTransfer).count(), db.query(KassaMovement).count()


# ─── 1. Validatsiya ──────────────────────────────────────────────────────────

def test_manfiy_summa_422_va_bir_xil_kassa_400(client, env, db):
    _, _, _, admin, wa, wb = env
    c = client.login(admin)
    before = _count(db)
    assert _out(c, wa, wb, amount=-3000000).status_code == 422
    assert _out(c, wa, wb, amount=0).status_code == 422
    assert _out(c, wa, wb, currency="usd").status_code == 422
    assert _out(c, wa, wb, payment_type="bitcoin").status_code == 422
    r = c.post(f"/api/kassa/{wa.id}/transfer/out", json={"receiver_wallet_id": wa.id, "amount": 10})
    assert r.status_code == 400
    assert _count(db) == before


def test_faol_bolmagan_va_yopiq_kassa_400(client, env, db, mk):
    comp, ba, _, admin, wa, wb = env
    c = client.login(admin)
    wb.is_active = False
    db.flush()
    assert _out(c, wa, wb).status_code == 400
    wb.is_active = True
    wa.is_open = False
    db.flush()
    assert _out(c, wa, wb).status_code == 400
    assert db.query(CashTransfer).count() == 0


# ─── 2. Qoldiq va pending ────────────────────────────────────────────────────

def test_qoldiq_yetmasa_400(client, env, db):
    _, _, _, admin, wa, wb = env
    c = client.login(admin)
    r = _out(c, wa, wb, amount=2_000_000)
    assert r.status_code == 400 and "yetarli emas" in r.json()["detail"]
    r = _out(c, wa, wb, amount=100, currency="EUR")
    assert r.status_code == 400
    assert db.query(CashTransfer).count() == 0


def test_out_pending_yaratadi_qabul_qiluvchiga_tegmaydi(client, env, db):
    _, ba, bb, admin, wa, wb = env
    c = client.login(admin)
    r = _out(c, wa, wb, amount=300000, note="kun oxiri")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["status"] == "pending"
    ct = db.get(CashTransfer, body["transfer_id"])
    assert ct.status == "pending" and ct.received_by is None and ct.received_at is None
    assert ct.sender_branch_id == ba.id and ct.receiver_branch_id == bb.id
    outs = _movements(db, wa, reference_type="transfer_out", reference_id=ct.id)
    assert len(outs) == 1 and outs[0].direction == "out" and outs[0].amount == Decimal("300000")
    assert _movements(db, wb) == []
    db.refresh(wa)
    db.refresh(wb)
    assert wa.balance == Decimal("700000") and wb.balance == 0
    log = db.query(AuditLog).filter_by(action="CASH_TRANSFER_OUT", entity_id=ct.id).first()
    assert log is not None and log.user_id == admin.id


# ─── 3. Qabul qilish ─────────────────────────────────────────────────────────

def test_in_qabul_qiluvchiga_yozadi(client, env, db, mk):
    comp, _, bb, admin, wa, wb = env
    tid = _out(client.login(admin), wa, wb, amount=300000).json()["transfer_id"]
    cashier_b = mk.user(comp, role=R.accountant, branch=bb)
    db.add(UserWallet(user_id=cashier_b.id, wallet_id=wb.id, company_id=comp.id))
    db.flush()
    c = client.login(cashier_b)
    r = c.post("/api/kassa/transfer/in", json={"transfer_id": tid})
    assert r.status_code == 200, r.text
    ct = db.get(CashTransfer, tid)
    db.refresh(ct)
    assert ct.status == "completed" and ct.received_by == cashier_b.id and ct.received_at is not None
    ins = _movements(db, wb, reference_type="transfer_in")
    assert len(ins) == 1 and ins[0].direction == "in" and ins[0].reference_id == tid
    db.refresh(wb)
    assert wb.balance == Decimal("300000")
    assert db.query(AuditLog).filter_by(action="CASH_TRANSFER_IN", entity_id=tid).count() == 1


# ─── 4. Ikki marta qayta ishlash ─────────────────────────────────────────────

def test_ikki_marta_in_va_in_reject_409(client, env, db):
    _, _, _, admin, wa, wb = env
    c = client.login(admin)
    tid = _out(c, wa, wb, amount=100000).json()["transfer_id"]
    assert c.post("/api/kassa/transfer/in", json={"transfer_id": tid}).status_code == 200
    assert c.post("/api/kassa/transfer/in", json={"transfer_id": tid}).status_code == 409
    assert c.post("/api/kassa/transfer/reject", json={"transfer_id": tid}).status_code == 409
    assert len(_movements(db, wb, reference_type="transfer_in")) == 1
    assert _movements(db, wa, reference_type="transfer_rejected") == []
    db.refresh(wb)
    assert wb.balance == Decimal("100000")


def test_reject_dan_keyin_in_409(client, env, db):
    _, _, _, admin, wa, wb = env
    c = client.login(admin)
    tid = _out(c, wa, wb, amount=100000).json()["transfer_id"]
    assert c.post("/api/kassa/transfer/reject", json={"transfer_id": tid}).status_code == 200
    assert c.post("/api/kassa/transfer/in", json={"transfer_id": tid}).status_code == 409
    assert c.post("/api/kassa/transfer/reject", json={"transfer_id": tid}).status_code == 409
    assert _movements(db, wb) == []
    assert len(_movements(db, wa, reference_type="transfer_rejected")) == 1


# ─── 5. Reject ───────────────────────────────────────────────────────────────

def test_reject_pulni_qaytaradi(client, env, db):
    _, _, _, admin, wa, wb = env
    c = client.login(admin)
    tid = _out(c, wa, wb, amount=250000).json()["transfer_id"]
    db.refresh(wa)
    assert wa.balance == Decimal("750000")
    assert c.post("/api/kassa/transfer/reject", json={"transfer_id": tid}).status_code == 200
    db.refresh(wa)
    assert wa.balance == Decimal("1000000")
    ct = db.get(CashTransfer, tid)
    assert ct.status == "rejected"
    rej = _movements(db, wa, reference_type="transfer_rejected")
    assert len(rej) == 1 and rej[0].direction == "in" and rej[0].amount == Decimal("250000")
    assert db.query(AuditLog).filter_by(action="CASH_TRANSFER_REJECT", entity_id=tid).count() == 1


def test_reject_yuboruvchi_ochirilgan_bolsa_400(client, env, db):
    _, _, _, admin, wa, wb = env
    c = client.login(admin)
    tid = _out(c, wa, wb, amount=100000).json()["transfer_id"]
    wa.is_active = False
    db.flush()
    r = c.post("/api/kassa/transfer/reject", json={"transfer_id": tid})
    assert r.status_code == 400 and "Yuboruvchi kassa topilmadi" in r.json()["detail"]
    assert db.get(CashTransfer, tid).status == "pending"


# ─── 6. Huquq ────────────────────────────────────────────────────────────────

def test_biriktirilmagan_kassir_403(client, env, db, mk):
    comp, ba, bb, admin, wa, wb = env
    tid = _out(client.login(admin), wa, wb, amount=100000).json()["transfer_id"]
    other = mk.user(comp, role=R.accountant, branch=bb)
    c = client.login(other)
    assert _out(c, wa, wb).status_code == 403
    assert c.post("/api/kassa/transfer/in", json={"transfer_id": tid}).status_code == 403
    assert c.post("/api/kassa/transfer/reject", json={"transfer_id": tid}).status_code == 403
    assert db.get(CashTransfer, tid).status == "pending"
    # oddiy kassir router darajasida ham yopiq
    cashier = mk.user(comp, role=R.cashier, branch=ba)
    assert _out(client.login(cashier), wa, wb).status_code == 403


def test_biriktirilgan_kassir_yubora_va_rad_eta_oladi(client, env, db, mk):
    comp, ba, bb, admin, wa, wb = env
    sender_user = mk.user(comp, role=R.accountant, branch=ba)
    db.add(UserWallet(user_id=sender_user.id, wallet_id=wa.id, company_id=comp.id))
    db.flush()
    c = client.login(sender_user)
    r = _out(c, wa, wb, amount=50000)
    assert r.status_code == 200, r.text
    # yuboruvchi kassa foydalanuvchisi o'zi yuborgan o'tkazmani rad eta oladi
    assert c.post("/api/kassa/transfer/reject", json={"transfer_id": r.json()["transfer_id"]}).status_code == 200


def test_user_can_use_wallet(db, mk):
    comp, ba, _, admin = mk.tenant()
    w = _wallet(db, comp, ba)
    other_comp = mk.company()
    foreign = mk.user(other_comp, role=R.admin)
    mgr = mk.user(comp, role=R.manager)
    cashier = mk.user(comp, role=R.cashier)
    sa = mk.user(None, role=R.super_admin)
    assert user_can_use_wallet(db, admin, w) and user_can_use_wallet(db, mgr, w)
    assert user_can_use_wallet(db, sa, w)
    assert not user_can_use_wallet(db, foreign, w)
    assert not user_can_use_wallet(db, cashier, w)
    db.add(UserWallet(user_id=cashier.id, wallet_id=w.id, company_id=comp.id))
    db.flush()
    assert user_can_use_wallet(db, cashier, w)
    assert not user_can_use_wallet(db, cashier, None)


# ─── 7. Korxonalar izolyatsiyasi ─────────────────────────────────────────────

def test_boshqa_korxona_404(client, env, db, mk):
    comp, ba, bb, admin, wa, wb = env
    tid = _out(client.login(admin), wa, wb, amount=100000).json()["transfer_id"]
    comp2, br2, _, admin2 = mk.tenant()
    w2 = _wallet(db, comp2, br2)
    _fund(db, w2, 1000)
    c = client.login(admin2)
    assert _out(c, wa, w2).status_code == 404            # A korxona kassasidan yuborish
    assert c.post(f"/api/kassa/{w2.id}/transfer/out", json={"receiver_wallet_id": wb.id, "amount": 10}).status_code == 404
    assert c.post("/api/kassa/transfer/in", json={"transfer_id": tid}).status_code == 404
    assert c.post("/api/kassa/transfer/reject", json={"transfer_id": tid}).status_code == 404
    assert db.get(CashTransfer, tid).status == "pending"
    assert _movements(db, w2) and len(_movements(db, w2)) == 1


# ─── 8. out-batch ────────────────────────────────────────────────────────────

def _batch(c, wa, wb, lines, **kw):
    return c.post(f"/api/kassa/{wa.id}/transfer/out-batch",
                  json={"receiver_wallet_id": wb.id, "note": "batch", "lines": lines, **kw})


def test_batch_atomar_birortasi_xato_hech_biri_saqlanmaydi(client, env, db):
    _, _, _, admin, wa, wb = env
    c = client.login(admin)
    before = _count(db)
    r = _batch(c, wa, wb, [
        {"payment_type": "cash", "currency": "UZS", "amount": 100000},
        {"payment_type": "cash", "currency": "USD", "amount": 10},
        {"payment_type": "card", "currency": "UZS", "amount": 5000},   # kartada pul yo'q
    ])
    assert r.status_code == 400
    assert _count(db) == before
    db.refresh(wa)
    assert wa.balance == Decimal("1000000")
    # bir xil tur/valyuta qatorlari yig'indisi ham tekshiriladi
    r = _batch(c, wa, wb, [
        {"payment_type": "cash", "currency": "UZS", "amount": 600000},
        {"payment_type": "cash", "currency": "UZS", "amount": 600000},
    ])
    assert r.status_code == 400 and _count(db) == before
    # validatsiya xatosi (422) ham hech narsa yozmaydi
    r = _batch(c, wa, wb, [{"payment_type": "cash", "currency": "UZS", "amount": 10},
                           {"payment_type": "cash", "currency": "UZS", "amount": -1}])
    assert r.status_code == 422 and _count(db) == before
    assert _batch(c, wa, wb, []).status_code == 422


def test_batch_muvaffaqiyat_uzs_va_usd(client, env, db):
    _, _, _, admin, wa, wb = env
    c = client.login(admin)
    r = _batch(c, wa, wb, [
        {"payment_type": "cash", "currency": "UZS", "amount": 100000},
        {"payment_type": "cash", "currency": "USD", "amount": 20},
    ])
    assert r.status_code == 200, r.text
    ids = r.json()["transfer_ids"]
    assert r.json()["ok"] and len(ids) == 2
    cts = [db.get(CashTransfer, i) for i in ids]
    assert all(ct.status == "pending" for ct in cts)
    assert {ct.currency for ct in cts} == {"UZS", "USD"}
    assert len(_movements(db, wa, reference_type="transfer_out")) == 2
    assert _movements(db, wb) == []
    db.refresh(wa)
    assert wa.balance == Decimal("900000")          # faqat UZS qismi
    assert db.query(AuditLog).filter_by(action="CASH_TRANSFER_OUT").count() == 2


# ─── 9. Migratsiya / model ───────────────────────────────────────────────────

def test_migratsiya_va_model_mos():
    import importlib.util
    import os
    p = os.path.join(os.path.dirname(__file__), "..", "..", "alembic", "versions",
                     "t0_35_cash_transfer_branch_and_guards.py")
    spec = importlib.util.spec_from_file_location("t0_35", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "t0_35" and mod.down_revision == 't0_33'
    cols = CashTransfer.__table__.c
    assert "sender_branch_id" in cols and "receiver_branch_id" in cols
