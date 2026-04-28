# ContextHub Full Local Bootstrap (Modules 4-8 + Dashboard + Extension)

This is the complete "start everything from scratch" runbook.

It combines and sequences the flows from:
- `docs/integration with 123.md`
- `docs/integration with 4-8.md`
- `docs/LOCAL_SYSTEM_TEST.md`

Use this when you want a clean local setup that includes:
- Backend pipeline from Modules 4-8 (providers, ingress, summarizer, embeddings, storage/jobs)
- Dashboard (`packages/dashboard`)
- Chrome extension (`packages/extension`)

---

## 0) Prerequisites

Install these first:
- Docker Desktop (for Postgres + Redis)
- Python 3.12+
- `uv`
- Node.js 18.18+ and `pnpm`
- `psql` CLI
- Chrome (for loading the extension)

Then start in repo root:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub
```

---

## 1) Install Dependencies (one-time per fresh checkout)

From `contexthub/`:

```bash
pnpm install
uv sync --all-extras --dev
```

---

## 2) Reset and Start Infra (Postgres + Redis)

From `contexthub/backend`:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
docker compose down -v
docker compose up -d
docker compose ps
```

Wait for Postgres readiness:

```bash
until docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; do
  sleep 1
done
```

---

## 3) Export Local Env

From `contexthub/backend`:

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/contexthub_dev
export SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes
export REDIS_URL=redis://localhost:6379
export USER_ID=11111111-1111-1111-1111-111111111111
export WORKSPACE_ID=22222222-2222-2222-2222-222222222222
```

Optional: persist these values for later shells:

```bash
cat > .env <<'EOF'
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/contexthub_dev
SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes
REDIS_URL=redis://localhost:6379
USER_ID=11111111-1111-1111-1111-111111111111
WORKSPACE_ID=22222222-2222-2222-2222-222222222222
EOF
```

Load it in any new backend terminal:

```bash
set -a
source .env
set +a
```

---

## 4) Initialize DB Schema + Local Auth Fixtures

From `contexthub/backend`:

```bash
psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -f sql/auth_stub.sql
uv run --package contexthub-backend python -m alembic upgrade head
```

Seed one user, profile, workspace, and interchange version:

```bash
psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" <<SQL
INSERT INTO auth.users (id, email)
VALUES ('$USER_ID', 'local@test.local')
ON CONFLICT DO NOTHING;

INSERT INTO profiles (user_id, display_name)
VALUES ('$USER_ID', 'Local User')
ON CONFLICT DO NOTHING;

INSERT INTO interchange_format_versions (version, json_schema)
VALUES ('ch.v0.1', '{}'::jsonb)
ON CONFLICT DO NOTHING;

INSERT INTO workspaces (id, user_id, name, slug)
VALUES ('$WORKSPACE_ID', '$USER_ID', 'Local WS', 'local-ws')
ON CONFLICT DO NOTHING;
SQL
```

Generate a local JWT:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
set -a
source .env
set +a

export JWT=$(uv run --package contexthub-backend python - <<'PY'
import uuid
from contexthub_backend.auth.jwt import make_test_jwt
print(make_test_jwt(
    uuid.UUID("11111111-1111-1111-1111-111111111111"),
    "test-secret-not-for-production-at-least-32-bytes",
))
PY
)
echo "$JWT"
```

Quick sanity check:

```bash
echo "$JWT" | awk -F. '{print "JWT segments:", NF}'
```

---

## 5) Start Backend Services (use separate terminals)

Use three terminals:

### Terminal A - API

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
set -a
source .env
set +a

uv run --package contexthub-backend --with uvicorn \
  uvicorn contexthub_backend.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

### Terminal B - Worker

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
set -a
source .env
set +a

uv run --package contexthub-backend python -c "from contexthub_backend.jobs.worker import start_worker; start_worker()"
```

### Terminal C - Backend smoke checks

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
set -a
source .env
set +a

curl -sS http://localhost:8000/v1/health
curl -sS http://localhost:8000/v1/me -H "Authorization: Bearer $JWT"
```

---

## 6) Start Dashboard

In a new terminal from `contexthub/`:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub
pnpm dashboard:dev
```

Open: `http://localhost:3001`

In the Dashboard:
1. Go to **Overview**.
2. In **API connection**, set:
   - API base URL: `http://localhost:8000`
   - Authorization: your JWT (raw JWT or `Bearer <jwt>` both work)
     - A JWT should look like `eyJ...` and have 3 dot-separated parts.
     - Do **not** paste `$JWT` literally; paste the expanded token value.
     - Do **not** paste a `ch_...` token here before minting.
3. Click **Save**.
4. Confirm JWT auth works before opening Tokens:

```bash
curl -sS http://localhost:8000/v1/me -H "Authorization: Bearer $JWT"
```

If this returns your `user_id`, your JWT is valid.
5. Go to **Tokens** page.
6. Click **Mint token** and copy the raw `ch_...` token (shown once).

Keep this token for the extension.

If Tokens page shows `unrecognised token format`:
1. Go back to **Overview** and replace Authorization with a freshly generated JWT.
2. Save again, then revisit **Tokens** and click **Refresh**.

---

## 7) Build and Load Extension

In a new terminal from `contexthub/`:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub
pnpm extension:build
```

Load unpacked extension in Chrome:
1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select: `contexthub/packages/extension/dist`
5. Open `https://claude.ai`
6. Click floating **ContextHub** button

In extension sidebar **Connection** section:
- API base URL: `http://localhost:8000`
- Workspace ID: `22222222-2222-2222-2222-222222222222`
- API token: paste raw `ch_...` token (without `Bearer `)
- Click **Save**

Then select some text in Claude and click **Push to ContextHub (real)**.

---

## 8) Verify Summaries Have Been Generated

From `contexthub/backend`:

```bash
psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -c "
SELECT
  layer,
  model,
  failure_reason,
  content_markdown
FROM summaries
WHERE push_id = (
  SELECT id
  FROM pushes
  WHERE workspace_id = '$WORKSPACE_ID'
  ORDER BY created_at DESC
  LIMIT 1
)
ORDER BY
  CASE layer
    WHEN 'commit_message' THEN 1
    WHEN 'structured_block' THEN 2
    WHEN 'raw_transcript' THEN 3
  END;
"
```

Check pipeline tables:

```bash
psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -c "
SELECT id, workspace_id, user_id, status, failure_reason, idempotency_key, created_at, updated_at
FROM pushes
ORDER BY created_at DESC
LIMIT 5;
"

psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -c "
SELECT push_id, storage_path, sha256, size_bytes, message_count
FROM transcripts
ORDER BY created_at DESC
LIMIT 5;
"

psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -c "
SELECT push_id, layer, model, prompt_version, created_at
FROM summaries
ORDER BY created_at DESC
LIMIT 10;
"

psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -c "
SELECT summary_id, embedding_model, created_at
FROM summary_embeddings
ORDER BY created_at DESC
LIMIT 10;
"
```

Healthy output pattern:
- latest `pushes.status` becomes `ready`
- a `transcripts` row exists
- `summaries` has 3 layers (`commit_message`, `structured_block`, `raw_transcript`)
- `summary_embeddings` rows exist for embeddable summaries

---

## 9) Shutdown / Reset

Stop API + worker via `Ctrl+C` in their terminals.

From `contexthub/backend`:

```bash
docker compose down
```

To wipe local DB data completely:

```bash
docker compose down -v
```

