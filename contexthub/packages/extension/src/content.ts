const launcherId = "ctxh-launcher";
const sidebarHostId = "ctxh-sidebar-host";

type ScrapedMessage = {
  role: "user" | "assistant";
  text: string;
};

type CandidateMessage = {
  role: "user" | "assistant";
  node: Element;
};

type SupportedPlatform = "claude_ai" | "chatgpt";

const CHATGPT_HOSTS = new Set(["chatgpt.com", "www.chatgpt.com", "chat.openai.com"]);

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
  iframe.title = "ContextHub Sidebar";
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

function detectPlatformFromHost(hostname: string): SupportedPlatform | null {
  if (hostname === "claude.ai" || hostname === "www.claude.ai") {
    return "claude_ai";
  }
  if (CHATGPT_HOSTS.has(hostname)) {
    return "chatgpt";
  }
  return null;
}

function extractConversationId(url: string, platform: SupportedPlatform): string | undefined {
  if (platform === "claude_ai") {
    return url.match(/\/chat\/([a-zA-Z0-9-]+)/)?.[1];
  }
  return (
    url.match(/\/c\/([a-zA-Z0-9-]+)/)?.[1] ||
    url.match(/\/share\/([a-zA-Z0-9-]+)/)?.[1]
  );
}

function extractCleanText(node: Element): string {
  const clone = node.cloneNode(true) as Element;
  const noiseSelectors = [
    "button",
    "svg",
    "style",
    "script",
    ".sr-only",
    "[aria-hidden='true']",
    "[role='group'][aria-label='Message actions']",
    "[data-testid='action-bar-copy']",
    "[data-testid='action-bar-retry']",
    "[data-is-streaming='true']"
  ];
  for (const selector of noiseSelectors) {
    clone.querySelectorAll(selector).forEach((el) => el.remove());
  }
  return (clone.textContent || "")
    .replace(/\s+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function collectClaudeCandidates(root: ParentNode): CandidateMessage[] {
  const candidates: CandidateMessage[] = [];
  const seenNodes = new Set<Element>();

  const userContentNodes = Array.from(root.querySelectorAll("[data-testid='user-message']"));
  for (const node of userContentNodes) {
    if (seenNodes.has(node)) continue;
    seenNodes.add(node);
    candidates.push({ role: "user", node });
  }

  const userBubbleNodes = Array.from(root.querySelectorAll("[data-user-message-bubble='true']"));
  for (const bubble of userBubbleNodes) {
    const contentNode = bubble.querySelector("[data-testid='user-message']") || bubble;
    if (seenNodes.has(contentNode)) continue;
    seenNodes.add(contentNode);
    candidates.push({ role: "user", node: contentNode });
  }

  const assistantMarkdownNodes = Array.from(root.querySelectorAll(".font-claude-response .standard-markdown"));
  for (const node of assistantMarkdownNodes) {
    if (seenNodes.has(node)) continue;
    seenNodes.add(node);
    candidates.push({ role: "assistant", node });
  }

  const assistantContainerNodes = Array.from(root.querySelectorAll(".font-claude-response"));
  for (const node of assistantContainerNodes) {
    if (seenNodes.has(node)) continue;
    seenNodes.add(node);
    candidates.push({ role: "assistant", node });
  }

  return candidates;
}

function collectChatgptCandidates(root: ParentNode): CandidateMessage[] {
  const candidates: CandidateMessage[] = [];
  const seenNodes = new Set<Element>();

  const turnNodes = Array.from(root.querySelectorAll("section[data-turn]"));
  for (const turn of turnNodes) {
    const roleAttr = turn.getAttribute("data-turn");
    if (roleAttr !== "user" && roleAttr !== "assistant") continue;
    const role = roleAttr as "user" | "assistant";
    const primaryNode = turn.querySelector(`[data-message-author-role='${role}']`) || turn;
    if (seenNodes.has(primaryNode)) continue;
    seenNodes.add(primaryNode);
    candidates.push({ role, node: primaryNode });
  }

  if (!candidates.length) {
    const roleNodes = Array.from(root.querySelectorAll("[data-message-author-role='user'], [data-message-author-role='assistant']"));
    for (const node of roleNodes) {
      const roleAttr = node.getAttribute("data-message-author-role");
      if (roleAttr !== "user" && roleAttr !== "assistant") continue;
      if (seenNodes.has(node)) continue;
      seenNodes.add(node);
      candidates.push({ role: roleAttr, node });
    }
  }

  return candidates;
}

function collectCandidates(platform: SupportedPlatform): CandidateMessage[] {
  const root: ParentNode = document.querySelector("main") ?? document;
  const candidates = platform === "chatgpt" ? collectChatgptCandidates(root) : collectClaudeCandidates(root);
  return candidates.filter(({ node }) => !node.closest(`#${sidebarHostId}`) && !node.closest(`#${launcherId}`));
}

function scrapeMessages(platform: SupportedPlatform): ScrapedMessage[] {
  const candidates = collectCandidates(platform);
  const sorted = candidates.sort((a, b) => {
    const rel = a.node.compareDocumentPosition(b.node);
    if (rel & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
    if (rel & Node.DOCUMENT_POSITION_PRECEDING) return 1;
    return 0;
  });
  const scraped = sorted
    .map(({ role, node }) => ({ role, text: extractCleanText(node) }))
    .filter((item) => item.text.length > 0);

  if (scraped.length > 0) {
    const stableDeduped: ScrapedMessage[] = [];
    const seen = new Set<string>();
    for (const message of scraped) {
      const key = `${message.role}::${message.text}`;
      if (seen.has(key)) continue;
      seen.add(key);
      stableDeduped.push(message);
    }
    return stableDeduped;
  }

  // Fallback: try common markdown/message blocks and alternate roles.
  const genericNodes = Array.from(document.querySelectorAll("main p, main pre, main li, main h1, main h2, main h3"));
  const chunks = genericNodes
    .map((node) => (node.textContent || "").trim())
    .filter((text) => text.length > 0)
    .slice(0, 80);
  if (!chunks.length) return [];
  const stitched = chunks.join("\n").trim();
  if (!stitched) return [];
  return [{ role: "assistant", text: stitched }];
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "ctxh:capture") {
    const platform = detectPlatformFromHost(window.location.hostname);
    if (!platform) {
      sendResponse({
        ok: false,
        message: "Unsupported host. Open Claude or ChatGPT before capturing."
      });
      return;
    }
    const pageUrl = window.location.href;
    const pageTitle = document.title;
    const scrapedMessages = scrapeMessages(platform);
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
        platform,
        conversation_id: extractConversationId(pageUrl, platform),
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
    const platform = detectPlatformFromHost(window.location.hostname);
    const editable = (
      (platform === "chatgpt"
        ? document.querySelector("form #prompt-textarea") ||
          document.querySelector("textarea[data-testid='prompt-textarea']") ||
          document.querySelector("textarea[placeholder*='Message']") ||
          document.querySelector("#prompt-textarea")
        : document.querySelector("div[contenteditable='true']") || document.querySelector("textarea")) as HTMLElement | null
    );
    if (!editable) {
      sendResponse({ ok: false, message: "Could not find chat input element" });
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

function isSupportedHost() {
  return detectPlatformFromHost(window.location.hostname) !== null;
}

function start() {
  if (!isSupportedHost()) {
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
