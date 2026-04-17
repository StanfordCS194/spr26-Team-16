# ContextHub — TODO

**Status:** living document. Last updated 2026-04-17 (rev. 2, post-answers pass).

Conventions:
- `[ ]` open · `[~]` in progress · `[x]` done (moves to **Done** section)
- `(sec)` = security surface — save full treatment for the dedicated security pass.
- `(eval)` = needs a measurable KPI / eval set.

---

## Pre-launch required

Items that must be closed before beta users touch the product.

### Security
- [ ] (sec) End-to-end security audit before first external user. Scope: auth flows, token storage, RLS policies, secret handling, dependency CVE sweep.
- [ ] (sec) Supabase RLS policy audit — assert "user A cannot read user B's rows" via automated integration test, not just code review.
- [ ] (sec) API token lifecycle: short-lived refresh model *or* strong revocation UX (audit on use, rate cap on misuse, visible "last used" per token).
- [ ] (sec) Backend ↔ extension auth hardening: CORS allowlist, `X-Request-Id` propagation, strict request-size caps, anti-CSRF for dashboard JWT usage.
- [ ] (sec) Secret management: no Supabase service key in client bundles; verify via build-time check. Rotate keys between staging/prod.
- [ ] (sec) Sensitive-data scrub: client-side preview in extension + server-side regex pass for obvious patterns (emails, API-key-looking strings, long hex, JWT shapes). NER-based scrub is v1+.
- [ ] (sec) Rate limiting + per-user cost caps on LLM calls (hard cap: block; soft cap: degrade to cached/cheaper model). Redis-backed.
- [ ] (sec) Abuse / spam mitigation on signup: rate limiting + hCaptcha or Cloudflare Turnstile on magic-link issuance.
- [ ] (sec) DPA check with Anthropic and Voyage confirming no training on API data.
- [ ] (sec) GDPR-compliant data deletion flow: account deletion purges all user rows (pushes, summaries, embeddings, transcripts in Storage, audit_log per retention policy), with a verification job and exportable receipt.
- [ ] (sec) Privacy policy + Terms of Service drafted and linked before beta invites go out.

### Quality & robustness
- [ ] (eval) Summary-quality eval set: ≥50 representative conversations with gold-standard layered summaries + automated LLM-as-judge scoring. KPI: ≥ 3.5 user rating, ≥ 0.7 judge/human agreement.
- [ ] (eval) Search-quality eval set: query → expected-push relevance judgments. KPI: search → pull rate ≥ 40%.
- [ ] (eval) Push funnel KPI dashboard in PostHog: push submit → ready → first pull. KPI: D7 retention ≥ 30%, weekly active pulls ≥ 2.
- [ ] (eval) Single-call three-layer summary failure-rate tracking. If aggregate failure rate > 5% on the eval set, implement retry-per-layer strategy before beta (else keep single-call for cost/latency). Metric emitted as PostHog event + stored failure reason.
- [ ] Extension ingestion robustness — the long list (note: basic auto-scroll-to-load ships in **Module 14 v0**; items below are stress / edge-case hardening on top of that baseline):
  - [ ] Very large conversations (>200 messages, >50k tokens) — auto-scroll stress test, verify integrity check catches missed messages, verify progress UX is readable.
  - [ ] Scroll-to-load failure modes: virtualization doesn't settle, infinite-loop detection, timeout + user-facing error with "retry" button.
  - [ ] Code blocks — preserved as `CodeBlockPart` with language tag.
  - [ ] Attachments (uploaded files) — captured as `AttachmentRefPart` with filename + size + MIME; content not uploaded by default.
  - [ ] Images — captured as `ImageRefPart` with URL or storage key, not inlined bytes.
  - [ ] Tool calls (artifacts, analysis) — captured as `ToolUsePart` with `name`, `input`, `output` stringified.
  - [ ] Unicode / emoji / zero-width char handling.
  - [ ] Markdown fidelity in/out (round-trip on review + inject) — covered by golden-fixture renderer tests.
- [ ] Error handling + retry logic: ARQ jobs with exponential backoff + jitter + DLQ; resumable uploads for transcripts; LLM JSON-output validation with bounded retries.
- [ ] Push status state machine: `pending → processing → ready | failed` with user-visible failure reasons and a retry button.
- [ ] Stuck-push alerting: Sentry alert when any push sits in `pending`/`processing` > 5 min; admin-only manual requeue endpoint.
- [ ] DOM-injection fallback path: clipboard copy with toast when the inject selector fails; chosen path recorded per pull.
- [ ] Claude.ai adapter canary tests: daily CI run against a known conversation URL to detect breaking DOM changes within 24h.
- [ ] Backend idempotency: `Idempotency-Key` header honored on POST /pushes; dedupe window 24h.
- [ ] Browser compatibility matrix: Chrome, Brave, Edge, Arc — manual smoke test of push + pull on each before beta.
- [ ] Migration testing discipline verified: Alembic up+down fixture run exists, is CI-gated, fixture dataset covers ≥50 workspaces / ≥500 pushes with every message part type populated.
- [ ] Data retention purge jobs verified: dry-run each purge job against staging, assert row counts match policy per ARCHITECTURE §13, alerting in place on zero-purge days.

### Onboarding & feedback
- [ ] Onboarding flow: post-install dashboard walkthrough (sign in → create workspace → connect extension → push sample conversation → pull it back).
- [ ] Feedback mechanism for summary quality: thumbs + 1–5 scale + optional comment, visible inline in dashboard push view and extension review screen.
- [ ] In-product feedback widget (generic) — PostHog surveys or a simple email trap.
- [ ] Backfill / import entry (P1) — manual paste for v0 so new users aren't looking at an empty workspace. Deferred to pre-launch, not module-1 blocker.
- [ ] Empty-state copy + help links for workspace list, search, push review.

### Ops
- [ ] Staging environment end-to-end: Railway staging backend + ARQ worker + Upstash staging Redis + Vercel preview dashboard + dedicated Supabase staging project.
- [ ] Backup strategy verified: Supabase PITR retention documented, restore procedure tested and runbook'd.
- [ ] Alerting: Sentry issue alerts → email; PostHog funnel alerts on push → pull drop-off; stuck-push alert; Redis/Upstash availability alert; ARQ worker healthcheck.
- [ ] Cost observability: daily dashboard of LLM + embedding + Supabase + Railway + Vercel + Upstash spend. Per-user LLM spend rollup + global total. Budget alerts.
- [ ] Chrome Web Store publishing prep: privacy disclosure, screenshots, description. Beta launches **unlisted** with direct-install link.
- [ ] Extension update rollback plan documented: how to pin version, how to push an emergency rollback listing, communication template for affected users.
- [ ] Incident runbook: DOM-break, Anthropic outage, Voyage outage, Supabase outage, Redis outage, auth outage.

---

## This week — Module 1: `packages/interchange-spec`

- [ ] Create `contexthub/` monorepo skeleton: `pnpm-workspace.yaml`, root `package.json`, `.gitignore`, `.env.example`, `.editorconfig`. Location to be finalized in the Module 1 proposal per Aalaap's guidance (existing repo root is untouched).
- [ ] `packages/interchange-spec/schemas/ch.v0.1.json` — conversation JSON Schema.
- [ ] `packages/interchange-spec/schemas/structured-block.v0.1.json` — structured-block sub-schema.
- [ ] `packages/interchange-spec/python/model.py` — Pydantic v2 models mirroring both schemas.
- [ ] `packages/interchange-spec/python/renderer.py` — structured-block → markdown renderer.
- [ ] `packages/interchange-spec/ts/renderer.ts` — structured-block → markdown renderer (TS).
- [ ] `packages/interchange-spec/fixtures/` — ≥5 conversation fixtures (short, long, code-heavy, tool-use, attachment-ref) + ≥10 structured-block fixtures.
- [ ] `packages/interchange-spec/tests/` — JSON Schema validation, Pydantic round-trip, renderer golden-fixture cross-impl test (Py vs TS byte-identical).
- [ ] `datamodel-code-generator` wired: `pnpm run codegen` → `packages/shared-types/src/*.ts`; CI drift check.
- [ ] Validator CLI: `uv run ch-validate <file>` for dev ergonomics.
- [ ] Propose-approve-implement cycle: module proposal (file structure, interfaces, test strategy) → Aalaap review → implement.

## Next up

- [ ] Module 2: backend schema + Alembic migrations — all tables from ARCHITECTURE.md §5 (incl. `pulls.workspace_ids`), RLS policies, seed data for dev, fixture dataset (≥50 workspaces / ≥500 pushes) + Alembic up+down CI job. No `rate_limit_counters` Postgres table (Redis-backed).
- [ ] Module 3: backend auth — Supabase JWT verification + API-token mint/verify/revoke; integration tests for both auth paths; RLS "user A ≠ user B" test.
- [ ] Module 4: `backend/providers` — `LLMProvider` + `EmbeddingProvider` ABCs + `AnthropicProvider` + `VoyageEmbeddingProvider` + prompt-version registry.
- [ ] Module 16: observability — Sentry + JSON logger + PostHog + request-ID middleware wired before summarizer/storage work begins, so every subsequent module ships with telemetry.

## Parking lot

### Product (from PRD, not in v0)
- [ ] Automatic topic segmentation at push time (P1 — conversation scoping).
- [ ] ChatGPT bulk-export ingestion + manual-paste backfill import (P1).
- [ ] Cross-platform pull: ChatGPT adapter (P2).
- [ ] Shared workspaces + team search + permissions (P3).
- [ ] Conflict detection across teammates' pushes (P3).
- [ ] Auto-push / draft save (open PRD question).
- [ ] Standalone chat interface that wraps LLM APIs (open PRD question).
- [ ] Open-source the `ch.v0.1` spec once stable + battle-tested across ≥2 adapters.
- [ ] Usernames / vanity URLs (revisit post-beta if sharing UX needs it).

### Architecture (XARPA alignment, v1+)
- [ ] Query cache with 95% match threshold (per handwritten notes). Redis already in stack.
- [ ] 5-gate confidence classifier (query coverage / conflict / staleness / authority / LLM-contrib ratio).
- [ ] Claim extraction + structured gap detection on pull.
- [ ] Episodic graph traversal — actual use of `push_relationships` edges.
- [ ] Cross-workspace memory search (teams).
- [ ] Fine-tuned summarization model to reduce per-push cost.
- [ ] Local / on-device summarization path (privacy story).

### UX polish (post-beta)
- [ ] Pairing-code flow to replace copy-paste token handoff (Module 18 stretch if time permits in v0).
- [ ] Idle / tab-close prompt to push (PRD §1.1 stretch).
- [ ] Per-workspace default settings (preferred resolution, preferred model, default tags).
- [ ] Renaming "workspace" → "project"/"notebook" based on user testing.
- [ ] Keyboard shortcuts across dashboard + extension.
- [ ] Public Chrome Web Store listing (flip from unlisted post-beta).

### Infra nice-to-haves
- [ ] Streaming push status via SSE instead of client polling.
- [ ] Pre-computed "recently pushed" feeds for faster dashboard first paint.
- [ ] Worker autoscaling on ARQ queue depth.

### Testing & quality (post-v0)
- [ ] Load / stress tests against the full push → search → pull loop.
- [ ] Chaos testing (Redis outage, Anthropic 5xx storm, Supabase slow-query burst).
- [ ] Fuzzing of interchange-spec validators.
- [ ] **Retry-per-layer summary generation** — trigger: if v0 single-call failure rate > 5% on the eval set, promote this to pre-beta.
- [ ] Audit-log cold archival (S3 or equivalent) past the 90-day hot window.

---

## Done

_(empty for now — populated as modules ship)_
