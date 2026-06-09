/// <reference types="vite/client" />

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string;
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string;
const DEFAULT_API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8765";

chrome.runtime.onInstalled.addListener(() => {
  console.info("[ContextHub] extension installed");
});

async function apiRequest(
  apiBaseUrl: string,
  authToken: string,
  path: string,
  init?: RequestInit
) {
  const base = String(apiBaseUrl).replace(/\/+$/, "");
  const url = `${base}${path}`;
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${authToken}`);
  if (!headers.has("Content-Type") && init?.body) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(url, { ...init, headers });
  const requestId = res.headers.get("X-Request-Id");
  const text = await res.text();
  if (!res.ok) {
    return { ok: false as const, message: `HTTP ${res.status}: ${text}`, requestId };
  }
  return { ok: true as const, data: text ? JSON.parse(text) : null, requestId };
}

type SupabaseSession = {
  access_token: string;
  refresh_token: string;
  expires_at: number; // unix seconds
  user_id: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
};

async function readSession(): Promise<SupabaseSession | null> {
  const { supabaseSession } = await chrome.storage.local.get("supabaseSession");
  if (!supabaseSession || typeof supabaseSession !== "object") return null;
  return supabaseSession as SupabaseSession;
}

async function writeSession(session: SupabaseSession | null): Promise<void> {
  if (session) {
    await chrome.storage.local.set({ supabaseSession: session });
  } else {
    await chrome.storage.local.remove("supabaseSession");
  }
}

async function refreshSession(session: SupabaseSession): Promise<SupabaseSession | null> {
  // Refresh ~60s before expiry.
  const skewSeconds = 60;
  if (session.expires_at - Date.now() / 1000 > skewSeconds) return session;

  try {
    const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: SUPABASE_ANON_KEY
      },
      body: JSON.stringify({ refresh_token: session.refresh_token })
    });
    if (!res.ok) return null;
    const data = await res.json();
    const next: SupabaseSession = {
      access_token: data.access_token,
      refresh_token: data.refresh_token || session.refresh_token,
      expires_at: Math.floor(Date.now() / 1000) + (data.expires_in || 3600),
      user_id: data.user?.id || session.user_id,
      email: data.user?.email || session.email,
      display_name: data.user?.user_metadata?.full_name || data.user?.user_metadata?.name || session.display_name,
      avatar_url: data.user?.user_metadata?.avatar_url || data.user?.user_metadata?.picture || session.avatar_url
    };
    await writeSession(next);
    return next;
  } catch {
    return null;
  }
}

async function getValidAccessToken(): Promise<string | null> {
  const session = await readSession();
  if (!session) return null;
  const fresh = await refreshSession(session);
  return fresh?.access_token || null;
}

function parseUrlFragment(url: string): URLSearchParams {
  const u = new URL(url);
  return new URLSearchParams(u.hash.startsWith("#") ? u.hash.slice(1) : u.hash);
}

async function performSupabaseGoogleSignIn(): Promise<SupabaseSession> {
  if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
    throw new Error("Supabase is not configured in the extension build.");
  }

  const redirectUri = chrome.identity.getRedirectURL();
  const authUrl = new URL(`${SUPABASE_URL}/auth/v1/authorize`);
  authUrl.searchParams.set("provider", "google");
  authUrl.searchParams.set("redirect_to", redirectUri);

  const resultUrl = await new Promise<string>((resolve, reject) => {
    chrome.identity.launchWebAuthFlow(
      { url: authUrl.toString(), interactive: true },
      (responseUrl) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message || "Sign-in failed."));
          return;
        }
        if (!responseUrl) {
          reject(new Error("Sign-in was cancelled."));
          return;
        }
        resolve(responseUrl);
      }
    );
  });

  const params = parseUrlFragment(resultUrl);
  const errorParam = params.get("error_description") || params.get("error");
  if (errorParam) throw new Error(`Sign-in failed: ${errorParam}`);

  const accessToken = params.get("access_token");
  const refreshToken = params.get("refresh_token");
  const expiresIn = Number(params.get("expires_in") || "3600");
  if (!accessToken || !refreshToken) {
    throw new Error("Sign-in response was missing tokens.");
  }

  // Fetch user info to populate display name + email.
  const userRes = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
    headers: { Authorization: `Bearer ${accessToken}`, apikey: SUPABASE_ANON_KEY }
  });
  if (!userRes.ok) {
    throw new Error(`Could not load user profile: HTTP ${userRes.status}`);
  }
  const user = await userRes.json();

  const session: SupabaseSession = {
    access_token: accessToken,
    refresh_token: refreshToken,
    expires_at: Math.floor(Date.now() / 1000) + expiresIn,
    user_id: user.id,
    email: user.email || null,
    display_name: user.user_metadata?.full_name || user.user_metadata?.name || null,
    avatar_url: user.user_metadata?.avatar_url || user.user_metadata?.picture || null
  };
  await writeSession(session);
  return session;
}

async function bootstrapBackend(
  apiBaseUrl: string,
  session: SupabaseSession
): Promise<{ workspaceId: string }> {
  const res = await apiRequest(apiBaseUrl, session.access_token, "/v1/me/bootstrap", {
    method: "POST",
    body: JSON.stringify({
      email: session.email,
      display_name: session.display_name,
      avatar_url: session.avatar_url
    })
  });
  if (!res.ok) throw new Error(res.message || "Backend bootstrap failed.");
  const workspaceId = String(res.data?.workspace_id || "");
  if (!workspaceId) throw new Error("Backend did not return a workspace_id.");
  return { workspaceId };
}

async function performSupabaseSignOut(): Promise<void> {
  const session = await readSession();
  if (session) {
    try {
      await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          apikey: SUPABASE_ANON_KEY
        }
      });
    } catch {
      // best-effort; clear local state regardless
    }
  }
  await writeSession(null);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "ctxh:sidebar:opened") {
    sendResponse({ ok: true, status: "connected" });
    return true;
  }

  if (message?.type === "ctxh:capture") {
    (async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) {
        sendResponse({ ok: false, message: "No active tab" });
        return;
      }
      const resp = await chrome.tabs.sendMessage(tab.id, { type: "ctxh:capture" });
      sendResponse(resp);
    })();
    return true;
  }

  if (message?.type === "ctxh:push") {
    (async () => {
      try {
        const { apiBaseUrl, workspaceId, conversation, idempotencyKey } = message.payload ?? {};
        const accessToken = await getValidAccessToken();
        if (!accessToken) {
          sendResponse({ ok: false, message: "Not signed in." });
          return;
        }
        if (!apiBaseUrl || !workspaceId || !conversation) {
          sendResponse({ ok: false, message: "Missing apiBaseUrl/workspaceId/conversation" });
          return;
        }

        const res = await apiRequest(apiBaseUrl, accessToken, `/v1/workspaces/${workspaceId}/pushes`, {
          method: "POST",
          headers: {
            "Idempotency-Key": idempotencyKey || `ext-${Date.now()}`
          },
          body: JSON.stringify(conversation)
        });
        sendResponse(res);
      } catch (err) {
        sendResponse({ ok: false, message: err instanceof Error ? err.message : "Unknown error" });
      }
    })();
    return true;
  }

  if (message?.type === "ctxh:push-status" || message?.type === "ctxh:push-detail") {
    (async () => {
      try {
        const { apiBaseUrl, pushId } = message.payload ?? {};
        const accessToken = await getValidAccessToken();
        if (!accessToken) {
          sendResponse({ ok: false, message: "Not signed in." });
          return;
        }
        if (!apiBaseUrl || !pushId) {
          sendResponse({ ok: false, message: "Missing apiBaseUrl/pushId" });
          return;
        }
        const res = await apiRequest(apiBaseUrl, accessToken, `/v1/pushes/${pushId}`);
        sendResponse(res);
      } catch (err) {
        sendResponse({ ok: false, message: err instanceof Error ? err.message : "Unknown error" });
      }
    })();
    return true;
  }

  if (message?.type === "ctxh:search") {
    (async () => {
      try {
        const { apiBaseUrl, query, workspaceId, includeTranscripts } = message.payload ?? {};
        const accessToken = await getValidAccessToken();
        if (!accessToken) {
          sendResponse({ ok: false, message: "Not signed in." });
          return;
        }
        if (!apiBaseUrl) {
          sendResponse({ ok: false, message: "Missing apiBaseUrl" });
          return;
        }
        const trimmedQuery = String(query || "").trim();
        const isBrowseAll = !trimmedQuery || trimmedQuery === "*";

        if (isBrowseAll) {
          // No query → list all recent pushes, even ones without summaries yet.
          const res = await apiRequest(
            apiBaseUrl,
            accessToken,
            "/v1/pushes/history?limit=50"
          );
          if (!res.ok) {
            sendResponse(res);
            return;
          }
          const items = Array.isArray(res.data?.items) ? res.data.items : [];
          // Normalize to the shape sidebar expects from /v1/search.
          sendResponse({
            ok: true,
            data: {
              items: items.map((p: Record<string, unknown>) => ({
                push_id: p.id,
                title: p.title || p.conversation_title || null,
                summary: p.summary || "",
                snippet: "",
                score: 0,
                status: p.status || "unknown",
                created_at: p.created_at,
                workspace_id: p.workspace_id
              }))
            }
          });
          return;
        }

        // Real search query → vector + BM25 (only matches summarized pushes).
        const params = new URLSearchParams({
          q: trimmedQuery,
          limit: "20",
          include_transcripts: includeTranscripts ? "true" : "false"
        });
        if (workspaceId) params.set("workspace_id", String(workspaceId));
        const res = await apiRequest(apiBaseUrl, accessToken, `/v1/search?${params.toString()}`);
        sendResponse(res);
      } catch (err) {
        sendResponse({ ok: false, message: err instanceof Error ? err.message : "Unknown error" });
      }
    })();
    return true;
  }

  if (message?.type === "ctxh:pull") {
    (async () => {
      try {
        const { apiBaseUrl, selections } = message.payload ?? {};
        const accessToken = await getValidAccessToken();
        if (!accessToken) {
          sendResponse({ ok: false, message: "Not signed in." });
          return;
        }
        if (!apiBaseUrl || !Array.isArray(selections) || selections.length === 0) {
          sendResponse({ ok: false, message: "Missing apiBaseUrl/selections" });
          return;
        }
        const res = await apiRequest(apiBaseUrl, accessToken, "/v1/pulls", {
          method: "POST",
          body: JSON.stringify({
            selections,
            target_platform: "claude_ai",
            origin: "extension"
          })
        });
        sendResponse(res);
      } catch (err) {
        sendResponse({ ok: false, message: err instanceof Error ? err.message : "Unknown error" });
      }
    })();
    return true;
  }

  if (message?.type === "ctxh:supabase-signin") {
    (async () => {
      try {
        const apiBaseUrl = (message.payload?.apiBaseUrl as string) || DEFAULT_API_BASE_URL;
        const session = await performSupabaseGoogleSignIn();
        const { workspaceId } = await bootstrapBackend(apiBaseUrl, session);
        sendResponse({
          ok: true,
          data: {
            workspace_id: workspaceId,
            user: {
              email: session.email,
              display_name: session.display_name,
              avatar_url: session.avatar_url
            },
            apiBaseUrl
          }
        });
      } catch (err) {
        sendResponse({ ok: false, message: err instanceof Error ? err.message : "Sign-in failed." });
      }
    })();
    return true;
  }

  if (message?.type === "ctxh:supabase-signout") {
    (async () => {
      await performSupabaseSignOut();
      sendResponse({ ok: true });
    })();
    return true;
  }

  if (message?.type === "ctxh:session-status") {
    (async () => {
      const session = await readSession();
      if (!session) {
        sendResponse({ ok: true, data: { signedIn: false } });
        return;
      }
      const refreshed = await refreshSession(session);
      if (!refreshed) {
        await writeSession(null);
        sendResponse({ ok: true, data: { signedIn: false } });
        return;
      }
      sendResponse({
        ok: true,
        data: {
          signedIn: true,
          user: {
            email: refreshed.email,
            display_name: refreshed.display_name,
            avatar_url: refreshed.avatar_url
          }
        }
      });
    })();
    return true;
  }

  if (message?.type === "ctxh:inject") {
    (async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) {
        sendResponse({ ok: false, message: "No active tab" });
        return;
      }
      const resp = await chrome.tabs.sendMessage(tab.id, { type: "ctxh:inject", text: message?.payload?.text || "" });
      sendResponse(resp);
    })();
    return true;
  }

  return false;
});
