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
- [`packages/dashboard`](./packages/dashboard) — Next.js app for workspace/token/search/pull workflows.
- [`packages/extension`](./packages/extension) — MV3 extension for Claude.ai sidebar injection.

ContextHub shares its design philosophy with the XARPA team project at the repo root; the two are the same effort under different names (product vs. team).

## Full Local Stack (Backend + Worker + Dashboard + Extension)

For end-to-end local development (Postgres, Redis, API, worker, dashboard, extension, and verification flow), use:

- [`docs/START_FROM_SCRATCH.md`](./docs/START_FROM_SCRATCH.md) - complete bootstrap from a clean machine.
- [`docs/LOCAL_SYSTEM_TEST.md`](./docs/LOCAL_SYSTEM_TEST.md) - end-to-end verification checklist.

Quick start:

```bash
pnpm install
uv sync --all-extras --dev
cd backend
docker compose up -d
```

## Frontend Apps

The frontend apps include:
- A dashboard app (`packages/dashboard`) built with Next.js App Router.
- A Chrome extension app (`packages/extension`) built with React + Manifest V3.

Both apps can run in two ways:
- UI-only mode for quick local iteration.
- End-to-end mode against the local backend stack in [`docs/START_FROM_SCRATCH.md`](./docs/START_FROM_SCRATCH.md).

### Run the dashboard app

```bash
pnpm install
pnpm dashboard:dev
```

Open `http://localhost:3001`.

### Build and load the extension app in Chrome

```bash
pnpm extension:build
```

Then in Chrome:
1. Go to `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select `contexthub/packages/extension/dist`.
5. Visit `https://claude.ai` and click the floating **ContextHub** button.

The extension can be used UI-only, but it also supports real backend push/search/pull when configured with API base URL, workspace ID, and token.

## Troubleshooting

- `Cannot connect to the Docker daemon ...`:
  - Docker Desktop is not running. Start Docker, then rerun `docker compose up -d` from `backend/`.
- `Can't locate revision identified by '...'` during `alembic upgrade head`:
  - Your local Postgres volume has stale migration history from an older branch/version.
  - For local dev reset:
    - `cd backend`
    - `docker compose down -v`
    - `docker compose up -d`
    - rerun `sql/auth_stub.sql` and `alembic upgrade head`.
- `ImportError: email-validator is not installed` when starting API:
  - Sync Python deps from `contexthub/`: `uv sync --all-extras --dev`.
  - If your env is stale, rerun from `contexthub/backend`: `uv run --package contexthub-backend python -m pip install email-validator`.
