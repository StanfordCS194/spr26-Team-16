# ContextHub — Architecture

**Status:** living document. Last updated 2026-04-23 (rev. 3, post-Modules 2/3 pass).
**Owner:** Aalaap Hegde.
**Scope of this doc:** v0 system design. Everything P1+ lives in `PLAN.md` parking lot.
**Implementation state:** Modules 1, 2, 3 shipped. Module 4 (providers) is next. Integration handshake for incoming contributors lives in `INTEGRATION.md`.

---

## 1. Product overview (v0)

ContextHub is a version control system for LLM conversations. A user finishes a conversation on Claude.ai, clicks the extension, and the system generates a three-layer summary (commit message, structured context block, raw transcript), stores it in the user's workspace, indexes it for semantic search, and lets the user pull it back into a future conversation at a chosen resolution.

**v0 is Claude.ai-only, single-user.** Cross-platform, teams, backfill import, and automatic topic segmentation are deferred but the architecture must not foreclose them. See §9 for the extension adapter pattern and §4 for relationship edges in the schema.

**Project identity:** ContextHub is the product; XARPA is the team codename (Stanford CS194 `spr26-Team-16`). Same underlying effort — the handwritten XARPA architecture notes directly inform ContextHub's internals.

**Success criterion for v0:** the push → search → pull loop runs end-to-end for 50–100 beta users against a real Supabase project deployed to Railway/Vercel, with summary-quality feedback and observability wired in.

---

## 2. Stack summary

| Layer         | Choice                                                                                 | Notes                                                                                          |
| ------------- | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Backend       | Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x + Alembic, uv                       | `uv` for deps + lockfile; async SQLAlchemy.                                                    |
| Database      | Supabase (Postgres 15 + pgvector + Auth + Storage)                                     | One Supabase project per env (local/staging/prod).                                             |
| Cache / queue | **Redis** (Upstash on Railway, `redis:7` in docker-compose)                            | Backs ARQ job queue and rate-limit counters. New in v0.                                        |
| Jobs          | **ARQ** (async Redis-backed task queue)                                                | ARQ worker runs as its own Railway service; job contracts + retries + DLQ per §4.1.            |
| Deploy        | Railway (backend API + ARQ worker), Vercel (dashboard)                                 | From day one. `main` → staging, tagged release → prod.                                         |
| Local dev     | docker-compose + `supabase start`                                                      | Extension loaded unpacked; backend + worker on localhost; dashboard on `localhost:3000`.       |
| Extension     | TypeScript + React, Manifest V3, Chromium-compatible                                   | Content script + background service worker + sidebar iframe.                                   |
| Dashboard     | **Next.js 15 App Router** + TypeScript                                                 | SSR for auth-gated pages, Vercel-native, room for marketing pages later.                       |
| Monorepo      | pnpm workspaces                                                                        | Packages: `extension`, `dashboard`, `shared-types`, `interchange-spec`.                        |
| Typegen       | **`datamodel-code-generator`** (Pydantic → TS)                                         | `pnpm run codegen` regenerates `packages/shared-types`; CI fails on drift.                     |
| LLM / embed   | **`LLMProvider`** + **`EmbeddingProvider`** abstractions                               | v0 impls: Anthropic Claude Haiku 4.5 (summarization), Voyage `voyage-3-large` (1024d) (embed). |
| Observability | Sentry (errors), Python `logging` JSON formatter, PostHog (product)                    | Request ID propagated from extension → API → worker → logs.                                    |
| Secrets       | Railway/Vercel env vars; Supabase service key server-side only                         | Flagged as security surfaces in `TODO.md`.                                                     |

---

## 3. Distribution & access model

- **Chrome Web Store** distribution for the extension. **Unlisted** for beta (installable via direct link, auto-update enabled); public listing is a post-beta step.
- **Dashboard** is the control plane: sign-in, workspace management, API token mint/revoke, browse, search, pull-from-dashboard.
- **Backend** API is public at `api.contexthub.dev`, authenticated on every request.
- **Auth:**
  - Dashboard → Supabase Auth (email magic link). Supabase JWT used on dashboard-origin API calls.
  - Extension → long-lived API token, minted on the dashboard's "Connect extension" page, stored in `chrome.storage.local`, sent as `Authorization: Bearer ch_<token>`. Revocable from the dashboard. Token ties back to a `user_id` and carries a scope bitset (v0: `push`, `pull`, `search`, `read`).
- **One account, many tokens.** Each device/browser profile gets its own token so users can revoke one without burning the rest.
- **Workspace URLs:** `app.contexthub.dev/w/{short_id}`. `short_id` is a base62-encoded UUIDv7 suffix (~11 chars); globally unique; not tied to a username (no username concept in v0).
- **Pairing-code UX** (open question §11): today the user copy-pastes the token; post-v0 we want a 6-digit pairing code flow so the extension never touches raw JWTs.

---

## 4. System architecture — block view (XARPA-inspired)

The push and pull pipelines compose from the same block primitives. Each block is a module with a typed interface, independent tests, and explicit inputs/outputs. Request IDs flow through every block for tracing.

### 4.1 Push pipeline (async via ARQ)

```
SYNC LEG — returns fast, writes a pending push row and enqueues a job.

[Extension: claude-adapter]                Ingression                         Job enqueue
  ├─ DOM scrape conversation  ────────▶    [api.ingress]              ──▶     [ARQ: enqueue 'summarize_push']
  ├─ Normalize to ch.v0.1                  ├─ Auth (token)                    └─ pushes row: status='pending'
  └─ POST /v1/pushes                       ├─ Rate limit (Redis)
                                           ├─ Sensitive-data scrub
                                           ├─ Schema validate (ch.v0.1)
                                           ├─ Idempotency key
                                           └─ Return 202 {push_id, status:'pending'}

ASYNC LEG — ARQ worker processes the job; extension polls GET /v1/pushes/{id}.

[ARQ worker]                               Processor                          Memory Tiers                         Status
  ├─ Job: summarize_push(push_id)  ──▶     [api.summarizer]            ──▶    [api.storage]                   ──▶  status='processing'
  │                                        ├─ Intent/topic tag                ├─ summaries rows (JSON auth.)       → status='ready'
  │                                        ├─ Three-layer via LLMProvider     │  + content_markdown derived         on success, or
  │                                        │  (single call, JSON output,      ├─ Enqueue 'embed_summary' jobs       status='failed'
  │                                        │  structured-block sub-schema)    ├─ transcripts → Supabase Storage     with failure_reason
  │                                        └─ Quality metadata                │  (SHA-256)
  │                                           (model, prompt_version,         └─ audit_log row
  │                                           latency, tokens, cost)
  └─ Job: embed_summary(summary_id) ──▶     [api.embeddings]            ──▶    summary_embeddings (pgvector HNSW)
                                            └─ EmbeddingProvider.embed()

Retries: ARQ with exponential backoff + jitter. DLQ on permanent failure.
```

Implementation note (2026-04-23): the shipped ingress path is `POST /v1/workspaces/{id}/pushes` in the shared FastAPI app factory (`api.app.create_app`) and uses Module 3 dependencies (`get_current_user`, `get_rls_session`) so all workspace/push writes are RLS-scoped. The sync leg writes both `pushes` (pending) and `transcripts`, then enqueues `summarize_push`.

### 4.2 Pull pipeline (sync)

```
[Dashboard or Extension]           Ingression           Retrieval                   Context Builder              Egression
  ├─ Search query or push_id  ──▶  [api.ingress]  ──▶   [api.search]         ──▶   [api.context_builder]  ──▶   [api.egress]
  ├─ Resolution choice             ├─ Auth               ├─ Vector + BM25 hybrid     ├─ Resolution selector        ├─ ACL check (workspace
  │  (commit|block|transcript)     ├─ Rate limit (Redis) │  over summaries           │  (layer pick)               │  ownership)
  └─ GET /v1/search or             └─ Param validate     ├─ Optional transcript      ├─ Multi-pull concat +        ├─ Audit log (pull event)
     POST /v1/pulls                                      │  full-text (toggle)       │  ordering                   ├─ Format for target
                                                         └─ Rank + preview highlights├─ Token budget estimator     │  platform (markdown via
                                                                                     ├─ System-framing prompt       │  shared renderer)
                                                                                     │  prepender                   └─ Return formatted
                                                                                     └─ Provenance footer              payload + provenance
```

### 4.3 Mapping to XARPA philosophy (explicit)

| XARPA block             | ContextHub v0 analogue                                                                          | Deferred to v1+                                             |
| ----------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Data ingressor          | Extension adapter + `api.ingress`                                                               | Rate-limit tuning, per-platform adapters                    |
| Processor (LLaMA)       | `api.summarizer` (Claude Haiku, prompt-versioned, JSON-output)                                  | Fine-tuned small model; intent classifier                   |
| Query cache             | Out of scope v0; Redis available if/when we add it                                              | Real query-cache keyed on normalized query                  |
| Episodic graph DB       | `push_relationships` table present in schema, unused in v0 logic                                | Graph traversal on pull                                     |
| Org memory              | Workspace-scoped pushes + pgvector index                                                        | Cross-workspace semantic memory (teams, v3)                 |
| Aggregator              | `api.search` hybrid ranker                                                                      | Parallel memory search across tiers                         |
| Context builder + conf. | `api.context_builder` with token-budget + provenance; quality metadata per summary              | 5-gate classifier, claim extraction, gap filler             |
| Egression               | `api.egress` auth/sanitize/audit; extension `injector` formats for Claude.ai                    | Per-platform egress formatters                              |

The XARPA "5 gates" are **not** built in v0. We ship the *scaffolding* — quality metadata and provenance fields on every summary — so a gate classifier can be added later without schema migration.

---

## 5. Data model

All tables in Supabase Postgres. UUID v7 primary keys (time-ordered, index-friendly). `created_at`/`updated_at`/`deleted_at` on every user-facing table. RLS enabled per-table with policies keyed on `auth.uid()`.

### 5.1 Tables

```
users                          # managed by Supabase Auth (auth.users). App-side profile in `profiles`.
profiles
  user_id PK FK→auth.users
  display_name, avatar_url
  created_at

api_tokens
  id PK
  user_id FK→auth.users
  name                          # human label ("Chrome MBP", "Chrome work")
  token_hash                    # sha256 of bearer token; raw token shown once on mint
  scopes                        # int bitset or text[]; v0: push, pull, search, read
  last_used_at, created_at, revoked_at

workspaces
  id PK                         # UUIDv7; URL path uses base62 suffix as short_id
  user_id FK→auth.users         # v0: single-owner; v3 adds memberships table
  name, slug                    # slug is cosmetic (display/breadcrumb); per-user unique; NOT in URL
  settings_json                 # per-workspace knobs (default resolution, model prefs)
  created_at, updated_at, deleted_at

pushes
  id PK
  workspace_id FK
  user_id FK
  source_platform               # enum: 'claude_ai' (v0); 'chatgpt', 'gemini' reserved
  source_url                    # Claude.ai conversation URL if available
  source_conversation_id        # platform-native ID if parseable
  interchange_version           # e.g. 'ch.v0.1' — references interchange_format_versions
  title                         # optional user-set title
  commit_message                # short searchable description, editable
  status                        # enum: pending, processing, ready, failed
  failure_reason
  idempotency_key               # unique per user; prevents duplicate pushes
  created_at, updated_at, deleted_at

summaries
  id PK
  push_id FK
  layer                         # enum: 'commit_message', 'structured_block', 'raw_transcript'
  content_json jsonb            # AUTHORITATIVE. Shape per layer:
                                #   commit_message → {"text": "..."}
                                #   structured_block → validated against structured-block sub-schema
                                #   raw_transcript → {"storage_path": "..."} (content in Storage)
  content_markdown text         # DERIVED by shared renderer (Py). Recomputed on write.
                                # Stored for search (BM25 tsvector) and injection payload speed.
  content_tsv                   # generated tsvector from content_markdown for BM25
  model                         # e.g. 'claude-haiku-4-5'
  prompt_version                # e.g. 'summarize_v1.2'
  latency_ms, input_tokens, output_tokens, cost_usd
  quality_score                 # float, null until feedback received
  superseded_by FK→summaries    # editable summaries keep history
  created_at

summary_embeddings
  summary_id PK FK
  embedding vector(1024)        # pgvector; Voyage voyage-3-large
  embedding_model               # 'voyage-3-large' in v0
  created_at
  # HNSW index on (embedding) with cosine

transcripts
  push_id PK FK
  storage_path                  # Supabase Storage key
  sha256                        # integrity + dedupe
  size_bytes
  message_count
  created_at

tags
  id PK
  workspace_id FK
  name, slug
  created_at

push_tags
  push_id, tag_id PK

push_relationships              # future-proof graph edges; read in v0, unused by logic
  id PK
  from_push_id FK
  to_push_id FK
  relation_type                 # enum: 'continuation', 'reference', 'supersession'
  created_at

summary_feedback
  id PK
  summary_id FK
  user_id FK
  score                         # 1-5
  comment
  created_at

pulls                           # audit + analytics of pull events
  id PK
  user_id FK
  target_platform               # 'claude_ai' in v0
  origin                        # 'extension' | 'dashboard'
  resolution                    # 'commit_message' | 'structured_block' | 'raw_transcript'
  push_ids text[]               # multi-pull support
  workspace_ids text[]          # parallel array to push_ids for cross-workspace analytics/audit
  token_estimate
  created_at

audit_log                       # cross-cutting egress audit
  id PK
  user_id FK
  action                        # e.g. 'push.create', 'pull.inject', 'token.mint'
  resource_type, resource_id
  request_id, ip, user_agent
  metadata_json
  created_at

interchange_format_versions     # schema-versioning for the portable conversation spec
  version PK                    # 'ch.v0.1'
  json_schema                   # the spec itself
  created_at, deprecated_at

# Rate-limit counters live in Redis (key: 'rl:{user_id}:{bucket}:{window}', value: count, TTL: window).
# No rate-limit table in Postgres.
```

### 5.2 Indices (v0 essentials)

- `pushes (workspace_id, created_at desc)` — dashboard listing.
- `pushes (user_id, idempotency_key)` unique — push dedupe.
- `summaries (push_id, layer)` unique.
- `summaries USING GIN(content_tsv)` — BM25 fallback.
- `summary_embeddings USING hnsw(embedding vector_cosine_ops)` — semantic search.
- `audit_log (user_id, created_at desc)`.
- `api_tokens (token_hash)` unique — auth lookup hot path.

### 5.3 Future-proofing decisions

- `workspaces.user_id` stays nullable-eligible via a future `memberships` table for teams; dropping the direct FK later is a clean migration.
- `push_relationships` ships empty but present so edges can be written later without migration.
- `interchange_version` on every push lets us evolve the spec without breaking old data.
- `summaries.superseded_by` lets users edit the structured block without losing history — required for the summary-quality eval set.
- `summaries.content_json` is authoritative; `content_markdown` is a rendered projection. Renderer change → backfill job, not migration.

### 5.4 Implementation notes (post-Module 2)

- Short-IDs: `contexthub_backend/db/short_id.py` encodes the lower 64 bits of a UUIDv7 as an 11-char base62 string. The UUIDv7 generator currently uses `random.getrandbits` for timestamp-tail randomness; this is **not cryptographically strong** and is tracked as a pre-launch security fix (swap to `secrets.randbits`). Collision risk at v0 scale remains negligible, so this is not a blocker for v0 implementation work but must close before beta.
- `summary_embeddings` is created via raw DDL in `001_initial_schema.py` because Alembic's autogenerate does not understand pgvector's `Vector` type. Any future schema change on that table must be hand-edited into a migration; autogenerate will not detect drift.

---

## 6. Module breakdown (implementation roadmap)

Modules are the unit of session work. Order below is the expected implementation sequence. 1–17 = v0 core; 18 = stretch.

| # | Module | Status | Purpose | Inputs | Outputs | Depends on |
| - | ------ | ------ | ------- | ------ | ------- | ---------- |
| 1 | `packages/interchange-spec` | **✅ shipped 2026-04-17** | JSON Schema + Pydantic for `ch.v0.1` + structured-block sub-schema; codegen (datamodel-code-generator → TS types); shared markdown renderer in Py + TS with golden-fixture cross-impl tests | — | `ch.v0.1` schemas, generated TS types, renderer, validator CLI | — |
| 2 | `backend/schema` | **✅ shipped 2026-04-22** | SQLAlchemy models + Alembic migrations for §5; RLS policies; seed data | interchange-spec | DB + generated TS types | 1 |
| 3 | `backend/auth` | **✅ shipped 2026-04-22** | Supabase JWT verifier + API token mint/verify/revoke; FastAPI dependency chain (`get_db_session`, `get_current_user`, `get_rls_session`, `require_jwt`); error envelope; `/v1/health`, `/v1/version`, `/v1/me`, `/v1/tokens` routes | HTTP requests | Authenticated `AuthUser` + RLS-bound session | 2 |
| 4 | `backend/providers` | ⏳ not started | `LLMProvider` + `EmbeddingProvider` ABCs; `AnthropicProvider` + `VoyageEmbeddingProvider` impls; prompt-version registry | prompts, messages | completions, embeddings + usage | — |
| 5 | `backend/ingress` | ⏳ not started | FastAPI middleware: auth, Redis rate limit, idempotency, schema validate, sensitive-data scrub hook | requests | validated typed requests | 2, 3 |
| 6 | `backend/summarizer` | ⏳ not started | Three-layer summary generator, single Claude call, JSON-output mode, versioned prompt | normalized conversation | 3 summaries (JSON) + quality metadata | 2, 4 |
| 7 | `backend/embeddings` | ⏳ not started | Embedding service using `EmbeddingProvider`; writes `summary_embeddings` | summary text | vector | 2, 4 |
| 8 | `backend/storage` + ARQ jobs | ⏳ not started | Pushes writer; ARQ job registry (`summarize_push`, `embed_summary`); transcript blob upload; retries + DLQ | push payload | persisted push; status transitions | 2, 6, 7 |
| 9 | `backend/search` | ⏳ not started | Hybrid (vector + BM25) search over summaries, workspace-scoped | query, filters | ranked results w/ previews | 2, 7 |
| 10 | `backend/context_builder` | ⏳ not started | Resolution selector, multi-pull concat, token budget, provenance footer, framing prompt; uses shared renderer | push_ids + resolution | formatted pull payload | 1, 2 |
| 11 | `backend/egress` | ⏳ not started | Response sanitization, ACL re-check, audit log write | domain response | HTTP response | 2, 3 |
| 12 | `backend/api` | ⏳ not started | FastAPI routes wiring §7 endpoints to modules above | HTTP | HTTP | 5–11 |
| 13 | `packages/extension/core` | ⏳ not started | Platform-agnostic: auth/token storage, API client, push review UI, search UI, pull UI, injector-abstract | user actions | API calls + DOM mutations (via adapter) | 1, 12 |
| 14 | `packages/extension/adapters/claude` | ⏳ not started | Claude.ai DOM scraper + **auto-scroll-to-load for virtualized conversations** + input-field injector + fragility guards | DOM | normalized conversation / injected text | 13 |
| 15 | `packages/dashboard` | ⏳ not started | Next.js App Router: auth, workspace list, push browse, search, token management, pull-from-dashboard | user actions | API calls | 1, 12 |
| 16 | `backend/observability` | ⏳ not started | Sentry init, JSON logger, PostHog server wrappers, request-ID middleware | events | emitted telemetry | — (parallelizable) |
| 17 | `backend/rate_limit_cost_cap` | ⏳ not started | Redis-backed per-user quota enforcement; cost cap on LLM calls (hard=block, soft=degrade) | request + user | allow/deny | 3 |
| 18 | `packages/extension/auth-pairing` (stretch) | ⏳ not started | Pairing-code flow replacing copy-paste token | code | stored token | 13 |

Module 1 ships before everything because every other module references the interchange schema and the shared renderer.

---

## 7. API surface (v0)

All endpoints under `/v1`. Auth: `Authorization: Bearer <supabase_jwt | ch_api_token>`. All responses include `request_id`. Error envelope: `{ "error": { "code", "message", "details" } }`.

### Auth & identity
- `GET  /v1/me` — current user + active workspace.
- `POST /v1/tokens` — mint API token (dashboard JWT required). Returns raw token **once**.
- `GET  /v1/tokens` — list tokens for current user.
- `DELETE /v1/tokens/{id}` — revoke.

### Workspaces
- `GET  /v1/workspaces`
- `POST /v1/workspaces`
- `PATCH /v1/workspaces/{id}`
- `DELETE /v1/workspaces/{id}` (soft)

### Pushes
- `POST /v1/workspaces/{id}/pushes` — create (extension primary path). Body = interchange format + optional user-set title/tags. Returns `202 {push_id, status:"pending"}`. ARQ job handles the rest.
- `GET  /v1/workspaces/{id}/pushes` — list, paginated, tag-filterable.
- `GET  /v1/pushes/{id}` — detail with all three layers; extension polls this until `status=ready|failed`.
- `PATCH /v1/pushes/{id}` — edit commit_message / structured_block (JSON) / tags. `content_markdown` regenerated server-side.
- `DELETE /v1/pushes/{id}` (soft).
- `POST /v1/pushes/{id}/feedback` — summary quality score + comment.

### Search
- `GET  /v1/search?q=&workspace_id=&include_transcripts=false&limit=` — semantic (+BM25 hybrid) over summaries.

### Pull
- `POST /v1/pulls` — body: `{ push_ids, resolution, target_platform }`. Returns formatted payload + token estimate + provenance block. Writes a `pulls` row.

### Health / ops
- `GET /v1/health`, `GET /v1/version`.

Endpoints explicitly **not** in v0 but reserved in routing: `/v1/pushes/{id}/relationships`, `/v1/imports` (backfill), `/v1/workspaces/{id}/members`.

---

## 8. Interchange format (spec-first)

`ch.v0.1` is a JSON Schema published in `packages/interchange-spec/schemas/ch.v0.1.json` with a matching Pydantic model. Every push body and every stored raw transcript conforms to it. The spec ships in the monorepo from Module 1 so backend, extension, and dashboard all import it.

Conversation schema:

```
ConversationV0 {
  spec_version: "ch.v0.1",
  source: { platform: "claude_ai", conversation_id?, url?, model?, captured_at },
  messages: [
    { role: "user"|"assistant"|"system", content: MessageContent[], created_at? }
  ],
  metadata: { title?, client_version, user_agent? }
}
MessageContent = TextPart | CodeBlockPart | ImageRefPart | ToolUsePart | AttachmentRefPart
```

**Structured-block sub-schema** (same package, versioned alongside the conversation schema):

```
StructuredBlockV0 {
  spec_version: "ch.v0.1",
  decisions: [{ title, rationale, message_refs?[] }],
  artifacts: [{ kind: "schema"|"code"|"outline"|"other", name, body, language? }],
  open_questions: [{ question, context? }],
  assumptions: [string],
  constraints: [string]
}
```

The summarizer is prompted to emit JSON matching this schema; the Python validator rejects non-conforming outputs and triggers a retry.

Images, tool calls, and attachments land as refs (not inlined) so the transcript stays portable. Robustness of scraping these parts is a **Pre-launch required** TODO, not a v0-day-one requirement.

---

## 9. Extension architecture

```
packages/extension/
  manifest.json                 # MV3, host_permissions: claude.ai
  src/
    background/                 # service worker: token refresh stub, long-running tasks, message bus
    content/
      content.ts                # injected into claude.ai; mounts sidebar iframe; routes events to adapter
    sidebar/                    # React app, rendered in an iframe for isolation
      App.tsx, PushReview.tsx, SearchAndPull.tsx, Settings.tsx
    core/
      api-client.ts             # fetch wrapper, token, retries, request-id
      auth.ts                   # chrome.storage.local token get/set/clear
      platform.ts               # PlatformAdapter interface
      injector.ts               # abstract over adapter.inject(text)
      renderer.ts               # re-exports shared structured-block markdown renderer
    adapters/
      claude.ts                 # implements PlatformAdapter for claude.ai
```

**`PlatformAdapter` interface (the extensibility seam):**

```ts
interface PlatformAdapter {
  platformId: 'claude_ai';                    // add union members later
  detect(): boolean;                          // are we on a supported conversation page?
  getConversation(): Promise<ConversationV0>; // scrape + normalize to interchange
  getInputElement(): HTMLElement | null;      // chat textarea
  inject(text: string): Promise<'injected' | 'clipboard-fallback'>;
  getMessageBoundaries(): MessageBoundary[];  // stretch: powers scoping UI
}
```

Adding ChatGPT later is a new file implementing this interface + registration in a platform registry — ~1–2 days of work as stated in the kickoff.

**Sidebar is an iframe**, not a floating div, so host-page CSS/JS cannot break it. The content script is the only thing that touches the host DOM.

---

## 10. Observability

- **Request ID** generated by the extension, propagated through every API call and into ARQ job payloads, logged on both sides.
- **Sentry DSN** in backend + dashboard + extension background + ARQ worker. Content script sentry is sampled aggressively.
- **PostHog events:** `push_submitted`, `push_completed`, `search_performed`, `pull_executed`, `summary_feedback`, `token_minted`. Funnel from push → pull is the primary retention dashboard.
- **Cost tracking:** every LLM / embedding call writes a row (model, tokens, USD) to `summaries`. Aggregate per user to drive the cost-cap module. Global cost dashboard is a **Pre-launch required** item.

---

## 11. Open architectural questions

Resolved on 2026-04-17 and moved into PLAN.md Decisions log:
- ~~Embedding provider~~ → Voyage `voyage-3-large` via `EmbeddingProvider`.
- ~~Structured-block storage~~ → JSON authoritative, markdown derived by shared renderer.
- ~~Sync vs async push~~ → async, ARQ-backed, extension polls.
- ~~Workspace URL shape~~ → `/w/{short_id}` (base62 UUIDv7 suffix).
- ~~Username concept~~ → dropped; not in v0.
- ~~Multi-pull ordering~~ → user-chosen UI order, chronological default.
- ~~Raw transcript encryption~~ → Supabase default; per-user KMS flagged pre-launch.
- ~~Extension sidebar origin~~ → extension origin iframe; message-passing to content script.

Still open, taking defaults unless you override:
1. **Pairing-code vs copy-paste token.** Default: copy-paste in v0, pairing-code as Module 18 stretch.
2. **Sensitive-data scrub depth in v0.** Default: extension-side visible-preview scrub only (emails, API-key-looking strings, long hex, JWT shapes). Server-side NER-based scrub deferred. Enough for beta?
3. **ARQ worker count / concurrency.** Default: single worker, concurrency=4 in v0. Revisit on cost or latency pressure.
4. **Short-ID collision handling.** Default: 11-char base62 suffix of UUIDv7 gives ~65 bits of entropy → collision probability negligible at any v0 scale. No retry-on-collision logic needed; unique constraint catches it at DB level if it ever happens.

---

## 12. Testing strategy

Tests gate every module. Four tiers, with coverage expectations stated up front so we can cut without guessing.

| Tier | What it tests | Stack | v0 coverage target | Runs |
| ---- | ------------- | ----- | ------------------ | ---- |
| **Unit** | Pure functions, Pydantic validators, renderer logic, prompt assembly, small helpers | `pytest`, `vitest` | ≥80% line coverage on `backend/`, `packages/interchange-spec/`, `packages/extension/core/` | On every commit locally (pre-commit hook) + CI. |
| **Contract** | JSON Schema conformance (fixtures ↔ Pydantic ↔ generated TS), LLMProvider/EmbeddingProvider contracts against mocks + one recorded live call per provider, renderer byte-identical Py↔TS on golden fixtures | `pytest`, `vitest`, recorded HTTP cassettes (`vcrpy`) | 100% of interchange-spec + provider interfaces | CI; nightly replay against real providers. |
| **Integration** | API endpoints against a real Postgres + Redis from docker-compose + Supabase local; RLS enforcement; ARQ job execution end-to-end; migration up+down (§13 data retention interacts here) | `pytest-asyncio` against httpx-asgi; docker-compose fixtures | Every endpoint in §7 covered; every ARQ job type covered; RLS "user A ≠ user B" test | CI on every PR. |
| **End-to-end** | Extension + dashboard + backend together via browser automation. Happy paths only in v0: (a) sign in, (b) push a sample Claude conversation, (c) search and preview, (d) pull into a new conversation | Playwright (Chromium only in v0) | One flow per §1 P0 feature | CI nightly + pre-release; `claude.ai` canary (§10) covers DOM-drift detection separately. |

**What we are NOT testing in v0:** load/stress tests, chaos testing, fuzzing (tracked in parking lot). Exception: `summarize_push` ARQ job gets a large-conversation stress fixture (>100 messages) so we don't ship a silent regression there.

**Migration testing explicitly required.** Alembic migrations must be exercised **up and down** against a realistic fixture dataset (≥50 workspaces, ≥500 pushes, with all part types populated) before any migration lands on `main`. Owned by Module 2; CI job runs it on every schema PR.

---

## 13. Data retention policy (v0)

Retention is a compliance surface even for beta. Purges run as scheduled ARQ jobs.

| Class | Retention | Rationale | Purge mechanism |
| ----- | --------- | --------- | --------------- |
| Raw transcripts (Supabase Storage + `transcripts` row) | Lifetime of push; purged 30d after push soft-delete | Transcripts are the largest + most sensitive artifact; quick purge on user delete is table stakes | `purge_soft_deleted_pushes` ARQ job, daily |
| Pushes (soft-deleted rows) | 30 days, then hard delete (cascades to summaries, embeddings, tags, transcripts) | Lets users undo; matches transcript purge | Same job |
| Failed pushes (`status=failed`, never retried) | 7 days, then hard delete | No product value; keeps table clean | `purge_failed_pushes` ARQ job, daily |
| Summaries (`superseded_by` history) | Retained indefinitely while parent push is live; purged with push | Eval set + feedback history | Cascade on push hard delete |
| Summary feedback | Retained indefinitely (anonymized on user deletion) | Critical for quality eval over time | User-deletion job anonymizes `user_id` |
| `audit_log` | 90 days hot in Postgres; cold archival is v1 | Compliance + incident investigation window | `purge_audit_log` ARQ job, daily |
| `pulls` (analytics/audit) | 90 days | Matches audit_log window | Same schedule |
| Revoked `api_tokens` | 1 year after `revoked_at` | Audit trail for misuse investigation; `token_hash` is not a secret so retention is low-risk | `purge_revoked_tokens` ARQ job, weekly |
| User account deletion | Full purge of above within 30 days; verification job + exportable receipt | GDPR "right to erasure" | Kicked off by `account.delete` event |
| Interchange schema versions | Retained indefinitely | Needed to interpret old pushes | — |
| Backups (Supabase PITR) | Per Supabase retention (currently 7d on Pro); upgrade if GDPR requires shorter window on backups | Standard | Supabase-managed |

**Why these numbers:** 30/90-day hot windows match common beta defaults; 7d for failed-push is aggressive to avoid growing a dead-row pile; 1y for revoked-token hashes preserves audit without indefinite PII retention. All numbers are knobs in config so we can adjust per-env without a migration.

**Security pass interactions (deferred):** per-user KMS for transcripts, audit-log cold storage, anonymization-instead-of-deletion for certain classes — all `TODO.md` pre-launch items.
