chrome.runtime.onInstalled.addListener(() => {
  console.info("[ContextHub Demo] extension installed");
});

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

        const base = String(apiBaseUrl).replace(/\/+$/, "");
        const url = `${base}/v1/workspaces/${workspaceId}/pushes`;

        const res = await fetch(url, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${authToken}`,
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey || `ext-${Date.now()}`
          },
          body: JSON.stringify(conversation)
        });

        const requestId = res.headers.get("X-Request-Id");
        const text = await res.text();

        if (!res.ok) {
          sendResponse({ ok: false, message: `HTTP ${res.status}: ${text}`, requestId });
          return;
        }

        sendResponse({ ok: true, data: JSON.parse(text), requestId });
      } catch (err) {
        sendResponse({ ok: false, message: err instanceof Error ? err.message : "Unknown error" });
      }
    })();
    return true;
  }

  return false;
});
