"use client";

import { useEffect, useMemo, useState } from "react";
import { isApiTokenAuthHeader, isJwtAuthHeader, normalizeAuthHeader } from "@/lib/api";

export function ApiConfig() {
  const [apiBaseUrl, setApiBaseUrl] = useState("http://localhost:8000");
  const [authHeader, setAuthHeader] = useState("");
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [devLoginLoading, setDevLoginLoading] = useState(false);

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

  async function useLocalDevLogin() {
    setDevLoginLoading(true);
    setSaveMessage(null);
    try {
      const baseUrl = apiBaseUrl.replace(/\/+$/, "");
      const resp = await fetch(`${baseUrl}/v1/dev/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      const payload = await resp.json();
      if (!resp.ok) {
        const message =
          typeof payload?.error?.message === "string"
            ? payload.error.message
            : `Dev login failed (${resp.status}).`;
        setSaveMessage(message);
        return;
      }
      const token = typeof payload?.token === "string" ? payload.token : "";
      const normalized = normalizeAuthHeader(token);
      localStorage.setItem("ctxh_api_base_url", apiBaseUrl);
      localStorage.setItem("ctxh_auth_header", normalized);
      setAuthHeader(normalized);
      setSaveMessage("Saved local dev JWT from /v1/dev/login.");
      window.dispatchEvent(new Event("ctxh:config:updated"));
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : "Dev login failed.");
    } finally {
      setDevLoginLoading(false);
    }
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
          Manual authorization header or raw token
          <input
            value={authHeader}
            onChange={(e) => setAuthHeader(e.target.value)}
            placeholder="Paste JWT, ch_..., or Bearer <token>"
          />
        </label>

        <div className="row">
          <span className="muted">Advanced/local fallback. Saved as `Bearer &lt;token&gt;` for dashboard API calls.</span>
          <button className="button" onClick={save}>
            Save
          </button>
        </div>
        <div className="row">
          <span className="muted">Local dev shortcut: fetch a short-lived JWT from `/v1/dev/login`.</span>
          <button className="button secondary" onClick={useLocalDevLogin} disabled={devLoginLoading} type="button">
            {devLoginLoading ? "Signing in..." : "Use local dev login"}
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
