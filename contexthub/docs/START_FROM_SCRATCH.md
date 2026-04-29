# ContextHub Full Local Bootstrap (Backend + Worker + Dashboard + Extension)

This runbook brings up the **entire local system** from a clean state:
- Postgres + Redis
- Backend API
- ARQ worker
- Dashboard
- Chrome extension on `claude.ai`

It includes end-to-end verification for:
- Push pipeline (`/v1/workspaces/{id}/pushes` -> summaries + embeddings)
- Search (`/v1/search`)
- Pull/context build (`/v1/pulls`)

---

## 0) Prerequisites

Install:
- Docker Desktop
- Python 3.12+
- `uv`
- Node.js 18.18+ and `pnpm`
- `psql` CLI
- Chrome

Start in repo:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub
```

---

## 1) One-time dependency install

```bash
pnpm install
uv sync --all-extras --dev
```

---

## 2) Reset and start infra (Postgres + Redis)

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
docker compose down -v
docker compose up -d
docker compose ps
```

Wait for Postgres:

```bash
until docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; do
  sleep 1
done
```

---

## 3) Create backend `.env`

From `contexthub/backend`:

```bash
cat > .env <<'EOF'
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/contexthub_dev
SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes
REDIS_URL=redis://localhost:6379
USER_ID=11111111-1111-1111-1111-111111111111
WORKSPACE_ID=22222222-2222-2222-2222-222222222222

# Optional live provider path through Vercel AI Gateway:
# AI_GATEWAY_API_KEY=<your-key>
# AI_GATEWAY_BASE_URL=https://ai-gateway.vercel.sh/v1
# AI_GATEWAY_LLM_MODEL=deepseek/deepseek-v4-flash
# AI_GATEWAY_EMBEDDING_MODEL=voyage/voyage-3.5-lite
# AI_GATEWAY_EMBEDDING_DIMENSIONS=1024
EOF
```

Load env in each backend terminal:

```bash
set -a
source .env
set +a
```

---

## 4) Initialize database + local auth fixtures

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
set -a
source .env
set +a

psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -f sql/auth_stub.sql
uv run --package contexthub-backend python -m alembic upgrade head
```

Seed a local user/workspace:

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

Generate JWT for dashboard use:

```bash
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


---

## 5) Start services (4 terminals)

## Terminal A - API

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
set -a; source .env; set +a
uv run --package contexthub-backend --with uvicorn \
  uvicorn contexthub_backend.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

## Terminal B - Worker

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
set -a; source .env; set +a
uv run --package contexthub-backend python -c "from contexthub_backend.jobs.worker import start_worker; start_worker()"
```

## Terminal C - Dashboard

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub
pnpm dashboard:dev
```

Open `http://localhost:3001`.

## Terminal D - command runner (curl/psql checks)

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
set -a; source .env; set +a
curl -sS http://localhost:8000/v1/health
curl -sS http://localhost:8000/v1/me -H "Authorization: Bearer $JWT"
```

---

## 6) Configure dashboard and mint extension token

In Dashboard:
1. Go to **Overview** and set API config:
   - API base URL: `http://localhost:8000`
   - Authorization: paste JWT value (raw JWT or `Bearer <jwt>`)
2. Save.
3. Go to **Tokens** tab.
4. Ensure scopes include **push**, **pull**, **search**, and **read**.
5. Click **Mint token**.
6. Copy the raw `ch_...` token (shown once).

Keep this token for the extension.

If token mint says `unrecognised token format`, your dashboard auth is not JWT. Re-paste JWT in Overview and save again.

---

## 7) Build and load extension

Build:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub
pnpm extension:build
```

Load in Chrome:
1. Open `chrome://extensions`
2. Enable **Developer mode**
3. **Load unpacked**
4. Choose `contexthub/packages/extension/dist`
5. Open `https://claude.ai`
6. Click floating **ContextHub** button

In extension **Connection**:
- API base URL: `http://localhost:8000`
- Workspace ID: `22222222-2222-2222-2222-222222222222`
- API token: paste raw `ch_...` token (no `Bearer ` prefix)
- Save

---

## 8) End-to-end check: push -> status -> search -> pull

### A) Push from extension

In `claude.ai`, select text and click **Push to ContextHub (real)** in the extension.

Use **Refresh push status** until it shows `ready`.

### B) Verify push and summaries in DB

```bash
psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -c "
SELECT id, status, failure_reason, idempotency_key, created_at
FROM pushes
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

Healthy pattern:
- latest push reaches `ready`
- three summary layers exist
- embeddings exist for embeddable layers

### C) Verify search endpoint

```bash
curl -sS "http://localhost:8000/v1/search?q=local&limit=10" \
  -H "Authorization: Bearer $JWT"
```

Expected shape: `{ "query": "...", "items": [...] }`

### D) Verify pull endpoint

Use latest push id:

```bash
export LAST_PUSH_ID=$(psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -Atc "
SELECT id
FROM pushes
WHERE workspace_id = '$WORKSPACE_ID'
ORDER BY created_at DESC
LIMIT 1;
")
echo "$LAST_PUSH_ID"
```

Call pull:

```bash
curl -sS -X POST "http://localhost:8000/v1/pulls" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d "{
    \"push_ids\": [\"$LAST_PUSH_ID\"],
    \"resolution\": \"structured_block\",
    \"target_platform\": \"claude_ai\",
    \"origin\": \"dashboard\"
  }"
```

Expected response includes:
- `payload_markdown`
- `token_estimate`
- `provenance`

You can also run this flow from:
- Dashboard **Search** page (search + build pull payload)
- Extension **Search and pull** section (pull + inject into Claude input)

---

## 9) Shutdown and reset

Stop API/worker/dashboard with `Ctrl+C`.

Stop infra:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
docker compose down
```

Full reset (wipe DB volume):

```bash
docker compose down -v
```

