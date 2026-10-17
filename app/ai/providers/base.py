"""
app/ai/providers/base.py
────────────────────────
Yagona provayderdan mustaqil LLM interfeysi va ma'lumotlar tuzilmasi.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import re
from typing import Dict, Any, List, Optional


@dataclass
class ToolCall:
    """Yagona provayderdan mustaqil tool (funksiya) chaqiruvi."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class TokenUsage:
    """Token sarfi ko'rsatkichlari."""
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    """Har qanday LLM provayderidan qaytadigan yagona javob formati."""
    text: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    stop_reason: str = "stop"  # "stop", "tool_use", "length", "error", "local_fallback"
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    provider: str = ""
    model: str = ""
    raw_response: Optional[Dict[str, Any]] = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMProvider(ABC):
    """Barcha provayderlar (Anthropic, OpenAI, OpenRouter, Mock) uchun asosiy interfeys."""
    name: str = "base"

    @abstractmethod
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
        """
        Provayder orqali so'rov yuborish.
        - system: tizim prompti
        - messages: ichki formatdagi xabarlar ro'yxati:
          * {"role": "user", "content": "..."}
          * {"role": "assistant", "content": "...", "tool_calls": [...]}
          * {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}
        - tools: ichki formatdagi tool sxemalari:
          * [{"name": "...", "description": "...", "parameters": {...}}]
        """
        pass


# ───────────────────────── Shaxsiy ma'lumotlarni maskalash (PII Masking) ─────────────────────────

_PHONE_RE = re.compile(r"(\+?998[\s\-]?)(\d{2})[\s\-]?(\d{3})[\s\-]?(\d{2})[\s\-]?(\d{2})")
_PINFL_RE = re.compile(r"\b(\d{2})\d{8}(\d{4})\b")
_PASSPORT_RE = re.compile(r"\b([A-Z]{2})\d{5}(\d{2})\b")
_CARD_RE = re.compile(r"\b(8600|9860|5440|4\d{3})[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?(\d{4})\b")
_SECRET_RE = re.compile(r"(bearer\s+[A-Za-z0-9_\-\.]{15,}|sk\-[A-Za-z0-9_\-]{15,})", re.IGNORECASE)


def mask_pii(text: str) -> str:
    """Audit loglar va xatolarda foydalanuvchilarning shaxsiy ma'lumotlarini maskalaydi."""
    if not text or not isinstance(text, str):
        return text

    # Telefon raqamlari (+998 90 *** 67)
    masked = _PHONE_RE.sub(r"\1\2 *** ** \5", text)
    # JSHSHIR (PINFL 14 xonali -> 12***3456)
    masked = _PINFL_RE.sub(r"\1********\2", masked)
    # Pasport (AA1234567 -> AA*****67)
    masked = _PASSPORT_RE.sub(r"\1*****\2", masked)
    # Karta raqamlari (8600 **** **** 1234)
    masked = _CARD_RE.sub(r"\1 **** **** \2", masked)
    # API token va sirlar
    masked = _SECRET_RE.sub("[REDACTED_SECRET]", masked)

    return masked
