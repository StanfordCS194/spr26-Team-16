"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch, getDashboardApiBaseUrl, getDashboardAuthHeader, isJwtAuthHeader } from "@/lib/api";
import { getSupabaseAccessToken } from "@/lib/supabase";

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
  const [workspaceId, setWorkspaceId] = useState("");
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [pairingExpiresAt, setPairingExpiresAt] = useState<string | null>(null);
  const [hasSupabaseSession, setHasSupabaseSession] = useState(false);

  const canMint = useMemo(() => isJwtAuthHeader(authHeader) || hasSupabaseSession, [authHeader, hasSupabaseSession]);

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
    setWorkspaceId(localStorage.getItem("ctxh_workspace_id") || "");
    refresh();
    getSupabaseAccessToken().then((token) => setHasSupabaseSession(Boolean(token)));
    const handler = () => {
      setAuthHeader(getDashboardAuthHeader());
      refresh();
      getSupabaseAccessToken().then((token) => setHasSupabaseSession(Boolean(token)));
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

  async function createPairingCode() {
    setPairingCode(null);
    setPairingExpiresAt(null);
    setLoading(true);
    setError(null);
    setRequestId(undefined);

    const res = await apiFetch<{ code: string; expires_at: string }>("/v1/extension-pairing-codes", {
      method: "POST",
      body: JSON.stringify({
        token_name: mintName,
        scopes: mintScopes,
        workspace_id: workspaceId || null,
        api_base_url: getDashboardApiBaseUrl()
      })
    });

    if (!res.ok) {
      setError(`${res.message} (pairing requires JWT auth)`);
      setRequestId(res.requestId);
      setLoading(false);
      return;
    }

    setPairingCode(res.data.code);
    setPairingExpiresAt(res.data.expires_at);
    setLoading(false);
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
          <p className="muted" style={{ color: "#b02746" }}>
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
          {canMint ? "JWT auth detected (manual or Supabase session)." : "To mint, sign in with Supabase or set a JWT auth header."}
        </p>
        <div className="grid" style={{ gap: 10, marginTop: 10 }}>
          <label className="muted">
            Name
            <input value={mintName} onChange={(e) => setMintName(e.target.value)} />
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
            <div className="card" style={{ background: "#f3faff" }}>
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
          <h3 style={{ margin: 0 }}>Connect extension</h3>
          <button className="button secondary" onClick={createPairingCode} disabled={!canMint || loading}>
            Create pairing code
          </button>
        </div>
        <p className="muted">Creates a one-time code for extension setup without copying a raw token.</p>
        <label className="muted">
          Workspace ID (optional but recommended)
          <input
            value={workspaceId}
            onChange={(e) => {
              setWorkspaceId(e.target.value);
              localStorage.setItem("ctxh_workspace_id", e.target.value);
            }}
            placeholder="22222222-2222-2222-2222-222222222222"
          />
        </label>
        {pairingCode ? (
          <div className="card" style={{ background: "#f3faff", marginTop: 10 }}>
            <p className="muted" style={{ marginTop: 0 }}>Enter this one-time code in the extension:</p>
            <code style={{ display: "block", wordBreak: "break-all", fontSize: 18 }}>{pairingCode}</code>
            <p className="muted" style={{ marginBottom: 0 }}>
              Expires: {pairingExpiresAt ? new Date(pairingExpiresAt).toLocaleString() : "soon"}
            </p>
          </div>
        ) : null}
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
