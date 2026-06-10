from __future__ import annotations

import unicodedata

from contexthub_interchange import StructuredBlockV0, render_structured_block


def _block(**overrides):
    base = {
        "spec_version": "ch.v0.1",
        "decisions": [],
        "artifacts": [],
        "open_questions": [],
        "assumptions": [],
        "constraints": [],
    }
    base.update(overrides)
    return StructuredBlockV0.model_validate(base)


def test_empty_block_renders_empty_string() -> None:
    assert render_structured_block(_block()) == ""


def test_single_decision_rendering() -> None:
    block = _block(decisions=[{"title": "Use Postgres", "rationale": "pgvector native"}])
    assert render_structured_block(block) == (
        "## Decisions\n\n- **Use Postgres** \u2014 pgvector native\n"
    )


def test_blank_line_between_sections() -> None:
    block = _block(
        decisions=[{"title": "Ship beta", "rationale": "pressure"}],
        assumptions=["single user"],
    )
    out = render_structured_block(block)
    assert "\n\n## Assumptions\n" in out
    assert out.endswith("- single user\n")


def test_artifacts_preserve_trailing_newline_semantics() -> None:
    block = _block(artifacts=[{"kind": "code", "name": "fn", "body": "print(1)"}])
    out = render_structured_block(block)
    assert "```\nprint(1)\n```\n" in out


def test_artifacts_with_already_trailing_newline() -> None:
    block = _block(artifacts=[{"kind": "code", "name": "fn", "body": "print(1)\n"}])
    out = render_structured_block(block)
    # must not double the trailing newline
    assert "print(1)\n```" in out
    assert "print(1)\n\n```" not in out


def test_artifact_without_language_uses_bare_fence() -> None:
    block = _block(artifacts=[{"kind": "other", "name": "note", "body": "hi"}])
    out = render_structured_block(block)
    assert "```\nhi\n```" in out


def test_open_question_with_and_without_context() -> None:
    block = _block(
        open_questions=[
            {"question": "What cache TTL?", "context": "pulls are hot"},
            {"question": "Unit of concurrency?"},
        ]
    )
    out = render_structured_block(block)
    assert "- What cache TTL?\n  _Context: pulls are hot_\n" in out
    assert "- Unit of concurrency?\n" in out
    # second question must NOT have a context line
    assert "- Unit of concurrency?\n  _Context:" not in out


def test_nfc_normalization_collapses_decomposed_input() -> None:
    decomposed_e = "e\u0301"  # e + COMBINING ACUTE ACCENT
    block = _block(
        assumptions=[f"caf{decomposed_e}"]
    )
    out = render_structured_block(block)
    assert unicodedata.is_normalized("NFC", out)
    assert "caf\u00e9" in out
    assert decomposed_e not in out


def test_output_ends_with_single_newline_when_nonempty() -> None:
    block = _block(constraints=["x"])
    out = render_structured_block(block)
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_empty_list_sections_omitted() -> None:
    block = _block(decisions=[{"title": "T", "rationale": "R"}])
    out = render_structured_block(block)
    assert "## Artifacts" not in out
    assert "## Assumptions" not in out
    assert "## Constraints" not in out
    assert "## Open Questions" not in out
