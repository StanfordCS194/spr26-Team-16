# ContextHub — Integration Guide (post-Modules 4/5/6/7/8)

**Status:** living document. Last updated 2026-04-27.  
**Audience:** whoever picks up Modules 9+ (search, pull, dashboard/API wiring, observability, retention, product flows). **If you are an AI assistant helping implement later modules, read this doc first, then `ARCHITECTURE.md` §4–§8 and `integration with 123.md`.**

This doc is the handshake between Modules 4–8 (providers, ingress, summarizer, embeddings, storage/jobs) and later work. It explains what is now available, how to interact with it, and which surfaces later modules should depend on instead of inventing parallel paths.

---

## 0. Before you write code

1. Read `contexthub/docs/integration with 123.md` first. Modules 4–8 sit on top of the auth/RLS/app/schema contracts from Modules 1–3.
2. Read this file top to bottom.
3. Run the local system test in `contexthub/docs/LOCAL_SYSTEM_TEST.md` once so you have seen the push pipeline reach `ready`.
4. Read `contexthub/docs/ARCHITECTURE.md` §4 (push/pull pipelines), §5 (data model), §6 (modules), §7 (API surface).
5. Do not add a second mini-app, in-memory repository, provider abstraction, job runner, storage layer, or markdown renderer. The integration points below are the supported seams.

---

## 1. What Modules 4–8 provide

### Module 4 — Providers

Path: `contexthub/backend/contexthub_backend/providers/`

Available abstractions:

- `LLMProvider.complete(prompt, *, response_format, max_tokens, temperature) -> LLMResponse`
- `EmbeddingProvider.embed(texts, *, input_type) -> EmbeddingResponse`
- `get_llm_provider()`
- `get_embedding_provider()`

Current concrete providers:

- `FakeLLMProvider` / `FakeEmbeddingProvider` for local and CI-safe tests.
- `AnthropicProvider` for direct Anthropic Messages API.
- `VoyageEmbeddingProvider` for direct Voyage embeddings API.

Current factory behavior:

- Workers choose live LLM only when `settings.anthropic_api_key` is present; otherwise fake.
- Workers choose live embeddings only when `settings.voyage_api_key` is present; otherwise fake.

Planned provider extension:

- Vercel AI Gateway should be added as another provider implementation, not wired directly into summarizer/jobs. Use the existing provider interfaces.

### Module 5 — Ingress

Path: `contexthub/backend/contexthub_backend/ingress/`

Available pieces:

- `RateLimiter` for per-user Redis-backed limits.
- `scrub_sensitive_patterns()` for server-side sensitive-pattern detection.
- Idempotency via `pushes.idempotency_key`.

Current API integration:

- `POST /v1/workspaces/{workspace_id}/pushes`
- Requires Module 3 auth: JWT or `ch_` token with `push` scope.
- Uses `get_rls_session`, so workspace lookup and push creation are user-scoped by RLS.
- Returns `202` for newly accepted pushes and idempotent replays.

### Module 6 — Summarizer

Path: `contexthub/backend/contexthub_backend/services/summarizer.py`

Available functions:

- `summarize_push(conversation, *, llm, prompt_version)`
- `structured_block_markdown(structured_block)`

Output contract:

- One LLM call produces a three-layer summary.
- Three `summaries` rows are written by the worker:
  - `commit_message`
  - `structured_block`
  - `raw_transcript`
- `summaries.content_json` is the source of truth.
- `summaries.content_markdown` is derived for searchable/displayable text.

### Module 7 — Embeddings

Path: `contexthub/backend/contexthub_backend/services/embeddings.py`

Available function:

- `embed_summary(summary_id, *, embedder, session)`

Behavior:

- Reads `summaries.content_markdown`.
- Calls `EmbeddingProvider.embed(..., input_type="document")`.
- Writes one `summary_embeddings` row per embedded summary.

Schema contract:

- `summary_embeddings.embedding` is `vector(1024)`.
- Embedding models must return 1024-dimensional vectors unless the schema/migration is updated deliberately.

### Module 8 — Storage + ARQ jobs

Paths:

- `contexthub/backend/contexthub_backend/services/storage.py`
- `contexthub/backend/contexthub_backend/jobs/registry.py`
- `contexthub/backend/contexthub_backend/jobs/tasks.py`
- `contexthub/backend/contexthub_backend/jobs/worker.py`

Available workflow:

1. API receives a push.
2. API writes `pushes` row with `status="pending"`.
3. API stores raw transcript and writes `transcripts` row.
4. API enqueues `summarize_push`.
5. Worker loads transcript, summarizes it, writes three `summaries` rows.
6. Worker enqueues `embed_summary` jobs for embeddable summary layers.
7. Worker writes embeddings.
8. Worker sets push status to `ready`; on failure, status becomes `failed` and `failure_reason` is populated.

Important RLS detail:

- Worker jobs apply RLS context using the owner `user_id`.
- Later jobs must do the same. Do not bypass RLS by widening table policies.

---

## 2. How to interact with Modules 4–8

### 2.1 Start the local stack

Use the complete runbook:

```text
contexthub/docs/LOCAL_SYSTEM_TEST.md
```

The short version is:

```bash
cd contexthub/backend
docker compose up -d

export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/contexthub_dev
export SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes
export REDIS_URL=redis://localhost:6379

psql "postgresql://postgres:postgres@localhost:5433/contexthub_dev" -f sql/auth_stub.sql
uv run --package contexthub-backend python -m alembic upgrade head
```

Start API:

```bash
uv run --package contexthub-backend --with uvicorn \
  uvicorn contexthub_backend.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

Start worker:

```bash
uv run --package contexthub-backend python -c "from contexthub_backend.jobs.worker import start_worker; start_worker()"
```

### 2.2 Authenticate as a local user

Local dev uses `sql/auth_stub.sql` plus a signed test JWT.

```bash
export USER_ID=11111111-1111-1111-1111-111111111111
export WORKSPACE_ID=22222222-2222-2222-2222-222222222222

export JWT=$(uv run --package contexthub-backend python - <<'PY'
import uuid
from contexthub_backend.auth.jwt import make_test_jwt

print(make_test_jwt(
    uuid.UUID("11111111-1111-1111-1111-111111111111"),
    "test-secret-not-for-production-at-least-32-bytes",
))
PY
)
```

Seed user/workspace/spec version:

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

Verify auth:

```bash
curl -sS http://localhost:8000/v1/me \
  -H "Authorization: Bearer $JWT"
```

### 2.3 Push a conversation

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

Expected response:

```json
{
  "push_id": "...",
  "status": "pending",
  "request_id": "...",
  "scrub_flags": []
}
```

If the same `Idempotency-Key` is sent again, the API should return the same `push_id`. The returned status may be newer than the first response because the worker may have already changed `pending` to `processing`, `ready`, or `failed`.

### 2.4 Verify the pipeline

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

Healthy state:

- latest push is `ready`
- transcript row exists
- three summary rows exist
- embedding rows exist for embeddable layers if the worker processed `embed_summary`

---

## 3. How later modules should use Modules 4–8

### Module 9+ Search

Search should read from:

- `summaries.content_tsv` / `summaries.content_markdown` for keyword/full-text search.
- `summary_embeddings.embedding` for vector search.
- `pushes`, `workspaces`, `transcripts` for metadata joins.

Do:

- Use `get_rls_session` in API routes.
- Restrict results to rows visible under RLS.
- Treat `summaries.content_json` as canonical when rendering structured output.
- Prefer `summary_embeddings` generated by Module 7 instead of embedding ad hoc query-side documents into storage tables.

Do not:

- Re-summarize during search.
- Re-embed stored summaries unless you are running an explicit backfill/migration job.
- Query as superuser to “simplify” cross-table joins.

### Pull / Context Retrieval

Pull routes should consume:

- ready `pushes`
- their `summaries`
- optional `summary_embeddings`
- workspace filters/tags/relationships once those later modules are implemented

Recommended shape:

```text
GET or POST /v1/workspaces/{workspace_id}/pulls
```

or a search-oriented route, depending on final product decision.

Behavior:

- Auth with `get_current_user`.
- Scope check with `user.require_scope("pull")` or `search`, depending on endpoint purpose.
- DB session with `get_rls_session`.
- Read only `ready` pushes unless an explicit diagnostic/admin endpoint says otherwise.
- Return renderer-ready structured blocks from `summaries.content_json`, not regenerated LLM output.

### Dashboard API

Dashboard routes should use:

- `pushes.status` for pipeline state.
- `failure_reason` for failed job diagnostics.
- `transcripts.message_count` and `size_bytes` for metadata display.
- `summaries.layer`, `content_markdown`, and `model` for summary previews.

Do not call provider APIs from dashboard routes.

### Extension / Client Pushes

Clients should send:

- `ConversationV0` JSON body.
- `Authorization: Bearer <JWT or ch_ token>`.
- `Idempotency-Key` header for retry-safe capture.

Clients should expect:

- `202 Accepted` immediately.
- A `push_id` for later status lookup once status endpoints exist.
- Server-side scrub flags in `scrub_flags`.

Current limitation:

- There is no public `GET /v1/pushes/{id}` status endpoint yet. Later modules should add one rather than reading DB directly from clients.

### Observability

Later observability work should attach:

- `request_id`
- `user_id`
- `workspace_id`
- `push_id`
- `job_id`
- provider model and latency fields

Existing tables already capture some of this:

- `audit_log`
- `pushes.failure_reason`
- `summaries.latency_ms`
- `summaries.input_tokens`
- `summaries.output_tokens`
- `summaries.cost_usd`
- `summary_embeddings.embedding_model`

---

## 4. Provider integration rules

Later code should never call Anthropic, Voyage, Vercel AI Gateway, OpenAI, or any other AI API directly.

Use:

```python
from contexthub_backend.providers import get_llm_provider, get_embedding_provider
```

or accept providers as function arguments:

```python
async def my_service(..., llm: LLMProvider, embedder: EmbeddingProvider) -> ...:
    ...
```

Why:

- Tests can use fake providers.
- Live providers can be swapped via config.
- Vercel AI Gateway can be added without touching summarizer/search/pull code.
- Later cost/observability/routing logic can be centralized.

Recommended Vercel AI Gateway addition:

- Add `VercelGatewayLLMProvider`.
- Add `VercelGatewayEmbeddingProvider`.
- Add settings:
  - `ai_gateway_api_key`
  - `ai_gateway_base_url`
  - `ai_gateway_llm_model`
  - `ai_gateway_embedding_model`
- Update factory selection so gateway wins when `AI_GATEWAY_API_KEY` exists.

Do not:

- Add Vercel-specific code into `services/summarizer.py`.
- Add Vercel-specific code into `services/embeddings.py`.
- Add provider keys to route handlers.

---

## 5. Job integration rules

Later modules that need async work should use ARQ.

Use:

```python
from contexthub_backend.jobs.registry import enqueue_job

await enqueue_job("job_name", key="value")
```

Register job functions in `WorkerSettings.functions` in `jobs/tasks.py` or split into submodules and import them there.

RLS rule:

- If a job reads/writes user-owned data, it must establish user context before user-scoped queries/writes.
- Use `apply_rls_context(session, user_id=...)`.
- Prefer passing or deriving `user_id` from a trusted DB row (`Push.user_id`, `Summary -> Push.user_id`), not from client input.

Status rule:

- User-facing long-running work should write status/failure state into a table (`pushes.status`, future `pulls.status`, etc.).
- Do not leave the only status in Redis.

Retry rule:

- Expected transient failures can raise `arq.Retry`.
- Permanent data/validation failures should write a useful `failure_reason`.

---

## 6. Data contracts later modules can rely on

### Push

Table: `pushes`

Important columns:

- `id`
- `workspace_id`
- `user_id`
- `source_platform`
- `interchange_version`
- `title`
- `status`
- `failure_reason`
- `idempotency_key`

Status values:

- `pending`
- `processing`
- `ready`
- `failed`

Later modules should treat `ready` as the normal readable state.

### Transcript

Table: `transcripts`

Important columns:

- `push_id`
- `storage_path`
- `sha256`
- `size_bytes`
- `message_count`

Use `TranscriptStorageService.load_transcript(storage_path)` to read the raw captured conversation. Do not assume a future production storage path is a local filesystem path.

### Summary

Table: `summaries`

Layers:

- `commit_message`
- `structured_block`
- `raw_transcript`

Important columns:

- `content_json`
- `content_markdown`
- `content_tsv`
- `model`
- `prompt_version`
- `latency_ms`
- `input_tokens`
- `output_tokens`
- `cost_usd`
- `failure_reason`

`content_json` is canonical. `content_markdown` is for display/search.

### SummaryEmbedding

Table: `summary_embeddings`

Important columns:

- `summary_id`
- `embedding`
- `embedding_model`

Current vector dimension: `1024`.

If a future embedding model returns another dimension, update:

- Alembic raw DDL for `summary_embeddings`
- ORM model `Vector(1024)`
- HNSW index
- tests
- this document

---

## 7. Current limitations and known gaps

- There is no public pull route yet.
- There is no public push-status route yet.
- Fake providers are the default when real API keys are absent.
- Vercel AI Gateway is planned but not implemented yet.
- Purge/retention jobs are skeletons.
- Production storage is abstracted, but local behavior is enough for the current system test.
- The local runbook is a smoke test, not a complete live-provider certification.

---

## 8. Testing expectations for later modules

Before later modules depend on this pipeline, run:

```bash
uv run --package contexthub-backend pytest \
  tests/test_auth_unit.py \
  tests/test_providers_unit.py \
  tests/test_providers_contract.py \
  -q
```

Run push integration against Docker pgvector:

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/contexthub_dev \
SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes \
uv run --package contexthub-backend pytest tests/test_pushes_api.py -m integration -v
```

Run the local system test:

```text
contexthub/docs/LOCAL_SYSTEM_TEST.md
```

For modules that add API routes:

- Add route-level integration tests.
- Include user A / user B RLS isolation checks.
- Include idempotency/retry behavior if the endpoint creates work.
- Do not require live AI provider keys in normal CI.

For modules that add provider behavior:

- Add fake-provider unit tests.
- Add contract tests that can run without network.
- Gate live provider tests behind environment variables and mark them `live`.

---

## 9. Quick reference

| Thing | Path |
| ----- | ---- |
| Push route | `contexthub/backend/contexthub_backend/api/routes/pushes.py` |
| App factory | `contexthub/backend/contexthub_backend/api/app.py` |
| Provider interfaces | `contexthub/backend/contexthub_backend/providers/base.py` |
| Provider factory | `contexthub/backend/contexthub_backend/providers/factory.py` |
| Prompt registry | `contexthub/backend/contexthub_backend/providers/registry.py` |
| Fake providers | `contexthub/backend/contexthub_backend/providers/fake.py` |
| Anthropic provider | `contexthub/backend/contexthub_backend/providers/anthropic.py` |
| Voyage provider | `contexthub/backend/contexthub_backend/providers/voyage.py` |
| Rate limiter | `contexthub/backend/contexthub_backend/ingress/rate_limit.py` |
| Scrubber | `contexthub/backend/contexthub_backend/ingress/scrub.py` |
| Summarizer service | `contexthub/backend/contexthub_backend/services/summarizer.py` |
| Embedding service | `contexthub/backend/contexthub_backend/services/embeddings.py` |
| Transcript storage | `contexthub/backend/contexthub_backend/services/storage.py` |
| Job enqueue helper | `contexthub/backend/contexthub_backend/jobs/registry.py` |
| Worker tasks | `contexthub/backend/contexthub_backend/jobs/tasks.py` |
| Worker entrypoint | `contexthub/backend/contexthub_backend/jobs/worker.py` |
| RLS dependency | `contexthub/backend/contexthub_backend/auth/dependencies.py` |
| Worker RLS helper | `contexthub/backend/contexthub_backend/auth/rls.py` |
| ORM models | `contexthub/backend/contexthub_backend/db/models.py` |
| Local system test | `contexthub/docs/LOCAL_SYSTEM_TEST.md` |

---

## 10. When you extend this surface

When a later module adds a route, job, provider, or table:

1. Update `ARCHITECTURE.md` if the product/data/API behavior changed.
2. Update `PLAN.md` if the work changes shipped state or future sequencing.
3. Update `TODO.md` if you close or discover follow-up work.
4. Update `VALIDATION.md` with exact commands and observed results.
5. Update this document if later modules should consume the new surface.

