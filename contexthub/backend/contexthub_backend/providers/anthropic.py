from __future__ import annotations

import time
from typing import Literal

import httpx

from contexthub_backend.providers.base import LLMProvider, LLMResponse
from contexthub_backend.providers.registry import get_prompt


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        prompt_version: str = "summarize_v1",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._prompt_version = prompt_version

    async def complete(
        self,
        prompt: str,
        *,
        response_format: Literal["json", "text"] = "json",
        max_tokens: int = 1600,
        temperature: float = 0.0,
    ) -> LLMResponse:
        started = time.perf_counter()
        system = get_prompt(self._prompt_version)
        format_instructions = (
            "\nReturn strict JSON only." if response_format == "json" else "\nReturn plain text."
        )
        body = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system + format_instructions,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
            )
            response.raise_for_status()
            raw = response.json()
        usage = raw.get("usage", {})
        text = raw.get("content", [{}])[0].get("text", "")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            text=text,
            model=self._model,
            prompt_version=self._prompt_version,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            latency_ms=latency_ms,
            cost_usd=0.0,
        )

