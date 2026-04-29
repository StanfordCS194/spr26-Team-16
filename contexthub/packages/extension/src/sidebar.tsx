import { createRoot } from "react-dom/client";
import { useEffect, useMemo, useState } from "react";
import "./sidebar.css";
import { ConversationV0 } from "@contexthub/interchange-spec";

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
    Array<{ push_id: string; title: string | null; workspace_id: string; summary: string; snippet: string; score: number }>
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
      { push_id: string; title: string | null; workspace_id: string; summary: string; snippet: string; score: number }
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
              <div key={result.push_id} className="muted card" style={{ display: "grid", gap: 6, padding: 10 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8, flexWrap: "nowrap" }}>
                  <input
                    type="checkbox"
                    checked={selectedPushIds.includes(result.push_id)}
                    onChange={() => toggleSelectedPush(result.push_id)}
                  />
                  <strong>{result.title || "Untitled push"}</strong>
                </span>
                {selectedPushIds.includes(result.push_id) ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8, whiteSpace: "nowrap" }}>
                    <input
                      type="checkbox"
                      checked={Boolean(transcriptSelections[result.push_id])}
                      onChange={() => toggleTranscriptSelection(result.push_id)}
                    />
                    Include transcript
                  </span>
                ) : null}
                <span>
                  <code>{result.push_id}</code>
                </span>
                <span style={{ whiteSpace: "pre-wrap", overflowWrap: "break-word", wordBreak: "break-word" }}>
                  {result.summary || result.snippet || "No summary available"}
                </span>
                <button
                  className="btn secondary"
                  type="button"
                  style={{ width: "fit-content" }}
                  onClick={() => togglePushDetails(result.push_id)}
                >
                  {expandedPushId === result.push_id ? "Hide details" : "View details"}
                </button>
                {expandedPushId === result.push_id ? (
                  <div className="card" style={{ marginTop: 4 }}>
                    {detailsLoadingPushId === result.push_id ? (
                      <span>Loading details...</span>
                    ) : (() => {
                        const detail = pushDetails[result.push_id];
                        const details = extractDetails(detail);
                        return (
                          <div style={{ display: "grid", gap: 8 }}>
                            <span><strong>Summary:</strong> {details.summary || "No summary available."}</span>
                            <div>
                              <strong>Key takeaways</strong>
                              {details.keyTakeaways.length ? (
                                <ul className="list">
                                  {details.keyTakeaways.map((takeaway) => <li key={takeaway}>{takeaway}</li>)}
                                </ul>
                              ) : (
                                <div>None</div>
                              )}
                            </div>
                            <div>
                              <strong>Tags</strong>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                                {details.tags.length
                                  ? details.tags.map((tag) => <span className="pill" key={tag}>{tag}</span>)
                                  : <span>None</span>}
                              </div>
                            </div>
                            <div>
                              <strong>Raw transcript</strong>
                              <pre style={{ maxHeight: 220, overflow: "auto", marginTop: 6 }}>
                                {detail?.raw_transcript || "No transcript available."}
                              </pre>
                            </div>
                          </div>
                        );
                      })()}
                  </div>
                ) : null}
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
