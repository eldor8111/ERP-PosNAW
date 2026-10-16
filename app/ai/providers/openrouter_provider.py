"""
app/ai/providers/openrouter_provider.py
───────────────────────────────────────
OpenRouter API provayder adapteri (OpenAI bilan mos).
"""
from typing import Dict, Any, List, Optional
from app.ai.providers.openai_provider import OpenAIProvider


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://openrouter.ai/api/v1",
        default_model: str = "cohere/north-mini-code:free",
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        combined_headers = {
            "HTTP-Referer": "https://ecode.uz",
            "X-Title": "Ecode ERP Copilot",
            **(extra_headers or {}),
        }
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            extra_headers=combined_headers,
        )
