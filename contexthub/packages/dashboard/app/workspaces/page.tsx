"use client";

import { useEffect, useMemo, useState } from "react";
import { ConversationV0 } from "@contexthub/interchange-spec";
import { apiFetch, getDashboardAuthHeader } from "@/lib/api";

type PushAccepted = { push_id: string; status: string; request_id: string; scrub_flags: string[] };

function defaultConversation(title: string): ConversationV0 {
  return {
    spec_version: "ch.v0.1",
    source: { platform: "claude_ai", captured_at: new Date().toISOString() },
    messages: [
      { role: "user", content: [{ type: "text", text: "This is a dashboard-triggered push test." }] },
      { role: "assistant", content: [{ type: "text", text: "If the worker is running, this should become ready." }] }
    ],
    metadata: { title }
  };
}

function PushTester() {
  const [workspaceId, setWorkspaceId] = useState("");
  const [idempotencyKey, setIdempotencyKey] = useState(`dash-${Date.now()}`);
  const [jsonBody, setJsonBody] = useState<string>(() => JSON.stringify(defaultConversation("Dashboard push test"), null, 2));

  const [result, setResult] = useState<PushAccepted | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);

  const auth = useMemo(() => getDashboardAuthHeader(), []);
  const authKind = useMemo(() => (auth.includes("ch_") ? "API token" : auth.split(".").length === 3 ? "JWT" : "Not set"), [auth]);

  useEffect(() => {
    const saved = localStorage.getItem("ctxh_workspace_id");
    if (saved) setWorkspaceId(saved);
  }, []);

  function persistWorkspaceId(value: string) {
    setWorkspaceId(value);
    localStorage.setItem("ctxh_workspace_id", value);
  }

  async function push() {
    setLoading(true);
    setError(null);
    setRequestId(undefined);
    setResult(null);

    let parsed: ConversationV0;
    try {
      parsed = JSON.parse(jsonBody) as ConversationV0;
    } catch {
      setError("Conversation JSON is not valid JSON.");
      setLoading(false);
      return;
    }

    const res = await apiFetch<PushAccepted>(`/v1/workspaces/${workspaceId}/pushes`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(parsed)
    });

    if (!res.ok) {
      setError(res.message);
      setRequestId(res.requestId);
      setLoading(false);
      return;
    }

    setResult(res.data);
    setRequestId(res.requestId ?? res.data.request_id);
    setLoading(false);
  }

  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <div className="row">
          <h1 style={{ margin: 0 }}>Workspaces</h1>
          <span className="pill">API: pushes live</span>
        </div>
        <p className="muted">
          Workspace listing isn’t exposed yet, but push ingestion is. Use this form to hit
          <code style={{ marginLeft: 8 }}>/v1/workspaces/&lt;workspace_id&gt;/pushes</code>.
        </p>
        <p className="muted">Auth: {authKind}</p>
      </section>

      <section className="card">
        <div className="grid" style={{ gap: 10 }}>
          <label className="muted">
            Workspace ID
            <input
              style={{
                width: "100%",
                marginTop: 6,
                borderRadius: 8,
                border: "1px solid #355087",
                background: "#0f1830",
                color: "#edf2ff",
                padding: "10px 12px"
              }}
              value={workspaceId}
              onChange={(e) => persistWorkspaceId(e.target.value)}
              placeholder="22222222-2222-2222-2222-222222222222"
            />
          </label>

          <label className="muted">
            Idempotency-Key
            <input
              style={{
                width: "100%",
                marginTop: 6,
                borderRadius: 8,
                border: "1px solid #355087",
                background: "#0f1830",
                color: "#edf2ff",
                padding: "10px 12px"
              }}
              value={idempotencyKey}
              onChange={(e) => setIdempotencyKey(e.target.value)}
            />
          </label>

          <label className="muted">
            ConversationV0 JSON
            <textarea
              style={{
                width: "100%",
                minHeight: 240,
                marginTop: 6,
                borderRadius: 8,
                border: "1px solid #355087",
                background: "#0f1830",
                color: "#edf2ff",
                padding: "10px 12px",
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                fontSize: 12
              }}
              value={jsonBody}
              onChange={(e) => setJsonBody(e.target.value)}
            />
          </label>

          <div className="row">
            <button className="button" onClick={push} disabled={loading || !workspaceId}>
              {loading ? "Pushing..." : "Push"}
            </button>
            <button
              className="button secondary"
              onClick={() => setJsonBody(JSON.stringify(defaultConversation("Dashboard push test"), null, 2))}
              disabled={loading}
            >
              Reset JSON
            </button>
          </div>

          {error ? (
            <p className="muted" style={{ color: "#ffb4b4" }}>
              Error: {error} {requestId ? <span>(request {requestId})</span> : null}
            </p>
          ) : null}

          {result ? (
            <div className="card" style={{ background: "#0f1830" }}>
              <div className="row">
                <strong>Accepted</strong>
                <span className="pill">{result.status}</span>
              </div>
              <p className="muted">push_id: {result.push_id}</p>
              <p className="muted">request_id: {result.request_id}</p>
              <p className="muted">scrub_flags: {result.scrub_flags.length ? result.scrub_flags.join(", ") : "[]"}</p>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

export default function WorkspacesPage() {
  return <PushTester />;
}
