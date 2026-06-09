"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import {
  getSupabaseSession,
  isSupabaseAuthConfigured,
  onSupabaseAuthStateChange,
  signInWithGoogle
} from "@/lib/supabase";

type ConversationListItem = {
  id: string;
  workspace_id: string;
  conversation_title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  title: string | null;
  summary: string | null;
  details: SummaryDetailsRaw | null;
};

type SummaryDetailsRaw = {
  summary?: unknown;
  key_takeaways?: unknown;
  tags?: unknown;
};

type PushHistoryResponse = {
  items: ConversationListItem[];
};

type PushDetailSummaryLayer = {
  layer: string;
  content_markdown: string | null;
  content_json: Record<string, unknown>;
};

type PushDetailResponse = {
  id: string;
  workspace_id: string;
  status: string;
  failure_reason: string | null;
  source_platform: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  raw_transcript: string | null;
  summaries: PushDetailSummaryLayer[];
};

type PullResponse = {
  payload_markdown: string;
  token_estimate: number;
};

type ConversationTurn = { role: "user" | "assistant"; text: string };

function parseTranscript(raw: string | null): ConversationTurn[] | null {
  if (!raw?.trim()) return null;
  try {
    const data = JSON.parse(raw) as { messages?: Array<{ role?: string; content?: unknown }> };
    if (!Array.isArray(data.messages)) return null;
    const turns: ConversationTurn[] = [];
    for (const m of data.messages) {
      const role: "user" | "assistant" = m.role === "assistant" ? "assistant" : "user";
      const parts: string[] = [];
      if (Array.isArray(m.content)) {
        for (const block of m.content) {
          if (
            block &&
            typeof block === "object" &&
            "type" in block &&
            (block as { type?: string }).type === "text" &&
            typeof (block as { text?: unknown }).text === "string"
          ) {
            parts.push((block as { text: string }).text);
          }
        }
      }
      const text = parts.join("\n").trim();
      if (text) turns.push({ role, text });
    }
    return turns.length ? turns : null;
  } catch {
    return null;
  }
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";

  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffSec = Math.round(diffMs / 1000);
  const diffMin = Math.round(diffSec / 60);
  const diffHr = Math.round(diffMin / 60);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin} min${diffMin === 1 ? "" : "s"} ago`;
  if (diffHr < 24 && d.getDate() === now.getDate()) return `${diffHr} hour${diffHr === 1 ? "" : "s"} ago`;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) {
    return `Yesterday at ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  }

  const sevenDaysAgo = new Date(now);
  sevenDaysAgo.setDate(now.getDate() - 7);
  if (d > sevenDaysAgo) {
    return d.toLocaleDateString(undefined, { weekday: "short" }) +
      ` at ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`;
  }

  if (d.getFullYear() === now.getFullYear()) {
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatAbsolute(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

export default function HomePage() {
  const supabaseEnabled = isSupabaseAuthConfigured();
  const [signedIn, setSignedIn] = useState(false);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const [chats, setChats] = useState<ConversationListItem[]>([]);
  const [chatsLoading, setChatsLoading] = useState(false);
  const [chatsRefreshing, setChatsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PushDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);

  const [copyState, setCopyState] = useState<"idle" | "copying" | "copied" | "failed">("idle");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const renameInputRef = useRef<HTMLInputElement | null>(null);

  // ---- auth bootstrap
  useEffect(() => {
    if (!supabaseEnabled) {
      setAuthLoading(false);
      return;
    }
    getSupabaseSession().then((session) => {
      setSignedIn(Boolean(session));
      setAuthLoading(false);
    });
    const unsubscribe = onSupabaseAuthStateChange((session) => {
      setSignedIn(Boolean(session));
    });
    return unsubscribe;
  }, [supabaseEnabled]);

  const loadChats = useCallback(async (mode: "initial" | "refresh" = "initial") => {
    if (mode === "refresh") setChatsRefreshing(true);
    else setChatsLoading(true);
    setError(null);
    const res = await apiFetch<PushHistoryResponse>("/v1/pushes/history?limit=50");
    setChatsLoading(false);
    setChatsRefreshing(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setChats(res.data.items || []);
  }, []);

  useEffect(() => {
    if (signedIn) loadChats("initial");
  }, [signedIn, loadChats]);

  // ---- detail load
  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setShowTranscript(false);
    setCopyState("idle");
    apiFetch<PushDetailResponse>(`/v1/pushes/${activeId}`).then((res) => {
      setDetailLoading(false);
      if (res.ok) {
        setDetail(res.data);
      } else {
        setDetail(null);
        setError(res.message);
      }
    });
  }, [activeId]);

  // ---- close kebab menu on outside click
  useEffect(() => {
    if (!openMenuId) return;
    function onDocClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenuId(null);
      }
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [openMenuId]);

  const filtered = useMemo(() => {
    if (!filter.trim()) return chats;
    const q = filter.toLowerCase();
    return chats.filter((c) => {
      const title = (c.title || c.conversation_title || "").toLowerCase();
      const summary = (c.summary || "").toLowerCase();
      return title.includes(q) || summary.includes(q);
    });
  }, [chats, filter]);

  async function handleSignIn() {
    setAuthError(null);
    try {
      await signInWithGoogle();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Sign-in failed.");
    }
  }

  async function handleCopyContext() {
    if (!activeId) return;
    setCopyState("copying");
    const res = await apiFetch<PullResponse>("/v1/pulls", {
      method: "POST",
      body: JSON.stringify({
        selections: [{ push_id: activeId, include_transcript: true }],
        target_platform: "claude_ai",
        origin: "dashboard"
      })
    });
    if (!res.ok) {
      setCopyState("failed");
      setError(res.message);
      setTimeout(() => setCopyState("idle"), 2000);
      return;
    }
    try {
      await navigator.clipboard.writeText(res.data.payload_markdown);
      setCopyState("copied");
      setTimeout(() => setCopyState("idle"), 2000);
    } catch {
      setCopyState("failed");
      setTimeout(() => setCopyState("idle"), 2000);
    }
  }

  async function handleDelete(id: string) {
    setOpenMenuId(null);
    if (!confirm("Delete this conversation? This can't be undone.")) return;
    setDeletingId(id);
    const res = await apiFetch<null>(`/v1/pushes/${id}`, { method: "DELETE" });
    setDeletingId(null);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setChats((cur) => cur.filter((c) => c.id !== id));
    if (activeId === id) {
      setActiveId(null);
      setDetail(null);
    }
  }

  function startRename(id: string, currentTitle: string) {
    setOpenMenuId(null);
    setActiveId(id);
    setRenamingId(id);
    setRenameDraft(currentTitle);
    // Focus the input on the next tick after it's rendered.
    setTimeout(() => renameInputRef.current?.select(), 0);
  }

  function cancelRename() {
    setRenamingId(null);
    setRenameDraft("");
  }

  async function commitRename() {
    if (!renamingId) return;
    const next = renameDraft.trim();
    if (!next) {
      cancelRename();
      return;
    }
    // Skip API call if title is unchanged.
    const current = chats.find((c) => c.id === renamingId);
    const existing = current?.title || current?.conversation_title || "";
    if (next === existing) {
      cancelRename();
      return;
    }
    setRenameSaving(true);
    const res = await apiFetch<PushDetailResponse>(`/v1/pushes/${renamingId}`, {
      method: "PATCH",
      body: JSON.stringify({ title: next })
    });
    setRenameSaving(false);
    if (!res.ok) {
      setError(res.message);
      cancelRename();
      return;
    }
    // Optimistic update on the list + detail.
    setChats((cur) =>
      cur.map((c) =>
        c.id === renamingId ? { ...c, title: next, conversation_title: next } : c
      )
    );
    if (detail && detail.id === renamingId) {
      setDetail({ ...detail, title: next });
    }
    cancelRename();
  }

  // ---- render

  if (authLoading) {
    return (
      <div className="loading">
        <span className="spinner" />
        Loading…
      </div>
    );
  }

  if (!supabaseEnabled) {
    return (
      <section className="signin-hero">
        <h2>Sign-in not configured</h2>
        <p>
          Add <code>NEXT_PUBLIC_SUPABASE_URL</code> and <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> to{" "}
          <code>packages/dashboard/.env.local</code> and reload.
        </p>
      </section>
    );
  }

  if (!signedIn) {
    return (
      <PreLoginPage onSignIn={handleSignIn} authError={authError} />
    );
  }

  const detailDetails = detail
    ? {
        summary:
          (detail.summaries.find((s) => s.layer === "summary")?.content_json?.text as string | undefined) ||
          detail.summaries.find((s) => s.layer === "summary")?.content_markdown ||
          null,
        details: detail.summaries.find((s) => s.layer === "details")?.content_json as
          | SummaryDetailsRaw
          | undefined
      }
    : null;
  const turns = detail ? parseTranscript(detail.raw_transcript) : null;

  return (
    <div className="page">
      <div className="page-heading">
        <h1>Your conversations</h1>
        <p>Search and reuse Claude conversations you've saved from the extension.</p>
      </div>

      <div className="hero-search">
        <span className="search-icon"><SearchIcon /></span>
        <input
          className="input"
          type="search"
          placeholder="Search by title or topic"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        {filter ? (
          <button className="clear-btn" onClick={() => setFilter("")} type="button" aria-label="Clear search">
            <CloseIcon />
          </button>
        ) : null}
      </div>

      {error ? <p className="toast toast-error">{error}</p> : null}

      <div className="workspace">
        <aside className="list-panel">
          <div className="list-panel-header">
            <span className="list-panel-title">
              {filtered.length} conversation{filtered.length === 1 ? "" : "s"}
            </span>
            <button
              className="icon-btn"
              onClick={() => loadChats("refresh")}
              disabled={chatsRefreshing || chatsLoading}
              type="button"
              aria-label="Refresh"
              title="Refresh"
            >
              <RefreshIcon spinning={chatsRefreshing} />
            </button>
          </div>

          <div className="list-scroll">
            {chatsLoading ? (
              <div className="loading">
                <span className="spinner" />
                Loading…
              </div>
            ) : filtered.length === 0 ? (
              <div className="list-empty">
                {chats.length === 0 ? (
                  <>
                    <h3>Nothing here yet</h3>
                    <p>Save a conversation from the extension on Claude.ai to get started.</p>
                  </>
                ) : (
                  <>
                    <h3>No matches</h3>
                    <p>Try a different search term.</p>
                  </>
                )}
              </div>
            ) : (
              filtered.map((c) => {
                const isActive = activeId === c.id;
                const isMenuOpen = openMenuId === c.id;
                return (
                  <div
                    key={c.id}
                    className={`list-item-wrap${isActive ? " is-active" : ""}`}
                  >
                    <button
                      className={`list-item${isActive ? " is-active" : ""}`}
                      onClick={() => setActiveId(c.id)}
                      type="button"
                      disabled={deletingId === c.id}
                    >
                      <h3 className="list-item-title">
                        {c.title || c.conversation_title || "Untitled conversation"}
                      </h3>
                      {c.summary ? <p className="list-item-snippet">{c.summary}</p> : null}
                      <span className="list-item-date" title={formatAbsolute(c.created_at)}>
                        {formatRelative(c.created_at)}
                      </span>
                    </button>
                    <div
                      className="list-item-menu"
                      ref={isMenuOpen ? menuRef : null}
                    >
                      <button
                        className="kebab-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenMenuId(isMenuOpen ? null : c.id);
                        }}
                        type="button"
                        aria-label="More options"
                      >
                        <KebabIcon />
                      </button>
                      {isMenuOpen ? (
                        <div className="kebab-menu" role="menu">
                          <button
                            className="kebab-item"
                            onClick={() =>
                              startRename(
                                c.id,
                                c.title || c.conversation_title || ""
                              )
                            }
                            type="button"
                            role="menuitem"
                          >
                            <PencilIcon /> Rename
                          </button>
                          <button
                            className="kebab-item kebab-danger"
                            onClick={() => handleDelete(c.id)}
                            type="button"
                            role="menuitem"
                          >
                            <TrashIcon /> Delete
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </aside>

        <section className="detail-panel">
          {!activeId ? (
            <div className="detail-empty">
              <h2>Select a conversation</h2>
              <p>Pick one from the list to see its summary, key takeaways, and full transcript.</p>
            </div>
          ) : detailLoading ? (
            <div className="loading">
              <span className="spinner" />
              Loading conversation…
            </div>
          ) : !detail ? (
            <div className="detail-empty">
              <h2>Couldn't load conversation</h2>
              <p>The conversation may have been removed.</p>
            </div>
          ) : (
            <article className="detail-content">
              <header className="detail-header">
                <div className="detail-header-row">
                  {renamingId === detail.id ? (
                    <input
                      ref={renameInputRef}
                      className="input detail-title-input"
                      value={renameDraft}
                      onChange={(e) => setRenameDraft(e.target.value)}
                      onBlur={commitRename}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          commitRename();
                        } else if (e.key === "Escape") {
                          e.preventDefault();
                          cancelRename();
                        }
                      }}
                      disabled={renameSaving}
                      placeholder="Conversation title"
                      autoFocus
                    />
                  ) : (
                    <h2
                      className="detail-title detail-title-editable"
                      onClick={() => startRename(detail.id, detail.title || "")}
                      title="Click to rename"
                    >
                      {detail.title || "Untitled conversation"}
                      <span className="detail-title-edit-hint" aria-hidden="true">
                        <PencilIcon />
                      </span>
                    </h2>
                  )}
                  <button
                    className={`btn copy-btn ${copyState !== "idle" ? "copy-" + copyState : ""}`}
                    onClick={handleCopyContext}
                    disabled={copyState === "copying"}
                    type="button"
                  >
                    {copyState === "copying" ? (
                      <><span className="spinner spinner-on-blue" /> Copying…</>
                    ) : copyState === "copied" ? (
                      <><CheckIcon /> Copied</>
                    ) : copyState === "failed" ? (
                      <>Copy failed — try again</>
                    ) : (
                      <><CopyIcon /> Copy context</>
                    )}
                  </button>
                </div>
                <div className="detail-meta">
                  <span className={`status-pill status-${detail.status}`}>{detail.status}</span>
                  <span title={formatAbsolute(detail.created_at)}>{formatRelative(detail.created_at)}</span>
                  <span>{detail.source_platform}</span>
                </div>
              </header>

              <div className="detail-body">
                {detailDetails?.summary ? (
                  <div>
                    <p className="section-label">Summary</p>
                    <p className="summary-text">{detailDetails.summary}</p>
                  </div>
                ) : null}

                {asStringArray(detailDetails?.details?.key_takeaways).length > 0 ? (
                  <div>
                    <p className="section-label">Key takeaways</p>
                    <ul className="takeaways">
                      {asStringArray(detailDetails?.details?.key_takeaways).map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                {asStringArray(detailDetails?.details?.tags).length > 0 ? (
                  <div>
                    <p className="section-label">Tags</p>
                    <div className="tags">
                      {asStringArray(detailDetails?.details?.tags).map((t) => (
                        <span key={t} className="tag">{t}</span>
                      ))}
                    </div>
                  </div>
                ) : null}

                {turns && turns.length > 0 ? (
                  <div>
                    <p className="section-label">Transcript</p>
                    <button
                      className="transcript-toggle"
                      onClick={() => setShowTranscript((v) => !v)}
                      type="button"
                    >
                      {showTranscript ? "Hide transcript" : `Show transcript (${turns.length} message${turns.length === 1 ? "" : "s"})`}
                    </button>
                    {showTranscript ? (
                      <div className="transcript" style={{ marginTop: 10 }}>
                        {turns.map((t, i) => (
                          <div key={i} className="turn">
                            <span className={`turn-role ${t.role}`}>{t.role}</span>
                            <div className="turn-text">{t.text}</div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {!detailDetails?.summary &&
                asStringArray(detailDetails?.details?.key_takeaways).length === 0 &&
                !turns ? (
                  <div className="detail-empty" style={{ minHeight: "auto", padding: "24px 0" }}>
                    <p>This conversation is still being processed. Check back in a moment.</p>
                  </div>
                ) : null}
              </div>
            </article>
          )}
        </section>
      </div>
    </div>
  );
}

function PreLoginPage({
  onSignIn,
  authError
}: {
  onSignIn: () => void;
  authError: string | null;
}) {
  return (
    <div className="prelogin">
      <section className="marketing-hero" aria-labelledby="marketing-title">
        <div className="marketing-copy">
          <p className="eyebrow">ContextHub for Claude.ai</p>
          <h1 id="marketing-title">Version control for your AI conversations</h1>
          <p className="hero-lede">
            Turn important Claude chats into committed, searchable, reusable context.
            Push finished conversations, search past work semantically, and pull the
            exact decisions, artifacts, and open questions into your next chat.
          </p>
          <div className="hero-actions">
            <button className="button hero-primary" onClick={onSignIn} type="button">
              Get started: Sign in with Google
              <GoogleIcon />
            </button>
            <a className="button secondary hero-secondary" href="#how-it-works">
              See how it works
            </a>
          </div>
          {authError ? <p className="toast toast-error">{authError}</p> : null}
          <div className="hero-proof" aria-label="Product capabilities">
            <span>Claude.ai first</span>
            <span>Structured summaries</span>
            <span>Provenance on every pull</span>
          </div>
        </div>

        <div className="hero-explainer" aria-label="ContextHub push search pull overview">
          <div className="hero-visual">
            <img
              src="/images/contexthub-hero.png"
              alt="ContextHub product flow showing Push, Search, and Pull stages"
            />
          </div>
          <div className="mini-flow" aria-label="Push search pull flow">
            <span>Finished chat</span>
            <strong>Push</strong>
            <strong>Search</strong>
            <strong>Pull</strong>
            <span>New chat with context</span>
          </div>
        </div>
      </section>

      <section className="problem-band" aria-label="Why ContextHub exists">
        <div>
          <p className="section-kicker">The problem</p>
          <h2>Good AI work gets buried in chat history.</h2>
        </div>
        <p>
          LLM conversations contain real decisions, specs, code, assumptions, and
          unresolved questions. ContextHub preserves that work as structured memory
          you can trust, search, and reuse.
        </p>
      </section>

      <section className="marketing-section" id="how-it-works" aria-labelledby="loop-title">
        <div className="section-heading">
          <p className="section-kicker">Core loop</p>
          <h2 id="loop-title">Push, search, pull.</h2>
          <p>
            A deliberately simple workflow for turning finished conversations into
            durable project context.
          </p>
        </div>
        <div className="flow-grid">
          <div className="flow-step">
            <span className="flow-icon">01</span>
            <h3>Push</h3>
            <p>Save a finished Claude conversation from the browser extension.</p>
          </div>
          <div className="flow-step">
            <span className="flow-icon">02</span>
            <h3>Search</h3>
            <p>Find prior work with natural-language search over structured summaries.</p>
          </div>
          <div className="flow-step">
            <span className="flow-icon">03</span>
            <h3>Pull</h3>
            <p>Inject the right context back into a new chat with source provenance.</p>
          </div>
        </div>
      </section>

      <section className="marketing-section split-section" aria-labelledby="resolutions-title">
        <div className="section-heading left">
          <p className="section-kicker">Context resolutions</p>
          <h2 id="resolutions-title">Choose how much memory the next chat needs.</h2>
          <p>
            ContextHub keeps every push at three resolutions, from a compact reminder
            to the full normalized transcript.
          </p>
        </div>
        <div className="resolution-panel" aria-label="Three saved context resolutions">
          <div className="resolution-row">
            <span>Commit message</span>
            <p>One-line searchable reminder.</p>
          </div>
          <div className="resolution-row featured">
            <span>Structured block</span>
            <p>Decisions, artifacts, questions, assumptions, and constraints.</p>
          </div>
          <div className="resolution-row">
            <span>Raw transcript</span>
            <p>The full conversation when you need everything.</p>
          </div>
        </div>
      </section>

      <section className="marketing-section audience-section" aria-labelledby="audience-title">
        <div className="section-heading">
          <p className="section-kicker">Built for</p>
          <h2 id="audience-title">People doing real work with AI.</h2>
        </div>
        <div className="audience-grid">
          <div>
            <h3>Project teams</h3>
            <p>Keep specs, tradeoffs, and design decisions from disappearing.</p>
          </div>
          <div>
            <h3>Engineers</h3>
            <p>Reuse debugging trails, implementation plans, and generated artifacts.</p>
          </div>
          <div>
            <h3>Researchers</h3>
            <p>Bring prior analysis and open questions into the next investigation.</p>
          </div>
        </div>
      </section>

      <section className="final-cta" aria-labelledby="beta-title">
        <div>
          <p className="section-kicker">Get started</p>
          <h2 id="beta-title">Start building a memory layer for your Claude work.</h2>
        </div>
        <button className="button" onClick={onSignIn} type="button">
          Sign in with Google
          <GoogleIcon />
        </button>
      </section>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.184l-2.908-2.258c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.964 10.707A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.707V4.961H.957A8.997 8.997 0 0 0 0 9c0 1.452.348 2.827.957 4.039l3.007-2.332z" />
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.961L3.964 7.293C4.672 5.166 6.656 3.58 9 3.58z" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6" />
      <path d="m11 11 3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="m3 3 8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect x="4" y="4" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M2.5 9.5V3a.5.5 0 0 1 .5-.5h6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="m3 7.5 3 3 5-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RefreshIcon({ spinning }: { spinning?: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={spinning ? { animation: "spin 0.7s linear infinite" } : undefined}
    >
      <path d="M2 7a5 5 0 0 1 8.5-3.5L12 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M12 2v3h-3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M12 7a5 5 0 0 1-8.5 3.5L2 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M2 12V9h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function KebabIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="7" cy="3" r="1.2" fill="currentColor" />
      <circle cx="7" cy="7" r="1.2" fill="currentColor" />
      <circle cx="7" cy="11" r="1.2" fill="currentColor" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M3 4h8M5.5 4V2.5h3V4M4 4l.5 7.5h5L10 4M6 6.5v3M8 6.5v3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PencilIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M8.9 2.4 11.6 5.1M2.5 11.5l2.9-.6 6.1-6.1a1.9 1.9 0 0 0-2.7-2.7L2.8 8.2l-.6 3c-.1.2.1.4.3.3Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
