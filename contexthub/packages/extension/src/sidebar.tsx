import { createRoot } from "react-dom/client";
import { useEffect, useMemo, useState } from "react";
import "./sidebar.css";
import { ConversationV0 } from "@contexthub/interchange-spec";

function SidebarApp() {
  const [apiBaseUrl, setApiBaseUrl] = useState("http://localhost:8000");
  const [workspaceId, setWorkspaceId] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [status, setStatus] = useState("idle");
  const [lastPushId, setLastPushId] = useState<string | null>(null);
  const [scrubFlags, setScrubFlags] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selectionPreview, setSelectionPreview] = useState<string>("");

  const isReady = useMemo(() => Boolean(apiBaseUrl && workspaceId && authToken), [apiBaseUrl, workspaceId, authToken]);

  useEffect(() => {
    chrome.storage.sync.get(["apiBaseUrl", "workspaceId", "authToken"], (items) => {
      if (typeof items.apiBaseUrl === "string") setApiBaseUrl(items.apiBaseUrl);
      if (typeof items.workspaceId === "string") setWorkspaceId(items.workspaceId);
      if (typeof items.authToken === "string") setAuthToken(items.authToken);
    });
  }, []);

  function saveSettings() {
    chrome.storage.sync.set({ apiBaseUrl, workspaceId, authToken });
  }

  function makeConversation(title: string, url: string, selectionText: string): ConversationV0 {
    const userText =
      selectionText.trim().length > 0
        ? `Selected text:\n\n${selectionText}`
        : "No text selected; pushed a minimal placeholder conversation from the extension.";

    return {
      spec_version: "ch.v0.1",
      source: { platform: "claude_ai", captured_at: new Date().toISOString(), url },
      messages: [
        { role: "user", content: [{ type: "text", text: userText }] },
        { role: "assistant", content: [{ type: "text", text: "Extension push (demo): backend pipeline should summarize/embed this." }] }
      ],
      metadata: { title }
    };
  }

  async function captureSelection() {
    setError(null);
    const resp = await chrome.runtime.sendMessage({ type: "ctxh:capture" });
    if (!resp?.ok) {
      setError(resp?.message || "Capture failed.");
      return null;
    }
    const preview = String(resp.selectionText || "").slice(0, 200);
    setSelectionPreview(preview);
    return { selectionText: String(resp.selectionText || ""), pageTitle: String(resp.pageTitle || ""), pageUrl: String(resp.pageUrl || "") };
  }

  async function push() {
    setStatus("pushing");
    setError(null);
    setLastPushId(null);
    setScrubFlags([]);

    if (!isReady) {
      setError("Set apiBaseUrl + workspaceId + authToken first.");
      setStatus("idle");
      return;
    }

    const captured = await captureSelection();
    if (!captured) {
      setStatus("idle");
      return;
    }

    const conversation = makeConversation(
      captured.pageTitle || "Claude push",
      captured.pageUrl || "https://claude.ai",
      captured.selectionText
    );

    const res = await chrome.runtime.sendMessage({
      type: "ctxh:push",
      payload: {
        apiBaseUrl,
        workspaceId,
        authToken,
        conversation,
        idempotencyKey: `claude-${Date.now()}`
      }
    });

    if (!res?.ok) {
      setError(res?.message || "Push failed.");
      setStatus("idle");
      return;
    }

    const data = res.data as { push_id: string; scrub_flags: string[] };
    setLastPushId(data.push_id);
    setScrubFlags(data.scrub_flags || []);
    setStatus("pushed");
  }

  return (
    <div className="shell">
      <header className="header">
        <h1>ContextHub Extension Demo</h1>
        <p>Claude.ai adapter + real push route</p>
      </header>

      <div className="body">
        <section className="card">
          <div className="row">
            <h2>Connection</h2>
            <span className="pill">{isReady ? "configured" : "needs settings"}</span>
          </div>
          <div className="muted" style={{ display: "grid", gap: 8 }}>
            <label>
              API base URL
              <input
                value={apiBaseUrl}
                onChange={(e) => setApiBaseUrl(e.target.value)}
                style={{
                  width: "100%",
                  marginTop: 6,
                  borderRadius: 8,
                  border: "1px solid #2f4572",
                  background: "#0f1730",
                  color: "#edf2ff",
                  padding: "8px 10px"
                }}
                placeholder="http://localhost:8000"
              />
            </label>
            <label>
              Workspace ID
              <input
                value={workspaceId}
                onChange={(e) => setWorkspaceId(e.target.value)}
                style={{
                  width: "100%",
                  marginTop: 6,
                  borderRadius: 8,
                  border: "1px solid #2f4572",
                  background: "#0f1730",
                  color: "#edf2ff",
                  padding: "8px 10px"
                }}
                placeholder="22222222-2222-2222-2222-222222222222"
              />
            </label>
            <label>
              API token (raw `ch_...`)
              <input
                value={authToken}
                onChange={(e) => setAuthToken(e.target.value)}
                style={{
                  width: "100%",
                  marginTop: 6,
                  borderRadius: 8,
                  border: "1px solid #2f4572",
                  background: "#0f1730",
                  color: "#edf2ff",
                  padding: "8px 10px"
                }}
                placeholder="ch_..."
              />
            </label>
            <div className="row">
              <button className="btn secondary" onClick={saveSettings}>
                Save
              </button>
              <span className="muted">{status}</span>
            </div>
          </div>
        </section>

        <section className="card">
          <h2>Captured conversation</h2>
          <p className="muted">
            For now this uses your current text selection as a lightweight payload (real DOM scraping can replace this).
          </p>
          {selectionPreview ? <p className="muted">Selection preview: {selectionPreview}</p> : null}
          <button
            className="btn"
            onClick={() => {
              push();
            }}
          >
            Push to ContextHub (real)
          </button>
          {lastPushId ? (
            <p className="muted">
              push_id: <code>{lastPushId}</code>
            </p>
          ) : null}
          {scrubFlags.length ? <p className="muted">scrub_flags: {scrubFlags.join(", ")}</p> : null}
          {error ? <p className="muted" style={{ color: "#ffb4b4" }}>Error: {error}</p> : null}
        </section>

        <section className="card">
          <h2>Pull context</h2>
          <ul className="list">
            <li>Not wired yet (no pull/search endpoint shipped)</li>
            <li>Planned: use stored ready summaries (no re-rendering)</li>
          </ul>
        </section>
      </div>
    </div>
  );
}

const mountNode = document.getElementById("root");
if (!mountNode) {
  throw new Error("Sidebar root mount node is missing.");
}

createRoot(mountNode).render(<SidebarApp />);
