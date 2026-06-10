from __future__ import annotations

import json
import re
from dataclasses import dataclass

from contexthub_interchange.models import ConversationV0


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+")
HEX_RE = re.compile(r"\b[a-fA-F0-9]{32,}\b")
API_KEY_RE = re.compile(r"\b(sk|rk|pk)_[A-Za-z0-9]{16,}\b")


@dataclass(slots=True)
class ScrubResult:
    flagged: bool
    findings: list[str]


def scrub_sensitive_patterns(conversation: ConversationV0) -> ScrubResult:
    findings: list[str] = []
    payload = json.dumps(conversation.model_dump(mode="json"))
    if EMAIL_RE.search(payload):
        findings.append("email")
    if JWT_RE.search(payload):
        findings.append("jwt")
    if HEX_RE.search(payload):
        findings.append("long_hex")
    if API_KEY_RE.search(payload):
        findings.append("api_key_shape")
    return ScrubResult(flagged=bool(findings), findings=findings)

