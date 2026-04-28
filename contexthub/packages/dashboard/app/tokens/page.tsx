"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, getDashboardAuthHeader, isJwtAuthHeader } from "@/lib/api";

type TokenRow = {
  id: string;
  name: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

type TokenMintResponse = TokenRow & { token: string };

export default function TokensPage() {
  const [tokens, setTokens] = useState<TokenRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | undefined>(undefined);

  const [mintName, setMintName] = useState("chrome-extension");
  const [mintScopes, setMintScopes] = useState<string[]>(["push", "read"]);
  const [mintedRawToken, setMintedRawToken] = useState<string | null>(null);
  const [authHeader, setAuthHeader] = useState("");

  const canMint = useMemo(() => isJwtAuthHeader(authHeader), [authHeader]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    setRequestId(undefined);

    const res = await apiFetch<TokenRow[]>("/v1/tokens");
    if (!res.ok) {
      setError(res.message);
      setRequestId(res.requestId);
      setLoading(false);
      return;
    }

    setTokens(res.data);
    setRequestId(res.requestId);
    setLoading(false);
  }, []);

  useEffect(() => {
    setAuthHeader(getDashboardAuthHeader());
    refresh();
    const handler = () => {
      setAuthHeader(getDashboardAuthHeader());
      refresh();
    };
    window.addEventListener("ctxh:config:updated", handler);
    return () => window.removeEventListener("ctxh:config:updated", handler);
  }, [refresh]);

  async function mint() {
    setMintedRawToken(null);
    setLoading(true);
    setError(null);
    setRequestId(undefined);

    const res = await apiFetch<TokenMintResponse>("/v1/tokens", {
      method: "POST",
      body: JSON.stringify({ name: mintName, scopes: mintScopes })
    });

    if (!res.ok) {
      setError(`${res.message} (mint requires JWT auth)`);
      setRequestId(res.requestId);
      setLoading(false);
      return;
    }

    setMintedRawToken(res.data.token);
    await refresh();
    setLoading(false);
  }

  async function revoke(tokenId: string) {
    setLoading(true);
    setError(null);
    setRequestId(undefined);

    const res = await apiFetch<unknown>(`/v1/tokens/${tokenId}`, { method: "DELETE" });
    if (!res.ok) {
      setError(res.message);
      setRequestId(res.requestId);
      setLoading(false);
      return;
    }

    await refresh();
    setLoading(false);
  }

  function toggleScope(scope: string) {
    setMintScopes((prev) => (prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope]));
  }

  return (
    <div className="grid" style={{ gap: 16 }}>
      <section className="card">
        <div className="row">
          <h1 style={{ margin: 0 }}>Extension tokens</h1>
          <span className="pill">{loading ? "Loading" : "Connected"}</span>
        </div>
        <p className="muted">
          Backed by backend routes: <code>/v1/tokens</code>. Mint requires JWT auth; list/revoke works for JWT or API
          token.
        </p>
        {error ? (
          <p className="muted" style={{ color: "#ffb4b4" }}>
            Error: {error} {requestId ? <span>(request {requestId})</span> : null}
          </p>
        ) : null}
      </section>

      <section className="card">
        <div className="row">
          <h3 style={{ margin: 0 }}>Mint</h3>
          <button className="button" onClick={mint} disabled={!canMint || loading}>
            Mint token
          </button>
        </div>
        <p className="muted">
          {canMint ? "JWT detected." : "To mint, set Authorization header to a JWT (Bearer ...)."}
        </p>
        <div className="grid" style={{ gap: 10, marginTop: 10 }}>
          <label className="muted">
            Name
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
              value={mintName}
              onChange={(e) => setMintName(e.target.value)}
            />
          </label>

          <div className="row" style={{ justifyContent: "flex-start", gap: 10, flexWrap: "wrap" }}>
            {["push", "pull", "search", "read"].map((scope) => (
              <button
                key={scope}
                className={`button secondary`}
                onClick={() => toggleScope(scope)}
                style={{ opacity: mintScopes.includes(scope) ? 1 : 0.55 }}
                type="button"
              >
                {mintScopes.includes(scope) ? "✓ " : ""}{scope}
              </button>
            ))}
          </div>

          {mintedRawToken ? (
            <div className="card" style={{ background: "#0f1830" }}>
              <p className="muted" style={{ marginTop: 0 }}>
                Raw token (shown once):
              </p>
              <code style={{ display: "block", wordBreak: "break-all" }}>{mintedRawToken}</code>
            </div>
          ) : null}
        </div>
      </section>

      <section className="card">
        <div className="row">
          <h3 style={{ margin: 0 }}>Active tokens</h3>
          <button className="button secondary" onClick={refresh} disabled={loading}>
            Refresh
          </button>
        </div>
        <ul className="list" style={{ marginTop: 12 }}>
          {tokens.map((t) => (
            <li className="card" key={t.id}>
              <div className="row">
                <strong>{t.name}</strong>
                <span className="pill">{t.scopes.join(", ")}</span>
              </div>
              <p className="muted">Created: {new Date(t.created_at).toLocaleString()}</p>
              <p className="muted">Last used: {t.last_used_at ? new Date(t.last_used_at).toLocaleString() : "—"}</p>
              <div className="row">
                <code>{t.id}</code>
                <button className="button secondary" onClick={() => revoke(t.id)} disabled={loading}>
                  Revoke
                </button>
              </div>
            </li>
          ))}
          {!loading && tokens.length === 0 ? <li className="muted">No active tokens.</li> : null}
        </ul>
      </section>
    </div>
  );
}
