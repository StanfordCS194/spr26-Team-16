# PRD for ContextHub

## Version Control for LLM-Assisted Knowledge Work

---

## Version History

| Date | Version | Notes |
|------|---------|-------|
| 1/16/2026 | 0.1 | Template created |
| 4/11/2026 | 1.0 | First version |

---

## Related Documents / Links

Use this section to link to other relevant documents, such as key benchmarks, technical papers, market research, summarized brainstorming output, etc.

---

## Overview

### Mission

ContextHub is a version control system for LLM-assisted knowledge work. It transforms ephemeral AI conversations into durable, searchable, shareable, and portable knowledge artifacts that teams and individuals can build on over time.

### Vision

In the near future, most professional knowledge work will involve collaboration with AI. When that happens, the conversation becomes the unit of intellectual progress. Yet today, these conversations vanish into unsearchable chat logs, locked inside a single platform, invisible to collaborators. ContextHub makes LLM conversations first-class work products: versionable, retrievable, and portable across models and teams.

### Product Summary

ContextHub lets users push completed LLM conversations to a shared repository as structured, layered context objects. Users can later search their repository to find past work, and pull relevant context into new conversations across any LLM platform. The system generates multi-resolution summaries at push time (a short commit message, a structured decision/artifact block, and the raw transcript) so that pulled context is right-sized for any use case.

- **v1** focuses on the single-user, single-platform experience: push, search, and pull within one LLM provider.
- **v2** extends to cross-platform portability.
- **v3** introduces team collaboration.

---

## Problem Statement

### Problem 1: Retrieval failure

LLM conversations older than a few days are effectively lost. Platform-native search is keyword-based and performs poorly on long, meandering conversations. Users cannot find the conversation where they made a critical design decision, established a technical approach, or refined a strategy. The cost is repeated work: users rederive conclusions they already reached, re-explain context the model already had, and lose the compounding value of prior sessions.

### Problem 2: Platform lock-in and zero portability

Conversations are trapped inside the platform where they originated. A user who develops deep context in Claude cannot carry that context into ChatGPT, Gemini, or any other model. As multi-model usage becomes the norm (different models for different strengths), this lock-in forces users to re-establish context from scratch every time they switch. There is no standard interchange format for LLM conversations.

### Problem 3: No collaboration layer

When two people are working on the same problem with LLMs, their only coordination mechanism is copy-pasting outputs into shared documents and verbally communicating what was decided. This is lossy, slow, and breaks the conversational context that made the LLM output useful in the first place. There is no way for Person B to pick up where Person A left off with full fidelity.

---

## Opportunity

### Why now

- **Multi-model usage is real.** Power users now routinely use 2–3 LLMs for different tasks. Cross-platform context portability has gone from nice-to-have to a daily friction point.
- **LLM usage has crossed from novelty to workflow.** Conversations are now genuine work products, not experiments. The cost of losing a conversation is real productivity loss.
- **Context windows are large enough.** 128K+ token windows mean injected summaries actually work. A year ago, 4K–8K windows made context injection impractical.
- **No platform will solve cross-platform portability.** Every LLM provider is incentivized to keep users locked in, not to enable portability. The interop layer must come from a third party.

### Market sizing

The addressable market is professionals who use LLMs as a regular part of their workflow and experience friction around retrieval, portability, or collaboration. Conservative estimate: there are approximately 50M weekly active ChatGPT users and growing populations on Claude, Gemini, and others. The initial target is the top 5–10% by usage intensity (~5–10M users) who conduct enough sessions that retrieval becomes painful. At a $10–15/month price point for individuals and $20–30/seat for teams, this represents a **$600M–3.6B annual TAM** at maturity.

### Realistic targets (by September 2026)

- Working browser extension with push/pull for at least one major LLM platform (Claude or ChatGPT)
- Functional repository with search, tagging, and layered summary generation
- 50–100 beta users in a closed pilot, with validated push/pull engagement loops
- Measured summarization quality with user satisfaction scores above 4/5

---

## User Segments

### Segment 1: Power individual (primary, v1 target)

A knowledge worker who uses LLMs 5+ times per week across sustained projects. They are a product manager writing specs, a researcher iterating on analysis, a consultant developing frameworks, or a founder building strategy. Their core pain: they had a critical conversation last week and cannot find it or rebuild the context. They often use 2+ LLM platforms.

**Key persona: Priya**, a senior PM at a mid-stage startup. She uses Claude for product strategy and ChatGPT for customer research summaries. She has 200+ conversations across both platforms and regularly wastes 15–20 minutes re-establishing context that she already developed in a prior session.

### Segment 2: Collaborative team (secondary, v3 target)

A small team (2–8 people) using LLMs as part of their shared workflow. They are a product team where the PM develops requirements in Claude, the designer explores UI patterns in ChatGPT, and the engineer scopes technical feasibility in Gemini. Their core pain: no one knows what context anyone else has established. Decisions get made in private LLM conversations and never surface.

**Key persona: Team Acme**, a 4-person product squad. The PM, designer, and two engineers each run their own LLM conversations about the same feature. They sync in standups, but nuanced reasoning and trade-off analysis from those conversations never transfers. The PM has to re-explain decisions she already worked through with Claude.

### Use cases to nail in v1

1. **Retrieval:** User had a conversation 8 days ago where they finalized a database schema. They search ContextHub, find it in under 10 seconds, and pull the relevant decisions into a new conversation.
2. **Continuation:** User wraps up a strategy conversation on Friday. On Monday, they pull the context into a new session and continue iterating without any re-explanation.
3. **Cross-session synthesis:** User has had 4 separate conversations about pricing strategy over 3 weeks. They pull all 4 summaries and ask the LLM to synthesize the evolution of their thinking.

---

## Value Proposition and Differentiators

### Core value proposition

> **ContextHub makes every LLM conversation you have compound into the next one. Push what you built, pull what you need, never start from zero again.**

### Three headline features

1. **One-click push with intelligent summarization.** End a conversation and push it to your repository in under 10 seconds. ContextHub auto-generates a layered summary: a short description (the commit message), a structured context block capturing decisions, artifacts, and open questions, and the raw transcript. You review, optionally edit, and confirm.

2. **Semantic search across your entire conversation history.** Find any past conversation by what it was about, not which keywords you happened to use. Search returns results ranked by relevance with preview summaries, so you can locate the right context without re-reading entire transcripts.

3. **Context-aware pull that injects at the right resolution.** Pull past context into a new conversation and ContextHub formats it for the LLM you are using. Need a quick refresher? It injects the summary. Need deep continuation? It injects the full structured block. The LLM picks up exactly where you left off.

### How this is better than the status quo

| Current approach | Problem | ContextHub |
|---|---|---|
| Start a new conversation | Lose all prior context. Re-derive from scratch. | Pull prior context in one click. LLM continues where you left off. |
| Platform search | Keyword-based, poor recall on long conversations. | Semantic search over structured summaries. Find by meaning, not keywords. |
| Copy-paste into Google Docs | Manual extraction, not structured for LLM consumption. | Auto-generated, LLM-optimized context objects. Pull-ready. |
| Share screenshots / outputs | Lossy, no reasoning chain, not actionable. | Shareable context blocks that preserve decisions and rationale. |

### Competitive moat

- **Cross-platform interop layer.** No LLM provider will build portability to competitors. ContextHub is the neutral layer between platforms. This moat strengthens as more platforms emerge.
- **Conversation interchange format.** By defining the standard schema for how LLM conversations are represented portably, ContextHub becomes infrastructure. Open-sourcing this spec could accelerate adoption the way Git object format enabled Git dominance.
- **Compounding repository value.** Every push makes the repository more valuable. After 3 months of usage, a user has a searchable knowledge base of all their LLM-assisted work. Switching costs are high and grow over time.

---

## Functional Requirements

This section describes the core features required for v1 (single-user, single-platform push/pull). Features are scoped to the minimum set needed to validate the core loop: push a conversation, search the repository, pull context into a new conversation.

### Feature priority matrix

| Feature | Power individual | Collab team | User story | Priority |
|---|---|---|---|---|
| Push flow | Yes | Yes | As a user, I want to save a completed conversation so I can retrieve it later. | P0 — Must have |
| Layered summarization | Yes | Yes | As a user, I want auto-generated summaries at multiple levels of detail. | P0 — Must have |
| Repository + search | Yes | Yes | As a user, I want to find a past conversation by topic. | P0 — Must have |
| Pull + injection | Yes | Yes | As a user, I want to load past context into a new chat. | P0 — Must have |
| Conversation scoping | Yes | No | As a user, I want to push only the relevant portion of a conversation. | P1 — Should have |
| Backfill import | Yes | No | As a user, I want to import my existing conversation history. | P1 — Should have |
| Cross-platform pull | Yes | No | As a user, I want to pull Claude context into ChatGPT. | P2 — v2 feature |
| Shared repositories | No | Yes | As a team member, I want to access my teammate's pushed context. | P3 — v3 feature |
| Conflict detection | No | Yes | As a team, we want to see when two people made contradictory decisions. | P3 — v3 feature |

---

### Feature 1: Push flow

The push flow is the entry point of the entire product. If pushing is not fast, intuitive, and low-friction, users will not build a repository and the product fails. The target is **under 10 seconds** from conversation end to confirmed push.

#### 1.1 Trigger mechanism

The push flow is triggered via the browser extension. Two trigger modes:

- **Manual:** User clicks the ContextHub extension icon or a persistent sidebar button. This is the primary trigger for v1.
- **Prompted:** Extension detects a long idle period or tab-close intent and shows a non-intrusive prompt asking if the user wants to push. This is a stretch goal for v1.

#### 1.2 Conversation scoping

Before summarization, the user can choose to push the full conversation or select a portion. The extension displays the conversation with selectable message boundaries. The user highlights the relevant range and confirms. Default is the full conversation. This addresses the problem that many conversations span multiple unrelated topics.

#### 1.3 Layered summary generation

On push, ContextHub generates three layers of summary via a single LLM call:

1. **Commit message (1–2 sentences):** A short, searchable description of what the conversation accomplished. Example: *"Finalized PostgreSQL schema for mentorship platform with 6 tables and defined API contract for mentor matching."*
2. **Structured context block:** A structured extraction containing: decisions made (with rationale), artifacts produced (schemas, code, outlines), open questions remaining, assumptions established, and key constraints identified. This is formatted as a well-organized markdown block optimized for LLM consumption on pull.
3. **Raw transcript:** The full conversation text, stored for audit and deep retrieval but not injected by default on pull.

#### 1.4 User review and edit

After generation, the user sees the commit message and structured context block in the extension sidebar. They can edit the commit message, add/remove items from the structured block, assign tags, and select which repository to push to. The raw transcript is stored automatically and is not editable. The user confirms with a single click.

#### 1.5 Repository assignment

Each push goes to a named repository. Users can create repositories at push time or select from existing ones. Repositories are simple named containers with no enforced hierarchy. Users can also apply freeform tags to any push for additional organization.

---

### Feature 2: Repository and search

The repository is where pushed context lives. It must support fast, intuitive retrieval across potentially hundreds of pushed conversations. Search quality is the single most important factor in whether users perceive value from the product.

#### 2.1 Repository dashboard

A web-based dashboard showing all repositories and their contents. Each repository displays its pushes in reverse-chronological order with the commit message, tags, source platform, and timestamp. Users can browse, filter by tag, and sort by date or relevance.

#### 2.2 Semantic search

Search operates over the commit message and structured context block layers using vector embeddings. Users type a natural language query (e.g., *"database schema for mentorship platform"*) and receive ranked results with highlighted matching context. Search does not operate over raw transcripts by default (too noisy) but offers a toggle to include full-text transcript search when summary-level results are insufficient.

#### 2.3 Context preview

Clicking a search result shows a preview panel with the commit message, structured context block, metadata (date, source platform, tags), and an expandable section for the raw transcript. From the preview, the user can initiate a pull.

---

### Feature 3: Pull and context injection

The pull flow is where the user realizes the value of having pushed. It must feel seamless: find context, inject it, and have the LLM immediately understand and build on it.

#### 3.1 Pull trigger

Pull is initiated from two entry points:

- **From the repository dashboard:** User finds a push via browsing or search and clicks "Pull to current conversation."
- **From the extension sidebar:** While in an active LLM conversation, the user opens the ContextHub sidebar, searches, and pulls directly into the current chat input field.

#### 3.2 Resolution selection

The user selects which layer to inject:

- **Summary only:** Injects just the commit message for lightweight context setting. Suitable for quick refreshers or when context window budget is tight.
- **Structured block (default):** Injects the full structured context block including decisions, artifacts, and open questions. This is the primary pull mode.
- **Full transcript:** Injects the raw conversation. Warning displayed if this exceeds an estimated context window threshold.

#### 3.3 Injection mechanism

For v1, injection works via the browser extension inserting formatted text into the LLM chat input field, prepended with a system-level framing prompt (e.g., *"The following is context from a prior working session. Use it to inform your responses."*). The injected content is formatted as clean markdown. The user can edit the injected text before sending.

**Fallback:** if DOM injection is unreliable, the extension copies the pull content to clipboard with a toast notification.

#### 3.4 Multi-pull

Users can pull from multiple pushes in a single action. The system concatenates the selected context blocks with clear delineation between sources, ordered by the user or by chronology. A token counter estimates the total injection size relative to the target platform's context window.

---

### Feature 4: Backfill import (P1)

This feature addresses the cold start problem. A new user's repository is empty, and the product provides no value until they push. Backfill import lets users bring in their existing conversation history so they experience retrieval value immediately.

#### 4.1 Platform export ingestion

Support ingestion of ChatGPT's bulk export (JSON format) and any other platforms that offer conversation exports. The system parses the export, segments conversations, and runs layered summarization on each one. Users see a progress indicator and can browse imported conversations as they are processed.

#### 4.2 Manual paste import

For platforms without export features, users can paste a conversation transcript manually. The system generates the layered summary and stores it as a push. This is the fallback for Claude and other platforms that lack bulk export at the time of launch.

---

### Feature 5: Conversation scoping (P1)

Many LLM conversations cover multiple topics in a single session. Pushing the entire conversation as one unit produces noisy, unfocused summaries. Conversation scoping lets users define the boundaries of what they are pushing.

#### 5.1 Automatic topic segmentation

At push time, the system uses an LLM call to identify distinct topic segments within the conversation and suggests split points. The user can accept the suggested segmentation or adjust it manually. Each segment can be pushed as a separate commit to the same or different repositories.

#### 5.2 Manual selection

The user can manually select a range of messages to include in the push by clicking start and end boundaries in the conversation view. Unselected messages are excluded from the summary but preserved in the raw transcript layer if the user chooses full-conversation archival.

---

## Go-to-Market Plan

### Launch strategy

ContextHub launches as a closed beta targeting LLM power users, specifically product managers, researchers, consultants, and technical founders who use AI tools daily and experience retrieval pain acutely. The initial platform focus is a Chrome extension for Claude.ai and/or ChatGPT.

### Distribution channels

- **Direct outreach:** Recruit initial beta users from communities where LLM power users congregate: AI Twitter/X, Hacker News, relevant subreddits (r/ChatGPT, r/ClaudeAI), and Stanford / university networks.
- **Content-led growth:** Publish content demonstrating the workflow problem and the ContextHub solution. Short demos, before/after comparisons, and workflow breakdowns.
- **Chrome Web Store:** Once the extension is stable, publish to the Chrome Web Store for organic discovery by users searching for LLM productivity tools.

### Messaging

- **Primary tagline:** *"Never start from zero again."*
- **Supporting message:** *"Every conversation you have with AI makes the next one smarter. Push what you built. Pull what you need."*

The core emotional promise is **relief** from the frustration of losing valuable work and the **empowerment** of compounding knowledge.

### Pricing (projected)

| Tier | Price | Includes |
|---|---|---|
| Free | $0 | Up to 50 pushes, 1 repository, basic search |
| Pro | $12 / month | Unlimited pushes, unlimited repositories, semantic search, cross-platform pull |
| Team | $25 / seat / month | Shared repositories, permissions, team search |

Pricing is not finalized and will be validated during beta.

---

## Metrics for Success

### Objective function

The **north star metric** is **weekly active pulls per user**. This measures whether users are deriving value from their repository. A user who pulls is a user who found something worth retrieving and injected it into a new workflow. Secondary metrics support diagnosis of funnel health.

### Key metrics

| Metric | Initial target | Aspirational | Why it matters |
|---|---|---|---|
| Weekly active pulls / user | ≥ 2 | ≥ 5 | North star. Proves retrieval value. |
| Push rate (conversations pushed / total conversations) | ≥ 20% | ≥ 50% | Measures habit formation. Low push rate = too much friction. |
| Summary quality score (user rating 1–5) | ≥ 3.5 | ≥ 4.5 | If summaries are bad, pulls are useless. |
| Search success rate (search → pull) | ≥ 40% | ≥ 70% | Measures search quality. Low rate = results are not useful. |
| Time to push | ≤ 15 sec | ≤ 8 sec | Friction proxy. Must stay below threshold. |
| D7 retention | ≥ 30% | ≥ 50% | Are users coming back after first week? |
| Pull-to-value (user reports pull was useful) | ≥ 60% | ≥ 85% | Qualitative validation that injected context helps. |

---

## Timeline

### Major milestones

| Date | Milestone | Deliverables |
|---|---|---|
| May 2026 | Architecture finalized | System design doc, tech stack decisions, conversation schema specification |
| June 2026 | Core engine complete | Summarization pipeline, repository storage, semantic search index |
| July 2026 | Extension alpha | Chrome extension with push/pull for one LLM platform, internal testing |
| Aug 2026 | Closed beta launch | 50–100 beta users, feedback loops, summarization quality iteration |
| Sep 2026 | v1 public launch | Chrome Web Store listing, landing page, backfill import, onboarding flow |
| Nov 2026 | v2 cross-platform | Platform adapters for second LLM provider, cross-platform pull |

---

## Design Considerations

- **Extension sidebar must be non-intrusive.** The ContextHub UI lives in a collapsible sidebar that does not interfere with the LLM conversation flow. It should feel like a natural extension of the chat interface, not a separate tool.
- **Push review screen must be scannable in under 5 seconds.** The commit message is displayed prominently. The structured block is collapsible. The user should be able to confirm or edit without reading the entire summary.
- **Repository dashboard should feel like a personal knowledge base, not a file manager.** Emphasize search and recent activity over hierarchical browsing. Most users will search, not browse.
- **Pull injection must be visually distinct from user-typed text.** When context is injected into the chat input, it should be clearly marked so the user knows what is being sent to the LLM and can edit before submitting.

---

## Technical Considerations

### Platform and architecture

The product consists of three components:

1. **Chrome browser extension** (TypeScript / React) — for push/pull UX and DOM interaction.
2. **Backend API** (Node.js or Python) — for repository storage, summarization orchestration, and search.
3. **Web dashboard** (React) — for repository browsing and management.

The extension communicates with the backend via authenticated REST API.

### Key technical risks

- **DOM fragility:** LLM platforms update their frontend frequently. The extension must abstract DOM interactions behind a platform-specific adapter layer that can be updated independently of the core extension logic. Monitor for breaking changes via automated tests against target platforms.
- **Summarization cost:** Each push requires at least one LLM API call. At scale, this is a significant cost center. Evaluate fine-tuned smaller models for summarization to reduce per-push cost. In v1, use Claude Haiku or GPT-4o-mini for cost efficiency.
- **Search quality:** Semantic search over short summaries requires high-quality embeddings. Evaluate embedding models (OpenAI ada-3, Cohere embed-v3, open-source alternatives) for retrieval quality on conversation summaries specifically.
- **Data privacy:** Conversation data is sensitive. All data must be encrypted at rest and in transit. Summarization should use trusted API providers with data processing agreements. The long-term roadmap should evaluate client-side summarization using local models to avoid sending conversation data to third-party APIs.

### Conversation interchange format

A critical piece of infrastructure is a standardized schema for representing LLM conversations portably. This schema must capture:

- Messages with roles and timestamps
- The model and platform used
- Conversation metadata
- The layered summary structure

Consider open-sourcing this specification to encourage ecosystem adoption and establish ContextHub as the standard.

---

## Open Questions

4. **Standalone interface vs. extension-only?** Should ContextHub also offer its own chat interface that wraps LLM APIs (like TypingMind), giving full control over UX and eliminating DOM fragility? This is a bigger build but a more defensible product. Needs validation on whether users would switch from native interfaces.
5. **Summarization model and prompt design:** What is the optimal summarization prompt structure for different conversation types (debugging, brainstorming, design review, strategy)? This requires systematic experimentation and possibly conversation-type classification before summarization.
6. **Auto-push vs. manual push:** Should conversations auto-save as drafts in ContextHub, reducing the push friction to zero but increasing storage / compute costs? Or does manual push serve as a valuable curation signal that keeps the repository high-quality?
7. **Repository as atomic unit:** Is a "repository" the right organizational metaphor for non-developer users? Would "project," "workspace," or "notebook" resonate better? Needs user testing.
8. **Relationship to personal memory tools:** How does ContextHub relate to platform-native memory features (Claude memory, ChatGPT memory) and personal knowledge management tools? Is it complementary or competitive? Positioning needs to be clear.
9. **MVP definition:** Can v1 ship with just push + search (no pull/injection) and still validate the core hypothesis? This would dramatically reduce scope but removes the "close the loop" moment where the user experiences the full value.
