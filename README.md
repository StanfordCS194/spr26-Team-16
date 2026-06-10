# spr26-Team-16 (XARPA)

**Team Wiki (landing page for the Wiki tab):** (https://github.com/StanfordCS194/spr26-Team-16/wiki)

## Project synopsis

We are building a **GitHub-aligned context layer** for **enterprise-scale LLM use**: a shared organizational layer that helps route questions to the right knowledge and code context so teams get **faster, grounded answers**—a **meta-LLM** substrate reusable across assistants and workflows.

The product implementation in this repo is **ContextHub**: version control for
LLM-assisted knowledge work. Push completed conversations to a repository, search
them semantically, and pull context back into new ones.

## Source for Wiki content

The Wiki **Home** page markdown lives in the wiki tab (including team name, logo, theme music, member matrix, and communication links). After you merge to `main`, paste or sync that file to the GitHub Wiki **Home** page so the Wiki tab matches version-controlled content.

## Team

**XARPA** — see the Wiki for logo, theme music, roster, and contact emails.

**Cici Hou** - SCWG
**Romina Jately** - SCWG
**Abhiraj Gupta** - SCWG
**Phillip Miao** - SCWG

---

# ContextHub (product)

A monorepo: a FastAPI backend with a background worker, a Next.js dashboard, and
a Manifest V3 Chrome extension that adds a sidebar to `claude.ai`. Auth is
Supabase Google OAuth; conversations are summarized and embedded for semantic
search.

## Getting started

**→ Follow [`docs/SETUP.md`](./docs/SETUP.md)** for full, step-by-step local
setup (prerequisites, Supabase provisioning, env files, migrations, building the
extension, running the stack, and troubleshooting).

Quick start once prerequisites are installed:

```bash
pnpm install            # Node workspace
uv sync                 # Python workspace (exact locked versions — don't use pip)

# configure env files (see docs/SETUP.md §5)
cp backend/.env_sample backend/.env
cp packages/dashboard/.env.local.example packages/dashboard/.env.local
cp packages/extension/.env.example packages/extension/.env

cd backend && uv run python -m alembic upgrade head && cd ..   # migrations

# run (separate terminals)
cd backend && uv run uvicorn contexthub_backend.api.app:create_app --factory --port 8765
cd backend && uv run python -c "from contexthub_backend.jobs.worker import start_worker; start_worker()"
pnpm dashboard:dev      # http://localhost:3001
pnpm extension:build    # load packages/extension/dist as an unpacked extension
```

## Repository layout

| Path | What |
|------|------|
| [`backend/`](./backend) | FastAPI service: auth, pushes/pulls/search routes, embeddings + LLM summaries, arq worker, alembic migrations |
| [`packages/extension/`](./packages/extension) | MV3 Chrome extension (Vite + React) for the `claude.ai` sidebar |
| [`packages/dashboard/`](./packages/dashboard) | Next.js dashboard (workspaces, tokens, search) |
| [`packages/interchange-spec/`](./packages/interchange-spec) | `ch.v0.1` JSON Schema + Pydantic + TS types + markdown renderer |
| [`packages/shared-types/`](./packages/shared-types) | generated TS types shared by the frontends |
| [`docs/`](./docs) | design docs and guides |

## Documentation

- [`docs/SETUP.md`](./docs/SETUP.md) — **local setup guide (start here)**.
- [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) — system design, data model, modules, API.
- [`docs/PRD.md`](./docs/PRD.md) — product requirements.
- [`docs/PLAN.md`](./docs/PLAN.md) — scope, decisions log, risks.
- [`docs/TODO.md`](./docs/TODO.md) — checklist and active work.
- [`docs/VALIDATION.md`](./docs/VALIDATION.md) — per-module test/validation log.
- [`docs/LOCAL_SYSTEM_TEST.md`](./docs/LOCAL_SYSTEM_TEST.md) — end-to-end verification queries.
- [`docs/START_FROM_SCRATCH.md`](./docs/START_FROM_SCRATCH.md) — fully-local Docker bootstrap.
- [`docs/renderer-spec.md`](./docs/renderer-spec.md) — structured-block markdown renderer contract.

## Development

```bash
pnpm test            # JS/TS package tests
pnpm typecheck       # TS typechecking across packages
cd backend && uv run pytest    # backend tests
```
