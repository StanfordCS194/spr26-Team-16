# ContextHub — Integration Guide (post-Modules 1/2/3)

**Status:** living document. Last updated 2026-04-23.
**Audience:** whoever picks up Modules 4–8 (backend providers, ingress, summarizer, embeddings, storage + ARQ). **If you are an AI assistant (Claude / other) helping implement one of those modules, read this doc first, then `ARCHITECTURE.md` §4–§7.**

This doc is the handshake between Modules 1/2/3 (already shipped) and Modules 4/5/6/7/8 (yours). It tells you what surface area already exists, how to plug into it, and what to update when you finish.

---

## 0. Before you write code

1. Read this file top to bottom.
2. Read `contexthub/docs/ARCHITECTURE.md` §4 (push/pull pipelines), §5 (data model), §6 (module breakdown), §7 (API surface).
3. Read `contexthub/docs/PLAN.md` "Active work" + "Decisions" — the decisions log has ~25 locked design choices. Do not relitigate them.
4. Skim `contexthub/docs/VALIDATION.md` Module 2 + 3 entries to understand what has been verified.
5. Propose your module's approach in a doc / PR description **before** implementing — Aalaap reviews before code lands. (Modules 2 and 3 skipped this cycle; we're re-asserting it for 4+.)

---

## 1. What's already built (surface area)

### Module 1 — `packages/interchange-spec` (shipped 2026-04-17)

- JSON Schemas (source of truth): `contexthub/packages/interchange-spec/schemas/ch.v0.1.conversation.json`, `ch.v0.1.structured-block.json`.
- Python binding: `from contexthub_interchange.models import ConversationV0, StructuredBlockV0, …`
- Python renderer: `from contexthub_interchange.renderer import render_structured_block`
- TypeScript binding: `import { ConversationV0, StructuredBlockV0 } from "@contexthub/interchange-spec"`
- TS renderer: `import { renderStructuredBlock } from "@contexthub/interchange-spec"`
- **Byte-identical** Py ↔ TS renderer output is a CI contract (golden fixtures). Never write a second markdown renderer — import the shared one.

### Module 2 — `backend/schema` (shipped 2026-04-22)

- ORM models: `from contexthub_backend.db.models import Workspace, Push, Summary, SummaryEmbedding, Transcript, Tag, PushTag, PushRelationship, SummaryFeedback, Pull, AuditLog, ApiToken, Profile, InterchangeFormatVersion` (14 tables).
- Engine factories: `from contexthub_backend.db.base import make_sync_engine, make_async_engine`.
- Short-ID: `from contexthub_backend.db.short_id import uuid7, short_id_from_uuid, new_uuid_and_short_id`.
- Alembic migration `001_initial_schema` creates all tables, HNSW index on `summary_embeddings.embedding`, GIN tsvector index + trigger on `summaries.content_tsv`, `ch_authenticated` role, and RLS policies on every table keyed on `auth.uid()` (driven by `current_setting('app.current_user_id')::uuid` in local/CI via `sql/auth_stub.sql`).
- Fixture loader (≥50 WS / ≥500 pushes): `contexthub/backend/scripts/gen_fixtures.py`.
- Local dev: `cd contexthub/backend && docker-compose up -d` brings up pgvector + redis.
- **Known caveat:** `summary_embeddings` table is raw DDL in the migration (pgvector's `Vector` type isn't in Alembic's autogenerate). If you add columns to that table, edit `001_initial_schema.py` manually; autogenerate will not detect drift.

### Module 3 — `backend/auth` (shipped 2026-04-22)

- FastAPI app factory: `from contexthub_backend.api.app import create_app`.
- Config: `from contexthub_backend.config import settings` (pydantic-settings; reads `DATABASE_URL`, `SUPABASE_JWT_SECRET` from env; exposes `settings.async_database_url`).
- Auth dependencies (this is the main integration seam for you):
  - `get_db_session` — opens an async transaction on the superuser connection. **RLS not yet applied.**
  - `get_current_user` — resolves `AuthUser(user_id, scopes, auth_type)` from JWT or `ch_` token. Runs on the superuser connection so it can see all `api_tokens`.
  - `get_rls_session` — issues `SET LOCAL ROLE ch_authenticated` + `SELECT set_config('app.current_user_id', <uid>, true)` on the open transaction. After this point, every query obeys RLS. **Use this for all user-scoped queries in new routes.**
  - `require_jwt` — guard that rejects API-token callers (only raw JWT). Use on privilege-escalating endpoints (token mint, account delete, etc.).
- Error envelope: `from contexthub_backend.api.errors import AuthError, ForbiddenError, NotFoundError, ValidationError`. Handlers are already wired in `create_app()`. Raise these from your routes; the middleware converts them to `{ "error": { "code", "message", "request_id" } }`.
- Request-ID middleware attaches `X-Request-Id` to every response and log line. No action needed from you; just reuse the existing middleware.
- Routes already live: `GET /v1/health`, `GET /v1/version`, `GET /v1/me`, `POST /v1/tokens`, `GET /v1/tokens`, `DELETE /v1/tokens/{id}`.

---

## 2. Patterns to follow

These are not suggestions — they're the house style Modules 1–3 established. Deviating forks the codebase.

### 2.1 Route handlers

```python
from fastapi import APIRouter, Depends
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.auth.dependencies import AuthUser, get_current_user, get_rls_session

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])

@router.get("/{workspace_id}")
async def get_workspace(
    workspace_id: uuid.UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
):
    # session now enforces RLS — user can only see their own rows.
    # Raise ForbiddenError / NotFoundError from contexthub_backend.api.errors.
    ...
```

**Do not** use `get_db_session` directly unless you are performing a pre-auth lookup (like `verify_api_token` does to look up token hashes before RLS is applied). That is the only legitimate reason.

### 2.2 Scope checking

`AuthUser.has_scope("push")` / `AuthUser.require_scope("push")`. Raise `ForbiddenError` if missing. Scopes are: `push`, `pull`, `search`, `read`. JWT callers implicitly get all scopes; API tokens carry their own subset.

### 2.3 Enqueuing ARQ jobs (Module 8 territory, but 6/7 will touch this)

Module 8 owns the ARQ registry. Until it lands, stub job enqueues as `# TODO: enqueue via ARQ ("summarize_push", push_id)`. Do **not** use `asyncio.create_task` or fire-and-forget — the decisions log explicitly rejects that (2026-04-17 "Push creation is async, backed by ARQ on Redis").

### 2.4 LLM / embedding calls (Module 4 is the only module that makes them directly)

Modules 6 (summarizer) and 7 (embeddings) **must** go through the `LLMProvider` / `EmbeddingProvider` ABCs that Module 4 exposes. Do not import `anthropic` or `voyageai` directly from Modules 6/7. The whole point of Module 4 is that swapping providers is a DI change, not a rewrite.

### 2.5 JSON-authoritative summaries

`summaries.content_json` is the source of truth. `summaries.content_markdown` is derived — regenerated by the shared renderer (`contexthub_interchange.renderer.render_structured_block`) on every write. Never write to `content_markdown` without also writing a matching `content_json`, and vice versa.

### 2.6 Testing discipline

- Unit tests: no DB, no network. Live in `contexthub/backend/tests/` with filename `test_<module>_unit.py`. Run in the `python` CI job.
- Integration tests: require Postgres + `auth_stub.sql` loaded. Mark with `@pytest.mark.integration`. Live in `test_<module>_api.py` or `test_<module>_integration.py`. Run in the `migrations` CI job.
- Contract tests (provider mocks, JSON-Schema conformance): put next to the thing they test; gate on CI.
- For any user-scoped endpoint you add, include an integration test that proves user A cannot read user B's rows through the API layer. `test_auth_api.py` has the template.

### 2.7 Conftest re-use

`contexthub/backend/tests/conftest.py` already provides `db_engine` (session-scoped, migrations applied) and `_psycopg_url()`. Re-use them. Do not add a parallel fixture factory.

### 2.8 Observability hooks

Module 16 (observability) isn't shipped yet — wire Sentry / PostHog later. For now: use `logging.getLogger(__name__)` with structured `extra={"request_id": ..., "user_id": ...}` fields. Do not add `print()`.

---

## 3. Your module's integration points

### Module 4 — `backend/providers` (the abstraction layer)

- Create `contexthub_backend/providers/{base.py,anthropic.py,voyage.py,registry.py}`.
- `LLMProvider` ABC: at minimum `async def complete(prompt, *, response_format="json", max_tokens, temperature) -> LLMResponse` where `LLMResponse` carries `text`, `model`, `prompt_version`, `input_tokens`, `output_tokens`, `latency_ms`, `cost_usd`, `failure_reason`.
- `EmbeddingProvider` ABC: `async def embed(texts: list[str], *, input_type: Literal["document","query"]) -> EmbeddingResponse(vectors, model, input_tokens, latency_ms, cost_usd)`.
- Concrete impls: `AnthropicProvider` (Claude Haiku 4.5, `claude-haiku-4-5-20251001`), `VoyageEmbeddingProvider` (`voyage-3-large`, 1024d). Keep API keys in `settings` via `pydantic-settings`.
- Prompt-version registry: a simple dict or file-backed registry mapping `prompt_version` → system prompt text. The summarizer module will depend on this.
- Tests: contract tests with recorded cassettes (`vcrpy`) + one live-call test nightly.
- **Exports downstream consumers will need:** `LLMProvider`, `EmbeddingProvider`, `get_llm_provider()`, `get_embedding_provider()` (DI factories reading `settings`).

### Module 5 — `backend/ingress`

- FastAPI middleware / dependency chain for request validation. Assumes `get_current_user` already resolved identity.
- Responsibilities: per-user rate limiting (Redis, via ARQ's Redis or a sibling connection), idempotency-key check against `pushes.idempotency_key`, request-size caps, ch.v0.1 schema validation on push bodies, sensitive-data scrub hook (extension-side scrub is primary; server-side is a second line).
- **Integration:** add as a FastAPI dependency on push/pull routes; don't monkey-patch the app. Rate-limit keys per decisions log: `rl:{user_id}:{bucket}:{window}` in Redis, TTL = window.
- **Do not** create a Postgres `rate_limit_counters` table. Rate limits live in Redis (decisions log 2026-04-17).

### Module 6 — `backend/summarizer`

- One function: `async def summarize_push(conversation: ConversationV0, *, llm: LLMProvider, prompt_version: str) -> ThreeLayerSummary`.
- Single LLM call, JSON-output mode, structured-block sub-schema as the output contract. Strict JSON parsing + Pydantic validation + bounded retries + plain-text commit-message fallback (see decisions log "Single-call three-layer summary flagged as known v0 quality risk").
- Writes a row to `summaries` per layer. Fills all quality metadata: `model`, `prompt_version`, `latency_ms`, `input_tokens`, `output_tokens`, `cost_usd`, `failure_reason`.
- `content_markdown` for `structured_block` layer = `render_structured_block(validated_block)`. For `commit_message`, it's the text itself. For `raw_transcript`, it's null (content in Storage).
- **Do not** call Anthropic directly — depend on `LLMProvider` from Module 4.

### Module 7 — `backend/embeddings`

- `async def embed_summary(summary_id: UUID, *, embedder: EmbeddingProvider, session: AsyncSession) -> None`.
- Reads `summaries.content_markdown`, calls `embedder.embed([text], input_type="document")`, writes to `summary_embeddings` (one row per summary).
- `summary_embeddings.embedding` column is already `vector(1024)`; the HNSW index is already built.
- **Do not** call Voyage directly — depend on `EmbeddingProvider` from Module 4.

### Module 8 — `backend/storage` + ARQ jobs

- ARQ worker setup: `contexthub_backend/jobs/{worker.py,registry.py,jobs/*.py}`. Redis URL from `settings`. Job contract per decisions log: exponential backoff + jitter, DLQ on permanent failure, status transitions on `pushes.status`.
- Jobs to register: `summarize_push(push_id)`, `embed_summary(summary_id)`, `purge_soft_deleted_pushes()`, `purge_failed_pushes()`, `purge_audit_log()`, `purge_revoked_tokens()` (the `purge_*` family per retention policy §13 — skeletons acceptable in v0; full logic can arrive with Module 17).
- Push writer: `POST /v1/workspaces/{id}/pushes` creates the `pushes` row (status=pending), writes the raw transcript to Supabase Storage, creates the `transcripts` row, enqueues `summarize_push`. Returns `202 {push_id, status: "pending"}`.
- **Integration:** routes depend on Module 3 auth, Module 4 providers, Module 5 ingress, Module 6 summarizer, Module 7 embeddings. This is the glue.

---

## 4. Definitely-do / definitely-don't

**Do:**
- Import the shared renderer for structured-block markdown. There is exactly one of them, in two language bindings.
- Raise `AuthError` / `ForbiddenError` / `NotFoundError` / `ValidationError` from `api.errors` — the middleware formats the response.
- Use `get_rls_session` for all user-scoped queries. If you find yourself using `get_db_session` directly, stop and justify it.
- Add an integration test asserting user-A-vs-user-B isolation for any new user-scoped endpoint.
- Register your new pytest files in the CI workflow (`contexthub/.github/workflows/ci.yml`).

**Don't:**
- Don't import `anthropic`, `voyageai`, or any LLM/embedding SDK from outside Module 4.
- Don't create a Postgres `rate_limit_counters` table. Redis.
- Don't use `asyncio.create_task` for long-running work. ARQ.
- Don't write a second markdown renderer. Import the shared one.
- Don't regenerate `packages/shared-types/src/db-types.ts` by hand — if you add a table, update `db-types.ts` AND `db/models.py` together.
- Don't widen RLS policies just because a test is annoying. Fix the test.
- Don't touch `short_id.py` without reading the security note in §6 below.

---

## 5. CI and local-dev setup

### Local dev loop

```bash
# from contexthub/
cd backend
docker-compose up -d                      # pgvector + redis
psql -h localhost -U postgres -d contexthub_test -f sql/auth_stub.sql
uv sync --all-extras --dev
uv run --package contexthub-backend python -m alembic upgrade head
uv run --package contexthub-backend python scripts/gen_fixtures.py   # or seed_dev.py for a lighter dataset
# run your module's tests
uv run --package contexthub-backend pytest tests/test_your_module_unit.py -v
# integration:
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/contexthub_test \
SUPABASE_JWT_SECRET=test-secret-not-for-production-at-least-32-bytes \
uv run --package contexthub-backend pytest tests/test_your_module_api.py -m integration -v
```

There is **no** `make` / `just` task yet — this is tracked as a "Left for later" in VALIDATION.md Module 2 entry. Adding one is a reasonable side-quest.

### Extending CI

`contexthub/.github/workflows/ci.yml` has three relevant jobs:

- `python` — add your unit-test file to the `backend unit tests` step (the `pytest tests/test_short_id.py tests/test_models.py tests/test_auth_unit.py` line).
- `migrations` — add your integration-test file to the `run migration + rls + auth api tests` step.
- `codegen-drift` — only touch if you add schemas.

CI runs on **PRs to `main` only**, not every push (decisions log). Don't switch this to `push:` triggers.

---

## 6. Known security notes inherited from Modules 1–3

These do not block v0 but must be closed before beta (they're in `TODO.md` under `(sec)`):

- **`contexthub/backend/contexthub_backend/db/short_id.py:19`** — UUIDv7 randomness uses `random.getrandbits` instead of `secrets.randbits`. Python's `secrets` module is the stdlib cryptographically-strong RNG (hardened against prediction). `random` is a Mersenne Twister and explicitly documented as "not suitable for security purposes." Swap to `secrets.randbits(12)` / `secrets.randbits(62)`. Trivial change; tracked in `TODO.md` pre-launch security.
- **`auth/tokens.py`** — `last_used_at` is updated in-memory and flushed at transaction commit. If the request fails between auth and commit, the update is lost. Acceptable v0 granularity.
- **`GET /v1/tokens`** — no pagination. Fine at ≤10 tokens/user; add cursor pagination pre-launch.
- **`GET /v1/me`** — returns null profile fields for a just-signed-in user who hasn't got a `profiles` row yet. Needs an on-first-login upsert pre-launch.
- **Direct per-table RLS tests** exist only for `workspaces`, `pushes`, `profiles`, `api_tokens`. `summary_embeddings`, `transcripts`, `push_tags`, `push_relationships`, `summary_feedback` are covered only transitively. Security-pass item.

---

## 7. When your module is done

**Before you merge / commit, update these four docs in the same change:**

1. **`ARCHITECTURE.md`** — if your module changed the data model, API surface, or a block in §4, reflect it there. Don't let the doc drift from reality.
2. **`PLAN.md`** — add a "Shipped YYYY-MM-DD: Module N — <name>" line in the Active work section; advance "Next session" to your successor. Add any new decisions to the Decisions log with date + context + rationale + consequences.
3. **`TODO.md`** — mark your module-row `[x]` and move it to the Done section with a line-by-line delivery list (follow the Module 2/3 template). Add any new pre-launch items your work uncovered.
4. **`VALIDATION.md`** — append a new `## Module N — <name> · <date>` entry with environment, checks table, known warnings, left-for-later. The template is at the bottom of that file.

**Then:** open a PR titled `Ship Module N: <thing>`, not a direct push to `main`. Let Aalaap review before it lands. (Modules 2/3 went in as direct commits; we're tightening that going forward.)

---

## 8. Quick reference — file paths

| Thing | Path |
| ----- | ---- |
| JSON Schemas | `contexthub/packages/interchange-spec/schemas/*.json` |
| Py interchange binding | `contexthub/packages/interchange-spec/python/contexthub_interchange/` |
| TS interchange binding | `contexthub/packages/interchange-spec/src/` |
| Shared renderer (Py) | `contexthub_interchange.renderer.render_structured_block` |
| Shared renderer (TS) | `@contexthub/interchange-spec` → `renderStructuredBlock` |
| ORM models | `contexthub/backend/contexthub_backend/db/models.py` |
| Alembic migrations | `contexthub/backend/alembic/versions/` |
| Auth deps | `contexthub/backend/contexthub_backend/auth/dependencies.py` |
| Error envelope | `contexthub/backend/contexthub_backend/api/errors.py` |
| FastAPI app factory | `contexthub/backend/contexthub_backend/api/app.py` |
| Config | `contexthub/backend/contexthub_backend/config.py` |
| Test fixtures | `contexthub/backend/tests/conftest.py` |
| CI workflow | `contexthub/.github/workflows/ci.yml` |
| Fixture generator | `contexthub/backend/scripts/gen_fixtures.py` |
| Dev seed | `contexthub/backend/scripts/seed_dev.py` |
| Local stack | `contexthub/backend/docker-compose.yml` |
| Auth stub (local/CI) | `contexthub/backend/sql/auth_stub.sql` |
