from __future__ import annotations

import json
from pathlib import Path

import jsonschema


def test_conversation_fixtures_validate_against_schema(
    conversation_schema: dict, conversation_fixture_paths: list[Path]
) -> None:
    validator = jsonschema.Draft202012Validator(conversation_schema)
    for path in conversation_fixture_paths:
        obj = json.loads(path.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(obj), key=lambda e: e.path)
        assert not errors, f"{path.name}: {[e.message for e in errors]}"


def test_structured_block_fixtures_validate_against_schema(
    structured_block_schema: dict, structured_block_fixture_paths: list[Path]
) -> None:
    validator = jsonschema.Draft202012Validator(structured_block_schema)
    for path in structured_block_fixture_paths:
        obj = json.loads(path.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(obj), key=lambda e: e.path)
        assert not errors, f"{path.name}: {[e.message for e in errors]}"
