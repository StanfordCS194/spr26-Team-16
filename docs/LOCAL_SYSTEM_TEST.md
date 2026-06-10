# Local System Test Runbook

This runbook starts ContextHub locally from a clean Docker database, runs the API and worker, performs a push, and verifies persisted rows.

Run commands from:

```bash
cd /Users/hou/GitHub/spr26-Team-16/contexthub/backend
```

## 1. Reset And Start Infrastructure

This deletes the local Docker Postgres volume for this compose project, then starts fresh Postgres + Redis.

```bash
docker compose down -v
docker compose up -d
docker compose ps
```

Wait until Postgres is ready:

```bash
until docker compose exec -T postgres pg_isready -U postgres >/dev/null 2>&1; do
  sleep 1
done
```

## 2. Export Local Environment

The repo maps Docker Postgres to host port `5433`.

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/contexthub_dev
export SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes
export REDIS_URL=redis://localhost:6379
export USER_ID=11111111-1111-1111-1111-111111111111
export WORKSPACE_ID=22222222-2222-2222-2222-222222222222
```

You can also store these values in `contexthub/backend/.env`. This file is ignored by git via `contexthub/.gitignore`; do not commit real secrets.

```bash
cat > .env <<'EOF'
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/contexthub_dev
SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes
REDIS_URL=redis://localhost:6379
USER_ID=11111111-1111-1111-1111-111111111111
WORKSPACE_ID=22222222-2222-2222-2222-222222222222

# Optional live AI via Vercel AI Gateway:
# AI_GATEWAY_API_KEY=<your-vercel-ai-gateway-key>
# AI_GATEWAY_BASE_URL=https://ai-gateway.vercel.sh/v1
# AI_GATEWAY_LLM_MODEL=deepseek/deepseek-v4-flash
# AI_GATEWAY_EMBEDDING_MODEL=voyage/voyage-3.5-lite
# AI_GATEWAY_EMBEDDING_DIMENSIONS=1024
# AI_GATEWAY_JSON_MODE=false
EOF
```

To load it into your current shell:

```bash
set -a
source .env
set +a
```

To use Vercel AI Gateway instead of fake providers, also export these values. Do not commit real keys to the repo.

```bash
export AI_GATEWAY_API_KEY=<your-vercel-ai-gateway-key>
export AI_GATEWAY_BASE_URL=https://ai-gateway.vercel.sh/v1
export AI_GATEWAY_LLM_MODEL=deepseek/deepseek-v4-flash
export AI_GATEWAY_EMBEDDING_MODEL=voyage/voyage-3.5-lite
export AI_GATEWAY_EMBEDDING_DIMENSIONS=1024
export AI_GATEWAY_JSON_MODE=false
```

## 3. Initialize Database

```bash
psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -f sql/auth_stub.sql

uv run --package contexthub-backend python -m alembic upgrade head
```

Seed one local user, one workspace, and the interchange version:

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

## 4. Generate Local JWT

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

echo "$JWT" | awk -F. '{print "JWT segments:", NF}'
```

Expected output:

```text
JWT segments: 3
```

## 5. Start API

Open a new terminal in `contexthub/backend` and run:

```bash
set -a
source .env
set +a

uv run --package contexthub-backend --with uvicorn \
  uvicorn contexthub_backend.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Health check from another terminal:

```bash
curl -sS http://localhost:8000/v1/health
curl -sS http://localhost:8000/v1/me -H "Authorization: Bearer $JWT"
```

## 6. Start Worker

Open another new terminal in `contexthub/backend` and run:

```bash
set -a
source .env
set +a

uv run --package contexthub-backend python -c "from contexthub_backend.jobs.worker import start_worker; start_worker()"
```

## 7. Push A Conversation

Run this from the terminal where `JWT` and `WORKSPACE_ID` are exported:

```bash
curl -sS -X POST "http://localhost:8000/v1/workspaces/$WORKSPACE_ID/pushes" \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: local-system-test-1" \
  -d '{
    "spec_version": "ch.v0.1",
    "source": {"platform": "claude_ai", "captured_at": "2026-04-23T00:00:00Z"},
    "messages": [
      {"role":"user","content":[{"type":"text","text":"Summarize this thread"}]},
      {"role":"assistant","content":[{"type":"text","text":"This is a local system test."}]}
    ],
    "metadata": {"title":"Local system test push"}
  }'
```

Expected shape:

```json
{
  "push_id": "...",
  "status": "pending",
  "request_id": "...",
  "scrub_flags": []
}
```

## 8. Verify Database State

```bash
psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -c "
SELECT id, user_id, name, slug
FROM workspaces
WHERE id = '$WORKSPACE_ID';
"

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
```

The current backend has push ingestion wired. A public pull API route is not implemented yet, so pull verification is DB-level only for now.

## 9. Run Automated Tests

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/contexthub_dev \
SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes \
uv run --package contexthub-backend pytest tests/test_pushes_api.py -m integration -v
```

Pure unit/provider tests:

```bash
uv run --package contexthub-backend pytest \
  tests/test_auth_unit.py \
  tests/test_providers_unit.py \
  tests/test_providers_contract.py \
  -q
```

## 10. Stop Services

Stop API and worker with `Ctrl+C` in their terminals.

Stop Docker services:

```bash
docker compose down
```

To reset all local DB data:

```bash
docker compose down -v
```
