"""
app/ai/providers/mock_provider.py
─────────────────────────────────
Testlar uchun soxta (mock) LLM provayderi. Tarmoqqa chiqmaydi,
skriptlangan javoblarni navbat bo'yicha qaytaradi va chaqiruvlarni qayd qiladi.
"""
from typing import Dict, Any, List, Optional
from app.ai.providers.base import LLMProvider, LLMResponse, ToolCall, TokenUsage


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, default_response: Optional[LLMResponse] = None):
        self.default_response = default_response or LLMResponse(
            text="Mock javob: test muvaffaqiyatli.",
            provider="mock",
            model="mock-model",
            usage=TokenUsage(input_tokens=10, output_tokens=15),
            latency_ms=5.0,
            stop_reason="stop",
        )
        self.response_queue: List[Any] = []  # LLMResponse yoki Exception
        self.recorded_calls: List[Dict[str, Any]] = []

    def queue_response(self, response_or_exception: Any) -> None:
        """Keyingi chaqiruv uchun javob yoki xatolikni navbatga qo'shadi."""
        self.response_queue.append(response_or_exception)

    def clear(self) -> None:
        """Navbat va chaqiruvlar tarixini tozalaydi."""
        self.response_queue.clear()
        self.recorded_calls.clear()

    def chat(
        self,
        system: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout_sec: Optional[int] = None,
    ) -> LLMResponse:
        call_info = {
            "system": system,
            "messages": messages,
            "tools": tools,
            "model": model or "mock-model",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout_sec": timeout_sec,
        }
        self.recorded_calls.append(call_info)

        if self.response_queue:
            item = self.response_queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        # Standart javob
        return self.default_response
