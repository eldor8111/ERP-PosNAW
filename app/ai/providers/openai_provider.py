"""
app/ai/providers/openai_provider.py
───────────────────────────────────
OpenAI Chat Completions API provayder adapteri.
"""
import json
import time
from typing import Dict, Any, List, Optional
import requests

from app.ai.providers.base import LLMProvider, LLMResponse, ToolCall, TokenUsage


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o-mini",
        extra_headers: Optional[Dict[str, str]] = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.extra_headers = extra_headers or {}

    def _convert_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None

        openai_tools = []
        for t in tools:
            # Agar allaqachon type: function formatida bo'lsa
            if "type" in t and "function" in t:
                openai_tools.append(t)
            else:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                    }
                })
        return openai_tools

    def _convert_messages(self, system: str, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        openai_msgs: List[Dict[str, Any]] = []

        if system:
            openai_msgs.append({"role": "system", "content": system})

        for m in messages:
            role = m.get("role")
            content = m.get("content")

            if role in ("user", "system"):
                openai_msgs.append({"role": role, "content": content or ""})

            elif role == "assistant":
                msg_dict: Dict[str, Any] = {"role": "assistant", "content": content or None}
                tool_calls = m.get("tool_calls") or []
                if tool_calls:
                    converted_tc = []
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            tc_id = tc.get("id") or tc.get("tool_call_id", "")
                            tc_name = tc.get("name", "")
                            tc_args = tc.get("arguments", {})
                        else:  # ToolCall
                            tc_id = tc.id
                            tc_name = tc.name
                            tc_args = tc.arguments

                        args_str = json.dumps(tc_args, ensure_ascii=False) if isinstance(tc_args, dict) else str(tc_args)
                        converted_tc.append({
                            "id": tc_id,
                            "type": "function",
                            "function": {
                                "name": tc_name,
                                "arguments": args_str,
                            }
                        })
                    msg_dict["tool_calls"] = converted_tc
                openai_msgs.append(msg_dict)

            elif role == "tool":
                tc_id = m.get("tool_call_id") or m.get("id", "")
                res_content = m.get("content", "")
                if isinstance(res_content, (dict, list)):
                    res_content = json.dumps(res_content, ensure_ascii=False)
                else:
                    res_content = str(res_content)

                openai_msgs.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": res_content,
                })

        return openai_msgs

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
        model = model or self.default_model
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        payload: Dict[str, Any] = {
            "model": model,
            "messages": self._convert_messages(system, messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        converted_tools = self._convert_tools(tools)
        if converted_tools:
            payload["tools"] = converted_tools

        start_t = time.time()
        timeout = timeout_sec or 30

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        latency_ms = (time.time() - start_t) * 1000
        resp.raise_for_status()
        data = resp.json()

        choices = data.get("choices") or []
        first_choice = choices[0] if choices else {}
        msg = first_choice.get("message") or {}

        text_content = msg.get("content") or ""
        tool_calls: List[ToolCall] = []

        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args_dict = json.loads(raw_args)
                except Exception:
                    args_dict = {}
            elif isinstance(raw_args, dict):
                args_dict = raw_args
            else:
                args_dict = {}

            tool_calls.append(ToolCall(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                arguments=args_dict,
            ))

        finish_reason = first_choice.get("finish_reason")
        stop_reason = "tool_use" if finish_reason in ("tool_calls", "function_call") else "stop"

        usage_data = data.get("usage") or {}
        usage = TokenUsage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        return LLMResponse(
            text=text_content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
            latency_ms=latency_ms,
            provider=self.name,
            model=model,
            raw_response=data,
        )
