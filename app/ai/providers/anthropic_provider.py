"""
app/ai/providers/anthropic_provider.py
──────────────────────────────────────
Anthropic Messages API provayder adapteri.
System parametrini alohida uzatadi, tool_use va tool_result bloklarini o'giradi,
va ixtiyoriy prompt caching (ephemeral) ni qo'llab-quvvatlaydi.
"""
import json
import time
from typing import Dict, Any, List, Optional
import requests

from app.ai.providers.base import LLMProvider, LLMResponse, ToolCall, TokenUsage


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.anthropic.com/v1",
        prompt_caching: bool = False,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.prompt_caching = prompt_caching

    def _convert_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None

        anthropic_tools = []
        for t in tools:
            tool_def = {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "input_schema": t.get("parameters") or {"type": "object", "properties": {}},
            }
            anthropic_tools.append(tool_def)

        # Prompt caching yoqilgan bo'lsa, oxirgi tool'ga cache_control qo'shamiz
        if self.prompt_caching and anthropic_tools:
            anthropic_tools[-1]["cache_control"] = {"type": "ephemeral"}

        return anthropic_tools

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        anthropic_msgs: List[Dict[str, Any]] = []

        for m in messages:
            role = m.get("role")
            content = m.get("content")

            if role == "user":
                anthropic_msgs.append({"role": "user", "content": content or ""})

            elif role == "assistant":
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                tool_calls = m.get("tool_calls") or []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = tc.get("id") or tc.get("tool_call_id", "")
                        tc_name = tc.get("name", "")
                        tc_args = tc.get("arguments", {})
                    else:  # ToolCall obyekti
                        tc_id = tc.id
                        tc_name = tc.name
                        tc_args = tc.arguments
                    blocks.append({
                        "type": "tool_use",
                        "id": tc_id,
                        "name": tc_name,
                        "input": tc_args,
                    })
                anthropic_msgs.append({"role": "assistant", "content": blocks if blocks else ""})

            elif role == "tool":
                # Anthropic tool_result larni "user" roli ichida qabul qiladi
                tc_id = m.get("tool_call_id") or m.get("id", "")
                res_content = m.get("content", "")
                if isinstance(res_content, (dict, list)):
                    res_content = json.dumps(res_content, ensure_ascii=False)
                else:
                    res_content = str(res_content)

                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": tc_id,
                    "content": res_content,
                }

                # Agar oldingi xabar allaqachon user bo'lsa va unda tool_result lar bo'lsa, birlashtiramiz
                if anthropic_msgs and anthropic_msgs[-1]["role"] == "user" and isinstance(anthropic_msgs[-1]["content"], list):
                    anthropic_msgs[-1]["content"].append(tool_result_block)
                else:
                    anthropic_msgs.append({"role": "user", "content": [tool_result_block]})

        return anthropic_msgs

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
        model = model or "claude-3-5-sonnet-20241022"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if self.prompt_caching:
            headers["anthropic-beta"] = "prompt-caching-2024-07-31"

        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._convert_messages(messages),
        }

        # System prompt
        if system:
            if self.prompt_caching:
                payload["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            else:
                payload["system"] = system

        converted_tools = self._convert_tools(tools)
        if converted_tools:
            payload["tools"] = converted_tools

        start_t = time.time()
        timeout = timeout_sec or 30

        resp = requests.post(
            f"{self.base_url}/messages",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        latency_ms = (time.time() - start_t) * 1000
        resp.raise_for_status()
        data = resp.json()

        # Parse Anthropic response
        text_parts = []
        tool_calls: List[ToolCall] = []

        for block in data.get("content", []):
            b_type = block.get("type")
            if b_type == "text":
                text_parts.append(block.get("text", ""))
            elif b_type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=block.get("input") or {},
                ))

        raw_stop = data.get("stop_reason")
        stop_reason = "tool_use" if raw_stop == "tool_use" else "stop"

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
        )

        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            latency_ms=latency_ms,
            provider="anthropic",
            model=model,
            raw_response=data,
        )
