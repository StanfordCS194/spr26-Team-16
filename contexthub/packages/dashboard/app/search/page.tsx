"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

type SearchResultItem = {
  push_id: string;
  workspace_id: string;
  title: string | null;
  status: string;
  created_at: string;
  layer: string;
  snippet: string;
  summary?: string;
  score: number;
  vector_score: number;
  text_score: number;
  message_count?: number | null;
  transcript_size_bytes?: number | null;
};

type SearchResponse = {
  query: string;
  limit: number;
  include_transcripts: boolean;
  items: SearchResultItem[];
};

type PushHistoryItem = {
  id: string;
  workspace_id: string;
  conversation_title: string | null;
  status: string;
  created_at: string;
  title: string | null;
  summary: string | null;
  details: SummaryDetails | null;
};

type PushHistoryResponse = {
  items: PushHistoryItem[];
};

type PullSource = {
  push_id: string;
  workspace_id: string;
  title: string | null;
  created_at: string;
};

type PullResponse = {
  mode: "summary_plus_optional_transcripts";
  target_platform: "claude_ai";
  token_estimate: number;
  payload_markdown: string;
  provenance: string;
  sources: PullSource[];
};

type PushDetailSummaryLayer = {
  layer: string;
  content_markdown: string | null;
  content_json: Record<string, unknown>;
  model: string | null;
  prompt_version: string | null;
  failure_reason: string | null;
};

type SummaryDetails = {
  summary?: unknown;
  key_takeaways?: unknown;
  tags?: unknown;
};

type ParsedSummaryDetails = {
  key_takeaways: string[];
  tags: string[];
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
  transcript_message_count: number | null;
  transcript_size_bytes: number | null;
  raw_transcript: string | null;
  summaries: PushDetailSummaryLayer[];
};

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

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [includeTranscripts, setIncludeTranscripts] = useState(false);
  const [items, setItems] = useState<SearchResultItem[]>([]);
  const [selectedPushIds, setSelectedPushIds] = useState<string[]>([]);
  const [transcriptSelections, setTranscriptSelections] = useState<Record<string, boolean>>({});
  const [pullResult, setPullResult] = useState<PullResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | undefined>(undefined);
  const [pulling, setPulling] = useState(false);
  const [viewMode, setViewMode] = useState<"all" | "search">("all");
  const [expandedPushId, setExpandedPushId] = useState<string | null>(null);
  const [pushDetails, setPushDetails] = useState<Record<string, PushDetailResponse>>({});
  const [detailLoadingPushId, setDetailLoadingPushId] = useState<string | null>(null);

  useEffect(() => {
    const savedWorkspaceId = localStorage.getItem("ctxh_workspace_id") || "";
    setWorkspaceId(savedWorkspaceId);
  }, []);

  const refreshAllConversations = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRequestId(undefined);
    setPullResult(null);
    const res = await apiFetch<PushHistoryResponse>("/v1/pushes/history?limit=50");
    if (!res.ok) {
      setError(res.message);
      setRequestId(res.requestId);
      setLoading(false);
      return;
    }
    const mapped: SearchResultItem[] = res.data.items.map((item) => ({
      push_id: item.id,
      workspace_id: item.workspace_id,
      title: item.title || item.conversation_title,
      status: item.status,
      created_at: item.created_at,
      layer: "summary",
      snippet: item.summary || "No summary available yet.",
      summary: (item.summary || "").trim(),
      score: 0,
      vector_score: 0,
      text_score: 0
    }));
    setItems(mapped);
    setSelectedPushIds([]);
    setTranscriptSelections({});
    setExpandedPushId(null);
    setViewMode("all");
    setRequestId(res.requestId);
    setLoading(false);
  }, []);

  const refresh = useCallback(async () => {
    const q = query.trim();
    if (!q) {
      await refreshAllConversations();
      return;
    }
    setLoading(true);
    setError(null);
    setRequestId(undefined);
    setPullResult(null);
    const params = new URLSearchParams({
      q,
      limit: "25",
      include_transcripts: includeTranscripts ? "true" : "false"
    });
    if (workspaceId.trim()) {
      params.set("workspace_id", workspaceId.trim());
    }
    const res = await apiFetch<SearchResponse>(`/v1/search?${params.toString()}`);
    if (!res.ok) {
      setError(res.message);
      setRequestId(res.requestId);
      setLoading(false);
      return;
    }
    setItems(res.data.items);
    setSelectedPushIds([]);
    setTranscriptSelections({});
    setExpandedPushId(null);
    setViewMode("search");
    setRequestId(res.requestId);
    setLoading(false);
  }, [query, includeTranscripts, workspaceId, refreshAllConversations]);

  useEffect(() => {
    refreshAllConversations();
  }, [refreshAllConversations]);

  const uniquePushes = useMemo(() => {
    const deduped = new Map<string, SearchResultItem>();
    for (const item of items) {
      const existing = deduped.get(item.push_id);
      const shouldReplace =
        !existing ||
        (item.layer === "summary" && existing.layer !== "summary") ||
        (item.layer === existing.layer && item.score > existing.score);
      if (shouldReplace) {
        deduped.set(item.push_id, item);
      }
    }
    return Array.from(deduped.values());
  }, [items]);

  const asStringList = useCallback((value: unknown): string[] => {
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
  }, []);

  const detailsFromLayer = useCallback(
    (detail: PushDetailResponse | undefined): ParsedSummaryDetails => {
      const detailsLayer = detail?.summaries.find((summary) => summary.layer === "details")
        ?.content_json as SummaryDetails | undefined;
      return {
        key_takeaways: asStringList(detailsLayer?.key_takeaways),
        tags: asStringList(detailsLayer?.tags)
      };
    },
    [asStringList]
  );

  async function toggleDetails(pushId: string) {
    if (expandedPushId === pushId) {
      setExpandedPushId(null);
      return;
    }
    setExpandedPushId(pushId);
    if (pushDetails[pushId]) return;
    setDetailLoadingPushId(pushId);
    const res = await apiFetch<PushDetailResponse>(`/v1/pushes/${pushId}`);
    if (!res.ok) {
      setError(res.message);
      setRequestId(res.requestId);
      setDetailLoadingPushId(null);
      return;
    }
    setPushDetails((prev) => ({ ...prev, [pushId]: res.data }));
    setDetailLoadingPushId(null);
  }

  async function pullSelected() {
    if (selectedPushIds.length === 0) return;
    setPulling(true);
    setError(null);
    setRequestId(undefined);
    const res = await apiFetch<PullResponse>("/v1/pulls", {
      method: "POST",
      body: JSON.stringify({
        selections: selectedPushIds.map((pushId) => ({
          push_id: pushId,
          include_transcript: Boolean(transcriptSelections[pushId])
        })),
        target_platform: "claude_ai",
        origin: "dashboard"
      })
    });
    if (!res.ok) {
      setError(res.message);
      setRequestId(res.requestId);
      setPulling(false);
      return;
    }
    setPullResult(res.data);
    setRequestId(res.requestId);
    setPulling(false);
  }

  function toggleSelected(pushId: string) {
    setSelectedPushIds((prev) => (prev.includes(pushId) ? prev.filter((id) => id !== pushId) : [...prev, pushId]));
  }

  function toggleTranscript(pushId: string) {
    setTranscriptSelections((prev) => ({ ...prev, [pushId]: !prev[pushId] }));
  }

  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 12,
            marginBottom: 12
          }}
        >
          <h1 style={{ margin: 0 }}>Search and pull</h1>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8, marginLeft: "auto" }}>
            <button className="button secondary" type="button" onClick={refreshAllConversations} disabled={loading}>
              Show all conversations
            </button>
            <p className="muted" style={{ margin: 0, textAlign: "right" }}>
              View: {viewMode === "all" ? "all conversations" : "search results"}
            </p>
          </div>
        </div>
        <div className="grid" style={{ gap: 10 }}>
          <input
            style={{
              width: "100%",
              borderRadius: 8,
              border: "1px solid #a8cde7",
              background: "#f7fcff",
              color: "#123b5a",
              padding: "10px 12px"
            }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search your saved pushes..."
          />
          <input
            style={{
              width: "100%",
              borderRadius: 8,
              border: "1px solid #a8cde7",
              background: "#f7fcff",
              color: "#123b5a",
              padding: "10px 12px"
            }}
            value={workspaceId}
            onChange={(e) => {
              setWorkspaceId(e.target.value);
              localStorage.setItem("ctxh_workspace_id", e.target.value);
            }}
            placeholder="Optional workspace UUID filter"
          />
          <label className="muted" style={{ display: "flex", flexDirection: "column", gap: 6, alignItems: "flex-start", maxWidth: "100%" }}>
            <span
              style={{
                display: "flex",
                flexWrap: "nowrap",
                gap: 8,
                alignItems: "center",
                maxWidth: "100%"
              }}
            >
              <input
                type="checkbox"
                checked={includeTranscripts}
                onChange={(e) => setIncludeTranscripts(e.target.checked)}
                style={{
                  flexShrink: 0,
                  width: "auto",
                  marginTop: 0,
                  marginInlineEnd: 0
                }}
              />
              <span style={{ whiteSpace: "nowrap", flexShrink: 0 }}>Include raw transcript in search hits</span>
            </span>
            <span style={{ fontSize: 12, lineHeight: 1.4, maxWidth: 720 }}>
              When checked, hybrid search also ranks the stored conversation transcript layer (not just title/summary/details).
              Useful if your query matches something only said in the full chat. Slightly noisier results when off-topic text
              appears in transcripts.
            </span>
          </label>
        </div>
        <div
          className="row"
          style={{
            marginTop: 16,
            justifyContent: "flex-start",
            flexWrap: "wrap",
            gap: 10
          }}
        >
          <button className="button secondary" type="button" onClick={refresh} disabled={loading}>
            {loading ? "Loading..." : "Search"}
          </button>
        </div>
        {error ? (
          <p className="muted" style={{ color: "#b02746", marginTop: 12, marginBottom: 0 }}>
            Error: {error} {requestId ? <span>(request {requestId})</span> : null}
          </p>
        ) : null}
      </section>

      <section className="grid">
        <article className="card">
          <div className="row">
            <strong>Pull from selected pushes</strong>
            <span className="pill">{selectedPushIds.length} selected</span>
          </div>
          <div className="row" style={{ justifyContent: "flex-start", gap: 10, marginTop: 10 }}>
            <button className="button" disabled={!selectedPushIds.length || pulling} onClick={pullSelected}>
              {pulling ? "Building..." : "Build pull payload"}
            </button>
          </div>
          {pullResult ? (
            <div className="grid" style={{ gap: 8, marginTop: 12 }}>
              <p className="muted" style={{ margin: 0 }}>
                Token estimate: {pullResult.token_estimate}
              </p>
              <details>
                <summary>Payload markdown</summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    marginTop: 8,
                    background: "#f3faff",
                    border: "1px solid #b9d7ed",
                    borderRadius: 8,
                    padding: 10,
                    maxHeight: 360,
                    overflow: "auto"
                  }}
                >
                  {pullResult.payload_markdown}
                </pre>
              </details>
            </div>
          ) : null}
        </article>

        {uniquePushes.map((item) => (
          <article className="card" key={item.push_id} style={{ minWidth: 0, maxWidth: "100%", overflow: "hidden" }}>
            <div className="row">
              <h3 style={{ margin: 0 }}>{item.title || "Untitled push"}</h3>
              <span className="pill">{item.status}</span>
            </div>
            <div className="row" style={{ justifyContent: "flex-start", gap: 12, flexWrap: "nowrap" }}>
              <label className="muted" style={{ display: "inline-flex", gap: 8, alignItems: "center", whiteSpace: "nowrap" }}>
                <input
                  type="checkbox"
                  checked={selectedPushIds.includes(item.push_id)}
                  onChange={() => toggleSelected(item.push_id)}
                />
                Select for pull
              </label>
              {selectedPushIds.includes(item.push_id) ? (
                <label className="muted" style={{ display: "inline-flex", gap: 8, alignItems: "center", whiteSpace: "nowrap" }}>
                  <input
                    type="checkbox"
                    checked={Boolean(transcriptSelections[item.push_id])}
                    onChange={() => toggleTranscript(item.push_id)}
                  />
                  Include transcript
                </label>
              ) : null}
            </div>
            <p className="muted">
              Push: <code>{item.push_id}</code>
            </p>
            <p className="muted">
              Workspace: <code style={wrapTextStyle}>{item.workspace_id}</code>
            </p>
            <p className="muted">Created: {new Date(item.created_at).toLocaleString()}</p>

            <div className="grid" style={{ gap: 8, minWidth: 0, maxWidth: "100%" }}>
              <div style={{ minWidth: 0, maxWidth: "100%" }}>
                <strong>Summary</strong>
                <p className="muted" style={{ marginTop: 6, ...wrapTextStyle }}>
                  {((item.summary?.trim() || item.snippet || "").trim()) || "No summary available"}
                </p>
              </div>
              <button
                className="button secondary"
                type="button"
                style={{ width: "fit-content" }}
                onClick={() => toggleDetails(item.push_id)}
              >
                {expandedPushId === item.push_id ? "Hide details" : "View details"}
              </button>
              {expandedPushId === item.push_id ? (
                <div
                  className="card"
                  style={{
                    background: "#f3faff",
                    borderColor: "#b9d7ed",
                    maxWidth: "100%",
                    minWidth: 0,
                    boxSizing: "border-box",
                    overflow: "hidden"
                  }}
                >
                  {detailLoadingPushId === item.push_id ? (
                    <p className="muted" style={{ margin: 0 }}>
                      Loading details...
                    </p>
                  ) : (() => {
                      const detail = pushDetails[item.push_id];
                      const details = detailsFromLayer(detail);
                      const turns = parseConversationTranscript(detail?.raw_transcript ?? null);
                      return (
                        <div className="grid" style={{ gap: 12, minWidth: 0, maxWidth: "100%" }}>
                          <div style={{ minWidth: 0 }}>
                            <strong>Key takeaways</strong>
                            {details.key_takeaways.length ? (
                              <ul className="muted" style={{ marginTop: 6, ...wrapTextStyle, paddingLeft: 20 }}>
                                {details.key_takeaways.map((takeaway) => (
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
                            <strong>Tags</strong>
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
                            <strong>Conversation</strong>
                            <div
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
                                    <span className="muted" style={{ ...wrapTextStyle, display: "block", color: "#123b5a" }}>
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
          </article>
        ))}

        {!loading && uniquePushes.length === 0 ? (
          <article className="card">
            <p className="muted" style={{ margin: 0 }}>
              No matches yet. Run a search query and confirm your auth/workspace settings.
            </p>
          </article>
        ) : null}
      </section>
    </div>
  );
}
