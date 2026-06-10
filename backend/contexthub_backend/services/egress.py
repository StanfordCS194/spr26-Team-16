from __future__ import annotations


def sanitize_egress_markdown(payload: str, *, max_chars: int = 120_000) -> str:
    cleaned = payload.replace("\x00", "").strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars].rstrip() + "\n\n[truncated]"
    return cleaned + ("\n" if not cleaned.endswith("\n") else "")
