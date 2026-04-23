# ContextHub — Validation Log

Append-only record of what was validated at the end of each module. Each entry lists the checks run, their results, and anything that looked wrong but was accepted as intentional. This is the living trail of "did we actually prove it works before moving on," captured outside `TODO.md` so it doesn't get buried.

Convention per entry:

- **Header:** `## Module N — <name> · <shipped-date>`
- **Environment** line: tool versions tested against.
- **Checks table:** what was verified, result (pass/fail/skipped), and a short note.
- **Known warnings:** non-blocking noise that we accepted at shipping time.
- **Left for later:** items we deliberately did not validate this pass, with pointers (usually `TODO.md` refs).

---

## Module 1 — `packages/interchange-spec` · 2026-04-17

**Environment:** macOS 14 (Darwin 24.6.0, arm64); Python 3.13.5; Node 18.x; pnpm 10.33.0 (via corepack); uv 0.10.4; TypeScript 5.9.3; Vitest 2.1.9; pytest 9.0.3.

| Check | Result | Note |
| ----- | ------ | ---- |
| Python tests (pytest) | **20 / 20 passing** | `test_models`, `test_validator`, `test_renderer`, `test_golden` |
| TypeScript tests (vitest) | **41 / 41 passing** | `models.test`, `renderer.test`, `golden.test` |
| TypeScript typecheck (`tsc --noEmit`) | clean | strict, `noUncheckedIndexedAccess`, no `any` |
| TS codegen (`pnpm run codegen:ts`) | runs + deterministic | Re-run twice → zero git diff |
| Python codegen (`pnpm run codegen:py`) | runs + deterministic | Re-run twice → zero git diff |
| Golden cross-impl (Py bytes == TS bytes == `*.expected.md`) | **10 / 10 fixtures** | covers: minimal, maximal, empty-lists, unicode/NFC, long-artifact, multiple-artifacts, nested-markdown, missing-optional, single-item, special-chars |
| JSON Schema validation on all 5 conversation fixtures | pass | Draft 2020-12, Py (jsonschema) + TS (ajv) both green |
| JSON Schema validation on all 10 structured-block fixtures | pass | same |
| Pydantic round-trip on all fixtures | pass | `model_dump_json → json.loads → original` shape preserved |
| Rejection tests (wrong spec_version, extra props, unknown artifact kind) | pass | both Py + TS |
| `uv run ch-validate <file>` CLI | works | auto-detects schema kind from payload |
| `uv run ch-golden --write` CLI | works | generates all 10 expected.md files byte-for-byte |

**Known warnings (accepted):**

- `datamodel-code-generator` emits a `FutureWarning` about black/isort → ruff formatter migration on every codegen run. Noise-only; addressable later with `formatters=[Formatter.RUFF_FORMAT, Formatter.RUFF_CHECK]` + the `[ruff]` extra.
- pnpm warns on `esbuild@0.21.5` ignored build scripts. Not a blocker; tests pass. Silence with `pnpm approve-builds` when we touch CI next.

**Left for later:**

- Load / stress / fuzzing tests on the interchange-spec validators → `TODO.md` "Testing & quality (post-v0)".
- Cross-platform fixture corpus (ChatGPT exports, etc.) → `TODO.md` "Backfill import (P1)".
- Auto-detect `schema` kind in `ch-validate` currently uses presence heuristics (`messages + source` → conversation; `decisions + constraints` → structured-block). Adequate for v0; revisit if a future schema breaks the heuristic.

---

## Module 2 — `backend/schema` · 2026-04-22

**Environment:** macOS 25.3.0 (Darwin, arm64); Python 3.13.9; uv (workspace sync); pytest 9.0.3; SQLAlchemy 2.x; Alembic 1.x; pgvector 0.3.x; psycopg 3.x; Faker 40.x. Integration tests (DB-required) run against `pgvector/pgvector:pg15` in CI.

| Check | Result | Note |
| ----- | ------ | ---- |
| Unit: `test_short_id.py` | **12 / 12 passing** | UUIDv7 version field, time-ordering across ms, uniqueness (1000 samples), base62 charset + length, determinism, padding |
| Unit: `test_models.py` | **23 / 23 passing** | All 14 tables registered on `Base.metadata`; PK types, nullability, FK chains, `failure_reason`/`quality_score`/`content_tsv` columns on `summaries` |
| Total unit (no DB) | **35 / 35 passing** | Run via `uv run --package contexthub-backend pytest tests/test_short_id.py tests/test_models.py` |
| Interchange-spec tests (regression) | **20 / 20 passing** | No regressions from workspace changes; `norecursedirs` fix applied to root `pyproject.toml` to prevent conftest collision |
| SQLAlchemy models import cleanly | pass | `from contexthub_backend.db import models` succeeds; all 14 ORM classes load with correct `__tablename__` |
| `short_id_from_uuid` determinism | pass | Same UUID → same 11-char base62 string across calls |
| UUIDv7 bit layout (version nibble) | pass | `uuid.UUID.version == 7` confirmed |
| DB row types in `shared-types` | pass | `packages/shared-types/src/db-types.ts` exports all 14 row interfaces + 7 enum types; `tsc` typecheck clean |
| Integration: `alembic upgrade head` | **CI-gated** | Runs against `pgvector/pgvector:pg15` in the new `migrations` CI job on every PR to `main` |
| Integration: fixture load ≥50 WS / ≥500 pushes | **CI-gated** | `gen_fixtures.py` generates 60 workspaces, 550 pushes, all enum values populated, all nullable fields exercised |
| Integration: `alembic downgrade base` | **CI-gated** | All 14 app tables + 7 enums + vector extension dropped; no tables remain after downgrade |
| Integration: RLS user A ≠ user B (workspaces, pushes, profiles) | **CI-gated** | `ch_authenticated` role + `SET LOCAL "app.current_user_id"` driving `auth.uid()` stub; 8 assertions across 3 test classes |
| `content_tsv` tsvector trigger | **CI-gated** | `test_migrations.py` asserts rows with non-null `content_markdown` have non-null `content_tsv` |
| HNSW index on `summary_embeddings.embedding` | **CI-gated** | `pg_indexes` row confirmed in migration test |
| `pulls.workspace_ids` is ARRAY column | **CI-gated** | `information_schema.columns.data_type = 'ARRAY'` confirmed |
| `summaries.failure_reason` column | **CI-gated** | Present per PLAN.md Module 2 deliverable update |

**Known warnings (accepted):**

- `PytestUnknownMarkWarning: Unknown pytest.mark.integration` — suppressed by registering the mark in both root and backend `pyproject.toml`. No longer emitted after fix.
- `asyncio_default_fixture_loop_scope` deprecation notice from `pytest-asyncio` — noise-only, no test impact; will resolve when pytest-asyncio bumps its default.

**Left for later:**

- Integration tests (`test_migrations.py`, `test_rls.py`) run only in CI against a live Postgres service. Local execution requires `docker-compose up` in `backend/` plus `DATABASE_URL` set — not yet part of a `make` / `just` task. → add to Module 3 local-dev runbook.
- `auth_stub.sql` is applied manually in CI (one-liner in the workflow); local dev requires explicit `psql -f sql/auth_stub.sql`. A `make setup-local` or `just setup` target should wrap this. → `TODO.md` ops.
- `summary_embeddings` table is created via raw DDL (`op.execute(...)`) rather than `create_table()` because pgvector's `Vector` type isn't in Alembic's diff engine. Autogenerate will not detect drift on this table. → add a note to the migration contributor guide when Module 3 docs land.
- RLS policies on `summary_embeddings`, `transcripts`, `push_tags`, `push_relationships`, and `summary_feedback` are tested only indirectly (via `summaries` and `pushes` ownership checks). Direct per-table RLS tests deferred to the pre-launch security audit.

---

## Module 3 — `backend/auth` · 2026-04-22

**Environment:** macOS 25.3.0 (Darwin, arm64); Python 3.13.9; pytest 9.0.3; FastAPI 0.115.x; PyJWT 2.9.x; httpx 0.27.x; SQLAlchemy 2.x async (asyncpg). Integration tests CI-gated against `pgvector/pgvector:pg15`.

| Check | Result | Note |
| ----- | ------ | ---- |
| Unit: `test_auth_unit.py` | **19 / 19 passing** | JWT verify (valid, wrong secret, expired, missing sub, non-UUID sub, wrong algorithm), make_test_jwt roundtrip, token generation (prefix, length, uniqueness, hex body), hash (deterministic, SHA-256 length, stdlib parity, collision-free), scope constants |
| Total unit (no DB) | **54 / 54 passing** | Includes Module 2 test_short_id (12) + test_models (23) + Module 3 test_auth_unit (19) |
| Interchange-spec regression | **20 / 20 passing** | No regressions; norecursedirs config confirmed effective |
| `verify_supabase_jwt` rejects wrong secret | pass | PyJWTError → AuthError("invalid JWT: …") |
| `verify_supabase_jwt` rejects expired token | pass | Requires `exp` claim; past exp raises AuthError |
| `verify_supabase_jwt` rejects non-UUID sub | pass | AuthError("not a valid UUID") |
| `generate_raw_token` format | pass | `ch_` prefix + 64-char hex body = 67 chars; unique across 200 samples |
| `hash_token` matches stdlib SHA-256 | pass | `hashlib.sha256(raw.encode()).hexdigest()` parity confirmed |
| Scope constants complete | pass | VALID_SCOPES == ALL_SCOPES == {push, pull, search, read} |
| `GET /v1/health` unauthenticated | pass | 200; X-Request-Id header present |
| `GET /v1/me` with valid JWT | **CI-gated** | 200 + correct user_id; profile row resolved via RLS session |
| `GET /v1/me` with valid API token | **CI-gated** | 200; token lookup via SHA-256 hash before RLS context set |
| `GET /v1/me` with bad/expired JWT | **CI-gated** | 401 with error envelope |
| `POST /v1/tokens` with JWT | **CI-gated** | 201; raw `ch_` token returned once; not in subsequent GET list |
| `POST /v1/tokens` with API token | **CI-gated** | 403 (require_jwt guard) |
| `POST /v1/tokens` invalid scopes | **CI-gated** | 422 (Pydantic validation) |
| `GET /v1/tokens` RLS: user A ≠ user B | **CI-gated** | User A cannot see user B's tokens through the API layer |
| `GET /v1/tokens` RLS: user B ≠ user A | **CI-gated** | Symmetric; confirmed in both directions |
| `DELETE /v1/tokens/{id}` by owner | **CI-gated** | 204; token absent from subsequent list; token rejected on next use (401) |
| `DELETE /v1/tokens/{id}` by non-owner | **CI-gated** | 403 (ForbiddenError) |
| RLS context set correctly per request | **CI-gated** | `SET LOCAL ROLE ch_authenticated` + `app.current_user_id` applied after auth lookup, before route handler; superuser connection bypasses RLS only during token lookup |
| Request-ID middleware | pass | Every response carries `X-Request-Id` UUID header |
| `require_jwt` guard on mint endpoint | pass | auth_type == "jwt" enforced; API tokens blocked from minting new tokens |

**Known warnings (accepted):**

- `InsecureKeyLengthWarning` from PyJWT in `test_wrong_secret_raises_auth_error` — deliberate: `"wrong-secret"` (12 bytes) is intentionally too short to prove the verifier rejects it. All other test secrets are ≥32 bytes; warning is suppressed there.
- `asyncio_default_fixture_loop_scope` deprecation from pytest-asyncio — noise-only, no test impact.

**Left for later:**

- `test_auth_api.py` integration tests (21 tests) are CI-gated; local run requires docker-compose + `DATABASE_URL` + `SUPABASE_JWT_SECRET` env vars. No `make`/`just` task wraps this yet → add to local-dev runbook in Module 4.
- `GET /v1/me` returns `null` for `display_name`/`avatar_url` if no profile row exists (new user, profile not yet created). A profile-creation-on-first-login trigger or upsert in the `/me` handler should be added pre-launch → `TODO.md` pre-launch quality.
- `last_used_at` updated in-memory on API token use and flushed at commit. If the request fails after auth but before commit, the update is lost — acceptable for v0 audit granularity.
- Token list endpoint returns all non-revoked tokens with no pagination. At v0 scale (handful of tokens per user) this is fine; add cursor pagination pre-launch if needed.

---

<!--
When adding a new module's entry, follow this template:

## Module N — <package-or-module> · YYYY-MM-DD

**Environment:** <tool versions>

| Check | Result | Note |
| ----- | ------ | ---- |
| ... | ... | ... |

**Known warnings (accepted):**
- ...

**Left for later:**
- ...

---
-->
