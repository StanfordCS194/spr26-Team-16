"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api";

type PushHistoryItem = {
  id: string;
  workspace_id: string;
  title: string | null;
  status: string;
  source_platform: string;
  source_url: string | null;
  created_at: string;
  updated_at: string;
  commit_message: string | null;
  structured_summary_markdown: string | null;
  raw_transcript: string | null;
};

type PushHistoryResponse = { items: PushHistoryItem[] };

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<PushHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | undefined>(undefined);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRequestId(undefined);
    const res = await apiFetch<PushHistoryResponse>("/v1/pushes/history?limit=25");
    if (!res.ok) {
      setError(res.message);
      setRequestId(res.requestId);
      setLoading(false);
      return;
    }
    setItems(res.data.items);
    setRequestId(res.requestId);
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const handler = () => refresh();
    window.addEventListener("ctxh:config:updated", handler);
    return () => window.removeEventListener("ctxh:config:updated", handler);
  }, [refresh]);

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) => {
      const haystack = [
        item.title || "",
        item.commit_message || "",
        item.structured_summary_markdown || "",
        item.raw_transcript || ""
      ]
        .join("\n")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [items, query]);

  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <div className="row">
          <h1 style={{ marginTop: 0, marginBottom: 0 }}>Search and pull</h1>
          <button className="button secondary" onClick={refresh} disabled={loading}>
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        <p className="muted">
          Auto-loaded from your past pushes. Filter locally by title, summaries, or transcript text.
        </p>
        <div className="row">
          <input
            style={{
              width: "100%",
              borderRadius: 8,
              border: "1px solid #355087",
              background: "#0f1830",
              color: "#edf2ff",
              padding: "10px 12px"
            }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by keywords from title, summary, or transcript..."
          />
        </div>
        {error ? (
          <p className="muted" style={{ color: "#ffb4b4" }}>
            Error: {error} {requestId ? <span>(request {requestId})</span> : null}
          </p>
        ) : null}
      </section>

      <section className="grid">
        {filteredItems.map((item) => (
          <article className="card" key={item.id}>
            <div className="row">
              <h3 style={{ margin: 0 }}>{item.title || "Untitled chat"}</h3>
              <span className="pill">{item.status}</span>
            </div>
            <p className="muted">
              Workspace: <code>{item.workspace_id}</code>
            </p>
            <p className="muted">
              Source: {item.source_platform} {item.source_url ? `- ${item.source_url}` : ""}
            </p>
            <p className="muted">Created: {new Date(item.created_at).toLocaleString()}</p>

            <div className="grid" style={{ gap: 8 }}>
              <div>
                <strong>Commit summary</strong>
                <p className="muted" style={{ marginTop: 6 }}>
                  {item.commit_message || "Not available yet (worker may still be processing)."}
                </p>
              </div>

              <details>
                <summary>Structured summary</summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    marginTop: 8,
                    background: "#0f1830",
                    border: "1px solid #2f4572",
                    borderRadius: 8,
                    padding: 10
                  }}
                >
                  {item.structured_summary_markdown || "Not available yet."}
                </pre>
              </details>

              <details>
                <summary>Raw transcript</summary>
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    marginTop: 8,
                    background: "#0f1830",
                    border: "1px solid #2f4572",
                    borderRadius: 8,
                    padding: 10,
                    maxHeight: 320,
                    overflow: "auto"
                  }}
                >
                  {item.raw_transcript || "Not available."}
                </pre>
              </details>
            </div>
          </article>
        ))}

        {!loading && filteredItems.length === 0 ? (
          <article className="card">
            <p className="muted" style={{ margin: 0 }}>
              No pushed chats found for this user yet.
            </p>
          </article>
        ) : null}
      </section>
    </div>
  );
}
