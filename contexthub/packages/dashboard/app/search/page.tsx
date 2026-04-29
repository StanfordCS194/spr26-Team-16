"use client";

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
  title: string | null;
  status: string;
  created_at: string;
  commit_message: string | null;
  structured_summary_markdown: string | null;
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
  mode: "structured_block_plus_optional_transcripts";
  target_platform: "claude_ai";
  token_estimate: number;
  payload_markdown: string;
  provenance: string;
  sources: PullSource[];
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
      title: item.title,
      status: item.status,
      created_at: item.created_at,
      layer: "structured_block",
      snippet: item.structured_summary_markdown || item.commit_message || "No summary available yet.",
      score: 0,
      vector_score: 0,
      text_score: 0
    }));
    setItems(mapped);
    setSelectedPushIds([]);
    setTranscriptSelections({});
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
      if (!deduped.has(item.push_id) || (deduped.get(item.push_id)?.score ?? 0) < item.score) {
        deduped.set(item.push_id, item);
      }
    }
    return Array.from(deduped.values());
  }, [items]);

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
        <div className="row">
          <h1 style={{ marginTop: 0, marginBottom: 0 }}>Search and pull</h1>
          <div className="row" style={{ gap: 8 }}>
            <button className="button secondary" onClick={refresh} disabled={loading}>
              {loading ? "Loading..." : "Search"}
            </button>
            <button className="button secondary" onClick={refreshAllConversations} disabled={loading}>
              Show all conversations
            </button>
          </div>
        </div>
        <p className="muted">
          Uses backend `/v1/search` (hybrid ranking) and `/v1/pulls` to build prompt-ready context payloads.
        </p>
        <p className="muted" style={{ marginTop: -6 }}>
          View: {viewMode === "all" ? "all conversations" : "search results"}
        </p>
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
          <label className="muted" style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={includeTranscripts}
              onChange={(e) => setIncludeTranscripts(e.target.checked)}
            />
            Include transcript summary layer
          </label>
        </div>
        {error ? (
          <p className="muted" style={{ color: "#b02746" }}>
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
          <article className="card" key={item.push_id}>
            <div className="row">
              <h3 style={{ margin: 0 }}>{item.title || "Untitled push"}</h3>
              <span className="pill">{item.status}</span>
            </div>
            <p className="muted">
              <label style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={selectedPushIds.includes(item.push_id)}
                  onChange={() => toggleSelected(item.push_id)}
                />
                Select for pull
              </label>
              {selectedPushIds.includes(item.push_id) ? (
                <label style={{ display: "inline-flex", gap: 8, alignItems: "center", marginLeft: 12 }}>
                  <input
                    type="checkbox"
                    checked={Boolean(transcriptSelections[item.push_id])}
                    onChange={() => toggleTranscript(item.push_id)}
                  />
                  Include transcript
                </label>
              ) : null}
            </p>
            <p className="muted">
              Push: <code>{item.push_id}</code>
            </p>
            <p className="muted">
              Workspace: <code>{item.workspace_id}</code>
            </p>
            <p className="muted">Created: {new Date(item.created_at).toLocaleString()} · Layer: {item.layer}</p>

            <div className="grid" style={{ gap: 8 }}>
              <div>
                <strong>Snippet</strong>
                <p className="muted" style={{ marginTop: 6 }}>
                  {item.snippet || "No snippet available"}
                </p>
              </div>
              <p className="muted" style={{ margin: 0 }}>
                score={item.score.toFixed(3)} · vector={item.vector_score.toFixed(3)} · text={item.text_score.toFixed(3)}
              </p>
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
