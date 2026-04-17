# ContextHub

Version control for LLM-assisted knowledge work. Push completed conversations to a repository, search them semantically, pull context back into new ones.

Design docs live in [`docs/`](./docs):

- [`ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — system design, data model, modules, API.
- [`PLAN.md`](./docs/PLAN.md) — scope, decisions log, risks, parking lot.
- [`TODO.md`](./docs/TODO.md) — pre-launch checklist, active work, next up.
- [`VALIDATION.md`](./docs/VALIDATION.md) — append-only log of per-module test/validation results.
- [`renderer-spec.md`](./docs/renderer-spec.md) — byte-level contract for the structured-block markdown renderer.

Packages:

- [`packages/interchange-spec`](./packages/interchange-spec) — `ch.v0.1` JSON Schema + Pydantic + TS types + markdown renderer (Py + TS).
- [`packages/shared-types`](./packages/shared-types) — generated TS types consumed by extension + dashboard.

ContextHub shares its design philosophy with the XARPA team project at the repo root; the two are the same effort under different names (product vs. team).
