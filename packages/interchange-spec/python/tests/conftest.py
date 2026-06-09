from __future__ import annotations

import json
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1].parent
SCHEMAS_DIR = PACKAGE_ROOT / "schemas"
FIXTURES_DIR = PACKAGE_ROOT / "fixtures"


@pytest.fixture(scope="session")
def conversation_schema() -> dict:
    return json.loads((SCHEMAS_DIR / "ch.v0.1.conversation.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def structured_block_schema() -> dict:
    return json.loads((SCHEMAS_DIR / "ch.v0.1.structured-block.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def conversation_fixture_paths() -> list[Path]:
    return sorted((FIXTURES_DIR / "conversations").glob("*.json"))


@pytest.fixture(scope="session")
def structured_block_fixture_paths() -> list[Path]:
    return sorted((FIXTURES_DIR / "structured-blocks").glob("*.json"))
