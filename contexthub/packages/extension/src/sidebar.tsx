import { createRoot } from "react-dom/client";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import "./sidebar.css";
import { ConversationV0 } from "@contexthub/interchange-spec";

type ConversationTurn = { role: "user" | "assistant"; text: string };

function parseConversationTranscript(raw: string | null): ConversationTurn[] | null {
  if (!raw?.trim()) return null;
  try {
    const data = JSON.parse(raw) as {
      messages?: Array<{ role?: string; content?: unknown }>;
    };
    const messages = data.messages;
    if (!Array.isArray(messages)) return null;
    const turns: ConversationTurn[] = [];
    for (const m of messages) {
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

const wrapTextStyle: CSSProperties = {
  overflowWrap: "break-word",
  wordBreak: "break-word",
  whiteSpace: "pre-wrap",
  maxWidth: "100%"
};

function SidebarApp() {
  type PushDetailSummaryLayer = {
    layer: string;
    content_json: Record<string, unknown>;
  };
  type PushDetail = {
    id: string;
    raw_transcript: string | null;
    summaries: PushDetailSummaryLayer[];
  };
  type SummaryDetails = { summary?: unknown; key_takeaways?: unknown; tags?: unknown };

  const [apiBaseUrl, setApiBaseUrl] = useState("http://localhost:8000");
  const [workspaceId, setWorkspaceId] = useState("");
  const [authToken, setAuthToken] = useState("");
  const [status, setStatus] = useState("idle");
  const [lastPushId, setLastPushId] = useState<string | null>(null);
  const [scrubFlags, setScrubFlags] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [capturePreview, setCapturePreview] = useState<string>("");
  const [capturedMessageCount, setCapturedMessageCount] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState("onboarding workflow");
  const [searchResults, setSearchResults] = useState<
    Array<{
      push_id: string;
      title: string | null;
      workspace_id: string;
      status: string;
      created_at: string;
      summary: string;
      snippet: string;
      score: number;
    }>
  >([]);
  const [selectedPushIds, setSelectedPushIds] = useState<string[]>([]);
  const [transcriptSelections, setTranscriptSelections] = useState<Record<string, boolean>>({});
  const [pullPayload, setPullPayload] = useState<string>("");
  const [lastPushStatus, setLastPushStatus] = useState<string | null>(null);
  const [expandedPushId, setExpandedPushId] = useState<string | null>(null);
  const [pushDetails, setPushDetails] = useState<Record<string, PushDetail>>({});
  const [detailsLoadingPushId, setDetailsLoadingPushId] = useState<string | null>(null);

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

  async function captureConversation() {
    setError(null);
    const resp = await chrome.runtime.sendMessage({ type: "ctxh:capture" });
    if (!resp?.ok) {
      setError(resp?.message || "Capture failed.");
      return null;
    }
    setCapturePreview(String(resp.previewText || "").slice(0, 200));
    setCapturedMessageCount(Number(resp.messageCount || 0));
    return {
      pageTitle: String(resp.pageTitle || ""),
      pageUrl: String(resp.pageUrl || ""),
      conversation: resp.conversation as ConversationV0
    };
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

    const captured = await captureConversation();
    if (!captured) {
      setStatus("idle");
      return;
    }

    const conversation = captured.conversation;

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
    setLastPushStatus("pending");
    setStatus("pushed");
  }

  async function refreshPushStatus() {
    if (!lastPushId || !isReady) return;
    const res = await chrome.runtime.sendMessage({
      type: "ctxh:push-status",
      payload: {
        apiBaseUrl,
        authToken,
        pushId: lastPushId
      }
    });
    if (!res?.ok) {
      setError(res?.message || "Status check failed.");
      return;
    }
    setLastPushStatus(String(res.data?.status || "unknown"));
  }

  async function runSearch() {
    if (!isReady) {
      setError("Set apiBaseUrl + workspaceId + authToken first.");
      return;
    }
    setError(null);
    const res = await chrome.runtime.sendMessage({
      type: "ctxh:search",
      payload: {
        apiBaseUrl,
        authToken,
        workspaceId,
        query: searchQuery,
        includeTranscripts: false
      }
    });
    if (!res?.ok) {
      setError(res?.message || "Search failed.");
      return;
    }
    const items = Array.isArray(res.data?.items) ? res.data.items : [];
    const deduped = new Map<
      string,
      {
        push_id: string;
        title: string | null;
        workspace_id: string;
        status: string;
        created_at: string;
        summary: string;
        snippet: string;
        score: number;
      }
    >();
    for (const item of items) {
      const key = String(item.push_id);
      const current = deduped.get(key);
      if (!current || Number(current.score) < Number(item.score || 0)) {
        const summary = String(item.summary ?? "").trim();
        const snippet = String(item.snippet ?? "").trim();
        deduped.set(key, {
          push_id: key,
          title: item.title ?? null,
          workspace_id: String(item.workspace_id),
          status: String(item.status ?? "unknown"),
          created_at: String(item.created_at ?? ""),
          summary: summary || snippet,
          snippet,
          score: Number(item.score || 0)
        });
      }
    }
    setSearchResults(Array.from(deduped.values()));
    setSelectedPushIds([]);
    setTranscriptSelections({});
  }

  function toggleSelectedPush(pushId: string) {
    setSelectedPushIds((prev) => (prev.includes(pushId) ? prev.filter((id) => id !== pushId) : [...prev, pushId]));
  }

  function toggleTranscriptSelection(pushId: string) {
    setTranscriptSelections((prev) => ({ ...prev, [pushId]: !prev[pushId] }));
  }

  function asStringList(value: unknown): string[] {
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
  }

  function extractDetails(detail: PushDetail | undefined): { summary: string; keyTakeaways: string[]; tags: string[] } {
    const detailsLayer = detail?.summaries.find((summary) => summary.layer === "details")?.content_json as SummaryDetails | undefined;
    const summaryLayer = detail?.summaries.find((summary) => summary.layer === "summary")?.content_json;
    const fallbackSummary = typeof summaryLayer?.text === "string" ? summaryLayer.text : "";
    return {
      summary: typeof detailsLayer?.summary === "string" ? detailsLayer.summary : fallbackSummary,
      keyTakeaways: asStringList(detailsLayer?.key_takeaways),
      tags: asStringList(detailsLayer?.tags)
    };
  }

  async function togglePushDetails(pushId: string) {
    if (expandedPushId === pushId) {
      setExpandedPushId(null);
      return;
    }
    setExpandedPushId(pushId);
    if (pushDetails[pushId]) return;
    setDetailsLoadingPushId(pushId);
    const res = await chrome.runtime.sendMessage({
      type: "ctxh:push-detail",
      payload: {
        apiBaseUrl,
        authToken,
        pushId
      }
    });
    if (!res?.ok) {
      setError(res?.message || "Failed to load push details.");
      setDetailsLoadingPushId(null);
      return;
    }
    setPushDetails((prev) => ({ ...prev, [pushId]: res.data as PushDetail }));
    setDetailsLoadingPushId(null);
  }

  async function buildAndInjectPull() {
    if (!isReady || selectedPushIds.length === 0) return;
    setError(null);
    const res = await chrome.runtime.sendMessage({
      type: "ctxh:pull",
      payload: {
        apiBaseUrl,
        authToken,
        selections: selectedPushIds.map((pushId) => ({
          push_id: pushId,
          include_transcript: Boolean(transcriptSelections[pushId])
        }))
      }
    });
    if (!res?.ok) {
      setError(res?.message || "Pull failed.");
      return;
    }
    const payloadMarkdown = String(res.data?.payload_markdown || "");
    setPullPayload(payloadMarkdown);
    const injectRes = await chrome.runtime.sendMessage({
      type: "ctxh:inject",
      payload: { text: payloadMarkdown }
    });
    if (!injectRes?.ok) {
      setError(injectRes?.message || "Inject failed.");
    }
  }

  return (
    <div className="shell">
      <header className="header">
        <h1>ContextHub Assistant</h1>
        <p>Capture, retrieve, and inject context directly into Claude.</p>
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
              <input value={apiBaseUrl} onChange={(e) => setApiBaseUrl(e.target.value)} placeholder="http://localhost:8000" />
            </label>
            <label>
              Workspace ID
              <input
                value={workspaceId}
                onChange={(e) => setWorkspaceId(e.target.value)}
                placeholder="22222222-2222-2222-2222-222222222222"
              />
            </label>
            <label>
              API token (raw `ch_...`)
              <input value={authToken} onChange={(e) => setAuthToken(e.target.value)} placeholder="ch_..." />
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
            Push now scrapes the current Claude conversation from the page so you do not need to select text.
          </p>
          {capturedMessageCount > 0 ? (
            <p className="muted">
              Last capture: {capturedMessageCount} message(s)
            </p>
          ) : null}
          {capturePreview ? <p className="muted">Preview: {capturePreview}</p> : null}
          <button
            className="btn"
            onClick={() => {
              push();
            }}
          >
            Push to ContextHub
          </button>
          {lastPushId ? (
            <p className="muted">
              push_id: <code>{lastPushId}</code> {lastPushStatus ? <span>({lastPushStatus})</span> : null}
            </p>
          ) : null}
          {lastPushId ? (
            <button className="btn secondary" style={{ marginTop: 8 }} onClick={refreshPushStatus}>
              Refresh push status
            </button>
          ) : null}
          {scrubFlags.length ? <p className="muted">scrub_flags: {scrubFlags.join(", ")}</p> : null}
          {error ? <p className="muted" style={{ color: "#b02746" }}>Error: {error}</p> : null}
        </section>

        <section className="card">
          <h2>Search and pull</h2>
          <div className="grid" style={{ gap: 8 }}>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search pushed chats"
            />
            <button className="btn secondary" onClick={runSearch}>
              Search
            </button>
            <button className="btn" onClick={buildAndInjectPull} disabled={selectedPushIds.length === 0}>
              Pull + inject into Claude
            </button>
            {searchResults.map((result) => (
              <div
                key={result.push_id}
                className="card search-hit-card"
                style={{ minWidth: 0, maxWidth: "100%", overflow: "hidden", display: "grid", gap: 8 }}
              >
                <div className="row">
                  <h3 className="search-hit-title">{result.title || "Untitled push"}</h3>
                  <span className="pill">{result.status}</span>
                </div>
                <div className="row" style={{ justifyContent: "flex-start", gap: 12, flexWrap: "wrap" }}>
                  <label className="muted search-hit-select" style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                    <input
                      type="checkbox"
                      checked={selectedPushIds.includes(result.push_id)}
                      onChange={() => toggleSelectedPush(result.push_id)}
                    />
                    Select for pull
                  </label>
                  {selectedPushIds.includes(result.push_id) ? (
                    <label className="muted search-hit-select" style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                      <input
                        type="checkbox"
                        checked={Boolean(transcriptSelections[result.push_id])}
                        onChange={() => toggleTranscriptSelection(result.push_id)}
                      />
                      Include transcript
                    </label>
                  ) : null}
                </div>
                <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                  Push: <code>{result.push_id}</code>
                </p>
                <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                  Workspace: <code style={wrapTextStyle}>{result.workspace_id}</code>
                </p>
                <p className="muted" style={{ margin: 0, fontSize: 12 }}>
                  Created:{" "}
                  {result.created_at
                    ? new Date(result.created_at).toLocaleString()
                    : "—"}
                </p>

                <div className="grid" style={{ gap: 8, minWidth: 0, maxWidth: "100%" }}>
                  <div style={{ minWidth: 0, maxWidth: "100%" }}>
                    <strong className="search-hit-section-label">Summary</strong>
                    <p className="muted search-hit-summary" style={{ marginTop: 6, ...wrapTextStyle }}>
                      {((result.summary?.trim() || result.snippet || "").trim()) || "No summary available"}
                    </p>
                  </div>
                  <button
                    className="btn secondary"
                    type="button"
                    style={{ width: "fit-content" }}
                    onClick={() => togglePushDetails(result.push_id)}
                  >
                    {expandedPushId === result.push_id ? "Hide details" : "View details"}
                  </button>
                  {expandedPushId === result.push_id ? (
                    <div
                      className="card search-hit-details"
                      style={{
                        background: "#f3faff",
                        borderColor: "#b9d7ed",
                        maxWidth: "100%",
                        minWidth: 0,
                        boxSizing: "border-box",
                        overflow: "hidden",
                        boxShadow: "none",
                        margin: 0
                      }}
                    >
                      {detailsLoadingPushId === result.push_id ? (
                        <p className="muted" style={{ margin: 0 }}>
                          Loading details...
                        </p>
                      ) : (() => {
                          const detail = pushDetails[result.push_id];
                          const details = extractDetails(detail);
                          const turns = parseConversationTranscript(detail?.raw_transcript ?? null);
                          return (
                            <div style={{ display: "grid", gap: 12, minWidth: 0, maxWidth: "100%" }}>
                              <div style={{ minWidth: 0 }}>
                                <strong className="search-hit-section-label">Key takeaways</strong>
                                {details.keyTakeaways.length ? (
                                  <ul className="muted list search-hit-list" style={{ marginTop: 6, ...wrapTextStyle }}>
                                    {details.keyTakeaways.map((takeaway) => (
                                      <li key={takeaway} style={{ marginBottom: 4 }}>
                                        {takeaway}
                                      </li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p className="muted" style={{ marginTop: 6 }}>
                                    None
                                  </p>
                                )}
                              </div>
                              <div style={{ minWidth: 0 }}>
                                <strong className="search-hit-section-label">Tags</strong>
                                <div
                                  style={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    gap: 8,
                                    marginTop: 6,
                                    maxWidth: "100%"
                                  }}
                                >
                                  {details.tags.length ? (
                                    details.tags.map((tag) => (
                                      <span className="pill" key={tag}>
                                        {tag}
                                      </span>
                                    ))
                                  ) : (
                                    <span className="muted">None</span>
                                  )}
                                </div>
                              </div>
                              <div style={{ minWidth: 0 }}>
                                <strong className="search-hit-section-label">Conversation</strong>
                                <div
                                  className="search-hit-conversation"
                                  style={{
                                    marginTop: 8,
                                    maxHeight: 360,
                                    overflowY: "auto",
                                    border: "1px solid #b9d7ed",
                                    borderRadius: 8,
                                    padding: 10,
                                    background: "#fff",
                                    ...wrapTextStyle
                                  }}
                                >
                                  {turns?.length ? (
                                    turns.map((turn, idx) => (
                                      <div
                                        key={`${turn.role}-${idx}`}
                                        style={{
                                          marginBottom: idx < turns.length - 1 ? 14 : 0,
                                          ...wrapTextStyle
                                        }}
                                      >
                                        <span
                                          style={{
                                            fontWeight: 700,
                                            color: turn.role === "user" ? "#0d47a1" : "#2e7d32",
                                            display: "block",
                                            marginBottom: 4
                                          }}
                                        >
                                          {turn.role === "user" ? "User" : "Assistant"}:
                                        </span>
                                        <span
                                          className="muted"
                                          style={{ ...wrapTextStyle, display: "block", color: "#123b5a" }}
                                        >
                                          {turn.text}
                                        </span>
                                      </div>
                                    ))
                                  ) : (
                                    <span className="muted">No conversation transcript available.</span>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })()}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
            {pullPayload ? (
              <details>
                <summary>Last pulled payload</summary>
                <pre>
                  {pullPayload}
                </pre>
              </details>
            ) : null}
          </div>
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
