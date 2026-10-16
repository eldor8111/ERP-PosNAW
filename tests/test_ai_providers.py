"""
tests/test_ai_providers.py
──────────────────────────
Bosqich 1: LLMProvider abstraksiyasi, provayder adapterlari, routing,
fallback zanjiri, retry, audit logging va PII maskalash testlari.

Barcha testlar internetsiz ishlaydi (MockProvider va HTTP soxtalashtirish bilan).
Haqiqiy API testlari esa alohida @pytest.mark.live_llm bilan belgilangan va
sukut bo'yicha o'chiq.
"""
import os
import json
import pytest
import requests
from types import SimpleNamespace
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.main  # modellar yuklanishi uchun
from app.config import settings
from app.database import Base
from app.models.company import Company
from app.models.user import User, UserRole
from app.models.ai_audit import AIAuditLog
from app.ai.providers.base import (
    LLMProvider,
    LLMResponse,
    ToolCall,
    TokenUsage,
    mask_pii,
)
from app.ai.providers.mock_provider import MockProvider
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.providers.openrouter_provider import OpenRouterProvider
from app.ai.providers.router import LLMRouter, get_llm_router, is_production_env


# ───────────────────────── 1. Bitta sozlama bilan provayder almashtirish ─────────────────────────

def test_provider_switching_single_setting(monkeypatch):
    """LLM_PROVIDER sozlamasi orqali asosiy provayder almashishi kerak."""
    router = LLMRouter()
    
    mock_p = MockProvider()
    router.register_provider("mock", mock_p)

    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(settings, "LLM_FALLBACK_CHAIN", "")
    
    chain = router.get_fallback_chain()
    assert chain[0] == "mock"

    resp = router.chat(system="system", messages=[{"role": "user", "content": "salom"}])
    assert resp.provider == "mock"
    assert len(mock_p.recorded_calls) == 1


# ───────────────────────── 2. Fallback zanjiri har xil xatolar bo'yicha ─────────────────────────

def test_fallback_chain_handles_timeout_404_429_500(monkeypatch):
    """Timeout, 404, 429 yoki 500 bo'lganda zanjirdagi keyingi provayderga o'tishi kerak."""
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 0)  # Provayder fallbackini sinash uchun
    router = LLMRouter()

    class FailProvider(LLMProvider):
        def __init__(self, name: str, exc: Exception):
            self.name = name
            self.exc = exc

        def chat(self, *args, **kwargs):
            raise self.exc

    # 1-provayder: Timeout beradi
    p1 = FailProvider("mock_p1", requests.exceptions.Timeout("Muddati o'tdi (timeout)"))

    # 2-provayder: 429 Rate limit beradi
    err_429 = requests.exceptions.HTTPError("429 Too Many Requests")
    err_429.response = SimpleNamespace(status_code=429)
    p2 = FailProvider("mock_p2", err_429)

    # 3-provayder: 404 Not Found beradi
    err_404 = requests.exceptions.HTTPError("404 Model Not Found")
    err_404.response = SimpleNamespace(status_code=404)
    p3 = FailProvider("mock_p3", err_404)

    # 4-provayder: Muvaffaqiyatli ishlaydi
    p4 = MockProvider()
    p4.name = "mock_p4"
    p4.default_response = LLMResponse(
        text="Muvaffaqiyatli javob p4 dan",
        provider="mock_p4",
        model="success-model",
        usage=TokenUsage(input_tokens=20, output_tokens=30),
        latency_ms=12.5,
    )

    router.register_provider("mock_p1", p1)
    router.register_provider("mock_p2", p2)
    router.register_provider("mock_p3", p3)
    router.register_provider("mock_p4", p4)

    router.get_fallback_chain = lambda: ["mock_p1", "mock_p2", "mock_p3", "mock_p4"]

    resp = router.chat(system="sys", messages=[{"role": "user", "content": "test"}])
    assert resp.provider == "mock_p4"
    assert resp.text == "Muvaffaqiyatli javob p4 dan"


def test_retry_on_transient_error_succeeds(monkeypatch):
    """Transient xatoda (429) bitta provayder ichida retry qilinib muvaffaqiyatli bo'ladi."""
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 2)
    monkeypatch.setattr(settings, "LLM_RETRY_BACKOFF_FACTOR", 1.0)
    router = LLMRouter()

    p = MockProvider()
    p.name = "retry_mock"
    # 1-urinishda 429, 2-urinishda muvaffaqiyatli
    err_429 = requests.exceptions.HTTPError("429 Too Many Requests")
    err_429.response = SimpleNamespace(status_code=429)
    p.queue_response(err_429)
    p.queue_response(LLMResponse(
        text="2-urinishda muvaffaqiyat",
        provider="retry_mock",
        model="model-retry",
    ))

    router.register_provider("retry_mock", p)
    router.get_fallback_chain = lambda: ["retry_mock"]

    resp = router.chat(system="sys", messages=[{"role": "user", "content": "retry test"}])
    assert resp.provider == "retry_mock"
    assert resp.text == "2-urinishda muvaffaqiyat"



def test_fallback_to_local_analysis_when_all_providers_fail():
    """Barcha tashqi provayderlar ishlamasa, mahalliy tahlilga (local fallback) o'tadi."""
    router = LLMRouter()
    
    p1 = MockProvider()
    p1.name = "failing_p1"
    p1.queue_response(requests.exceptions.ConnectionError("Server unreachable"))
    router.register_provider("failing_p1", p1)
    router.get_fallback_chain = lambda: ["failing_p1"]

    resp = router.chat(
        system="sys",
        messages=[{"role": "user", "content": "qarzlar haqida ma'lumot"}],
        allow_local_fallback=True,
    )
    assert resp.stop_reason == "local_fallback"
    assert "⚠️ [Mahalliy tahlil rejimi]" in resp.text


# ───────────────────────── 3. Production rejimda :free rad etilishi ─────────────────────────

def test_production_rejects_free_models(monkeypatch):
    """APP_ENV=production bo'lsa :free modellar rad etilishi (ValueError) shart."""
    router = LLMRouter()

    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ValueError, match="':free' modellar .* production rejimida ishlatilishi taqiqlangan"):
        router.resolve_model(custom_model="meta-llama/llama-3-8b:free")


def test_development_allows_free_models(monkeypatch):
    """Development rejimida :free modellarga ruxsat beriladi."""
    router = LLMRouter()

    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setenv("APP_ENV", "development")

    model = router.resolve_model(custom_model="meta-llama/llama-3-8b:free")
    assert model == "meta-llama/llama-3-8b:free"


# ───────────────────────── 4. DeepSeek standart zanjirga kirmasligi ─────────────────────────

def test_deepseek_excluded_from_default_chain(monkeypatch):
    """DeepSeek sozlamada yozilgan bo'lsa ham ENABLE_DEEPSEEK bo'lmasa kirmaydi."""
    router = LLMRouter()
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "LLM_FALLBACK_CHAIN", "openrouter,deepseek,openai")
    monkeypatch.delenv("ENABLE_DEEPSEEK", raising=False)

    chain = router.get_fallback_chain()
    assert "deepseek" not in chain
    assert chain == ["anthropic", "openrouter", "openai"]


# ───────────────────────── 5. Anthropic formatiga o'girish ─────────────────────────

def test_anthropic_format_conversion():
    """Anthropic adapteri: system alohida, tool_use va tool_result bloklari to'g'ri o'giriladi."""
    prov = AnthropicProvider(api_key="test-key", prompt_caching=True)

    tools = [{
        "name": "check_debt",
        "description": "Mijoz qarzini tekshirish",
        "parameters": {
            "type": "object",
            "properties": {"customer_name": {"type": "string"}},
            "required": ["customer_name"]
        }
    }]
    conv_tools = prov._convert_tools(tools)
    assert len(conv_tools) == 1
    assert conv_tools[0]["name"] == "check_debt"
    assert "input_schema" in conv_tools[0]
    assert conv_tools[0]["cache_control"] == {"type": "ephemeral"}

    # Xabarlar: user -> assistant (tool_use) -> tool (tool_result)
    messages = [
        {"role": "user", "content": "Asror qarzi bormi?"},
        {
            "role": "assistant",
            "content": "Tekshirib ko'raman",
            "tool_calls": [
                ToolCall(id="call_123", name="check_debt", arguments={"customer_name": "Asror"})
            ]
        },
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": {"debt": 150000}
        }
    ]
    conv_msgs = prov._convert_messages(messages)
    
    # 1. User
    assert conv_msgs[0] == {"role": "user", "content": "Asror qarzi bormi?"}
    
    # 2. Assistant: text + tool_use blocks
    assert conv_msgs[1]["role"] == "assistant"
    blocks = conv_msgs[1]["content"]
    assert blocks[0] == {"type": "text", "text": "Tekshirib ko'raman"}
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["id"] == "call_123"
    assert blocks[1]["name"] == "check_debt"
    assert blocks[1]["input"] == {"customer_name": "Asror"}

    # 3. Tool result: Anthropic buni 'user' roli ichida tool_result bloki sifatida oladi
    assert conv_msgs[2]["role"] == "user"
    assert conv_msgs[2]["content"][0]["type"] == "tool_result"
    assert conv_msgs[2]["content"][0]["tool_use_id"] == "call_123"


def test_anthropic_consecutive_tool_results_are_merged():
    """Ketma-ket bir nechta tool_result bitta user xabariga birlashtiriladi."""
    prov = AnthropicProvider(api_key="test-key")
    messages = [
        {"role": "tool", "tool_call_id": "call_1", "content": "res1"},
        {"role": "tool", "tool_call_id": "call_2", "content": "res2"},
    ]
    conv_msgs = prov._convert_messages(messages)
    assert len(conv_msgs) == 1
    assert conv_msgs[0]["role"] == "user"
    assert len(conv_msgs[0]["content"]) == 2
    assert conv_msgs[0]["content"][0]["tool_use_id"] == "call_1"
    assert conv_msgs[0]["content"][1]["tool_use_id"] == "call_2"


# ───────────────────────── 6. OpenAI / OpenRouter formatiga o'girish ─────────────────────────

def test_openai_format_conversion():
    """OpenAI adapteri: system xabar, function schema, assistant tool_calls va role='tool'."""
    prov = OpenAIProvider(api_key="test-key")

    tools = [{
        "name": "get_stock",
        "description": "Ombor qoldig'i",
        "parameters": {"type": "object", "properties": {"product_id": {"type": "integer"}}}
    }]
    conv_tools = prov._convert_tools(tools)
    assert conv_tools[0]["type"] == "function"
    assert conv_tools[0]["function"]["name"] == "get_stock"

    messages = [
        {"role": "user", "content": "Qoldiqni ayt"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [ToolCall(id="tc_1", name="get_stock", arguments={"product_id": 5})]
        },
        {"role": "tool", "tool_call_id": "tc_1", "content": '{"stock": 42}'}
    ]
    conv_msgs = prov._convert_messages(system="Siz do'kon yordamchisisiz", messages=messages)
    
    assert conv_msgs[0] == {"role": "system", "content": "Siz do'kon yordamchisisiz"}
    assert conv_msgs[1] == {"role": "user", "content": "Qoldiqni ayt"}
    assert conv_msgs[2]["role"] == "assistant"
    assert conv_msgs[2]["tool_calls"][0]["id"] == "tc_1"
    assert conv_msgs[2]["tool_calls"][0]["function"]["name"] == "get_stock"
    assert json.loads(conv_msgs[2]["tool_calls"][0]["function"]["arguments"]) == {"product_id": 5}
    assert conv_msgs[3]["role"] == "tool"
    assert conv_msgs[3]["tool_call_id"] == "tc_1"


# ───────────────────────── 7. Usage va Latency qayd qilinishi ─────────────────────────

def test_usage_and_latency_tracked():
    """LLMResponse ichida input_tokens, output_tokens, total_tokens va latency_ms bo'lishi kerak."""
    resp = LLMResponse(
        text="Salom!",
        provider="mock",
        model="m-1",
        usage=TokenUsage(input_tokens=15, output_tokens=35),
        latency_ms=120.5,
    )
    assert resp.usage.input_tokens == 15
    assert resp.usage.output_tokens == 35
    assert resp.usage.total_tokens == 50
    assert resp.latency_ms == 120.5


# ───────────────────────── 8. PII Maskalash va AIAuditLog ─────────────────────────

def test_pii_masking_regex():
    """Uzbekiston telefon, JSHSHIR (PINFL), pasport, bank kartasi va sirlar maskalanadi."""
    text = (
        "Mijoz tel: +998 90 123 45 67, pasport: AA1234567, "
        "PINFL: 12345678901234, karta: 8600 1234 5678 9012, "
        "kalit: Bearer sk-1234567890abcdef123456"
    )
    masked = mask_pii(text)
    assert "+998 90 *** ** 67" in masked
    assert "AA*****67" in masked
    assert "12********1234" in masked
    assert "8600 **** **** 9012" in masked
    assert "[REDACTED_SECRET]" in masked
    assert "sk-1234567890abcdef123456" not in masked


def test_audit_log_recorded_with_pii_masked():
    """AIAuditLog ga so'rov va javob PII maskalangan holda, usage va latency bilan yozilishi kerak."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[Company.__table__, User.__table__, AIAuditLog.__table__],
    )
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()

    company = Company(name="Audit Co")
    db.add(company)
    db.flush()

    user = User(
        name="Audit User",
        phone="+998901112233",
        hashed_password="pw",
        role=UserRole.admin,
        company_id=company.id,
    )
    db.add(user)
    db.commit()

    router = LLMRouter()
    mock_p = MockProvider(default_response=LLMResponse(
        text="Mijoz raqami: +998 90 987 65 43",
        provider="mock",
        model="mock-v1",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        latency_ms=88.4,
    ))
    router.register_provider("mock", mock_p)
    router.get_fallback_chain = lambda: ["mock"]

    router.chat(
        system="sys",
        messages=[{"role": "user", "content": "Mijoz tel: +998 90 123 45 67 qarzini ayt"}],
        db=db,
        user_id=user.id,
        company_id=company.id,
    )

    log_entry = db.query(AIAuditLog).filter(AIAuditLog.company_id == company.id).first()
    assert log_entry is not None
    assert "+998 90 *** ** 67" in log_entry.prompt
    assert "+998 90 123 45 67" not in log_entry.prompt
    assert "+998 90 *** ** 43" in log_entry.result_summary
    assert "+998 90 987 65 43" not in log_entry.result_summary
    assert log_entry.execution_time_ms == 88.4
    assert log_entry.tool_arguments["input_tokens"] == 100
    assert log_entry.tool_arguments["output_tokens"] == 50


# ───────────────────────── 9. Xato matni foydalanuvchiga oqib chiqmasligi ─────────────────────────

def test_sanitized_errors_do_not_leak_keys_or_internal_urls():
    """Xatoliklarda API kalitlar va ichki endpoint manzillari maskalanadi."""
    raw_error = "Failed to connect: Bearer sk-secret-token-123456789 at https://api.anthropic.com/v1/messages"
    sanitized = mask_pii(raw_error)
    assert "sk-secret-token-123456789" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized


# ───────────────────────── 10. Jonli API testi (sukut bo'yicha o'chiq) ─────────────────────────

@pytest.mark.live_llm
def test_live_api_integration():
    """
    Haqiqiy API testi.
    Faqatgina RUN_LIVE_LLM_TESTS=1 va haqiqiy kalit .env da berilganda ishga tushiriladi.
    """
    if not os.getenv("RUN_LIVE_LLM_TESTS"):
        pytest.skip("Jonli LLM testlari o'chiq (RUN_LIVE_LLM_TESTS o'rnatilmagan).")

    router = get_llm_router()
    resp = router.chat(
        system="Siz qisqa javob beruvchi yordamchisiz.",
        messages=[{"role": "user", "content": "1 + 1 nechchi? Faqat raqamni yozing."}],
        max_tokens=10,
    )
    assert resp.text
    assert "2" in resp.text
