"""T0.18 — Mir-maza webhook himoyasi, kodga yozilgan sirlar, Payme va SMS kodi oqishi.

Ishga tushirish (repo ildizidan):
    python -m pytest tests/branch_audit/test_T0_18.py -q -p no:cacheprovider
"""
import base64
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.config import settings
from app.core.limiter import limiter
from app.models.marketplace import (
    MarketplaceAgentTransaction, MarketplaceProduct, MarketplaceProductStatus, MarketplaceTransactionType,
)
from app.models.payme_transaction import PaymeTransaction
from app.models.user import SmsVerification, User, UserRole, UserStatus
from app.routers import payme as payme_mod
from app.services import marketplace_service as mp_service
from app.utils.tariff_check import check_user_limit

WEBHOOK = "/api/mobile/marketplace/webhook/order"
SEND_CODE = "/api/mobile/marketplace/register/send-code"
PAYME = "/api/payme/webhook"
KEY = "test-integration-key-T0-18"


# ── Yordamchilar ────────────────────────────────────────────────────────────

@pytest.fixture
def token(monkeypatch):
    """MARKETPLACE_API_TOKEN sozlangan muhit."""
    monkeypatch.setattr(settings, "MARKETPLACE_API_TOKEN", KEY)
    return KEY


@pytest.fixture
def no_limiter(monkeypatch):
    """slowapi IP limiti (3/minute) testlarda xalaqit bermasin."""
    monkeypatch.setattr(limiter, "enabled", False)


def _agent(mk, company, **kw):
    kw.setdefault("status", UserStatus.active)
    return mk.user(company, role=UserRole.marketplace_agent, **kw)


def _product(db, company, agent, price="10000", qty="10"):
    p = MarketplaceProduct(
        company_id=company.id, agent_id=agent.id, name=f"Tovar {agent.id}",
        price=Decimal(price), qty=Decimal(qty), category_id=1,
        status=MarketplaceProductStatus.approved,
    )
    db.add(p)
    db.flush()
    return p


def _incomes(db, product):
    return db.query(MarketplaceAgentTransaction).filter(
        MarketplaceAgentTransaction.marketplace_product_id == product.id,
        MarketplaceAgentTransaction.transaction_type == MarketplaceTransactionType.income,
    ).all()


def _payload(product, qty=2, total=None, order_id=777):
    if total is None:
        total = float(product.price) * qty
    return {"marketOrderId": order_id,
            "items": [{"externalId": f"ECODE-PROD-{product.id}", "quantity": qty, "total": total}]}


def _post_webhook(client, payload, key=KEY):
    headers = {"X-Integration-Key": key} if key is not None else {}
    return client.post(WEBHOOK, json=payload, headers=headers)


# ── 1. Webhook autentifikatsiyasi ───────────────────────────────────────────

def test_webhook_token_sozlanmagan_503(client, db, mk, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_API_TOKEN", "")
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    r = _post_webhook(client, _payload(p), key="har-qanday")
    assert r.status_code == 503
    assert _incomes(db, p) == []


def test_webhook_sarlavhasiz_401(client, db, mk, token):
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    r = _post_webhook(client, _payload(p), key=None)
    assert r.status_code == 401
    assert _incomes(db, p) == []
    assert float(db.get(MarketplaceProduct, p.id).qty) == 10


def test_webhook_notogri_kalit_401(client, db, mk, token):
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    r = _post_webhook(client, _payload(p), key="notogri")
    assert r.status_code == 401
    assert _incomes(db, p) == []


def test_webhook_togri_kalit_income_yoziladi(client, db, mk, token):
    c, b, w, u = mk.tenant()
    agent = _agent(mk, c)
    p = _product(db, c, agent)
    r = _post_webhook(client, _payload(p, qty=2))
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok", "processed": 1, "skipped": 0, "rejected": 0}
    txs = _incomes(db, p)
    assert len(txs) == 1
    assert float(txs[0].amount) == 20000
    assert txs[0].agent_id == agent.id and txs[0].company_id == c.id
    assert txs[0].order_id == 777
    assert float(db.get(MarketplaceProduct, p.id).qty) == 8


# ── 2. Idempotentlik ────────────────────────────────────────────────────────

def test_webhook_10_marta_bitta_income(client, db, mk, token):
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    for i in range(10):
        r = _post_webhook(client, _payload(p, qty=2))
        assert r.status_code == 200
        if i > 0:
            assert r.json()["skipped"] == 1 and r.json()["processed"] == 0
    assert len(_incomes(db, p)) == 1
    assert float(db.get(MarketplaceProduct, p.id).qty) == 8


def test_webhook_boshqa_buyurtma_alohida_yoziladi(client, db, mk, token):
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    assert _post_webhook(client, _payload(p, qty=1, order_id=1)).status_code == 200
    assert _post_webhook(client, _payload(p, qty=1, order_id=2)).status_code == 200
    assert len(_incomes(db, p)) == 2
    assert float(db.get(MarketplaceProduct, p.id).qty) == 8


def test_unikal_indeks_income_dublikatni_bazada_ham_tosadi(db, mk):
    """Modeldagi qisman unikal indeks: bir order+mahsulot uchun ikkinchi income yozilmaydi."""
    from sqlalchemy.exc import IntegrityError
    c, b, w, u = mk.tenant()
    agent = _agent(mk, c)
    p = _product(db, c, agent)
    for _ in range(2):
        db.add(MarketplaceAgentTransaction(
            agent_id=agent.id, company_id=c.id, order_id=5, marketplace_product_id=p.id,
            transaction_type=MarketplaceTransactionType.income, amount=1,
        ))
    with pytest.raises(IntegrityError):
        db.flush()


# ── 3. Sxema va summa tekshiruvi ────────────────────────────────────────────

def test_webhook_manfiy_total_422(client, db, mk, token):
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    r = _post_webhook(client, _payload(p, qty=1, total=-5000))
    assert r.status_code == 422
    assert _incomes(db, p) == []


def test_webhook_nol_quantity_422(client, db, mk, token):
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    r = _post_webhook(client, _payload(p, qty=0, total=0))
    assert r.status_code == 422


def test_webhook_summa_narxga_mos_kelmasa_rad(client, db, mk, token):
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    r = _post_webhook(client, _payload(p, qty=1, total=50_000_000))
    assert r.status_code == 200
    assert r.json()["rejected"] == 1 and r.json()["processed"] == 0
    assert _incomes(db, p) == []
    assert float(db.get(MarketplaceProduct, p.id).qty) == 10


def test_webhook_orderId_alias_qabul_qilinadi(client, db, mk, token):
    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    body = {"orderId": 55, "items": [{"externalId": f"ECODE-PROD-{p.id}", "quantity": 1, "total": 10000}]}
    r = _post_webhook(client, body)
    assert r.status_code == 200 and r.json()["processed"] == 1
    assert _incomes(db, p)[0].order_id == 55


# ── 4. Savepoint: bitta xato item qolganlarini buzmaydi ─────────────────────

def test_webhook_bitta_notogri_item_qolganlari_yoziladi(client, db, mk, token):
    c, b, w, u = mk.tenant()
    agent = _agent(mk, c)
    p1 = _product(db, c, agent)
    p2 = _product(db, c, agent)
    body = {"marketOrderId": 900, "items": [
        {"externalId": "ECODE-PROD-abc", "quantity": 1, "total": 10000},        # int() xatosi (savepoint)
        {"externalId": f"ECODE-PROD-{p1.id}", "quantity": 1, "total": 10000},   # to'g'ri
        {"externalId": "ECODE-PROD-999999999", "quantity": 1, "total": 10000},  # mahsulot yo'q
        {"externalId": "PROD-5", "quantity": 1, "total": 10000},                # agent mahsuloti emas
        {"externalId": f"ECODE-PROD-{p2.id}", "quantity": 3, "total": 30000},   # to'g'ri
    ]}
    r = _post_webhook(client, body)
    assert r.status_code == 200, r.text
    assert r.json()["processed"] == 2 and r.json()["rejected"] == 2
    assert len(_incomes(db, p1)) == 1 and len(_incomes(db, p2)) == 1
    assert float(db.get(MarketplaceProduct, p1.id).qty) == 9
    assert float(db.get(MarketplaceProduct, p2.id).qty) == 7


def test_webhook_xatoda_name_error_yoq(client, db, mk, token, caplog):
    """Modulda logger bor: xato item uchun NameError emas, warning yoziladi."""
    c, b, w, u = mk.tenant()
    with caplog.at_level(logging.WARNING, logger="app.routers.mobile.marketplace_agent"):
        r = _post_webhook(client, {"marketOrderId": 1, "items": [{"externalId": "ECODE-PROD-x", "quantity": 1, "total": 1}]})
    assert r.status_code == 200
    assert "Webhookda xatolik" in caplog.text
    assert "NameError" not in caplog.text


# ── 5. Ikki korxona izolyatsiyasi ───────────────────────────────────────────

def test_webhook_izolyatsiya_ikki_korxona(client, db, mk, token):
    ca, ba, wa, ua = mk.tenant()
    cb, bb, wb, ub = mk.tenant()
    agent_a = _agent(mk, ca)
    agent_b = _agent(mk, cb)
    pa = _product(db, ca, agent_a)
    pb = _product(db, cb, agent_b)

    # Faqat A mahsuloti sotildi (B bilan bir xil marketOrderId)
    r = _post_webhook(client, _payload(pa, qty=1, order_id=100))
    assert r.status_code == 200 and r.json()["processed"] == 1

    tx_a = _incomes(db, pa)
    assert len(tx_a) == 1 and tx_a[0].company_id == ca.id and tx_a[0].agent_id == agent_a.id
    assert _incomes(db, pb) == []
    assert db.query(MarketplaceAgentTransaction).filter(
        MarketplaceAgentTransaction.company_id == cb.id).count() == 0
    assert float(db.get(MarketplaceProduct, pb.id).qty) == 10

    # B mahsuloti ham o'sha order bilan — o'z korxonasiga yoziladi, A ga ta'sir qilmaydi
    r = _post_webhook(client, _payload(pb, qty=1, order_id=100))
    assert r.status_code == 200 and r.json()["processed"] == 1
    assert len(_incomes(db, pa)) == 1
    tx_b = _incomes(db, pb)
    assert len(tx_b) == 1 and tx_b[0].company_id == cb.id and tx_b[0].agent_id == agent_b.id


# ── 6. Kodga yozilgan kalit yo'q; kalit bo'sh bo'lsa so'rov ketmaydi ───────

def test_qattiq_kalit_app_ichida_yoq():
    import os
    root = os.path.join(os.path.dirname(__file__), "..", "..", "app")
    hits = []
    for dp, _, files in os.walk(root):
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(dp, f)
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if "ecode_secret_key_mirmaza_2026" in fh.read():
                        hits.append(path)
    assert hits == []


def test_kalit_bosh_bolsa_chiquvchi_sorov_yuborilmaydi(db, mk, monkeypatch):
    monkeypatch.setattr(settings, "MARKETPLACE_API_TOKEN", "")

    def _boom(*a, **k):
        raise AssertionError("tashqi so'rov yuborilmasligi kerak edi")

    monkeypatch.setattr(mp_service.httpx, "get", _boom)
    monkeypatch.setattr(mp_service.httpx, "post", _boom)
    monkeypatch.setattr(mp_service.httpx, "put", _boom)

    c, b, w, u = mk.tenant()
    p = _product(db, c, _agent(mk, c))
    assert mp_service.push_product_to_mirmaza(p, "Kategoriya") is False
    assert mp_service.pull_mirmaza_orders(db, c.id) is None
    assert mp_service.push_courier_status_to_mirmaza(db, "mirmaza-1", 0, "ASSIGNED") is None
    assert mp_service._integration_key() is None


def test_kalit_bor_bolsa_sarlavhada_ketadi(db, mk, token, monkeypatch):
    sent = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"orders": []}

    def _get(url, headers=None, **k):
        sent["headers"] = headers
        return _Resp()

    monkeypatch.setattr(mp_service.httpx, "get", _get)
    c, b, w, u = mk.tenant()
    mp_service.pull_mirmaza_orders(db, c.id)
    assert sent["headers"]["X-Integration-Key"] == KEY


def test_pull_income_webhook_bilan_dublikat_qilmaydi(db, mk, token, monkeypatch):
    """pull_mirmaza_orders: webhook allaqachon income yozgan bo'lsa qayta kreditlamaydi."""
    c, b, w, u = mk.tenant()
    agent = _agent(mk, c)
    p = _product(db, c, agent)
    # Webhook yozgan income
    db.add(MarketplaceAgentTransaction(
        agent_id=agent.id, company_id=c.id, order_id=4242, marketplace_product_id=p.id,
        transaction_type=MarketplaceTransactionType.income, amount=10000,
    ))
    db.flush()

    class _Resp:
        status_code = 200

        def json(self):
            return {"orders": [{
                "marketOrderId": 4242,
                "customer": {"phone": "998901234567", "name": "Mijoz"},
                "items": [{"externalId": f"ECODE-PROD-{p.id}", "quantity": 1, "total": 10000, "price": 10000}],
                "total": 10000,
            }]}

    monkeypatch.setattr(mp_service.httpx, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(mp_service.httpx, "post", lambda *a, **k: _Resp())
    monkeypatch.setattr(mp_service.httpx, "put", lambda *a, **k: _Resp())
    mp_service.pull_mirmaza_orders(db, c.id)
    assert len(_incomes(db, p)) == 1
    assert float(db.get(MarketplaceProduct, p.id).qty) == 10


# ── 7. SMS kodi: debug_code yo'q, Eskiz xatosida 503, limit ─────────────────

def _mp_company(mk):
    return mk.company(marketplace_agents_enabled=True, is_active=True)


@pytest.fixture
def eskiz(monkeypatch):
    from app.services.eskiz_service import eskiz_service
    state = {"success": True, "calls": []}

    async def _send(phone, msg):
        state["calls"].append((phone, msg))
        return {"success": state["success"], "error": None if state["success"] else "limit"}

    monkeypatch.setattr(eskiz_service, "send_sms", _send)
    return state


def test_send_code_eskiz_xatosi_503_va_kod_yoq(client, db, mk, no_limiter, eskiz):
    c = _mp_company(mk)
    eskiz["success"] = False
    r = client.post(SEND_CODE, json={"org_code": c.org_code, "phone": "998901234567"})
    assert r.status_code == 503
    body = r.json()
    assert "debug_code" not in body and "sms_error" not in body
    assert "SMS yuborilmadi" in body["detail"]
    assert db.query(SmsVerification).filter(SmsVerification.phone == "998901234567").count() == 0


def test_send_code_muvaffaqiyatli_debug_code_yoq(client, db, mk, no_limiter, eskiz):
    c = _mp_company(mk)
    r = client.post(SEND_CODE, json={"org_code": c.org_code, "phone": "998901234567"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["sms_sent"] is True
    assert "debug_code" not in body and "sms_error" not in body
    rows = db.query(SmsVerification).filter(SmsVerification.phone == "998901234567").all()
    assert len(rows) == 1
    assert rows[0].code.isdigit() and len(rows[0].code) == 5 and 10000 <= int(rows[0].code) <= 99999
    # Kod SMS matnida ketgan, javobda emas
    assert rows[0].code in eskiz["calls"][0][1]
    assert rows[0].code not in r.text


def test_send_code_telefon_limiti_429(client, db, mk, no_limiter, eskiz):
    c = _mp_company(mk)
    for _ in range(5):
        assert client.post(SEND_CODE, json={"org_code": c.org_code, "phone": "998901234567"}).status_code == 200
    r = client.post(SEND_CODE, json={"org_code": c.org_code, "phone": "998901234567"})
    assert r.status_code == 429
    # Boshqa raqam uchun limit alohida
    assert client.post(SEND_CODE, json={"org_code": c.org_code, "phone": "998901234568"}).status_code == 200


def test_send_code_eski_urinishlar_limitga_kirmaydi(client, db, mk, no_limiter, eskiz):
    c = _mp_company(mk)
    for _ in range(5):
        db.add(SmsVerification(phone="998901234567", code="11111",
                               expires_at=datetime.now(timezone.utc),
                               created_at=datetime.now(timezone.utc) - timedelta(hours=2)))
    db.flush()
    r = client.post(SEND_CODE, json={"org_code": c.org_code, "phone": "998901234567"})
    assert r.status_code == 200


# ── 8. Pending agentlar xodim kvotasiga kirmaydi ─────────────────────────────

def test_pending_agentlar_check_user_limitga_kirmaydi(db, mk):
    from fastapi import HTTPException
    c, b, w, admin = mk.tenant()           # 1 ta faol admin
    for _ in range(3):
        mk.user(c, role=UserRole.cashier)  # jami 4 ta xodim (limit 5)
    for _ in range(100):
        _agent(mk, c, status=UserStatus.pending)
    for _ in range(3):
        _agent(mk, c, status=UserStatus.active)
    check_user_limit(db, c.id, admin)      # 4 < 5 — xato bo'lmasligi kerak
    mk.user(c, role=UserRole.cashier)      # 5-xodim
    with pytest.raises(HTTPException) as ei:
        check_user_limit(db, c.id, admin)
    assert ei.value.status_code == 403


# ── 9. Payme ───────────────────────────────────────────────────────────────

SECRET = "zq7vSecretKey-T018-w3kx"  # prefiks/suffiks log matnida tasodifan uchramasin


@pytest.fixture
def payme(monkeypatch):
    monkeypatch.setattr(payme_mod, "PAYME_SECRET_KEY", SECRET)
    monkeypatch.setattr(payme_mod, "PAYME_MERCHANT_ID", "merchant-id")


def _basic(user="Paycom", password=SECRET):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def _rpc(client, method, params, headers=None, rid=1):
    return client.post(PAYME, json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
                       headers=headers if headers is not None else _basic())


def test_payme_togri_parol_otadi(client, db, mk, payme):
    r = _rpc(client, "CheckPerformTransaction", {"amount": 1, "account": {"org_code": "YOQ"}})
    assert r.status_code == 200
    assert r.json()["error"]["code"] == payme_mod.ERR_ORDER_NOT_FOUND  # auth o'tdi, org topilmadi


def test_payme_notogri_parol_401_va_logda_parol_yoq(client, db, mk, payme, caplog):
    wrong = "WrongPassword-abc123"
    with caplog.at_level(logging.DEBUG, logger="app.routers.payme"):
        r = _rpc(client, "CheckPerformTransaction", {"amount": 1, "account": {}}, headers=_basic(password=wrong))
        r2 = client.post(PAYME, json={"jsonrpc": "2.0", "id": 2, "method": "CheckPerformTransaction", "params": {}},
                         headers={"Authorization": "Basic " + base64.b64encode(b"nocolonsecretvalue").decode()})
    assert r.json()["error"]["code"] == payme_mod.ERR_UNAUTHORIZED
    assert r2.json()["error"]["code"] == payme_mod.ERR_UNAUTHORIZED
    text = caplog.text
    assert wrong not in text and wrong[:3] not in text.replace("Pass matches", "")
    assert SECRET not in text and SECRET[:3] not in text and SECRET[-3:] not in text
    assert "nocolonsecretvalue" not in text
    assert base64.b64encode(f"Paycom:{wrong}".encode()).decode()[:20] not in text


def test_payme_compare_digest_ishlatiladi():
    import inspect
    src = inspect.getsource(payme_mod._verify_auth)
    assert "hmac.compare_digest" in src
    assert "== PAYME_SECRET_KEY" not in src


def test_payme_bloklangan_agent_check_va_create_rad(client, db, mk, payme):
    c, b, w, u = mk.tenant()
    phone = "998933334455"
    _agent(mk, c, status=UserStatus.blocked, phone=phone)
    r = _rpc(client, "CheckPerformTransaction", {"amount": 20000000, "account": {"agent_phone": phone}})
    assert r.json()["error"]["code"] == payme_mod.ERR_UNABLE_TO_PERFORM
    r = _rpc(client, "CreateTransaction", {"id": "txblocked1", "time": 1, "amount": 20000000,
                                           "account": {"agent_phone": phone}})
    assert r.json()["error"]["code"] == payme_mod.ERR_UNABLE_TO_PERFORM
    assert db.query(PaymeTransaction).filter(PaymeTransaction.payme_id == "txblocked1").count() == 0


def test_payme_faol_agent_check_va_create_otadi(client, db, mk, payme):
    c, b, w, u = mk.tenant()
    phone = "998933334466"
    _agent(mk, c, status=UserStatus.pending, phone=phone)
    r = _rpc(client, "CheckPerformTransaction", {"amount": 20000000, "account": {"agent_phone": phone}})
    assert r.json()["result"] == {"allow": True}
    r = _rpc(client, "CreateTransaction", {"id": "txok1", "time": 1, "amount": 20000000,
                                           "account": {"agent_phone": phone}})
    assert "result" in r.json(), r.text
    txn = db.query(PaymeTransaction).filter(PaymeTransaction.payme_id == "txok1").first()
    assert txn is not None and txn.company_id == c.id


def test_payme_company_id_yoq_agent_or1_fallback_yoq(client, db, mk, payme):
    phone = "998933334477"
    mk.user(None, role=UserRole.marketplace_agent, phone=phone)  # company_id=None
    r = _rpc(client, "CreateTransaction", {"id": "txnoco", "time": 1, "amount": 20000000,
                                           "account": {"agent_phone": phone}})
    assert r.json()["error"]["code"] == payme_mod.ERR_ORDER_NOT_FOUND
    assert db.query(PaymeTransaction).filter(PaymeTransaction.payme_id == "txnoco").count() == 0


def _txn(db, company, phone, payme_id, state=1, amount=20000000):
    t = PaymeTransaction(company_id=company.id, payme_id=payme_id, amount=amount, state=state,
                         create_time=1, perform_time=2 if state == 2 else None, account_org_code=phone)
    db.add(t)
    db.flush()
    return t


def test_payme_perform_bloklangan_agent_active_bolmaydi(client, db, mk, payme):
    c, b, w, u = mk.tenant()
    phone = "998933334488"
    agent = _agent(mk, c, status=UserStatus.blocked, phone=phone)
    _txn(db, c, phone, "txperf-blocked")
    r = _rpc(client, "PerformTransaction", {"id": "txperf-blocked"})
    assert r.json()["result"]["state"] == 2
    db.refresh(agent)
    assert agent.status == UserStatus.blocked


def test_payme_perform_inactive_agent_active_bolmaydi(client, db, mk, payme):
    c, b, w, u = mk.tenant()
    phone = "998933334489"
    agent = _agent(mk, c, status=UserStatus.inactive, phone=phone)
    _txn(db, c, phone, "txperf-inactive")
    _rpc(client, "PerformTransaction", {"id": "txperf-inactive"})
    db.refresh(agent)
    assert agent.status == UserStatus.inactive


def test_payme_perform_pending_agent_faollashadi(client, db, mk, payme):
    c, b, w, u = mk.tenant()
    phone = "998933334499"
    agent = _agent(mk, c, status=UserStatus.pending, phone=phone)
    _txn(db, c, phone, "txperf-pending")
    r = _rpc(client, "PerformTransaction", {"id": "txperf-pending"})
    assert r.json()["result"]["state"] == 2
    db.refresh(agent)
    assert agent.status == UserStatus.active
    assert agent.subscription_ends_at is not None
    assert float(agent.paid_amount) == 200000


def test_payme_cancel_statusni_ozgartirmaydi_kunlarni_qaytaradi(client, db, mk, payme):
    c, b, w, u = mk.tenant()
    phone = "998933335500"
    ends = datetime(2027, 1, 31, tzinfo=timezone.utc)
    agent = _agent(mk, c, status=UserStatus.active, phone=phone, subscription_ends_at=ends, paid_amount=200000)
    _txn(db, c, phone, "txcancel1", state=2)
    r = _rpc(client, "CancelTransaction", {"id": "txcancel1", "reason": 5})
    assert r.json()["result"]["state"] == -2
    db.refresh(agent)
    assert agent.status == UserStatus.active
    got = agent.subscription_ends_at
    if got.tzinfo is None:
        got = got.replace(tzinfo=timezone.utc)
    assert got == ends - timedelta(days=30)
    assert float(agent.paid_amount) == 0
