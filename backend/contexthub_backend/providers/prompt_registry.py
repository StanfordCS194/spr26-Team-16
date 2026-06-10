from __future__ import annotations

from contexthub_backend.providers.registry import get_prompt

PROMPTS = {"summarize_v1": get_prompt("summarize_v1")}

__all__ = ["PROMPTS", "get_prompt"]

