"""The chat model through OpenRouter (OpenAI-compatible), with tool calling.

`models` lists fallbacks: if the first provider fails, OpenRouter tries the next one
inside the same request.
"""

import json
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from portfolio.contexts.assistant.application.ports import (
    Message,
    ModelReply,
    Tier,
    ToolCall,
    ToolSpec,
    Usage,
)

BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 40.0
MAX_TOKENS = 1200
TEMPERATURE = 0.2


class ChatError(RuntimeError):
    """The provider answered, but not with a usable completion."""


def _message(message: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.calls:
        out["content"] = message.content or None
        out["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.calls
        ]
    if message.tool_call_id:
        out["tool_call_id"] = message.tool_call_id
    return out


def _tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": dict(spec.parameters),
        },
    }


class OpenRouterChat:
    def __init__(self, http: httpx.AsyncClient, models: Mapping[Tier, Sequence[str]]) -> None:
        self._http = http
        self._models = models

    @classmethod
    def create(cls, api_key: str, models: Mapping[Tier, Sequence[str]]) -> "OpenRouterChat":
        http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "erickkbonfim.com.br"},
            timeout=TIMEOUT_SECONDS,
        )
        return cls(http, models)

    async def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSpec], tier: Tier
    ) -> ModelReply:
        models = list(self._models[tier])
        body: dict[str, Any] = {
            "model": models[0],
            "models": models,
            "messages": [_message(m) for m in messages],
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "usage": {"include": True},
            # Reasoning models think briefly: answers here are short and grounded in
            # passages, and long thinking only adds seconds.
            "reasoning": {"effort": "low"},
        }
        if tools:
            body["tools"] = [_tool(spec) for spec in tools]
        response = await self._http.post("/chat/completions", json=body)
        response.raise_for_status()
        data = response.json()
        try:
            choice = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise ChatError(f"no completion in the answer: {str(data)[:200]}") from error
        calls = tuple(
            ToolCall(
                str(call.get("id") or f"call_{index}"),
                str(call["function"]["name"]),
                str(call["function"].get("arguments") or "{}"),
            )
            for index, call in enumerate(choice.get("tool_calls") or [])
        )
        usage = data.get("usage") or {}
        return ModelReply(
            text=str(choice.get("content") or "").strip(),
            calls=calls,
            usage=Usage(
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
                float(usage.get("cost") or 0.0),
            ),
            model=str(data.get("model") or models[0]),
        )

    async def close(self) -> None:
        await self._http.aclose()


def arguments(raw: str) -> dict[str, Any]:
    """Tool arguments as a dict, for traces; an unreadable payload stays a string."""
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"raw": raw}
