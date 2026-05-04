"use client";

import { useEffect, useMemo, useState } from "react";
import { isApiTokenAuthHeader, isJwtAuthHeader, normalizeAuthHeader } from "@/lib/api";

export function ApiConfig() {
  const [apiBaseUrl, setApiBaseUrl] = useState("http://localhost:8000");
  const [authHeader, setAuthHeader] = useState("");
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  const isJwt = useMemo(() => isJwtAuthHeader(authHeader), [authHeader]);
  const isApiToken = useMemo(() => isApiTokenAuthHeader(authHeader), [authHeader]);

  useEffect(() => {
    setApiBaseUrl(localStorage.getItem("ctxh_api_base_url") || "http://localhost:8000");
    setAuthHeader(localStorage.getItem("ctxh_auth_header") || "");
  }, []);

  function save() {
    const normalized = normalizeAuthHeader(authHeader);
    localStorage.setItem("ctxh_api_base_url", apiBaseUrl);
    localStorage.setItem("ctxh_auth_header", normalized);
    setAuthHeader(normalized);
    setSaveMessage(
      normalized
        ? `Saved ${isApiTokenAuthHeader(normalized) ? "API token" : isJwtAuthHeader(normalized) ? "JWT" : "authorization value"}.`
        : "Saved API URL without an auth token."
    );
    window.dispatchEvent(new Event("ctxh:config:updated"));
  }

  return (
    <section className="card">
      <div className="row">
        <h3 style={{ margin: 0 }}>API connection</h3>
        <span className="pill">{isJwt ? "JWT" : isApiToken ? "API token" : "Not set"}</span>
      </div>

      <div className="grid" style={{ gap: 10, marginTop: 12 }}>
        <label className="muted">
          API base URL
          <input
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            placeholder="http://localhost:8000"
          />
        </label>

        <label className="muted">
          Authorization header or raw token
          <input
            value={authHeader}
            onChange={(e) => setAuthHeader(e.target.value)}
            placeholder="Paste JWT, ch_..., or Bearer <token>"
          />
        </label>

        <div className="row">
          <span className="muted">Saved as `Bearer &lt;token&gt;` for `/v1/me`, `/v1/tokens`, and push operations.</span>
          <button className="button" onClick={save}>
            Save
          </button>
        </div>
        {saveMessage ? (
          <p className="muted" style={{ margin: 0, color: "#2d7a45" }}>
            {saveMessage}
          </p>
        ) : null}
      </div>
    </section>
  );
}
