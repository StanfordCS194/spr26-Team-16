from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from contexthub_interchange import ConversationV0, StructuredBlockV0


def test_conversation_fixtures_parse(conversation_fixture_paths: list[Path]) -> None:
    assert conversation_fixture_paths, "expected at least one conversation fixture"
    for path in conversation_fixture_paths:
        obj = json.loads(path.read_text(encoding="utf-8"))
        ConversationV0.model_validate(obj)


def test_structured_block_fixtures_parse(structured_block_fixture_paths: list[Path]) -> None:
    assert structured_block_fixture_paths, "expected at least one structured-block fixture"
    for path in structured_block_fixture_paths:
        obj = json.loads(path.read_text(encoding="utf-8"))
        StructuredBlockV0.model_validate(obj)


def test_roundtrip_preserves_shape(structured_block_fixture_paths: list[Path]) -> None:
    for path in structured_block_fixture_paths:
        obj = json.loads(path.read_text(encoding="utf-8"))
        block = StructuredBlockV0.model_validate(obj)
        roundtripped = json.loads(block.model_dump_json(exclude_none=True))
        # Ordering of optional None keys may differ, but non-null keys must roundtrip.
        for k, v in obj.items():
            assert roundtripped[k] == v, f"roundtrip mismatch on {k} in {path.name}"


def test_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StructuredBlockV0.model_validate(
            {
                "spec_version": "ch.v0.1",
                "decisions": [],
                "artifacts": [],
                "open_questions": [],
                "assumptions": [],
                "constraints": [],
                "surprise": "hello",
            }
        )


def test_rejects_wrong_spec_version() -> None:
    with pytest.raises(ValidationError):
        StructuredBlockV0.model_validate(
            {
                "spec_version": "ch.v0.2",
                "decisions": [],
                "artifacts": [],
                "open_questions": [],
                "assumptions": [],
                "constraints": [],
            }
        )


def test_artifact_kind_enum() -> None:
    with pytest.raises(ValidationError):
        StructuredBlockV0.model_validate(
            {
                "spec_version": "ch.v0.1",
                "decisions": [],
                "artifacts": [{"kind": "spreadsheet", "name": "x", "body": ""}],
                "open_questions": [],
                "assumptions": [],
                "constraints": [],
            }
        )
