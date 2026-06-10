"""Structured-block → markdown renderer.

Authoritative spec: `contexthub/docs/renderer-spec.md`.
MUST produce byte-identical output to `ts/src/renderer.ts` for every valid
StructuredBlockV0. Golden fixtures in `fixtures/structured-blocks/` enforce this.
"""

from __future__ import annotations

import unicodedata

from .models import StructuredBlockV0

EM_DASH = "\u2014"


def render_structured_block(block: StructuredBlockV0) -> str:
    sections: list[str] = []

    if block.decisions:
        body = ""
        for d in block.decisions:
            body += f"- **{d.title}** {EM_DASH} {d.rationale}\n"
        sections.append("## Decisions\n\n" + body)

    if block.artifacts:
        body = ""
        for i, a in enumerate(block.artifacts):
            if i > 0:
                body += "\n"
            body += f"### {a.name} ({a.kind})\n"
            body += "```" + (a.language or "") + "\n"
            body += a.body
            if not a.body.endswith("\n"):
                body += "\n"
            body += "```\n"
        sections.append("## Artifacts\n\n" + body)

    if block.open_questions:
        body = ""
        for q in block.open_questions:
            body += f"- {q.question}\n"
            if q.context:
                body += f"  _Context: {q.context}_\n"
        sections.append("## Open Questions\n\n" + body)

    if block.assumptions:
        body = ""
        for a in block.assumptions:
            body += f"- {a}\n"
        sections.append("## Assumptions\n\n" + body)

    if block.constraints:
        body = ""
        for c in block.constraints:
            body += f"- {c}\n"
        sections.append("## Constraints\n\n" + body)

    if not sections:
        return ""

    out = "\n".join(sections)
    out = out.rstrip("\n") + "\n"
    return unicodedata.normalize("NFC", out)
