"""CLI entry points:

- `ch-validate <file>`        validate a JSON file against a ch.v0.1 schema.
- `ch-golden [--write]`       regenerate or verify golden .expected.md fixtures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Literal

import jsonschema
import typer
from pydantic import ValidationError

from .models import ConversationV0, StructuredBlockV0
from .renderer import render_structured_block

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = PACKAGE_ROOT / "schemas"
FIXTURES_DIR = PACKAGE_ROOT / "fixtures"


def _load_schema(kind: Literal["conversation", "structured-block"]) -> dict:
    path = SCHEMAS_DIR / f"ch.v0.1.{kind}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _detect_kind(obj: dict) -> Literal["conversation", "structured-block"]:
    if "messages" in obj and "source" in obj:
        return "conversation"
    if "decisions" in obj and "constraints" in obj:
        return "structured-block"
    raise typer.BadParameter(
        "Cannot detect schema kind from payload. Pass --schema explicitly."
    )


validate_app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Validate a ch.v0.1 JSON file."
)


@validate_app.command()
def validate(
    file: Path = typer.Argument(..., exists=True, readable=True),
    schema: str | None = typer.Option(
        None, "--schema", "-s", help="conversation | structured-block (auto-detect if omitted)"
    ),
) -> None:
    """Validate FILE against the appropriate ch.v0.1 schema."""
    obj = json.loads(file.read_text(encoding="utf-8"))
    kind: Literal["conversation", "structured-block"]
    if schema is None:
        kind = _detect_kind(obj)
    else:
        if schema not in ("conversation", "structured-block"):
            raise typer.BadParameter("--schema must be 'conversation' or 'structured-block'")
        kind = schema  # type: ignore[assignment]

    schema_doc = _load_schema(kind)
    jsonschema.Draft202012Validator(schema_doc).validate(obj)

    if kind == "conversation":
        ConversationV0.model_validate(obj)
    else:
        StructuredBlockV0.model_validate(obj)

    typer.echo(f"ok: {file} validates against ch.v0.1 {kind}")


golden_app = typer.Typer(
    add_completion=False, no_args_is_help=False, help="Regenerate structured-block golden .expected.md fixtures."
)


@golden_app.command()
def golden(
    write: bool = typer.Option(False, "--write", help="Write expected.md files; otherwise dry-run + diff."),
) -> None:
    """Regenerate `<name>.expected.md` for every structured-block fixture.

    Without --write, prints which files would change and exits 1 if any would.
    """
    fixtures_dir = FIXTURES_DIR / "structured-blocks"
    if not fixtures_dir.is_dir():
        typer.echo(f"no fixtures dir: {fixtures_dir}", err=True)
        raise typer.Exit(code=1)

    drift = False
    for json_path in sorted(fixtures_dir.glob("*.json")):
        expected_path = json_path.with_suffix(".expected.md")
        try:
            obj = json.loads(json_path.read_text(encoding="utf-8"))
            block = StructuredBlockV0.model_validate(obj)
        except ValidationError as e:
            typer.echo(f"invalid fixture {json_path}: {e}", err=True)
            raise typer.Exit(code=1) from e

        rendered = render_structured_block(block)
        current = expected_path.read_text(encoding="utf-8") if expected_path.exists() else None

        if current != rendered:
            drift = True
            if write:
                expected_path.write_text(rendered, encoding="utf-8")
                typer.echo(f"wrote {expected_path.relative_to(PACKAGE_ROOT)}")
            else:
                typer.echo(f"drift: {expected_path.relative_to(PACKAGE_ROOT)}", err=True)

    if drift and not write:
        typer.echo("Run `uv run ch-golden --write` to regenerate.", err=True)
        raise typer.Exit(code=1)
    if not drift:
        typer.echo("golden fixtures up to date" if not write else "no changes needed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "golden":
        sys.argv.pop(1)
        golden_app()
    else:
        validate_app()
