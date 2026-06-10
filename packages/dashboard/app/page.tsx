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
  is_owner: boolean;
  shared_by: string | null;
};

type ShareRow = {
  id: string;
  push_id: string;
  owner_email: string;
  recipient_email: string;
  created_at: string;
};

type ShareListResponse = {
  items: ShareRow[];
};

type SharedWithMeItem = {
  share_id: string;
  push_id: string;
  conversation_title: string | null;
  status: string;
  source_platform: string;
  owner_email: string;
  shared_at: string;
  created_at: string;
  updated_at: string;
  title: string | null;
  summary: string | null;
  details: SummaryDetailsRaw | null;
};

type SharedWithMeResponse = {
  items: SharedWithMeItem[];
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
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [transcriptSelections, setTranscriptSelections] = useState<Record<string, boolean>>({});
  const [multiCopyState, setMultiCopyState] = useState<"idle" | "copying" | "copied" | "failed">("idle");
  const [multiCopyTokens, setMultiCopyTokens] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  // Rename state
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [renameSaving, setRenameSaving] = useState(false);
  const renameInputRef = useRef<HTMLInputElement | null>(null);

  // Share state
  const [sharedChats, setSharedChats] = useState<SharedWithMeItem[]>([]);
  const [shareTarget, setShareTarget] = useState<{ id: string; title: string } | null>(null);
  const [shareEmail, setShareEmail] = useState("");
  const [shareSubmitting, setShareSubmitting] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [shareNotice, setShareNotice] = useState<string | null>(null);
  const [shareList, setShareList] = useState<ShareRow[]>([]);
  const [shareListLoading, setShareListLoading] = useState(false);
  const [revokingShareId, setRevokingShareId] = useState<string | null>(null);
  const shareEmailRef = useRef<HTMLInputElement | null>(null);

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

  const loadShared = useCallback(async () => {
    const res = await apiFetch<SharedWithMeResponse>("/v1/shares/received?limit=50");
    // Older backends don't have this endpoint; treat failures as "no shares"
    // so the dashboard keeps working.
    setSharedChats(res.ok ? res.data.items || [] : []);
  }, []);

  useEffect(() => {
    if (signedIn) {
      loadChats("initial");
      loadShared();
    }
  }, [signedIn, loadChats, loadShared]);

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

  // ---- close share modal on Escape
  useEffect(() => {
    if (!shareTarget) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setShareTarget(null);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [shareTarget]);

  const filtered = useMemo(() => {
    if (!filter.trim()) return chats;
    const q = filter.toLowerCase();
    return chats.filter((c) => {
      const title = (c.title || c.conversation_title || "").toLowerCase();
      const summary = (c.summary || "").toLowerCase();
      return title.includes(q) || summary.includes(q);
    });
  }, [chats, filter]);

  const filteredShared = useMemo(() => {
    if (!filter.trim()) return sharedChats;
    const q = filter.toLowerCase();
    return sharedChats.filter((c) => {
      const title = (c.title || c.conversation_title || "").toLowerCase();
      const summary = (c.summary || "").toLowerCase();
      return title.includes(q) || summary.includes(q) || c.owner_email.toLowerCase().includes(q);
    });
  }, [sharedChats, filter]);

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
        // Shared chats grant summary access only — never request the
        // transcript for a chat the viewer doesn't own.
        selections: [{ push_id: activeId, include_transcript: detail?.is_owner ?? true }],
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

  function toggleSelected(id: string) {
    if (selectedIds.includes(id)) {
      setSelectedIds((cur) => cur.filter((x) => x !== id));
      setTranscriptSelections((cur) => {
        const next = { ...cur };
        delete next[id];
        return next;
      });
      return;
    }
    if (selectedIds.length >= 20) {
      setError("You can pull at most 20 conversations at once.");
      return;
    }
    setSelectedIds((cur) => [...cur, id]);
  }

  function toggleTranscript(id: string) {
    setTranscriptSelections((cur) => ({ ...cur, [id]: !cur[id] }));
  }

  function clearSelection() {
    setSelectedIds([]);
    setTranscriptSelections({});
    setMultiCopyState("idle");
    setMultiCopyTokens(null);
  }

  async function handleCopySelected() {
    if (selectedIds.length === 0) return;
    setMultiCopyState("copying");
    setMultiCopyTokens(null);
    const res = await apiFetch<PullResponse>("/v1/pulls", {
      method: "POST",
      body: JSON.stringify({
        selections: selectedIds.map((id) => ({
          push_id: id,
          include_transcript: Boolean(transcriptSelections[id])
        })),
        target_platform: "claude_ai",
        origin: "dashboard"
      })
    });
    if (!res.ok) {
      setMultiCopyState("failed");
      setError(res.message);
      setTimeout(() => setMultiCopyState("idle"), 2000);
      return;
    }
    try {
      await navigator.clipboard.writeText(res.data.payload_markdown);
      setMultiCopyTokens(res.data.token_estimate);
      setMultiCopyState("copied");
      setTimeout(() => setMultiCopyState("idle"), 2500);
    } catch {
      setMultiCopyState("failed");
      setTimeout(() => setMultiCopyState("idle"), 2000);
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
    setSelectedIds((cur) => cur.filter((x) => x !== id));
    setTranscriptSelections((cur) => {
      const next = { ...cur };
      delete next[id];
      return next;
    });
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

  // ---- sharing

  async function openShareModal(id: string, title: string) {
    setOpenMenuId(null);
    setShareTarget({ id, title });
    setShareEmail("");
    setShareError(null);
    setShareNotice(null);
    setShareList([]);
    setShareListLoading(true);
    setTimeout(() => shareEmailRef.current?.focus(), 0);
    const res = await apiFetch<ShareListResponse>(`/v1/pushes/${id}/shares`);
    setShareListLoading(false);
    if (res.ok) setShareList(res.data.items || []);
    else setShareError(res.message);
  }

  function closeShareModal() {
    setShareTarget(null);
    setShareEmail("");
    setShareError(null);
    setShareNotice(null);
  }

  async function handleShareSubmit() {
    if (!shareTarget) return;
    const email = shareEmail.trim();
    if (!email) return;
    setShareSubmitting(true);
    setShareError(null);
    setShareNotice(null);
    const res = await apiFetch<ShareRow>(`/v1/pushes/${shareTarget.id}/shares`, {
      method: "POST",
      body: JSON.stringify({ recipient_email: email })
    });
    setShareSubmitting(false);
    if (!res.ok) {
      setShareError(res.message);
      return;
    }
    setShareList((cur) => [res.data, ...cur]);
    setShareEmail("");
    setShareNotice(`Shared with ${res.data.recipient_email}. It now appears on their dashboard.`);
  }

  async function handleRevokeShare(share: ShareRow) {
    setRevokingShareId(share.id);
    setShareError(null);
    const res = await apiFetch<null>(`/v1/pushes/${share.push_id}/shares/${share.id}`, {
      method: "DELETE"
    });
    setRevokingShareId(null);
    if (!res.ok) {
      setShareError(res.message);
      return;
    }
    setShareList((cur) => cur.filter((s) => s.id !== share.id));
    setShareNotice(null);
  }

  async function handleLeaveShare(item: SharedWithMeItem) {
    setOpenMenuId(null);
    if (!confirm("Remove this shared conversation from your dashboard?")) return;
    const res = await apiFetch<null>(`/v1/pushes/${item.push_id}/shares/${item.share_id}`, {
      method: "DELETE"
    });
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSharedChats((cur) => cur.filter((s) => s.share_id !== item.share_id));
    if (activeId === item.push_id) {
      setActiveId(null);
      setDetail(null);
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
        <p>Search and reuse chatbot conversations you've saved from the extension.</p>
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

      {selectedIds.length > 0 ? (
        <div className="selection-bar">
          <div className="selection-info">
            <span className="selection-count">
              {selectedIds.length} conversation{selectedIds.length === 1 ? "" : "s"} selected
            </span>
            <span className="selection-hint">
              {multiCopyState === "copied" && multiCopyTokens != null
                ? `Copied to clipboard — ~${multiCopyTokens.toLocaleString()} tokens`
                : "Pull the selected conversations together into one context"}
            </span>
          </div>
          <div className="selection-actions">
            <button className="btn btn-secondary" onClick={clearSelection} type="button">
              Clear
            </button>
            <button
              className={`btn copy-btn ${multiCopyState !== "idle" ? "copy-" + multiCopyState : ""}`}
              onClick={handleCopySelected}
              disabled={multiCopyState === "copying"}
              type="button"
            >
              {multiCopyState === "copying" ? (
                <><span className="spinner spinner-on-blue" /> Building…</>
              ) : multiCopyState === "copied" ? (
                <><CheckIcon /> Copied</>
              ) : multiCopyState === "failed" ? (
                <>Copy failed — try again</>
              ) : (
                <><CopyIcon /> Copy combined context</>
              )}
            </button>
          </div>
        </div>
      ) : null}

      <div className="workspace">
        <aside className="list-panel">
          <div className="list-panel-header">
            <span className="list-panel-title">
              {filtered.length} conversation{filtered.length === 1 ? "" : "s"}
            </span>
            <button
              className="icon-btn"
              onClick={() => {
                loadChats("refresh");
                loadShared();
              }}
              disabled={chatsRefreshing || chatsLoading}
              type="button"
              aria-label="Refresh"
              title="Refresh"
            >
              <RefreshIcon spinning={chatsRefreshing} />
            </button>
          </div>

          <div className={`list-scroll${selectedIds.length > 0 ? " select-active" : ""}`}>
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
                const isSelected = selectedIds.includes(c.id);
                return (
                  <div
                    key={c.id}
                    className={`list-item-wrap${isActive ? " is-active" : ""}${isSelected ? " is-selected" : ""}`}
                  >
                    <label className="list-item-select" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelected(c.id)}
                        aria-label="Select conversation for combined pull"
                      />
                    </label>
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
                            className="kebab-item"
                            onClick={() =>
                              openShareModal(
                                c.id,
                                c.title || c.conversation_title || "Untitled conversation"
                              )
                            }
                            type="button"
                            role="menuitem"
                          >
                            <ShareIcon /> Share
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
                    {isSelected ? (
                      <label className="list-item-transcript" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={Boolean(transcriptSelections[c.id])}
                          onChange={() => toggleTranscript(c.id)}
                        />
                        Include full transcript
                      </label>
                    ) : null}
                  </div>
                );
              })
            )}

            {filteredShared.length > 0 ? (
              <>
                <div className="list-section-label">Shared with me</div>
                {filteredShared.map((c) => {
                  const isActive = activeId === c.push_id;
                  const isMenuOpen = openMenuId === c.share_id;
                  return (
                    <div
                      key={c.share_id}
                      className={`list-item-wrap${isActive ? " is-active" : ""}`}
                    >
                      <button
                        className={`list-item${isActive ? " is-active" : ""}`}
                        onClick={() => setActiveId(c.push_id)}
                        type="button"
                      >
                        <h3 className="list-item-title">
                          {c.title || c.conversation_title || "Untitled conversation"}
                        </h3>
                        {c.summary ? <p className="list-item-snippet">{c.summary}</p> : null}
                        <span className="list-item-date" title={formatAbsolute(c.shared_at)}>
                          <span className="shared-from">from {c.owner_email}</span>
                          {" · "}
                          {formatRelative(c.shared_at)}
                        </span>
                      </button>
                      <div className="list-item-menu" ref={isMenuOpen ? menuRef : null}>
                        <button
                          className="kebab-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpenMenuId(isMenuOpen ? null : c.share_id);
                          }}
                          type="button"
                          aria-label="More options"
                        >
                          <KebabIcon />
                        </button>
                        {isMenuOpen ? (
                          <div className="kebab-menu" role="menu">
                            <button
                              className="kebab-item kebab-danger"
                              onClick={() => handleLeaveShare(c)}
                              type="button"
                              role="menuitem"
                            >
                              <TrashIcon /> Remove
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </>
            ) : null}
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
                  ) : detail.is_owner ? (
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
                  ) : (
                    <h2 className="detail-title">
                      {detail.title || "Untitled conversation"}
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
                  {!detail.is_owner ? (
                    <span className="shared-chip" title="This conversation was shared with you (summary only)">
                      <ShareIcon /> Shared by {detail.shared_by || "another user"}
                    </span>
                  ) : null}
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

      {shareTarget ? (
        <div
          className="modal-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) closeShareModal();
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="share-modal-title"
        >
          <div className="modal">
            <div className="modal-header">
              <h3 id="share-modal-title">Share “{shareTarget.title}”</h3>
              <button
                className="icon-btn"
                onClick={closeShareModal}
                type="button"
                aria-label="Close"
              >
                <CloseIcon />
              </button>
            </div>
            <p className="modal-hint">
              The recipient sees this conversation's summary on their dashboard — not the
              transcript. They need a ContextHub account with this email.
            </p>
            <form
              className="share-form"
              onSubmit={(e) => {
                e.preventDefault();
                handleShareSubmit();
              }}
            >
              <input
                ref={shareEmailRef}
                className="input"
                type="email"
                placeholder="teammate@example.com"
                value={shareEmail}
                onChange={(e) => setShareEmail(e.target.value)}
                disabled={shareSubmitting}
              />
              <button
                className="btn"
                type="submit"
                disabled={shareSubmitting || !shareEmail.trim()}
              >
                {shareSubmitting ? (
                  <><span className="spinner spinner-on-blue" /> Sharing…</>
                ) : (
                  <><ShareIcon /> Share</>
                )}
              </button>
            </form>
            {shareError ? <p className="toast toast-error">{shareError}</p> : null}
            {shareNotice ? <p className="toast">{shareNotice}</p> : null}

            <div className="share-list">
              <p className="section-label">Who has access</p>
              {shareListLoading ? (
                <div className="loading">
                  <span className="spinner" />
                  Loading…
                </div>
              ) : shareList.length === 0 ? (
                <p className="share-list-empty">Not shared with anyone yet.</p>
              ) : (
                shareList.map((s) => (
                  <div key={s.id} className="share-list-item">
                    <span className="share-list-email">{s.recipient_email}</span>
                    <button
                      className="link-btn share-revoke"
                      onClick={() => handleRevokeShare(s)}
                      disabled={revokingShareId === s.id}
                      type="button"
                    >
                      {revokingShareId === s.id ? "Removing…" : "Remove"}
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      ) : null}
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

function ShareIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="3.5" cy="7" r="1.6" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="10.5" cy="3.2" r="1.6" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="10.5" cy="10.8" r="1.6" stroke="currentColor" strokeWidth="1.3" />
      <path d="M5 6.2 9 4M5 7.8 9 10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
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
