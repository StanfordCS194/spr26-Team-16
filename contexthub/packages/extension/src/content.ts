const launcherId = "ctxh-demo-launcher";
const sidebarHostId = "ctxh-demo-sidebar-host";

type ScrapedMessage = {
  role: "user" | "assistant";
  text: string;
};

function removeExistingSidebar() {
  const existing = document.getElementById(sidebarHostId);
  if (existing) {
    existing.remove();
  }
}

function mountSidebar() {
  removeExistingSidebar();

  const host = document.createElement("div");
  host.id = sidebarHostId;
  host.style.position = "fixed";
  host.style.top = "0";
  host.style.right = "0";
  host.style.width = "420px";
  host.style.height = "100vh";
  host.style.zIndex = "2147483646";
  host.style.boxShadow = "rgba(7, 14, 28, 0.55) 0 0 0 1px, rgba(7, 14, 28, 0.7) 0 18px 48px";

  const iframe = document.createElement("iframe");
  iframe.title = "ContextHub Demo Sidebar";
  iframe.src = chrome.runtime.getURL("sidebar.html");
  iframe.style.width = "100%";
  iframe.style.height = "100%";
  iframe.style.border = "0";
  iframe.style.background = "#0e1730";

  host.appendChild(iframe);
  document.body.appendChild(host);

  chrome.runtime.sendMessage({ type: "ctxh:sidebar:opened" });
}

function ensureLauncher() {
  if (document.getElementById(launcherId)) {
    return;
  }

  const launcher = document.createElement("button");
  launcher.id = launcherId;
  launcher.textContent = "ContextHub";
  launcher.style.position = "fixed";
  launcher.style.right = "16px";
  launcher.style.bottom = "16px";
  launcher.style.padding = "10px 14px";
  launcher.style.border = "none";
  launcher.style.borderRadius = "999px";
  launcher.style.background = "#3558c9";
  launcher.style.color = "white";
  launcher.style.fontWeight = "700";
  launcher.style.cursor = "pointer";
  launcher.style.zIndex = "2147483647";
  launcher.style.boxShadow = "0 8px 24px rgba(12, 24, 56, 0.5)";

  launcher.addEventListener("click", () => {
    const host = document.getElementById(sidebarHostId);
    if (host) {
      host.remove();
      return;
    }
    mountSidebar();
  });

  document.body.appendChild(launcher);
}

function extractConversationId(url: string): string | undefined {
  const match = url.match(/\/chat\/([a-zA-Z0-9-]+)/);
  return match?.[1];
}

function inferRole(node: Element): "user" | "assistant" | null {
  const attrs = [
    node.getAttribute("data-message-author-role"),
    node.getAttribute("data-author-role"),
    node.getAttribute("data-role"),
    node.getAttribute("aria-label")
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const classes = (node.getAttribute("class") || "").toLowerCase();
  const blob = `${attrs} ${classes}`;
  if (blob.includes("assistant") || blob.includes("claude")) return "assistant";
  if (blob.includes("user") || blob.includes("human")) return "user";
  return null;
}

function collectMessageNodes(): Element[] {
  const selectors = [
    "[data-message-author-role]",
    "[data-author-role]",
    "article[data-testid*='message']",
    "div[data-testid*='message']",
    "article",
    "main article"
  ];
  const all = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
  const deduped = Array.from(new Set(all));
  return deduped.filter((node) => {
    if (node.closest(`#${sidebarHostId}`)) return false;
    const text = (node.textContent || "").trim();
    return text.length > 0;
  });
}

function scrapeMessages(): ScrapedMessage[] {
  const nodes = collectMessageNodes();
  const scraped: ScrapedMessage[] = [];
  for (const node of nodes) {
    const role = inferRole(node);
    if (!role) continue;
    const text = (node.textContent || "").trim();
    if (!text) continue;
    scraped.push({ role, text });
  }

  if (scraped.length > 0) return scraped;

  // Fallback: try common markdown/message blocks and alternate roles.
  const genericNodes = Array.from(document.querySelectorAll("main p, main pre, main li, main h1, main h2, main h3"));
  const chunks = genericNodes
    .map((node) => (node.textContent || "").trim())
    .filter((text) => text.length > 0)
    .slice(0, 80);
  if (!chunks.length) return [];
  const stitched = chunks.join("\n").trim();
  if (!stitched) return [];
  return [{ role: "user", text: stitched }];
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "ctxh:capture") {
    const pageUrl = window.location.href;
    const pageTitle = document.title;
    const scrapedMessages = scrapeMessages();
    if (!scrapedMessages.length) {
      sendResponse({
        ok: false,
        message: "Could not scrape conversation messages from the current page."
      });
      return;
    }
    const conversation = {
      spec_version: "ch.v0.1" as const,
      source: {
        platform: "claude_ai" as const,
        conversation_id: extractConversationId(pageUrl),
        url: pageUrl,
        captured_at: new Date().toISOString()
      },
      messages: scrapedMessages.map((msg) => ({
        role: msg.role,
        content: [{ type: "text" as const, text: msg.text }]
      })),
      metadata: {
        title: pageTitle
      }
    };

    sendResponse({
      ok: true,
      pageTitle,
      pageUrl,
      messageCount: conversation.messages.length,
      previewText: scrapedMessages[0]?.text?.slice(0, 200) || "",
      conversation
    });
    return;
  }

  if (message?.type === "ctxh:inject") {
    const text = String(message?.text || "");
    const editable = (document.querySelector("div[contenteditable='true']") ||
      document.querySelector("textarea")) as HTMLElement | null;
    if (!editable) {
      sendResponse({ ok: false, message: "Could not find Claude input element" });
      return;
    }

    if (editable instanceof HTMLTextAreaElement) {
      editable.focus();
      editable.value = text;
      editable.dispatchEvent(new Event("input", { bubbles: true }));
      sendResponse({ ok: true, mode: "textarea" });
      return;
    }

    editable.focus();
    editable.textContent = text;
    editable.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
    sendResponse({ ok: true, mode: "contenteditable" });
    return;
  }
});

function isClaudeHost() {
  return window.location.hostname === "claude.ai" || window.location.hostname === "www.claude.ai";
}

function start() {
  if (!isClaudeHost()) {
    return;
  }

  if (document.body) {
    ensureLauncher();
    return;
  }

  window.addEventListener(
    "DOMContentLoaded",
    () => {
      ensureLauncher();
    },
    { once: true }
  );
}

start();
