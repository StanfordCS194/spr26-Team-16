# Customer Discovery for ContextHub

ContextHub is a version-control system for LLM-assisted knowledge work — a tool that lets users push completed AI conversations to a searchable repository and pull their context into new sessions across platforms. This document describes the customer-discovery work we did to validate and sharpen our target audience: the rationale for who we believed the desperate user to be, how we got to know that audience, the volume and nature of our real-time interactions, the clickable HTML prototype we put in front of them, and the measurement approach we designed to collect structured feedback beyond our own impressions.

---

## 1. Rationale for Target Audience: Who Is the Desperate User?

Our initial hypothesis was that the desperate user for ContextHub would be a **university student who is an LLM power user**. Four arguments pointed us here.

- **First, adoption intensity** — students are among the highest-frequency adopters of AI tools in any demographic group, so friction shows up quickly in their daily behavior.
- **Second, workflow fluidity:** a student writing a literature review, a problem set, and a design document in the same week imposes a more demanding shape on an AI-context tool than a professional working on a single project for a month.
- **Third, accessibility:** as members of a university community, we could have real, sustained conversations with our target users rather than relying on scheduled video calls with distant personas.
- **Fourth, pipeline logic:** today's student power users become tomorrow's professional power users, and a tool that earns a place in their workflow during school is well-positioned to persist when they enter the workforce.

Once we started talking to students, we quickly saw that the generic "student who uses AI" is **not** the desperate user. Most of the people we talked to early on used a single tool (almost always ChatGPT), on a free tier, on short-horizon work where friction was annoying but not blocking. The desperate user, we came to believe, sits inside that broader population but is defined by four concrete behaviors rather than by demographics:

- They use **two or more distinct AI platforms at least weekly** (e.g., ChatGPT plus Claude, or ChatGPT plus Gemini plus NotebookLM)
- They work on projects that **span multiple weeks** — thesis chapters, startup builds, multi-module coursework, research projects
- They have recently had a **concrete failure** where they could not retrieve or reproduce prior AI-assisted work
- They have already built a **workaround** — notes, screenshots, pinned chats, prompt libraries — because the pain was costing them real time

That last criterion, **workaround sophistication**, became our sharpest screen. People do not invest in workarounds for problems that are merely theoretical.

---

## 2. How We Got to Know the Target Audience

We built our understanding of the desperate user by having direct conversations with students in our network before we formally screened anyone. Over three to four days, we had about **15 casual conversations** — over coffee, between classes, in group chats — with CS classmates, friends in graduate engineering programs, members of Stanford AI-focused student organizations, and a couple of colleagues in a campus AI research lab. We asked them about their week, which AI tools they were using, what annoyed them, whether they had ever lost a conversation they wanted back. These were not pitches and they were not interviews; they were the kinds of conversations any student has with another student about their workflow.

Alongside these conversations, we did a small amount of desk research — student AI-adoption surveys, a scan of adjacent products — mostly to sanity-check that what we were hearing matched broader trends. Desk research was never the primary source of our understanding; the conversations were.

By the end of that short sprint, we had a sharp enough picture of the desperate user that we could identify one within the first five minutes of a conversation. We knew which programs and habits correlated with true multi-tool usage and sustained project work, and which did not — and we recruited our formal research cohort accordingly.

---

## 3. Real-Time Interactions With the Target Audience

We interacted in real time with **40 unique members** of the target audience through two complementary channels.

### Table 1. Research methods and participation volume

| Research Method | N | Avg. Duration | What we learned from this channel |
|---|---|---|---|
| Depth interviews (prototype walkthrough included) | 12 | 30–50 min | Workflow detail, current workarounds, informed prototype feedback |
| Prototype reaction sessions (shorter follow-ups) | 28 | 20–30 min | Larger sample for reaction ratings, feature ranking, and willingness-to-pay |
| **Total unique participants** | **40** | — | Across both channels, with no overlap between them |

The **depth interviews** were the anchor of our research. Twelve sessions of 30–50 minutes each, with participants who fit the refined desperate-user profile. Each session combined a workflow walkthrough (where we asked participants to describe their most recent significant AI-assisted project in chronological order), a pain-moment excavation (where we asked them to recall the most recent specific instance of their workflow failing), a walkthrough of our HTML prototype, and a structured price-anchoring exercise. Seven were conducted in person on campus; five over video. Participants were recruited through referrals from the informal conversations described in Section 2 and through postings in Stanford Slack channels focused on AI, entrepreneurship, and computer science.

The **prototype reaction sessions** were shorter (20–30 minutes) and focused specifically on response to the UI. Twenty-eight of them, recruited via opt-in from a short screening survey we distributed through the same channels. These sessions gave us the larger sample we needed for the structured quantitative measures — reaction ratings, feature ranking, willingness-to-pay — that our depth interviews alone could not support at meaningful n.

Table 2 captures the range of reactions we heard across sessions and what each one crystallized for us.

### Table 2. Representative quotes and the insights we gleaned

| Quote from Session | Insight We Gleaned |
|---|---|
| *"I've stopped trying to remember what I told which tool. I just re-paste the same project brief every morning into whichever one I'm starting with."* — P08, post-doc, AI Lab | Heavy users have given up on continuity. The manual re-pasting is exactly what ContextHub would automate. |
| *"I spent two hours yesterday hunting for the Claude conversation where I decided on federated auth. I never found it, so I just rederived the argument from scratch."* — P01, PhD, CS | Retrieval failure has a concrete time cost — hours, not moments. Pain is measurable in real work lost. |
| *"I have a 400-word 'who I am, what I'm building' paragraph I paste at the top of every new conversation. Every. Day."* — P12, CS undergrad / founder | Users are already doing manually what ContextHub would automate. The sophistication of the workaround is the clearest signal of latent demand. |
| *"My reading lives in NotebookLM. My thinking lives in Claude. They don't know about each other. I'm the bridge."* — P04, PhD, Biology | Cross-platform gap is felt as explicit bridge work. Portability is the core value, not a peripheral feature. |
| *"The idea is great, but how is this different from Claude Projects? I already put my stuff in a project."* — P03, MS, CS | The most common objection (43% of participants). Differentiation from platform-native alternatives is not yet sharp in the prototype. |
| *"Honestly, I don't have this problem. I use ChatGPT and that's it."* — P10, CS undergrad (Y2) | Single-tool users are not the ICP. A useful negative signal for screening future research participants. |

---

## 4. The HTML Prototype and How We Measured Response

We built a **clickable HTML prototype** — a single static file with linked pages — that simulated the complete ContextHub experience end-to-end. There was no backend; every screen was pre-populated with realistic sample data, and each click transitioned to the next simulated state. The prototype spanned roughly 20 connected pages covering the three core loops:

- **The push flow:** a simulated Claude.ai conversation with the ContextHub sidebar attached, a commit-message review screen, an edit-and-tag screen, a confirmation state.
- **The repository dashboard:** list view with commit messages, tags, and timestamps, plus a search bar.
- **The pull flow:** search results with previews, a resolution selector, a token-count estimate, and the injected context appearing in a new conversation.

### Purpose of the prototype

The prototype existed for **concept validation, not usability testing**. Its job was to give participants enough of a concrete "see and feel" that they could react to ContextHub as a real product rather than as an abstract pitch. That informs what we measured — and what we did not. Because we walked participants through the flow rather than asking them to navigate it unsupervised, metrics like task-completion rate and time-on-task would not have been meaningful. The question we were answering in this round was whether the concept, shown concretely, solves a problem people actually have and at a price they would actually pay.

### How we ran the sessions

We walked participants through the prototype at a natural pace, pausing at key screens to let them react. For the depth interviews, the walkthrough happened roughly two-thirds of the way into the session, after the workflow interview had grounded them in their own context. For the prototype reaction sessions, the walkthrough was the core of the session.

### What we measured, beyond our own impressions

We designed six structured measures to collect data we could trust independently of our in-the-room reactions, administered in the same order for every participant:

1. **Comprehension.** After the walkthrough, we asked participants to explain ContextHub back to us in their own words. Responses were timed, and the explanations were later blind-coded by two raters against a two-point rubric (captured push, search, and pull correctly = 2 / captured one or two = 1 / captured none = 0).
2. **Problem-fit.** A 5-point Likert scale on the statement *"This would solve a real problem I have."*
3. **Overall reaction.** A 1–10 Likert scale capturing their summary feeling about the concept.
4. **Feature ranking.** A forced-choice ranking of five core features (push, search, pull, cross-platform pull, layered summary) in order of perceived importance.
5. **Willingness to pay.** Three separate yes/no questions anchored at $5, $10, and $20 per month, rather than a single open-ended "what would you pay" question.
6. **Intent and objections.** A binary yes/no on *"would you sign up for a beta if invited today,"* followed by an open question about their top concern. Open responses were later thematically coded.

Together these produced a dataset where the patterns in the numbers could be checked against our qualitative impressions rather than the other way around. Reaction ratings correlated with intent-to-try (r ≈ 0.7) and with willingness to pay at $10, and participants with the highest workaround sophistication at intake scored systematically higher on every downstream measure — both patterns visible in the data before we noticed them in the sessions themselves.

### Table 3. Aggregate prototype-response data (N = 40)

| Metric | Result | What this tells us |
|---|---|---|
| Participants who saw the prototype (N) | 40 | 12 depth interviews + 28 prototype reaction sessions |
| Mean time to self-explain ContextHub after walkthrough (sec) | 47 | Under the 60s threshold we set for "gets it quickly" |
| Accurate self-explanation on blind-coded 2-pt rubric | 73% | Core concept is intelligible; the Git analogy landed for technical users |
| "This would solve a real problem I have" (5-pt Likert, % rating 4 or 5) | 68% | Majority see genuine fit, but not unanimous |
| Mean overall reaction rating (1–10 Likert) | 6.8 | Positive but not enthusiastic; ranges from 3 (dismissive) to 9 (ready to install) |
| Top-ranked features (forced choice) | Cross-platform pull 52% / Layered summary 27% | Portability is the primary perceived value; right-resolution injection is a distant second |
| Would sign up for a beta if invited today (% yes) | 58% | Low-commitment trial intent is reasonable |
| Willingness to pay $5 / $10 / $20 per month (% yes) | 58% / 34% / 18% | Meaningful drop at $10; the $20 tier is concentrated in the grad/post-doc sub-group |
| Most common objections (thematic coding, top 3) | (1) "How is this different from Claude Projects?" 43%  (2) Privacy / who sees my chats 27%  (3) Will it work with [tool I use]? 18% | — |

---

## 5. Depth Interview Log

Table 4 is the participant-level detail behind Table 3 — twelve depth-interview participants with their workflows, workarounds, prototype-reaction scores, and willingness-to-pay signals.

### Table 4. Depth interview log with prototype reaction scores (N = 12)

| ID | Role / Program | AI Tools Used Weekly | AI Hrs/Wk | Key Pain Point (Observed or Reported) | Current Workaround | Proto Rxn (1-10) | WTP @ $20/mo |
|---|---|---|---|---|---|---|---|
| P01 | PhD, CS (Y3) | ChatGPT, Claude, Cursor, Copilot, Obsidian | 22 | Lost the reasoning chain from a 2-week-old Claude conversation when she needed to cite a design decision in her thesis proposal. | Obsidian notes plus manually pasted Claude summaries at session end. | 9 | Yes |
| P02 | PhD, EE (Y2) | ChatGPT, Claude, Gemini | 15 | Re-explains thesis setup, advisor preferences, and prior findings to every new chat across all three tools. | Personal system-prompt doc; pastes at top of each new session. | 8 | Yes |
| P03 | MS, CS (Y1) | ChatGPT, Cursor, Copilot | 18 | Switching from ChatGPT (debugging) to Claude Code (refactor) forces him to re-state project architecture every time. | Screenshots in a Finder folder; occasional README paste. | 7 | Maybe (at $10) |
| P04 | PhD, Biology (Y4) | ChatGPT, Claude, NotebookLM | 12 | Her thinking happens in Claude and doesn't round-trip into the NotebookLM notebook where her sources live. | Copy-pastes Claude outputs into a Google Doc, which NotebookLM re-ingests. | 7 | Maybe |
| P05 | Undergrad, CS (Y3) | ChatGPT, Claude Code, Cursor | 14 | Could not locate the Claude Code conversation where he solved an SVM kernel bug during a CS229 project; re-derived it from scratch. | Browser history search; occasionally pins chats. | 6 | No |
| P06 | Undergrad, EE (Y4) | ChatGPT, Claude, Copilot | 16 | For his senior project, context is scattered across three tools; nothing ties them together. | Notion page with copy-pasted key outputs. | 7 | No (cost-sensitive) |
| P07 | MBA, GSB (Y2) | ChatGPT, Claude, Perplexity | 8 | Different tools for different class types; no single view of her AI-assisted work for the quarter. | No explicit workaround; accepts tool sprawl. | 5 | No |
| P08 | Post-doc, AI Lab | ChatGPT, Claude, Cursor, custom API scripts | 25 | Cannot reconstruct the prompt chain that led to a key experimental insight 3 weeks ago; chain spanned two models and four sessions. | Personal prompt library in Git; Notion log of outputs. | 9 | Yes |
| P09 | MS, EE (Y2) | ChatGPT, Gemini, NotebookLM | 9 | Uses NotebookLM for coursework and ChatGPT for personal projects; wishes the two shared what she had taught each. | None; accepts the friction. | 6 | Maybe |
| P10 | Undergrad, CS (Y2) | ChatGPT only | 8 | Reported no significant retrieval or portability pain; work is primarily single-session homework. | N/A | 3 | No |
| P11 | PhD, Stats (Y3) | ChatGPT, Claude, R-Copilot, Cursor | 20 | Analysis code (Cursor) and writeup (Claude) drift out of sync; cannot recall which version of the model spec was 'current' last week. | Notion page cross-linking session URLs and key outputs. | 8 | Yes |
| P12 | Undergrad, CS (Y4, building startup) | ChatGPT, Claude, Cursor, Copilot, Perplexity | 24 | Juggles startup engineering, coursework, and job search across five tools; context is constantly fragmented. | Dedicated Notion wiki of LLM outputs organized by project. | 9 | Yes (at $10 student) |

---

## 6. Findings & ICP

The ICP is the **multi-tool technical researcher**, defined by four concurrent traits rather than by demographics alone:

- **(a) Role** — graduate student (PhD or late-stage MS) or post-doc in a technical field (CS, EE, Stats, AI research), or advanced undergraduate building a startup or multi-month senior project.
- **(b) Tool footprint** — three or more LLM platforms in active weekly rotation, 15+ hours per week.
- **(c) Project shape** — sustained work spanning weeks or months.
- **(d) Workaround sophistication** — has already built a personal context-management workaround.

In Table 4, this maps to **P01, P02, P08, P11, and P12** — the only participants rating the prototype 8 or higher and the only ones willing to pay at their tier ($20/month for the graduate/post-doc core; a $10 student tier for the founder adjacency). The ICP is **not** the casual undergraduate on one tool, the MBA student, or anyone on a free tier content to re-paste the same brief each morning.

Three findings from this round support and refine this ICP definition.

**First, pain and willingness to pay concentrate in graduate-level technical work.** Eight of twelve participants rated the prototype 7 or higher, and all were graduate students, a post-doc, or advanced undergraduates with multi-week projects. Four of twelve said yes at $20/month (three grads plus the post-doc); a fifth, the CS-senior founder (P12), was willing only at a $10 student rate. This narrows our original hypothesis significantly.

**Second, workaround sophistication predicts everything downstream.** Participants who had built prompt libraries, context documents, or Notion logs gave the highest ratings and were the only ones consistently willing to pay at $20. Those with weak or absent workarounds gave the lowest ratings and were largely unwilling to pay. We plan to use workaround sophistication as the primary screening signal going forward.

**Third, the differentiation is not yet sharp enough.** 73% of participants accurately self-explained ContextHub in under 60 seconds. But 43% asked some version of "how is this different from Claude Projects?" Cross-platform pull was ranked the top feature by 52%, which tells us where the sharpened positioning should lead.
