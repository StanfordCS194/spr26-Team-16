# ContextHub — Validation Log

Append-only record of what was validated at the end of each module. Each entry lists the checks run, their results, and anything that looked wrong but was accepted as intentional. This is the living trail of "did we actually prove it works before moving on," captured outside `TODO.md` so it doesn't get buried.

Convention per entry:

- **Header:** `## Module N — <name> · <shipped-date>`
- **Environment** line: tool versions tested against.
- **Checks table:** what was verified, result (pass/fail/skipped), and a short note.
- **Known warnings:** non-blocking noise that we accepted at shipping time.
- **Left for later:** items we deliberately did not validate this pass, with pointers (usually `TODO.md` refs).

---

## Module 1 — `packages/interchange-spec` · 2026-04-17

**Environment:** macOS 14 (Darwin 24.6.0, arm64); Python 3.13.5; Node 18.x; pnpm 10.33.0 (via corepack); uv 0.10.4; TypeScript 5.9.3; Vitest 2.1.9; pytest 9.0.3.

| Check | Result | Note |
| ----- | ------ | ---- |
| Python tests (pytest) | **20 / 20 passing** | `test_models`, `test_validator`, `test_renderer`, `test_golden` |
| TypeScript tests (vitest) | **41 / 41 passing** | `models.test`, `renderer.test`, `golden.test` |
| TypeScript typecheck (`tsc --noEmit`) | clean | strict, `noUncheckedIndexedAccess`, no `any` |
| TS codegen (`pnpm run codegen:ts`) | runs + deterministic | Re-run twice → zero git diff |
| Python codegen (`pnpm run codegen:py`) | runs + deterministic | Re-run twice → zero git diff |
| Golden cross-impl (Py bytes == TS bytes == `*.expected.md`) | **10 / 10 fixtures** | covers: minimal, maximal, empty-lists, unicode/NFC, long-artifact, multiple-artifacts, nested-markdown, missing-optional, single-item, special-chars |
| JSON Schema validation on all 5 conversation fixtures | pass | Draft 2020-12, Py (jsonschema) + TS (ajv) both green |
| JSON Schema validation on all 10 structured-block fixtures | pass | same |
| Pydantic round-trip on all fixtures | pass | `model_dump_json → json.loads → original` shape preserved |
| Rejection tests (wrong spec_version, extra props, unknown artifact kind) | pass | both Py + TS |
| `uv run ch-validate <file>` CLI | works | auto-detects schema kind from payload |
| `uv run ch-golden --write` CLI | works | generates all 10 expected.md files byte-for-byte |

**Known warnings (accepted):**

- `datamodel-code-generator` emits a `FutureWarning` about black/isort → ruff formatter migration on every codegen run. Noise-only; addressable later with `formatters=[Formatter.RUFF_FORMAT, Formatter.RUFF_CHECK]` + the `[ruff]` extra.
- pnpm warns on `esbuild@0.21.5` ignored build scripts. Not a blocker; tests pass. Silence with `pnpm approve-builds` when we touch CI next.

**Left for later:**

- Load / stress / fuzzing tests on the interchange-spec validators → `TODO.md` "Testing & quality (post-v0)".
- Cross-platform fixture corpus (ChatGPT exports, etc.) → `TODO.md` "Backfill import (P1)".
- Auto-detect `schema` kind in `ch-validate` currently uses presence heuristics (`messages + source` → conversation; `decisions + constraints` → structured-block). Adequate for v0; revisit if a future schema breaks the heuristic.

---

<!--
When adding a new module's entry, follow this template:

## Module N — <package-or-module> · YYYY-MM-DD

**Environment:** <tool versions>

| Check | Result | Note |
| ----- | ------ | ---- |
| ... | ... | ... |

**Known warnings (accepted):**
- ...

**Left for later:**
- ...

---
-->
