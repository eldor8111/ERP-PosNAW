"""
app/ai/providers/router.py
──────────────────────────
LLM provayderlarini boshqarish, marshrutlash (routing), retry va fallback zanjiri.
"""
import logging
import os
import time
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.config import settings
from app.ai.providers.base import LLMProvider, LLMResponse, ToolCall, TokenUsage, mask_pii
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.providers.openrouter_provider import OpenRouterProvider
from app.ai.providers.mock_provider import MockProvider

_log = logging.getLogger("llm_router")


def is_production_env() -> bool:
    """Ilova production rejimida ekanligini tekshiradi."""
    env = (getattr(settings, "ENV", "") or os.getenv("APP_ENV", "") or "").lower()
    return env in ("production", "prod")


class LLMRouter:
    def __init__(self):
        self._providers: Dict[str, LLMProvider] = {}
        self._mock_provider = MockProvider()
        self._init_providers()

    def _init_providers(self) -> None:
        # 1. Mock provayder (testlar uchun)
        self._providers["mock"] = self._mock_provider

        # 2. OpenRouter
        openrouter_key = getattr(settings, "OPENROUTER_API_KEY", "") or os.getenv("OPENROUTER_API_KEY", "")
        self._providers["openrouter"] = OpenRouterProvider(
            api_key=openrouter_key,
            base_url=getattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            default_model=getattr(settings, "LLM_MODEL_MAIN", "cohere/north-mini-code:free"),
        )

        # 3. Anthropic
        anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
        self._providers["anthropic"] = AnthropicProvider(
            api_key=anthropic_key,
            base_url=getattr(settings, "ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
            prompt_caching=getattr(settings, "ANTHROPIC_PROMPT_CACHING", False),
        )

        # 4. OpenAI
        openai_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
        self._providers["openai"] = OpenAIProvider(
            api_key=openai_key,
            default_model=getattr(settings, "LLM_MODEL_MAIN", "gpt-4o-mini"),
        )

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        """Yangi provayderni ro'yxatdan o'tkazish (masalan testlar uchun)."""
        self._providers[name] = provider

    def get_provider(self, name: str) -> Optional[LLMProvider]:
        return self._providers.get(name)

    def resolve_model(self, task_type: str = "general", custom_model: Optional[str] = None) -> str:
        """
        Marshrutlash (routing): vazifa turiga qarab model tanlash.
        - complex, write, action, crud -> LLM_MODEL_MAIN
        - simple, fast, general, chat -> LLM_MODEL_FAST
        """
        if custom_model:
            model = custom_model
        elif task_type in ("complex", "write", "action", "crud", "sales"):
            model = getattr(settings, "LLM_MODEL_MAIN", "cohere/north-mini-code:free")
        else:
            model = getattr(settings, "LLM_MODEL_FAST", "cohere/north-mini-code:free")

        # Production muhitida :free modellarni ogohlantirish (avariya qilmaslik)
        if is_production_env() and ":free" in model.lower():
            _log.warning("':free' model (%s) production rejimida ishlatilmoqda.", model)

        return model

    def get_fallback_chain(self) -> List[str]:
        """Konfiguratsiyadagi fallback zanjirini oladi."""
        raw_chain = getattr(settings, "LLM_FALLBACK_CHAIN", "")
        primary = (getattr(settings, "LLM_PROVIDER", "") or "").strip().lower()
        anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
        openrouter_key = getattr(settings, "OPENROUTER_API_KEY", "") or os.getenv("OPENROUTER_API_KEY", "")
        openai_key = getattr(settings, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")

        chain = []
        if primary and primary in ("anthropic", "openai", "mock"):
            chain.append(primary)
        elif anthropic_key:
            chain.append("anthropic")
        elif primary:
            chain.append(primary)

        if raw_chain:
            for p in raw_chain.split(","):
                p_clean = p.strip().lower()
                if p_clean and p_clean not in chain:
                    if p_clean == "deepseek" and not os.getenv("ENABLE_DEEPSEEK"):
                        continue
                    chain.append(p_clean)

        if anthropic_key and "anthropic" not in chain:
            chain.append("anthropic")
        if openrouter_key and "openrouter" not in chain:
            chain.append("openrouter")
        if openai_key and "openai" not in chain:
            chain.append("openai")

        return chain if chain else ["openrouter"]

    def _execute_with_retry(
        self,
        provider: LLMProvider,
        system: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout_sec: int,
    ) -> LLMResponse:
        """Bitta provayderga retry (eksponensial kutish) bilan so'rov yuborish."""
        max_retries = getattr(settings, "LLM_MAX_RETRIES", 2)
        backoff_factor = getattr(settings, "LLM_RETRY_BACKOFF_FACTOR", 1.5)

        last_err: Optional[Exception] = None
        for attempt in range(max_retries + 1):
            try:
                return provider.chat(
                    system=system,
                    messages=messages,
                    tools=tools,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_sec=timeout_sec,
                )
            except Exception as e:
                last_err = e
                status_code = getattr(getattr(e, "response", None), "status_code", 0)

                # Qayta uriniladigan xatolar: Timeout, 429 (Rate Limit), 5xx (Server Error)
                is_transient = (
                    "timeout" in str(e).lower()
                    or status_code in (429, 500, 502, 503, 504)
                )

                if is_transient and attempt < max_retries:
                    sleep_time = (backoff_factor ** attempt) * 0.5
                    _log.warning(
                        "LLM [%s] urinish %d muvaffaqiyatsiz (%s). %0.1f soniya kutilyapti...",
                        provider.name, attempt + 1, e, sleep_time
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    # 400, 401, 404 yoki urinishlar tugagan bo'lsa qayta urinmaymiz
                    raise e

        if last_err:
            raise last_err
        raise RuntimeError("LLM chaqiruvida kutilmagan xatolik yuz berdi")

    def chat(
        self,
        system: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        task_type: str = "general",
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        allow_local_fallback: bool = True,
        db: Optional[Session] = None,
        user_id: Optional[int] = None,
        company_id: Optional[int] = None,
        conversation_id: Optional[str] = None,
    ) -> LLMResponse:
        """
        Asosiy kirish nuqtasi:
        1. Modelni marshrutlaydi.
        2. Fallback zanjiri bo'yicha provayderlarga murojaat qiladi.
        3. Hammasi ishlamasa mahalliy qoidalarga fallback qiladi (agar allow_local_fallback=True bo'lsa).
        4. Audit log yozadi (PII ni maskalaydi).
        """
        chosen_model = self.resolve_model(task_type=task_type, custom_model=model)
        chain = self.get_fallback_chain()
        timeout_sec = getattr(settings, "LLM_TIMEOUT_SEC", 30)

        errors_log: List[str] = []
        final_response: Optional[LLMResponse] = None

        for prov_name in chain:
            provider = self._providers.get(prov_name)
            if not provider:
                continue

            try:
                final_response = self._execute_with_retry(
                    provider=provider,
                    system=system,
                    messages=messages,
                    tools=tools,
                    model=chosen_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_sec=timeout_sec,
                )
                break  # Muvaffaqiyatli bo'lsa zanjirdan chiqamiz
            except Exception as e:
                sanitized_msg = mask_pii(str(e))
                _log.warning("Provayder [%s] xatosi: %s. Keyingi provayderga o'tiladi.", prov_name, sanitized_msg)
                errors_log.append(f"{prov_name}: {sanitized_msg}")

        # Agar barcha provayderlar ishlamasa
        if not final_response:
            if not allow_local_fallback:
                raise RuntimeError(f"All providers failed: {'; '.join(errors_log)}")
            final_response = self._local_fallback(
                system=system,
                messages=messages,
                db=db,
                company_id=company_id,
                errors=errors_log,
            )

        # Audit logga yozish
        if db and user_id and company_id:
            self._record_audit_log(
                db=db,
                user_id=user_id,
                company_id=company_id,
                conversation_id=conversation_id,
                system=system,
                messages=messages,
                response=final_response,
            )

        return final_response

    def _local_fallback(
        self,
        system: str,
        messages: List[Dict[str, Any]],
        db: Optional[Session],
        company_id: Optional[int],
        errors: List[str],
    ) -> LLMResponse:
        """Tashqi LLM ishlamay qolganda mahalliy qoidalar asosidagi javob."""
        local_text = "⚠️ [Mahalliy tahlil rejimi]: Tashqi AI provayderlari bilan aloqa vaqtincha uzildi."
        if db and company_id:
            try:
                from app.services.ai_service import build_daily_context
                daily_info = build_daily_context(db, company_id)
                local_text += f"\n\nBugungi asosiy ma'lumotlar:\n{daily_info}"
            except Exception as e:
                local_text += f"\n(Mahalliy kontekst olishda xatolik: {mask_pii(str(e))})"

        return LLMResponse(
            text=local_text,
            tool_calls=[],
            stop_reason="local_fallback",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            latency_ms=0.0,
            provider="local",
            model="rule-based",
        )

    def _record_audit_log(
        self,
        db: Session,
        user_id: int,
        company_id: int,
        conversation_id: Optional[str],
        system: str,
        messages: List[Dict[str, Any]],
        response: LLMResponse,
    ) -> None:
        """Har bir LLM chaqiruvini AIAuditLog ga xavfsiz (maskalangan) qayd qiladi."""
        try:
            from app.models.ai_audit import AIAuditLog
            user_msg = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    user_msg = str(m.get("content", ""))
                    break

            masked_prompt = mask_pii(user_msg)
            masked_reply = mask_pii(response.text)

            log_entry = AIAuditLog(
                company_id=company_id,
                user_id=user_id,
                conversation_id=conversation_id or "",
                prompt=masked_prompt[:1000] if masked_prompt else "",
                tool_name=f"llm_chat:{response.provider}:{response.model}",
                tool_arguments={
                    "provider": response.provider,
                    "model": response.model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "stop_reason": response.stop_reason,
                },
                permission="ai.chat",
                risk_level="LOW",
                status="SUCCESS" if response.stop_reason != "error" else "ERROR",
                result_summary=masked_reply[:1000] if masked_reply else "",
                execution_time_ms=response.latency_ms,
            )
            db.add(log_entry)
            db.commit()
        except Exception as e:
            db.rollback()
            _log.warning("Audit log yozishda xatolik: %s", mask_pii(str(e)))


_default_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """Yagona singleton LLMRouter instansiyasini qaytaradi."""
    global _default_router
    if _default_router is None:
        _default_router = LLMRouter()
    return _default_router
