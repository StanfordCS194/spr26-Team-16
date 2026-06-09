# ContextHub — Local Setup Guide

This guide takes a brand-new machine to a fully running ContextHub stack:
backend API, background worker, dashboard, and the Chrome extension on
`claude.ai`. Read it top to bottom the first time.

There are **two ways** to run the stack:

- **Path A — Supabase-backed (recommended).** Uses a hosted Supabase project
  for Postgres + Auth (real Google sign-in). This is the path the team runs and
  the one verified end-to-end. Start here.
- **Path B — Fully local (Docker).** Uses Docker Postgres + Redis and a dev-auth
  bypass instead of Google. Good for offline backend work. See
  [Appendix: Fully-local Docker path](#appendix-fully-local-docker-path).

---

## 1. Architecture in one minute

```
┌────────────────────┐     ┌────────────────────┐
│  Chrome extension  │     │   Next.js dashboard│
│  (claude.ai side-  │     │   localhost:3001   │
│   bar, MV3)        │     │                    │
└─────────┬──────────┘     └─────────┬──────────┘
          │  Bearer JWT (Supabase)   │
          └────────────┬─────────────┘
                       ▼
            ┌────────────────────────┐
            │   FastAPI backend      │   ← you run this on localhost:8765
            │   /v1/* routes         │
            └───────┬────────┬───────┘
                    │        │
        ┌───────────▼──┐   ┌─▼──────────────┐
        │ Postgres +   │   │ Redis + arq    │
        │ pgvector     │   │ worker (push   │
        │ (Supabase)   │   │ summaries +    │
        │              │   │ embeddings)    │
        └──────────────┘   └────────────────┘
```

- **Auth:** Supabase Google OAuth. The extension and dashboard obtain a Supabase
  JWT; the backend verifies it via the project's JWKS endpoint.
- **Push pipeline:** the extension/dashboard `POST` a conversation; the backend
  stores it and the **worker** generates summary layers + vector embeddings.
- **Search/pull:** vector + keyword search over summaries, then rebuild context
  to inject back into a new conversation.

Monorepo layout:

| Path | What |
|------|------|
| `backend/` | FastAPI service, auth, routes, services, worker, alembic migrations |
| `packages/extension/` | MV3 Chrome extension (Vite + React) |
| `packages/dashboard/` | Next.js dashboard |
| `packages/interchange-spec/` | `ch.v0.1` schema + Pydantic + TS types + renderer |
| `packages/shared-types/` | generated TS types shared by frontends |
| `docs/` | design docs + this guide |

---

## 2. Prerequisites

Install these first:

| Tool | Version | Install |
|------|---------|---------|
| **Node.js** | ≥ 18.18 | https://nodejs.org or `nvm install 18` |
| **pnpm** | 10.x | `corepack enable && corepack prepare pnpm@10.33.0 --activate` |
| **Python** | ≥ 3.12 | https://python.org or `pyenv install 3.12` |
| **uv** | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Google Chrome** | latest | https://google.com/chrome |
| **Docker Desktop** | latest | Only for Path B (fully-local). https://docker.com |

> **Why `uv`?** The Python dependencies are pinned in `uv.lock`. Installing with
> plain `pip` can resolve *different* versions and break startup (we hit exactly
> this — an older FastAPI rejected a `204` route, and `email-validator` was
> missing). Always use `uv sync` so you get the locked versions.

Verify:

```bash
node -v      # v18.18+ (or newer)
pnpm -v      # 10.x
python3 -V   # 3.12+
uv --version
```

---

## 3. Clone and install dependencies

```bash
git clone https://github.com/StanfordCS194/spr26-Team-16.git
cd spr26-Team-16

# Node workspace (extension, dashboard, interchange-spec, shared-types)
pnpm install

# Python workspace (backend + interchange-spec python), exact locked versions
uv sync
```

`uv sync` creates a `.venv/` at the repo root with every backend dependency.

---

## 4. Provision a Supabase project

You can use the **team's shared project** (ask a teammate for the URL + keys) or
create **your own** (recommended for isolated dev). To create your own:

1. Create a project at https://supabase.com/dashboard.
2. **Enable the pgvector extension:** Dashboard → Database → Extensions → search
   `vector` → enable.
3. **Enable Google auth:** Dashboard → Authentication → Providers → Google →
   toggle on. You'll need a Google OAuth client (next step).
4. **Create a Google OAuth client:** https://console.cloud.google.com →
   APIs & Services → Credentials → Create OAuth client ID → *Web application*.
   - Add this **Authorized redirect URI**:
     `https://<your-project-ref>.supabase.co/auth/v1/callback`
   - Copy the client ID/secret into the Supabase Google provider settings.
5. **Allow-list the app redirect URLs:** Dashboard → Authentication →
   URL Configuration → **Redirect URLs**. Add (see §7 for the extension URL):
   ```
   http://localhost:3001
   http://localhost:3001/**
   https://<extension-id>.chromiumapp.org
   https://<extension-id>.chromiumapp.org/*
   ```
   > ⚠️ **This is the #1 cause of "Authorization page could not be loaded."**
   > If the redirect URL isn't allow-listed, Supabase silently falls back to the
   > Site URL after Google sign-in and the auth window lands on a dead page.

Grab these from Dashboard → Project Settings → API and → Database:
- **Project URL** — `https://<ref>.supabase.co`
- **anon / publishable key**
- **service_role key** (backend only — keep secret)
- **Connection string (URI)** — for `DATABASE_URL`

---

## 5. Configure environment files

Each component has a committed template. Copy it and fill in real values. The
real files (`.env`, `.env.local`) are gitignored — never commit them.

### Backend — `backend/.env`

```bash
cp backend/.env_sample backend/.env
```

Edit `backend/.env`:

```ini
# Supabase Postgres connection (Project Settings -> Database -> Connection string -> URI).
# Use the pooler host for app connections.
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<db-password>@aws-1-<region>.pooler.supabase.com:5432/postgres

# Supabase auth. Modern projects use asymmetric JWTs verified via JWKS,
# derived automatically from SUPABASE_URL — leave the legacy secret as-is.
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>
SUPABASE_JWT_SECRET=unused-for-asymmetric-projects

# Google OAuth client IDs the backend will accept ID tokens from
# (comma-separated; extension + dashboard clients).
GOOGLE_OAUTH_CLIENT_IDS=<client-id>.apps.googleusercontent.com

# Worker queue
REDIS_URL=redis://localhost:6379

# LLM + embeddings via Vercel AI Gateway (or set ANTHROPIC_API_KEY / VOYAGE_API_KEY).
AI_GATEWAY_API_KEY=<your-vercel-ai-gateway-key>
AI_GATEWAY_BASE_URL=https://ai-gateway.vercel.sh/v1
AI_GATEWAY_LLM_MODEL=deepseek/deepseek-v4-flash
AI_GATEWAY_EMBEDDING_MODEL=voyage/voyage-3.5-lite
AI_GATEWAY_EMBEDDING_DIMENSIONS=1024
```

> The backend reads `backend/.env` automatically (via pydantic-settings) — you do
> not need to `source` it.

### Dashboard — `packages/dashboard/.env.local`

```bash
cp packages/dashboard/.env.local.example packages/dashboard/.env.local
```

```ini
NEXT_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
```

### Extension — `packages/extension/.env`

```bash
cp packages/extension/.env.example packages/extension/.env
```

```ini
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-key>
VITE_API_BASE_URL=http://localhost:8765
```

---

## 6. Run database migrations

```bash
cd backend
uv run python -m alembic upgrade head
cd ..
```

This creates all tables (workspaces, pushes, summaries, embeddings, tokens,
audit log, …) and RLS policies in your Supabase Postgres.

---

## 7. Build and load the extension

The extension ID is **fixed** by the public `key` in
`packages/extension/public/manifest.json`, so it's stable across machines and
reloads. For this repo's key, the ID is:

```
hhnhcdmafaliffndneloldkbcblcilpo
→ redirect URL: https://hhnhcdmafaliffndneloldkbcblcilpo.chromiumapp.org/
```

Make sure that redirect URL is in your Supabase **Redirect URLs** allow-list (§4).

Build and load:

```bash
pnpm extension:build          # outputs packages/extension/dist/
```

1. Open `chrome://extensions`
2. Enable **Developer mode** (top-right)
3. **Load unpacked** → select `packages/extension/dist` (the `dist` folder, not
   the package root)
4. To pick up later rebuilds, click the **↻ reload** icon on the extension card.

> `pnpm extension:dev` rebuilds `dist/` on every save, but Chrome still needs the
> ↻ reload and a refresh of the `claude.ai` tab to load new code.

---

## 8. Start the stack

Run each in its own terminal from the repo root.

**Terminal A — Backend API (port 8765, matches the extension default):**

```bash
cd backend
uv run uvicorn contexthub_backend.api.app:create_app --factory --port 8765
```

Smoke test: open http://localhost:8765/docs (Swagger UI) — **http**, not https.
Health endpoint: `curl http://localhost:8765/v1/health`.

**Terminal B — Worker (processes pushes → summaries + embeddings):**

```bash
cd backend
uv run python -c "from contexthub_backend.jobs.worker import start_worker; start_worker()"
```

Requires Redis. If you don't have Redis locally: `docker run -p 6379:6379 -d redis`.

**Terminal C — Dashboard (port 3001):**

```bash
pnpm dashboard:dev
```

Open http://localhost:3001 and set its **API base URL** field to
`http://localhost:8765`.

---

## 9. Sign in and verify end-to-end

1. On `claude.ai`, open the ContextHub sidebar and click **Continue with
   Google**. You should sign in and the backend should bootstrap a workspace.
2. Select text in a conversation → **Push to ContextHub**.
3. Watch the worker terminal process the job; refresh push status until `ready`.
4. Use **Search** in the sidebar/dashboard to find the push, then **pull** it
   back into a conversation.

For DB-level verification queries (pushes/summaries/embeddings), see
[`LOCAL_SYSTEM_TEST.md`](./LOCAL_SYSTEM_TEST.md).

---

## 10. Troubleshooting

| Symptom | Cause & fix |
|---------|-------------|
| **"Authorization page could not be loaded."** on Google sign-in | The extension's `chromiumapp.org` redirect URL (§7) isn't in Supabase → Auth → URL Configuration → Redirect URLs. Add it. |
| Sign-in works, then **"Backend bootstrap failed."** | Backend isn't running on the port the extension targets (`VITE_API_BASE_URL`, default `:8765`). Start Terminal A. |
| **`AssertionError: Status code 204 must not have a response body`** at startup | Wrong FastAPI version from `pip`. Use `uv sync` to get the locked `fastapi`/`starlette`. |
| **`email-validator is not installed`** | Same cause — install via `uv sync`, not loose `pip`. |
| Dashboard shows "Add NEXT_PUBLIC_SUPABASE_URL…" | `packages/dashboard/.env.local` missing or empty (§5). Restart `pnpm dashboard:dev` after editing. |
| Browser error "sent an invalid response" hitting the API | You used `https://localhost:8765`. Use plain `http` for local dev. |
| `/health` returns 404 | Health lives under the `/v1` prefix: `/v1/health`. |
| Extension ID changed after reload | It won't — the manifest `key` pins it. If you removed the key, restore it so the redirect URL stays valid. |
| Push never reaches `ready` | The worker (Terminal B) isn't running, or `REDIS_URL`/AI gateway key is wrong. |

---

## Appendix: Fully-local Docker path

For backend work without Supabase/Google, use Docker Postgres + Redis and the
dev-auth bypass. This path is documented in detail in
[`START_FROM_SCRATCH.md`](./START_FROM_SCRATCH.md). In short:

```bash
pnpm install && uv sync
cd backend
docker compose up -d                       # Postgres (5433) + Redis (6379)
cp .env_sample .env                        # uses ENABLE_DEV_AUTH=true
psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -f sql/auth_stub.sql
uv run python -m alembic upgrade head
uv run uvicorn contexthub_backend.api.app:create_app --factory --port 8000
```

Then in the dashboard, click **Use local dev login** instead of Google. Note
that path uses port **8000**; keep the dashboard/extension "API base URL" field
in sync with whichever port you run.
