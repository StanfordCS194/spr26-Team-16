from __future__ import annotations

import json
from pathlib import Path

import pytest

from contexthub_interchange import StructuredBlockV0, render_structured_block


@pytest.fixture(scope="session")
def structured_block_fixture_pairs(
    structured_block_fixture_paths: list[Path],
) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for json_path in structured_block_fixture_paths:
        expected = json_path.with_suffix(".expected.md")
        assert expected.exists(), f"missing golden for {json_path.name}"
        pairs.append((json_path, expected))
    return pairs


def test_all_structured_blocks_have_golden(
    structured_block_fixture_pairs: list[tuple[Path, Path]],
) -> None:
    assert len(structured_block_fixture_pairs) >= 10, (
        "expected at least 10 structured-block fixtures per Module 1 scope"
    )


def test_python_renderer_matches_golden(
    structured_block_fixture_pairs: list[tuple[Path, Path]],
) -> None:
    for json_path, expected_path in structured_block_fixture_pairs:
        obj = json.loads(json_path.read_text(encoding="utf-8"))
        block = StructuredBlockV0.model_validate(obj)
        rendered = render_structured_block(block)
        expected = expected_path.read_text(encoding="utf-8")
        assert rendered == expected, (
            f"golden mismatch for {json_path.name}\n"
            f"  expected bytes: {expected!r}\n"
            f"  actual bytes:   {rendered!r}"
        )
