from __future__ import annotations

import time
from typing import Literal

import httpx

from contexthub_backend.providers.base import (
    EmbeddingProvider,
    EmbeddingResponse,
    LLMProvider,
    LLMResponse,
)
from contexthub_backend.providers.registry import get_prompt


class VercelGatewayLLMProvider(LLMProvider):
    """OpenAI-compatible LLM provider backed by Vercel AI Gateway."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        prompt_version: str = "summarize_v1",
        json_mode: bool = False,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._prompt_version = prompt_version
        self._json_mode = json_mode

    async def complete(
        self,
        prompt: str,
        *,
        response_format: Literal["json", "text"] = "json",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse:
        started = time.perf_counter()
        system = get_prompt(self._prompt_version)
        format_instructions = (
            "\nReturn strict JSON only." if response_format == "json" else "\nReturn plain text."
        )
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system + format_instructions},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format == "json" and self._json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=body,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"Vercel AI Gateway chat request failed "
                    f"({response.status_code}): {response.text}"
                ) from exc
            payload = response.json()

        usage = payload.get("usage", {})
        choice = payload.get("choices", [{}])[0]
        message = choice.get("message", {})
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LLMResponse(
            text=message.get("content", ""),
            model=self._model,
            prompt_version=self._prompt_version,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            cost_usd=0.0,
        )


def _resize_vector(vector: list[float], target_dimensions: int | None) -> list[float]:
    if target_dimensions is None or len(vector) == target_dimensions:
        return vector
    if len(vector) > target_dimensions:
        return vector[:target_dimensions]
    return [*vector, *([0.0] * (target_dimensions - len(vector)))]


class VercelGatewayEmbeddingProvider(EmbeddingProvider):
    """OpenAI-compatible embedding provider backed by Vercel AI Gateway."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        target_dimensions: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._target_dimensions = target_dimensions

    async def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"] = "document",
    ) -> EmbeddingResponse:
        _ = input_type
        started = time.perf_counter()
        body = {"model": self._model, "input": texts}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self._base_url}/embeddings",
                headers=headers,
                json=body,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"Vercel AI Gateway embedding request failed "
                    f"({response.status_code}): {response.text}"
                ) from exc
            payload = response.json()

        vectors = [
            _resize_vector(item["embedding"], self._target_dimensions)
            for item in payload.get("data", [])
        ]
        usage_tokens = int(payload.get("usage", {}).get("total_tokens", 0))
        latency_ms = int((time.perf_counter() - started) * 1000)
        return EmbeddingResponse(
            vectors=vectors,
            model=self._model,
            input_tokens=usage_tokens,
            latency_ms=latency_ms,
            cost_usd=0.0,
        )
