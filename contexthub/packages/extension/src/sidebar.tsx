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

  return (
    <div className="shell">
      <header className="header">
        <div className="row">
          <h1>Context</h1>
          {isConnected ? (
            <div className="row" style={{ gap: 8 }}>
              {userEmail ? <span className="muted" style={{ fontSize: 12 }}>{userEmail}</span> : null}
              <button className="link-btn" onClick={signOut} type="button" title="Sign out">
                Sign out
              </button>
            </div>
          ) : null}
        </div>
      </header>

      <div className="body">
        {!isConnected ? (
          <section className="card empty" style={{ textAlign: "center" }}>
            <p className="muted" style={{ marginTop: 0 }}>
              Sign in with Google to browse and reuse your past conversations.
            </p>
            <button
              className="btn"
              onClick={signInWithGoogle}
              disabled={busy === "signing-in"}
              type="button"
            >
              {busy === "signing-in" ? "Signing in…" : "Sign in with Google"}
            </button>
          </section>
        ) : null}

        {isConnected ? (
          <>
            <div className="toolbar">
              <input
                className="search"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Search past conversations"
              />
              <button className="btn" onClick={saveCurrentChat} disabled={busy !== "idle"}>
                {busy === "saving" ? "Saving…" : "Save current chat"}
              </button>
            </div>

            {busy === "loading" ? (
              <p className="muted">Loading…</p>
            ) : filtered.length === 0 ? (
              <p className="muted">
                {chats.length === 0
                  ? "No saved conversations yet. Click “Save current chat” to add this one."
                  : "No matches."}
              </p>
            ) : (
              <ul className="chat-list">
                {filtered.map((c) => (
                  <li key={c.push_id} className="chat-item">
                    <div className="chat-meta">
                      <h3 className="chat-title">{c.title || "Untitled conversation"}</h3>
                      {c.created_at ? <span className="chat-date">{formatDate(c.created_at)}</span> : null}
                    </div>
                    {c.summary ? <p className="chat-summary">{c.summary}</p> : null}
                    <button
                      className="btn"
                      onClick={() => addToChat(c.push_id)}
                      disabled={busy !== "idle"}
                    >
                      Add to chat
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}

        {statusMsg ? <p className="toast">{statusMsg}</p> : null}
        {error ? <p className="toast toast-error">{error}</p> : null}
      </div>
    </div>
  );
}

const mountNode = document.getElementById("root");
if (!mountNode) {
  throw new Error("Sidebar root mount node is missing.");
}

createRoot(mountNode).render(<SidebarApp />);
