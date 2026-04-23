# ContextHub — Plan

**Status:** living document. Last updated 2026-04-17 (rev. 2, post-answers pass).

---

## Current phase

**v0 build — foundation session (rev. 2).** Architecture + planning docs finalized for Module 1 kickoff. No application code committed yet. Implementation starts next session with Module 1 (`interchange-spec` + codegen + markdown renderer) on your green light.

Target: closed beta with 50–100 users, aligned with PRD milestones (architecture finalized May 2026, core engine June, extension alpha July, beta launch Aug).

---

## In scope (v0)

- Push flow: extension trigger, DOM scrape, async ARQ-backed three-layer summary generation, user review of JSON-authoritative structured block, confirm, persist.
- Repository + semantic search: workspace model, pgvector (1024d, Voyage) hybrid search over summaries.
- Pull + injection: dashboard and extension pull entry points, resolution selection, multi-pull concat, DOM injection with clipboard fallback.
- Claude.ai adapter only; `PlatformAdapter` interface in place for future adapters.
- Supabase Auth (magic link) for dashboard; long-lived API tokens for extension.
- Redis (Upstash) for ARQ job queue + rate-limit counters.
- ARQ worker as a dedicated Railway service.
- Shared markdown renderer (Py + TS) for the structured block, with golden-fixture cross-impl tests.
- Observability (Sentry, JSON logs, PostHog) wired day one.
- Deployment to Railway (API + worker) + Vercel (dashboard) + Supabase cloud from the first shippable module.
- `ch.v0.1` interchange spec published in the monorepo with structured-block sub-schema.
- Typegen via `datamodel-code-generator` with CI drift check.
- **Auto-scroll-to-load** for Claude.ai's virtualized conversation UI (Module 14 scope, not pre-launch polish).
- **Alembic up+down migration testing** against a realistic fixture dataset, CI-gated from Module 2 onward.
- **Data retention policy enforcement**: scheduled ARQ purge jobs per ARCHITECTURE.md §13.
- **Four-tier testing discipline** (unit / contract / integration / E2E) per ARCHITECTURE.md §12, set up from Module 1.

## Out of scope (v0)

- Cross-platform pull (ChatGPT / Gemini / etc.) — architectural seams only.
- Team / shared workspaces — schema allows memberships later; not wired.
- Automatic topic segmentation on push — manual scoping deferred to P1.
- Backfill import (ChatGPT JSON, manual paste) — deferred to P1.
- Local / on-device summarization — `LLMProvider` abstraction only.
- 5-gate confidence classifier, claim extraction, gap filler, fine-tuned routing — scaffolded (metadata + provenance) but not implemented.
- Conversation interchange format as an open-source spec — we author internally; open-sourcing is a v1 consideration.
- Query cache, episodic graph traversal, cross-workspace semantic search — reserved in schema only.
- Auto-push / draft-save — manual push remains the single flow.
- Usernames / user-scoped URLs — dropped from v0; workspaces are id-routed.

---

## Active work

**Shipped 2026-04-17:** Module 1 — `packages/interchange-spec`. See `TODO.md` Done section for the full delivery list. 20 Python tests + 41 TypeScript tests + typecheck all green against a running codegen pipeline.

**Shipped 2026-04-22:** Module 2 — `backend/schema`. All 14 §5 tables, Alembic up+down migration, RLS policies (`ch_authenticated` role + `auth.uid()` stub), tsvector trigger, HNSW index, `gen_fixtures.py` (60 WS / 550 pushes), `seed_dev.py`, `docker-compose.yml`, 35/35 unit tests green, integration tests CI-gated (`pgvector/pgvector:pg15`), `shared-types` TS row types. See `VALIDATION.md` Module 2 entry for full check list.

**Next session (after review):** Module 3 — `backend/auth`. Supabase JWT verifier middleware + API-token mint/verify/revoke endpoints; integration tests for both auth paths against the Module 2 schema; confirm RLS "user A ≠ user B" holds end-to-end through the FastAPI layer (not just raw Postgres).

---

## Open questions

High-impact blockers for Module 1 are resolved. Remaining items (all non-blocking for Module 1; defaults in ARCHITECTURE.md §11):

- Pairing-code vs copy-paste token for extension auth (default: copy-paste in v0).
- Sensitive-data scrub depth for beta (default: extension-side preview only).
- Claude.ai "one conversation" definition (default: scroll-to-top, user responsibility; auto-scroll pre-launch item).
- ARQ worker count / concurrency (default: 1 worker, concurrency=4).
- Short-ID collision handling (default: unique-constraint catch, no retry logic).

---

## Parking lot (v1+ features from PRD, with context)

Each entry is enough for a future-you to pick it up without rereading the PRD.

- **Conversation scoping (P1).** User selects message range before push. Automatic topic segmentation via LLM call proposing split points. Requires extension message-boundary UI + backend endpoint to produce segmentation. Enables multi-commit-per-conversation.
- **Backfill import (P1).** ChatGPT bulk-export JSON ingestion + manual paste import. Needs bulk summarization pipeline (batch, progress UI) and duplicate detection. Cold-start fix.
- **Cross-platform pull (P2).** Target ChatGPT first. Requires a ChatGPT adapter implementing `PlatformAdapter`, and egress formatting tuned per target platform. Unlocks the "portability" value prop.
- **Shared workspaces (P3).** `memberships` table, role enum, RLS policy changes, team search scope. Opens pricing tier.
- **Conflict detection (P3).** Flag when two members' pushes make contradictory decisions on the same topic. Depends on shared workspaces + claim extraction.
- **5-gate confidence engine (XARPA-aligned).** Classifier over query-coverage/conflict/staleness/authority/LLM-contrib. Routes pulls across cached / episodic / LLM-augmented categories. Big lift; scaffolded via quality metadata in v0.
- **Episodic graph traversal.** `push_relationships` becomes a real graph. Pull can traverse continuation/reference/supersession edges. Depends on edges being populated (manually in v0 → auto-detected later).
- **Query cache.** 95% match threshold as in the XARPA notes, short-circuits the LLM/context builder. Worth it once push-to-pull latency becomes user-visible. Redis already in the stack for v0.
- **Fine-tuned summarization model.** PRD flags as a cost-reduction lever at scale. Depends on having an eval set (TODO pre-launch item) and enough production data.
- **Open-source the interchange spec.** Positions ContextHub as infrastructure. Needs the spec to be stable and battle-tested across at least two platforms first.
- **Standalone chat interface (wraps LLM APIs).** Open question from the PRD. Decision point: after v0 validates that users want the workflow badly enough to install an extension at all.
- **Renaming "workspace" → "project" or "notebook."** PRD flags as needing user testing. `workspace` is the code-level name; UI copy can diverge.
- **Platform-native memory integration.** How does ContextHub coexist with Claude memory / ChatGPT memory? Positioning + possibly import-from-memory flow.
- **Usernames / vanity URLs.** Dropped from v0 to keep auth and routing simple. Revisit post-beta if sharing UX needs it.

---

## Known risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Claude.ai DOM changes mid-beta, breaks scraper | High | High | Adapter pattern + automated canary tests against claude.ai + fast-follow release path |
| Summary quality below 4/5 user rating | Med | High | Eval set before launch, prompt-version tracking, per-summary feedback widget, A/B prompt harness |
| LLM cost spikes with big conversations | Med | Med | Per-user cost cap, pre-push token estimate, Haiku default, gate on transcript size |
| Scraping long conversations drops messages | Med | High | Auto-scroll-to-load + integrity check on `message_count` + user-facing warning |
| Extension↔dashboard token handoff UX is fragile | Med | Med | Pairing-code flow (module 18) post-v0; clear copy-paste instructions with clipboard helper in v0 |
| Supabase RLS misconfig leaks cross-user data | Low | Critical | RLS policies shipped with schema; integration test asserts user A cannot read user B |
| DOM injection into Claude.ai input is blocked by app re-renders | Med | Med | Clipboard fallback with toast is the documented path; DOM path is best-effort |
| Interchange spec changes break old pushes | Low | Med | `interchange_version` column + versioned schemas; migrations handle shape upgrades |
| **ARQ worker crash / Redis outage leaves pushes stuck in `pending`** | Med | High | Sentry alert on pushes stuck >5 min; healthcheck on worker; manual requeue endpoint (admin-only) |
| **Py / TS markdown renderer drift** | Med | Med | Golden-fixture cross-impl test gated in CI; any drift fails the build |
| **JSON-authoritative structured block: LLM returns invalid JSON** | Med | Med | Strict JSON-output mode + Pydantic validation + bounded retries + fallback to plain-text commit message |
| **Single-call three-layer summary is brittle** (malformed output for one layer loses all three) | Med | Med | v0: strict JSON schema + bounded retries + plain-text commit-message fallback. v1: retry-per-layer strategy with independent prompts if aggregate failure rate is above tolerance — tracked in parking lot. |
| **Migration regressions on production data** (up works in CI with empty DB, fails against real data) | Med | High | Alembic up+down exercised against a ≥50-workspace / ≥500-push fixture dataset in CI; no migration merges without green up+down. |
| **Data retention purge jobs fail silently** (compliance gap) | Low | High | Each purge job emits a PostHog event with rows purged; Sentry alert on zero-purge days; runbook entry. |
| Over-scoping in beta leads to slip past Aug launch | Med | Med | This plan's strict out-of-scope list; parking lot is the pressure valve |

---

## Decisions

Running log. Each entry: **date — decision — context — rationale — consequences.**

- **2026-04-17 — Stack locked.**
  - Context: kickoff prompt; user explicitly overrides PRD tech suggestions.
  - Decision: Python 3.12 + FastAPI + Pydantic + SQLAlchemy + Alembic + uv; Supabase (Postgres + pgvector + Auth + Storage); Railway + Vercel from day one; pnpm monorepo; TS+React extension (MV3) + Next.js App Router dashboard.
  - Rationale: production-grade and each layer has a managed-service answer; FastAPI/Pydantic/SQLAlchemy is a standard async Python stack; Supabase collapses three vendors (DB, Auth, Storage) into one; Next.js on Vercel gives SSR for auth pages and a marketing-site growth path.
  - Consequences: we accept vendor coupling to Supabase and Anthropic for v0; both are hidden behind abstractions (`LLMProvider`, DB is just Postgres).

- **2026-04-17 — Platform target for v0 is Claude.ai only.**
  - Context: PRD scope, kickoff prompt.
  - Decision: ship a single adapter (`claude-adapter.ts`) behind a `PlatformAdapter` interface.
  - Rationale: focus; Claude is the PRD's primary target and where the user has most context.
  - Consequences: ChatGPT adapter becomes a ~1–2 day module later; we do not tune summarization prompts per platform in v0.

- **2026-04-17 — LLM and embedding providers are Anthropic (Haiku) and Voyage (voyage-3-large) via abstractions.**
  - Context: kickoff prompt + answers pass.
  - Decision: `LLMProvider` + `EmbeddingProvider` ABCs; `AnthropicProvider` (Haiku 4.5) and `VoyageEmbeddingProvider` (`voyage-3-large`, 1024d) as the only concrete impls in v0. No Ollama / local models.
  - Rationale: Haiku is cheap per push and good enough for structured summarization; Voyage retrieval quality on summaries is strong and keeps us off OpenAI; abstractions future-proof.
  - Consequences: every call site takes a provider dependency; swapping providers is a DI change, not a rewrite. `summary_embeddings.embedding vector(1024)` locked.

- **2026-04-17 — Dashboard framework is Next.js App Router (not Vite).**
  - Context: open question raised during foundation session; user confirmed.
  - Decision: Next.js 15 on Vercel.
  - Rationale: SSR for auth-gated repo pages, room for marketing pages on the same domain, Vercel-native.
  - Consequences: dashboard is server-rendered by default; API client runs both in RSC and client components. Slightly heavier than a Vite SPA.

- **2026-04-17 — Interchange format is spec-first from day one.**
  - Context: user confirmed during foundation session.
  - Decision: `ch.v0.1` is authored as JSON Schema + Pydantic + TS types in `packages/interchange-spec` before any backend or extension module is built. Structured-block sub-schema co-located and co-versioned.
  - Rationale: both backend ingestion and extension scraping conform to the same contract; open-sourcing it later becomes a copy-paste, not a rewrite.
  - Consequences: Module 1 is pure spec work + codegen + renderer. Breaking the spec requires a version bump; old pushes stay valid under their original version.

- **2026-04-17 — Atomic unit is "workspace," not "repository."**
  - Context: PRD leaves open; user confirmed.
  - Decision: code- and schema-level name is `workspace`; UI copy can vary.
  - Rationale: resonates better than "repository" for non-dev users (per PRD); we avoid a late rename migration.
  - Consequences: URL and code consistently say `workspace`. Marketing language can still say "your LLM repo" without touching the schema.

- **2026-04-17 — Auth: Supabase magic link for dashboard + long-lived API tokens for extension.**
  - Context: user confirmed.
  - Decision: dashboard uses Supabase Auth session JWT; extension holds a token minted from the dashboard, stored in `chrome.storage.local`, revocable, sent as `Authorization: Bearer`.
  - Rationale: keeps extension auth stateless w.r.t. Supabase sessions; one code path for the backend (verify JWT *or* lookup token hash).
  - Consequences: token handoff UX is copy-paste in v0 (pairing-code deferred to Module 18 stretch). Tokens are long-lived — revocation surface must be clear.

- **2026-04-17 — v0 files land under `contexthub/` in the existing repo (Option Z).**
  - Context: XARPA (Stanford CS194 `spr26-Team-16`) and ContextHub are the same project — team vs product naming. User asked to keep existing files untouched.
  - Decision: ContextHub docs live at `contexthub/docs/*.md`. Monorepo scaffolding (pnpm + uv workspaces) lives at `contexthub/`. Existing repo root (`README.md`, `docs/`, `wiki/`) is untouched.
  - Rationale: user directive; avoid destructive changes to team-identity files; scoping ContextHub inside `contexthub/` keeps class repo tidy.
  - Consequences: pnpm-workspace root + uv workspace root are both at `contexthub/`; repo root has no JS or Python tooling.

- **2026-04-17 — Two-tool codegen pipeline (json-schema-to-typescript + datamodel-code-generator).**
  - Context: Module 1 proposal; `datamodel-code-generator`'s TS output is weaker than the dedicated tool.
  - Decision: JSON Schema is the single source of truth. TS types regenerated from it via `json-schema-to-typescript`; Python Pydantic models regenerated via `datamodel-code-generator`. Both drive a single `pnpm run codegen` orchestrator; CI drift-checks both outputs.
  - Rationale: cleaner generated output per language beats forcing one tool to do both; the drift check catches any regressions either way.
  - Consequences: two codegen scripts (`scripts/codegen.mjs` + `scripts/codegen_py.py`); one additional dev dep (`json-schema-to-typescript`). Acceptable.

- **2026-04-17 — Workspace URL short_ID generation deferred to Module 2.**
  - Context: Module 1 didn't need it; encoder will be written when `workspaces.id` lands.
  - Decision: the base62-of-UUIDv7-suffix encoder lives in a backend utility module, not in `interchange-spec` (which stays pure data-model).
  - Consequences: `interchange-spec` remains dependency-light; URL concerns live with the backend.

- **2026-04-17 — Observability wired on day one, not a post-MVP concern.**
  - Context: kickoff prompt.
  - Decision: Sentry, structured JSON logs with request-ID propagation, PostHog from the first deployed module.
  - Rationale: cheaper to instrument early than retrofit; beta feedback loop needs event data.
  - Consequences: every module adds telemetry hooks; DSNs/keys become secrets to manage.

- **2026-04-17 — Structured block is JSON-authoritative; markdown is derived.**
  - Context: answers pass.
  - Decision: `summaries.content_json jsonb NOT NULL` is the source of truth; `content_markdown text` is regenerated by a shared renderer on write. Summarizer prompt produces JSON conforming to the structured-block sub-schema.
  - Rationale: unlocks UI editing widgets, eval metrics, and schema evolution; avoids markdown-parsing round-trips.
  - Consequences: shared renderer must exist in both Py and TS (for server vs extension/dashboard); golden-fixture cross-impl tests gate CI; editing goes through the JSON form, not a free-text markdown editor.

- **2026-04-17 — Push creation is async, backed by ARQ on Redis.**
  - Context: answers pass.
  - Decision: `POST /v1/pushes` returns `202 {push_id, status:"pending"}`, enqueues a `summarize_push` ARQ job. Worker generates summaries, enqueues `embed_summary`, updates status. Extension polls `GET /v1/pushes/{id}`.
  - Rationale: decouples UI from LLM latency and transcript size; standard retry/DLQ semantics; Redis unlocks rate limiting for free.
  - Consequences: Redis (Upstash) added to v0 stack. ARQ worker is a dedicated Railway service. `rate_limit_counters` Postgres table dropped — rate limits move to Redis. New failure mode "stuck in pending" with alerting.

- **2026-04-17 — Workspace URL shape is `/w/{short_id}`.**
  - Context: answers pass (username-based scheme considered, then dropped).
  - Decision: URL path is `/w/{short_id}` where `short_id` is a base62-encoded UUIDv7 suffix (~11 chars). No username concept in v0.
  - Rationale: ships faster; no reserved-words list; no onboarding username-picker step; no squatting risk; still shareable.
  - Consequences: workspace `slug` stays per-user-unique but is cosmetic (breadcrumbs, display). No `username` column on `profiles`. Vanity URLs deferred to parking lot.

- **2026-04-17 — Beta distribution is Chrome Web Store unlisted.**
  - Context: answers pass.
  - Decision: unlisted CWS listing with direct-install link, auto-update enabled. Public listing is a post-beta step.
  - Rationale: auto-update + store-signed trust without public discovery during beta.
  - Consequences: onboarding flow includes a "click to install" direct link. Post-beta checklist adds "flip listing to public."

- **2026-04-17 — Codegen committed from day one.**
  - Context: answers pass.
  - Decision: `datamodel-code-generator` wired in Module 1. `pnpm run codegen` regenerates TS types from Pydantic into `packages/shared-types`. CI runs codegen and fails on drift against committed output.
  - Rationale: single source of truth (Pydantic); prevents drift between backend and frontend types.
  - Consequences: every schema change requires a codegen run + commit. Small friction, big safety.

- **2026-04-17 — Py + TS markdown renderer duplication is accepted; golden-fixture test guards it.**
  - Context: micro-question deferred to me.
  - Decision: structured-block markdown renderer exists in both Python (server) and TypeScript (extension + dashboard client-side). ≥10 golden fixtures assert byte-identical output across both; CI-gated.
  - Rationale: extension offline preview and dashboard snappy rendering both require client-side markdown; single-server render would force a network round-trip for every preview.
  - Consequences: any structured-block schema change touches two renderers + fixtures. Drift = build fail.

- **2026-04-17 — Short IDs are base62-encoded UUIDv7 suffix.**
  - Context: micro-question deferred to me.
  - Decision: URL short IDs derive from the last 64 bits of each UUIDv7 PK, base62-encoded (~11 chars).
  - Rationale: shareable, compact, collision probability negligible at v0 scale, no extra column needed (pure presentation).
  - Consequences: unique constraint on `id` catches any theoretical collision; URL parser converts short ID → UUID.

- **2026-04-17 — Auto-scroll-to-load is v0 core scope, not pre-launch polish.**
  - Context: Aalaap push-back on rev. 2 — Claude.ai virtualizes aggressively; manual scroll-to-top is unusable for any real conversation.
  - Decision: Module 14 (`claude-adapter`) must implement auto-scroll-to-load with progress indicator and message-count integrity check. Not a P1 item.
  - Rationale: core UX; beta is dead on arrival without it.
  - Consequences: Module 14 grows in scope. Adapter gains a virtualization-settle wait primitive that's reusable across platforms later.

- **2026-04-17 — Migration testing is CI-gated from Module 2.**
  - Context: Aalaap flagged gap in rev. 2.
  - Decision: Alembic up+down exercised against a ≥50-workspace / ≥500-push fixture dataset in CI. No migration merges without green up+down. Owned by Module 2.
  - Rationale: production migration failure on real data is a very-high-impact risk and cheap to prevent.
  - Consequences: Module 2 ships with the fixture dataset + CI job, not just the schema.

- **2026-04-17 — Pulls table records `workspace_ids` alongside `push_ids`.**
  - Context: Aalaap flagged gap — multi-pull can span workspaces; audit/analytics needed to see which workspace(s) contributed.
  - Decision: add `workspace_ids text[]` as a parallel array to `push_ids` on the `pulls` row.
  - Rationale: denormalized but cheap; avoids a join at query time for analytics dashboards; parallels existing `push_ids`.
  - Consequences: `POST /v1/pulls` fills both arrays; dashboard's "recent pulls" view can filter by workspace without touching `pushes`.

- **2026-04-17 — Testing strategy formalized (§12).**
  - Context: Aalaap flagged missing strategy section.
  - Decision: four tiers — unit / contract / integration / E2E — with coverage targets and tool choices. Load/stress/fuzzing in parking lot. Large-conversation stress fixture for `summarize_push` job is in v0.
  - Rationale: aligns testing expectations across modules; prevents "tests later" drift.
  - Consequences: every module proposal lists which tier(s) it owns tests for.

- **2026-04-17 — Data retention policy explicit in v0 (§13).**
  - Context: Aalaap flagged compliance gap — even beta needs this defined.
  - Decision: per-class retention matrix (transcripts, pushes, summaries, feedback, audit_log, pulls, tokens, account deletion) with scheduled ARQ purge jobs. All windows are config knobs.
  - Rationale: GDPR-readiness + operational cleanliness + clear story for pre-launch security pass.
  - Consequences: new ARQ job family (`purge_*`); Module 8 (storage + ARQ) adds purge-job skeletons even if full implementation slips to Module 17 timeframe.

- **2026-04-17 — Single-call three-layer summary flagged as known v0 quality risk.**
  - Context: Aalaap pattern concern — one malformed output loses all three layers.
  - Decision: keep single-call in v0 (cost + latency win); ship strict JSON schema + Pydantic validation + bounded retries + plain-text commit-message fallback. v1 retry-per-layer goes into parking lot with the threshold trigger "if aggregate failure rate > 5% on the eval set, implement before beta."
  - Rationale: brittleness is real but retry-per-layer triples LLM cost per push; gated on measured failure rate rather than speculation.
  - Consequences: failure-rate tracked as a Pre-launch KPI; failure metadata stored on `summaries.failure_reason` (needs schema addition — Module 2 deliverable update).
