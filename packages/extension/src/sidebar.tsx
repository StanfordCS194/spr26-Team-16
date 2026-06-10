/// <reference types="vite/client" />
import { createRoot } from "react-dom/client";
import { useEffect, useState } from "react";
import "./sidebar.css";
import { ConversationV0 } from "@contexthub/interchange-spec";

const DEFAULT_API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8765";

type SavedChat = {
  push_id: string;
  title: string | null;
  summary: string;
  created_at: string;
};

function SidebarApp() {
  const [apiBaseUrl, setApiBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [workspaceId, setWorkspaceId] = useState("");
  const [userEmail, setUserEmail] = useState("");
  const [signedIn, setSignedIn] = useState(false);

  const [chats, setChats] = useState<SavedChat[]>([]);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState<"idle" | "saving" | "loading" | "adding" | "signing-in">("idle");
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isConnected = signedIn && Boolean(workspaceId);

  useEffect(() => {
    chrome.storage.sync.get(["apiBaseUrl", "workspaceId", "userEmail"], (items) => {
      const stored = typeof items.apiBaseUrl === "string" ? items.apiBaseUrl : "";
      const isStaleDefault = stored === "http://localhost:8000";
      const effective = !stored || isStaleDefault ? DEFAULT_API_BASE_URL : stored;
      setApiBaseUrl(effective);
      if (effective !== stored) chrome.storage.sync.set({ apiBaseUrl: effective });
      if (typeof items.workspaceId === "string") setWorkspaceId(items.workspaceId);
      if (typeof items.userEmail === "string") setUserEmail(items.userEmail);
    });
    // Hydrate session state from background.
    chrome.runtime.sendMessage({ type: "ctxh:session-status" }, (res) => {
      if (res?.ok && res.data?.signedIn) {
        setSignedIn(true);
        if (res.data.user?.email) setUserEmail(res.data.user.email);
      } else {
        setSignedIn(false);
      }
    });
  }, []);

  useEffect(() => {
    if (isConnected) loadChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected]);

  function flash(msg: string) {
    setStatusMsg(msg);
    setTimeout(() => setStatusMsg((cur) => (cur === msg ? null : cur)), 2500);
  }

  async function signInWithGoogle() {
    setError(null);
    setBusy("signing-in");
    try {
      const res = await chrome.runtime.sendMessage({
        type: "ctxh:supabase-signin",
        payload: { apiBaseUrl }
      });
      if (!res?.ok) {
        setBusy("idle");
        setError(res?.message || "Sign-in failed.");
        return;
      }
      const nextWorkspaceId = typeof res.data?.workspace_id === "string" ? res.data.workspace_id : "";
      const nextEmail = typeof res.data?.user?.email === "string" ? res.data.user.email : "";
      const nextApiBaseUrl =
        typeof res.data?.apiBaseUrl === "string" && res.data.apiBaseUrl
          ? res.data.apiBaseUrl
          : apiBaseUrl;
      if (!nextWorkspaceId) {
        setBusy("idle");
        setError("Sign-in succeeded but no workspace was returned.");
        return;
      }
      setApiBaseUrl(nextApiBaseUrl);
      setWorkspaceId(nextWorkspaceId);
      setUserEmail(nextEmail);
      setSignedIn(true);
      chrome.storage.sync.set({
        apiBaseUrl: nextApiBaseUrl,
        workspaceId: nextWorkspaceId,
        userEmail: nextEmail
      });
      setBusy("idle");
      flash("Signed in.");
    } catch (err) {
      setBusy("idle");
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    }
  }

  async function signOut() {
    try {
      await chrome.runtime.sendMessage({ type: "ctxh:supabase-signout" });
    } catch {
      // ignore
    }
    setSignedIn(false);
    setWorkspaceId("");
    setUserEmail("");
    setChats([]);
    chrome.storage.sync.set({ workspaceId: "", userEmail: "" });
    flash("Signed out.");
  }

  async function loadChats() {
    if (!isConnected) return;
    setBusy("loading");
    setError(null);
    const res = await chrome.runtime.sendMessage({
      type: "ctxh:search",
      payload: {
        apiBaseUrl,
        workspaceId,
        query: filter.trim() || "*",
        includeTranscripts: false
      }
    });
    setBusy("idle");
    if (!res?.ok) {
      setError(res?.message || "Could not load conversations.");
      return;
    }
    const items = Array.isArray(res.data?.items) ? res.data.items : [];
    const deduped = new Map<string, SavedChat>();
    for (const item of items) {
      const id = String(item.push_id);
      const score = Number(item.score || 0);
      const existing = deduped.get(id);
      if (!existing || Number(existing as unknown as { score: number }).valueOf() < score) {
        deduped.set(id, {
          push_id: id,
          title: item.title ?? null,
          summary: String(item.summary ?? item.snippet ?? "").trim(),
          created_at: String(item.created_at ?? "")
        });
      }
    }
    const list = Array.from(deduped.values()).sort((a, b) => {
      return (b.created_at || "").localeCompare(a.created_at || "");
    });
    setChats(list);
  }

  async function saveCurrentChat() {
    if (!isConnected) {
      setError("Sign in first.");
      return;
    }
    setBusy("saving");
    setError(null);

    const captured = await chrome.runtime.sendMessage({ type: "ctxh:capture" });
    if (!captured?.ok) {
      setBusy("idle");
      setError(captured?.message || "Couldn't read the current chat.");
      return;
    }

    const res = await chrome.runtime.sendMessage({
      type: "ctxh:push",
      payload: {
        apiBaseUrl,
        workspaceId,
        conversation: captured.conversation as ConversationV0,
        idempotencyKey: `claude-${Date.now()}`
      }
    });

    setBusy("idle");
    if (!res?.ok) {
      setError(res?.message || "Save failed.");
      return;
    }
    flash("Saved.");
    loadChats();
  }

  async function addToChat(pushId: string) {
    if (!isConnected) return;
    setBusy("adding");
    setError(null);
    const res = await chrome.runtime.sendMessage({
      type: "ctxh:pull",
      payload: {
        apiBaseUrl,
        selections: [{ push_id: pushId, include_transcript: true }]
      }
    });
    if (!res?.ok) {
      setBusy("idle");
      setError(res?.message || "Could not build context.");
      return;
    }
    const text = String(res.data?.payload_markdown || "");
    const inj = await chrome.runtime.sendMessage({ type: "ctxh:inject", payload: { text } });
    setBusy("idle");
    if (!inj?.ok) {
      setError(inj?.message || "Could not insert into chat.");
      return;
    }
    flash("Added to chat.");
  }

  function formatDate(iso: string): string {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  const filtered = chats.filter((c) => {
    if (!filter.trim()) return true;
    const q = filter.toLowerCase();
    return (
      (c.title || "").toLowerCase().includes(q) ||
      (c.summary || "").toLowerCase().includes(q)
    );
  });

  const userInitial = (userEmail || "?").charAt(0).toUpperCase();

  return (
    <div className="shell">
      <header className="header">
        <div className="row">
          <div className="brand">
            <span className="brand-mark">C</span>
            ContextHub
          </div>
          {isConnected ? (
            <div className="user-chip">
              <span className="avatar" title={userEmail}>{userInitial}</span>
              <button className="link-btn" onClick={signOut} type="button" title="Sign out">
                Sign out
              </button>
            </div>
          ) : null}
        </div>
      </header>

      <div className="body">
        {!isConnected ? (
          <section className="signin-hero">
            <h2>Pick up where you left off</h2>
            <p>Sign in to save Claude conversations and pull them back into new chats whenever you need.</p>
            <button
              className="signin-button"
              onClick={signInWithGoogle}
              disabled={busy === "signing-in"}
              type="button"
            >
              <GoogleIcon />
              {busy === "signing-in" ? "Signing in…" : "Continue with Google"}
            </button>
          </section>
        ) : null}

        {isConnected ? (
          <>
            <div className="toolbar">
              <div className="search-wrap">
                <span className="search-icon"><SearchIcon /></span>
                <input
                  className="input"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Search your conversations"
                  type="search"
                />
              </div>
              <button
                className="btn btn-block"
                onClick={saveCurrentChat}
                disabled={busy !== "idle"}
                type="button"
              >
                <PlusIcon />
                {busy === "saving" ? "Saving…" : "Save current chat"}
              </button>
            </div>

            {busy === "loading" ? (
              <div className="loading">
                <span className="spinner" />
                Loading conversations…
              </div>
            ) : filtered.length === 0 ? (
              <div className="empty-state">
                {chats.length === 0 ? (
                  <>
                    <h3>No saved conversations yet</h3>
                    <p>Open a Claude chat and tap “Save current chat” to add it here.</p>
                  </>
                ) : (
                  <>
                    <h3>No matches</h3>
                    <p>Try a different search term.</p>
                  </>
                )}
              </div>
            ) : (
              <>
                <div className="list-header">
                  <span>{filtered.length} conversation{filtered.length === 1 ? "" : "s"}</span>
                </div>
                <ul className="chat-list">
                  {filtered.map((c) => (
                    <li key={c.push_id} className="chat-item">
                      <div className="chat-meta">
                        <h3 className="chat-title">{c.title || "Untitled conversation"}</h3>
                        {c.created_at ? <span className="chat-date">{formatDate(c.created_at)}</span> : null}
                      </div>
                      {c.summary ? <p className="chat-summary">{c.summary}</p> : null}
                      <div className="chat-actions">
                        <button
                          className="btn btn-secondary"
                          onClick={() => addToChat(c.push_id)}
                          disabled={busy !== "idle"}
                          type="button"
                        >
                          Add to chat
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        ) : null}

        {statusMsg ? <p className="toast">{statusMsg}</p> : null}
        {error ? <p className="toast toast-error">{error}</p> : null}
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
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.6" />
      <path d="m11 11 3 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

const mountNode = document.getElementById("root");
if (!mountNode) {
  throw new Error("Sidebar root mount node is missing.");
}

createRoot(mountNode).render(<SidebarApp />);
