# ContextHub

**Version control for LLM-assisted knowledge work.**

ContextHub turns important AI conversations into durable, searchable, reusable context — so the work you do with LLMs compounds instead of disappearing into chat history.

> Push what you built. Pull what you need. Never start from zero again.

---

## The problem

LLM conversations are where real work happens: product specs, architecture decisions, research synthesis, debugging trails, and open questions. But that work is fragile.

- **Retrieval fails.** Conversations older than a few days are effectively lost. Platform search is keyword-based and breaks down on long, meandering threads.
- **Context does not carry forward.** Every new chat starts cold. Users re-derive conclusions they already reached and re-explain context the model already had.
- **Knowledge is trapped in one platform.** As people use multiple models for different strengths, there is no portable layer for the context they have already built.

ContextHub is the memory layer between you and your AI tools — a shared organizational substrate that routes the right knowledge into the next conversation.

---

## How it works

ContextHub runs a simple loop designed for everyday knowledge work:

| Step | What you do | What ContextHub does |
|------|-------------|----------------------|
| **Push** | Finish a conversation and save it from the browser extension | Generates a three-layer summary, indexes it for search, and stores it in your workspace |
| **Search** | Describe what you are looking for in natural language | Returns semantically ranked results over structured summaries — find work by meaning, not keywords |
| **Pull** | Start a new conversation and inject prior context | Formats the right resolution for the LLM and injects it with source provenance |

### Three context resolutions

Every push is stored at three levels of detail so you can match context to the task:

1. **Commit message** — a one-line, searchable reminder
2. **Structured block** — decisions, artifacts, assumptions, constraints, and open questions
3. **Raw transcript** — the full conversation when you need everything

---

## Who it is for

ContextHub is built for people doing sustained, high-stakes work with AI:

- **Product and project teams** keeping specs, tradeoffs, and design decisions from vanishing
- **Engineers** reusing debugging trails, implementation plans, and generated artifacts
- **Researchers and analysts** carrying prior findings and open questions into the next investigation
- **Power individual users** who run dozens of LLM sessions per week across long-running projects

---

## Product today and where we are headed

**Today (v0):** Claude.ai-first experience with a Chrome extension, web dashboard, semantic search, and push/search/pull across a personal workspace.

**Next:** Cross-platform portability (pull Claude context into ChatGPT, Gemini, and others), then shared team workspaces so collaborators can build on each other's LLM-assisted work.

Longer term, ContextHub aims to be a **GitHub-aligned context layer for enterprise-scale LLM use** — a reusable meta-LLM substrate that helps route questions to the right knowledge and code context so teams get faster, grounded answers across assistants and workflows.

---

## Why ContextHub

| Status quo | ContextHub |
|------------|--------------|
| Start a new chat and lose prior context | Pull prior context in one click and continue where you left off |
| Keyword search over chat logs | Semantic search over structured summaries |
| Copy-paste into docs manually | Auto-generated, LLM-ready context objects |
| Context locked inside one provider | Portable interchange format designed for cross-platform reuse |

No LLM provider is incentivized to solve cross-platform portability. ContextHub is the neutral layer — and every push makes your personal knowledge base more valuable over time.

---

## Get started

Implementation lives in [`contexthub/`](./contexthub/).

- **Product & engineering docs:** [`contexthub/README.md`](./contexthub/README.md)
- **Full PRD:** [`PRD.md`](./PRD.md)
- **Local development:** [`contexthub/docs/START_FROM_SCRATCH.md`](./contexthub/docs/START_FROM_SCRATCH.md)

---

## Team

**XARPA** — Stanford CS194 (`spr26-Team-16`)

| Name |
|------|
| Cici Hou |
| Romina Jately |
| Abhiraj Gupta |
| Phillip Miao |

**Team wiki:** [spr26-Team-16 Wiki](https://github.com/StanfordCS194/spr26-Team-16/wiki) — roster, branding, and course deliverables.
