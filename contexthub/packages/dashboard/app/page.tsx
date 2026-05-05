"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
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
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PushDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);

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

  const loadChats = useCallback(async () => {
    setChatsLoading(true);
    setError(null);
    const res = await apiFetch<PushHistoryResponse>("/v1/pushes/history?limit=50");
    setChatsLoading(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setChats(res.data.items || []);
  }, []);

  useEffect(() => {
    if (signedIn) loadChats();
  }, [signedIn, loadChats]);

  // ---- detail load
  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setShowTranscript(false);
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
      <section className="signin-hero">
        <h2>Welcome to ContextHub</h2>
        <p>
          Sign in to browse and search the Claude conversations you've saved from the extension.
        </p>
        <button className="signin-button" onClick={handleSignIn} type="button">
          <GoogleIcon />
          Continue with Google
        </button>
        {authError ? <p className="toast toast-error">{authError}</p> : null}
      </section>
    );
  }

  const activeIsActive = (id: string) => activeId === id;
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
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div className="page-heading">
        <h1>Your conversations</h1>
        <p>Search past Claude conversations you've saved from the extension.</p>
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
              filtered.map((c) => (
                <button
                  key={c.id}
                  className={`list-item${activeIsActive(c.id) ? " is-active" : ""}`}
                  onClick={() => setActiveId(c.id)}
                  type="button"
                >
                  <h3 className="list-item-title">
                    {c.title || c.conversation_title || "Untitled conversation"}
                  </h3>
                  {c.summary ? <p className="list-item-snippet">{c.summary}</p> : null}
                  <span className="list-item-date">{formatDate(c.created_at)}</span>
                </button>
              ))
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
                <h2 className="detail-title">{detail.title || "Untitled conversation"}</h2>
                <div className="detail-meta">
                  <span className={`status-pill status-${detail.status}`}>{detail.status}</span>
                  <span>{formatDate(detail.created_at)}</span>
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
