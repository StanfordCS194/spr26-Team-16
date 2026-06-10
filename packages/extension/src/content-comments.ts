// This content script runs inside the Claude webpage. It owns the small
// in-page ContextHub launcher button, the sidebar iframe, conversation scraping,
// and injecting pulled context back into Claude's prompt box.

// Stable DOM ids let the script find/remove its own UI and avoid creating
// duplicates if the script runs more than once.
const launcherId = "ctxh-launcher";
const sidebarHostId = "ctxh-sidebar-host";

// The normalized message shape we want after scraping Claude's DOM.
type ScrapedMessage = {
  role: "user" | "assistant";
  text: string;
};

// Intermediate scrape candidate: a DOM node plus the role we believe it
// represents. Later we clean the node's text and sort candidates by page order.
type CandidateMessage = {
  role: "user" | "assistant";
  node: Element;
};

// Remove the mounted sidebar iframe if it exists. This is used both before
// opening a fresh sidebar and when the launcher toggles the sidebar closed.
function removeExistingSidebar() {
  const existing = document.getElementById(sidebarHostId);
  if (existing) {
    existing.remove();
  }
}

// Create the right-side ContextHub sidebar. The sidebar UI itself lives in
// sidebar.html; this function only creates an iframe container inside Claude.
function mountSidebar() {
  removeExistingSidebar();

  // The host is a fixed-position wrapper attached directly to the page.
  const host = document.createElement("div");
  host.id = sidebarHostId;
  host.style.position = "fixed";
  host.style.top = "0";
  host.style.right = "0";
  host.style.width = "420px";
  host.style.height = "100vh";
  host.style.zIndex = "2147483646";
  host.style.boxShadow = "rgba(7, 14, 28, 0.55) 0 0 0 1px, rgba(7, 14, 28, 0.7) 0 18px 48px";

  // Load the extension's sidebar page inside the host. chrome.runtime.getURL
  // converts "sidebar.html" into a chrome-extension:// URL.
  const iframe = document.createElement("iframe");
  iframe.title = "ContextHub Sidebar";
  iframe.src = chrome.runtime.getURL("sidebar.html");
  iframe.style.width = "100%";
  iframe.style.height = "100%";
  iframe.style.border = "0";
  iframe.style.background = "#0e1730";

  host.appendChild(iframe);
  document.body.appendChild(host);

  // Notify the background script/sidebar plumbing that the iframe is mounted.
  chrome.runtime.sendMessage({ type: "ctxh:sidebar:opened" });
}

// Add the floating "ContextHub" launcher button to Claude. If the button is
// already present, do nothing so reloads/re-injection do not duplicate it.
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

  // The launcher acts as a toggle: close the sidebar if it is open, otherwise
  // mount a new sidebar iframe.
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

// Try to pull Claude's conversation id out of URLs like /chat/<id>. If the URL
// shape changes or there is no match, this returns undefined and capture still
// works without a native conversation id.
function extractConversationId(url: string): string | undefined {
  const match = url.match(/\/chat\/([a-zA-Z0-9-]+)/);
  return match?.[1];
}

// Convert a Claude message DOM node into clean text. We clone the node first so
// removing buttons/icons/action bars does not mutate the real page.
function extractCleanText(node: Element): string {
  const clone = node.cloneNode(true) as Element;

  // These selectors are UI noise, not conversation content.
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

  // Normalize whitespace so the backend receives readable message text instead
  // of DOM-layout spacing.
  return (clone.textContent || "")
    .replace(/\s+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

// Find DOM nodes that likely correspond to Claude user/assistant messages.
// This function is intentionally selector-based because content scripts cannot
// access Claude's internal React state; the DOM is the available interface.
function collectCandidates(): CandidateMessage[] {
  const root: ParentNode = document.querySelector("main") ?? document;
  const candidates: CandidateMessage[] = [];
  const seenNodes = new Set<Element>();

  // Primary user-message selector used by Claude.
  const userContentNodes = Array.from(root.querySelectorAll("[data-testid='user-message']"));
  for (const node of userContentNodes) {
    if (seenNodes.has(node)) continue;
    seenNodes.add(node);
    candidates.push({ role: "user", node });
  }

  // Alternate user-message selector. If a nested user-message node exists,
  // prefer that over the larger bubble wrapper.
  const userBubbleNodes = Array.from(root.querySelectorAll("[data-user-message-bubble='true']"));
  for (const bubble of userBubbleNodes) {
    const contentNode = bubble.querySelector("[data-testid='user-message']") || bubble;
    if (seenNodes.has(contentNode)) continue;
    seenNodes.add(contentNode);
    candidates.push({ role: "user", node: contentNode });
  }

  // Primary assistant content selector: the markdown content inside Claude's
  // assistant response wrapper.
  const assistantMarkdownNodes = Array.from(root.querySelectorAll(".font-claude-response .standard-markdown"));
  for (const node of assistantMarkdownNodes) {
    if (seenNodes.has(node)) continue;
    seenNodes.add(node);
    candidates.push({ role: "assistant", node });
  }

  // Broader assistant fallback: if the markdown node is absent, capture the
  // entire assistant response container.
  const assistantContainerNodes = Array.from(root.querySelectorAll(".font-claude-response"));
  for (const node of assistantContainerNodes) {
    if (seenNodes.has(node)) continue;
    seenNodes.add(node);
    candidates.push({ role: "assistant", node });
  }

  // Never scrape ContextHub's own UI as conversation content.
  return candidates.filter(({ node }) => !node.closest(`#${sidebarHostId}`) && !node.closest(`#${launcherId}`));
}

// Produce ordered, deduplicated messages from the candidate DOM nodes.
function scrapeMessages(): ScrapedMessage[] {
  const candidates = collectCandidates();

  // DOM queries do not guarantee the final order we want, so explicitly sort by
  // document position before turning nodes into text.
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
    // Some selectors overlap, so the same visible message may be found more
    // than once. Deduplicate by role + exact text while keeping first-seen order.
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

  // Last-resort fallback if Claude changes the message selectors: scrape common
  // text/markdown elements from main. Role accuracy is weaker here, so the whole
  // stitched block is returned as assistant text rather than pretending we know
  // the true turn boundaries.
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

// Main message bridge from the extension/background/sidebar into the page.
// Returning true is not needed here because the responses are synchronous.
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

    // Shape the scraped DOM text into the portable ContextHub interchange
    // format expected by the backend.
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

    // Return both metadata for UI preview and the full conversation object for
    // the background script to push to the backend.
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

    // Claude may use either a contenteditable div or a textarea depending on
    // the product surface/version, so support both.
    const editable = (document.querySelector("div[contenteditable='true']") ||
      document.querySelector("textarea")) as HTMLElement | null;
    if (!editable) {
      sendResponse({ ok: false, message: "Could not find Claude input element" });
      return;
    }

    // Textareas need their value set and an input event fired so the page's UI
    // state updates as if a user typed the text.
    if (editable instanceof HTMLTextAreaElement) {
      editable.focus();
      editable.value = text;
      editable.dispatchEvent(new Event("input", { bubbles: true }));
      sendResponse({ ok: true, mode: "textarea" });
      return;
    }

    // contenteditable inputs use textContent plus an InputEvent for the same
    // reason: Claude's frontend needs to observe the change.
    editable.focus();
    editable.textContent = text;
    editable.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
    sendResponse({ ok: true, mode: "contenteditable" });
    return;
  }
});

// Restrict activation to Claude. The manifest may also restrict matches, but
// this guard prevents accidental UI injection if the script ever runs elsewhere.
function isClaudeHost() {
  return window.location.hostname === "claude.ai" || window.location.hostname === "www.claude.ai";
}

// Entry point. If the body exists, install the launcher immediately; otherwise
// wait until DOMContentLoaded so document.body is available.
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

export {};
