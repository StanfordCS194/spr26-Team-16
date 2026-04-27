chrome.runtime.onInstalled.addListener(() => {
  console.info("[ContextHub Demo] extension installed");
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "ctxh:sidebar:opened") {
    sendResponse({ ok: true, status: "connected", tokenState: "demo-active" });
    return true;
  }

  if (message?.type === "ctxh:mock:push") {
    sendResponse({ ok: true, queued: true });
    return true;
  }

  return false;
});
