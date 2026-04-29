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
        const { apiBaseUrl, authToken, workspaceId, conversation, idempotencyKey } = message.payload ?? {};
        if (!apiBaseUrl || !authToken || !workspaceId || !conversation) {
          sendResponse({ ok: false, message: "Missing settings (apiBaseUrl/authToken/workspaceId) or conversation" });
          return;
        }

        const res = await apiRequest(apiBaseUrl, authToken, `/v1/workspaces/${workspaceId}/pushes`, {
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

  if (message?.type === "ctxh:push-status") {
    (async () => {
      try {
        const { apiBaseUrl, authToken, pushId } = message.payload ?? {};
        if (!apiBaseUrl || !authToken || !pushId) {
          sendResponse({ ok: false, message: "Missing apiBaseUrl/authToken/pushId" });
          return;
        }
        const res = await apiRequest(apiBaseUrl, authToken, `/v1/pushes/${pushId}`);
        sendResponse(res);
      } catch (err) {
        sendResponse({ ok: false, message: err instanceof Error ? err.message : "Unknown error" });
      }
    })();
    return true;
  }

  if (message?.type === "ctxh:push-detail") {
    (async () => {
      try {
        const { apiBaseUrl, authToken, pushId } = message.payload ?? {};
        if (!apiBaseUrl || !authToken || !pushId) {
          sendResponse({ ok: false, message: "Missing apiBaseUrl/authToken/pushId" });
          return;
        }
        const res = await apiRequest(apiBaseUrl, authToken, `/v1/pushes/${pushId}`);
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
        const { apiBaseUrl, authToken, query, workspaceId, includeTranscripts } = message.payload ?? {};
        if (!apiBaseUrl || !authToken || !query) {
          sendResponse({ ok: false, message: "Missing apiBaseUrl/authToken/query" });
          return;
        }
        const params = new URLSearchParams({
          q: String(query),
          limit: "20",
          include_transcripts: includeTranscripts ? "true" : "false"
        });
        if (workspaceId) params.set("workspace_id", String(workspaceId));
        const res = await apiRequest(apiBaseUrl, authToken, `/v1/search?${params.toString()}`);
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
        const { apiBaseUrl, authToken, selections } = message.payload ?? {};
        if (!apiBaseUrl || !authToken || !Array.isArray(selections) || selections.length === 0) {
          sendResponse({ ok: false, message: "Missing apiBaseUrl/authToken/selections" });
          return;
        }
        const res = await apiRequest(apiBaseUrl, authToken, "/v1/pulls", {
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
