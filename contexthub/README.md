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
- [`packages/dashboard`](./packages/dashboard) — Next.js visual demo of workspace/token/search flows.
- [`packages/extension`](./packages/extension) — MV3 visual demo extension for Claude.ai sidebar injection.

ContextHub shares its design philosophy with the XARPA team project at the repo root; the two are the same effort under different names (product vs. team).

## Frontend Demo

The frontend demo includes:
- A dashboard mock (`packages/dashboard`) built with Next.js App Router.
- A Chrome extension mock (`packages/extension`) built with React + Manifest V3.

### Run the dashboard demo

```bash
pnpm install
pnpm dashboard:dev
```

Open `http://localhost:3001`.

### Build and load the extension demo in Chrome

```bash
pnpm extension:build
```

Then in Chrome:
1. Go to `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select `contexthub/packages/extension/dist`.
5. Visit `https://claude.ai` and click the floating **ContextHub** button.

The extension is visual-only for demo purposes: no backend calls are required.
