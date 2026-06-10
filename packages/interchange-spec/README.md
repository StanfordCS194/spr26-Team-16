# @contexthub/interchange-spec · `ch.v0.1`

The portable-conversation format for ContextHub. Single source of truth for:

- **JSON Schema** in `schemas/` (authoritative)
- **Pydantic models** in `python/contexthub_interchange/models.py` (generated)
- **TypeScript types** in `src/models.ts` (generated)
- **Structured-block markdown renderer** in both languages, byte-identical (enforced by golden tests)

## Layout

```
schemas/                           JSON Schemas (source of truth)
fixtures/
  conversations/                   5 representative conversation fixtures
  structured-blocks/               10 structured-block fixtures + .expected.md pairs
src/                               TypeScript package
  models.ts                        (generated) TS types
  renderer.ts                      TS markdown renderer
  ajv.ts                           runtime JSON Schema validators
  index.ts                         package entry
scripts/codegen.mjs                regenerates src/models.ts via json-schema-to-typescript
tests/*.test.ts                    vitest suites
python/                            Python package (uv workspace member)
  contexthub_interchange/
    models.py                      (generated) Pydantic models
    renderer.py                    Py markdown renderer
    cli.py                         ch-validate + ch-golden CLIs
  tests/*.py                       pytest suites
```

## Invariants

- `docs/renderer-spec.md` is the byte-level contract for the structured-block renderer.
- Every structured-block fixture has a committed `<name>.expected.md`. Both Py and TS renderers must produce bytes matching this file. Any drift fails CI.
- The `pnpm run codegen` + `datamodel-code-generator` outputs must match the committed model files. Any drift fails CI.

## Common tasks

Regenerate generated files:

```
pnpm --filter @contexthub/interchange-spec run codegen        # TS models
uv run datamodel-codegen --input schemas/ch.v0.1.structured-block.json \
    --output python/contexthub_interchange/models.py           # Py models (see codegen script)
```

Regenerate golden fixtures (do this only if you intentionally changed the renderer spec):

```
uv run ch-golden --write
```

Validate a JSON file against the schema:

```
uv run ch-validate path/to/file.json
```

Run tests:

```
pnpm --filter @contexthub/interchange-spec run test            # TS
uv run --package contexthub-interchange pytest                 # Py
```
