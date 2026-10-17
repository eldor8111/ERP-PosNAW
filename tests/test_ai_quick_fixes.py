"""AI Copilot tezkor tuzatishlari testlari (Bosqich 0 dan keyingi birinchi qadam).

Internetsiz ishlaydi: OpenRouter chaqiruvlari soxtalashtirilgan, SMS tenant testi
xotiradagi SQLite'da (Customer jadvali) bajariladi.
"""
import asyncio
from types import SimpleNamespace

import pytest
import requests
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401  — barcha modellar/mapperlar ro'yxatdan o'tishi uchun
from app.config import settings
from app.models.customer import Customer
from app.routers import ai_analytics
from app.services import eskiz_service
from app.services import openrouter_copilot_service as copilot


# ───────────────────────── model zanjiri (sozlamadan) ─────────────────────────

def test_model_chain_comes_from_settings_dedup_and_order(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "main/model")
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", " fb/one , main/model,,fb/two ")
    assert copilot._model_chain() == ["main/model", "fb/one", "fb/two"]


def test_model_chain_without_fallbacks(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "main/model")
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", "")
    assert copilot._model_chain() == ["main/model"]


def test_no_hardcoded_free_models_left_in_copilot_module():
    assert not hasattr(copilot, "FREE_MODELS")


# ───────────────────────── call_copilot_ai xatolari ─────────────────────────

class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Client Error: https://openrouter.ai/secret-url")


def _patch_post(monkeypatch, handler):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json["model"])
        return handler(json["model"])

    monkeypatch.setattr(copilot.requests, "post", fake_post)
    return calls


def test_all_models_402_does_not_crash_with_nameerror(monkeypatch):
    """Ilgari barcha modellar 402/403 qaytarsa last_error aniqlanmay NameError berardi."""
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "m1")
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", "m2")
    calls = _patch_post(monkeypatch, lambda model: FakeResp(402))
    res = copilot.call_copilot_ai("salom", "ctx", "key")
    assert res["intent"] == "error"
    assert calls == ["m1", "m2"]


def test_internal_error_text_is_not_leaked_to_user(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "m1")
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", "")
    _patch_post(monkeypatch, lambda model: FakeResp(404))
    res = copilot.call_copilot_ai("salom", "ctx", "key")
    assert res["reply"] == copilot.AI_UNAVAILABLE_REPLY
    assert "openrouter" not in res["reply"].lower()
    assert "404" not in res["reply"]


def test_falls_over_to_next_model_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "dead/model")
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", "live/model")
    ok = {"choices": [{"message": {"content": " Salom! "}}]}
    calls = _patch_post(monkeypatch, lambda model: FakeResp(200, ok) if model == "live/model" else FakeResp(404))
    res = copilot.call_copilot_ai("salom", "ctx", "key")
    assert res == {"intent": "query", "reply": "Salom!"}
    assert calls == ["dead/model", "live/model"]


def test_tool_call_is_returned_as_execute_tool(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "m1")
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", "")
    body = {"choices": [{"message": {"content": None, "tool_calls": [
        {"function": {"name": "check_customer_debt", "arguments": '{"customer_name": "Asror"}'}}]}}]}
    _patch_post(monkeypatch, lambda model: FakeResp(200, body))
    res = copilot.call_copilot_ai("Asror qarzi", "ctx", "key")
    assert res == {"intent": "execute_tool", "tool_name": "check_customer_debt",
                   "tool_arguments": {"customer_name": "Asror"}}


def test_missing_key_and_model_are_reported(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "")
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", "")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert copilot.call_copilot_ai("x", "c", "")["reply"] == "OPENROUTER_API_KEY sozlanmagan."
    assert copilot.call_copilot_ai("x", "c", "key")["reply"] == "OPENROUTER_MODEL sozlanmagan."


def test_summarize_fallback_does_not_crash_on_string_result(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_MODEL", "m1")
    monkeypatch.setattr(settings, "OPENROUTER_FALLBACK_MODELS", "")
    _patch_post(monkeypatch, lambda model: FakeResp(404))
    out = copilot.summarize_tool_result_with_llm("savol", "tool", '{"a": 1}', "key")
    assert isinstance(out, str) and out


# ───────────────────────── /ai/status autentifikatsiya ─────────────────────────

def test_ai_status_requires_authentication():
    from fastapi.testclient import TestClient
    client = TestClient(app.main.app)
    resp = client.get(f"{app.main.API_PREFIX}/ai/status")
    assert resp.status_code in (401, 403)


# ───────────────────────── SMS kampaniya: qabul qiluvchi tekshiruvi ─────────────────────────

@pytest.fixture()
def db_and_sender(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    from app.models.sms_log import SMSLog
    Customer.__table__.create(bind=engine)
    SMSLog.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        Customer(id=1, name="A1", phone="+998901111111", company_id=1),
        Customer(id=2, name="A2", phone=None, company_id=1),
        Customer(id=3, name="B1", phone="+998902222222", company_id=2),
    ])
    db.commit()

    sent = []

    async def fake_send(phone, message):
        sent.append((phone, message))
        return {"success": True, "eskiz_id": "e1"}

    monkeypatch.setattr(eskiz_service, "send_sms", fake_send)
    yield db, sent
    db.close()


def _run(request, db, company_id=1):
    user = SimpleNamespace(id=10, company_id=company_id)
    return asyncio.run(ai_analytics.confirm_ai_sms_campaign(request, db, user))


def _req(*recipients, message="Salom"):
    return ai_analytics.ConfirmSmsRequest(
        recipients=[ai_analytics.ConfirmSmsRecipient(**r) for r in recipients], message=message)


def test_sms_uses_database_phone_not_client_phone(db_and_sender):
    db, sent = db_and_sender
    result = _run(_req({"id": 1, "phone": "+998999999999"}), db)
    assert sent == [("+998901111111", "Salom")]
    assert result["sent"] == 1 and result["failed"] == 0


def test_sms_rejects_other_company_customer_and_sends_nothing(db_and_sender):
    db, sent = db_and_sender
    with pytest.raises(HTTPException) as exc:
        _run(_req({"id": 1, "phone": "x"}, {"id": 3, "phone": "y"}), db)  # 3 — boshqa kompaniya
    assert exc.value.status_code == 400
    assert sent == []


def test_sms_rejects_arbitrary_number_without_customer_id(db_and_sender):
    db, sent = db_and_sender
    with pytest.raises(HTTPException) as exc:
        _run(_req({"phone": "+998933333333"}), db)
    assert exc.value.status_code == 400
    assert sent == []


def test_sms_rejects_unknown_customer_id(db_and_sender):
    db, sent = db_and_sender
    with pytest.raises(HTTPException) as exc:
        _run(_req({"id": 999, "phone": "+998933333333"}), db)
    assert exc.value.status_code == 400
    assert sent == []


def test_sms_dedupes_ids_and_counts_missing_phone_as_failed(db_and_sender):
    db, sent = db_and_sender
    result = _run(_req({"id": 1, "phone": "a"}, {"id": 1, "phone": "b"}, {"id": 2, "phone": "c"}), db)
    assert [p for p, _ in sent] == ["+998901111111"]
    assert result["sent"] == 1 and result["failed"] == 1
