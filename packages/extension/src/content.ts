// This content script runs inside a supported LLM chat webpage (Claude, ChatGPT,
// …). It owns the small in-page ContextHub launcher button, the sidebar iframe,
// conversation scraping, and injecting pulled context back into the page's prompt
// box.
//
// Everything platform-specific (host matching, message selectors, conversation-id
// parsing, and the prompt input element) lives in a PlatformAdapter. The rest of
// the script is platform-agnostic and drives whichever adapter matches the current
// page. Adding a new platform = adding one adapter to the ADAPTERS list.

// Stable DOM ids let the script find/remove its own UI and avoid creating
// duplicates if the script runs more than once.
const launcherId = "ctxh-launcher";
const sidebarHostId = "ctxh-sidebar-host";

// Source platforms we tag captured conversations with. Must stay in sync with the
// interchange schema enum (schemas/ch.v0.1.conversation.json) and SourcePlatform.
type Platform = "claude_ai" | "chatgpt" | "gemini";

// The normalized message shape we want after scraping a page's DOM.
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

// A PlatformAdapter encapsulates everything that differs between chat products.
// Content scripts cannot read a site's internal React state, so the DOM is the
// only available interface; each adapter is a thin map of that site's DOM shape.
type PlatformAdapter = {
  platform: Platform;
  // True when this adapter should drive the given page hostname.
  matchesHost: (hostname: string) => boolean;
  // Pull a native conversation id out of the page URL, if one is present.
  conversationId: (url: string) => string | undefined;
  // Find the DOM nodes that correspond to user/assistant messages, tagged with role.
  collectCandidates: (root: ParentNode) => CandidateMessage[];
  // Locate the prompt input element for context injection (textarea or contenteditable).
  findInput: () => HTMLElement | null;
};

// --- Claude (claude.ai) ----------------------------------------------------

const claudeAdapter: PlatformAdapter = {
  platform: "claude_ai",

  matchesHost: (hostname) => hostname === "claude.ai" || hostname === "www.claude.ai",

  // Claude conversation URLs look like /chat/<id>.
  conversationId: (url) => url.match(/\/chat\/([a-zA-Z0-9-]+)/)?.[1],

  collectCandidates: (root) => {
    const candidates: CandidateMessage[] = [];
    const seenNodes = new Set<Element>();

    const push = (role: CandidateMessage["role"], node: Element) => {
      if (seenNodes.has(node)) return;
      seenNodes.add(node);
      candidates.push({ role, node });
    };

    // Primary user-message selector used by Claude.
    for (const node of Array.from(root.querySelectorAll("[data-testid='user-message']"))) {
      push("user", node);
    }

    // Alternate user-message selector. If a nested user-message node exists,
    // prefer that over the larger bubble wrapper.
    for (const bubble of Array.from(root.querySelectorAll("[data-user-message-bubble='true']"))) {
      push("user", bubble.querySelector("[data-testid='user-message']") || bubble);
    }

    // Primary assistant content selector: the markdown content inside Claude's
    // assistant response wrapper.
    for (const node of Array.from(root.querySelectorAll(".font-claude-response .standard-markdown"))) {
      push("assistant", node);
    }

    // Broader assistant fallback: if the markdown node is absent, capture the
    // entire assistant response container.
    for (const node of Array.from(root.querySelectorAll(".font-claude-response"))) {
      push("assistant", node);
    }

    return candidates;
  },

  // Claude may use either a contenteditable div or a textarea depending on the
  // product surface/version, so support both.
  findInput: () =>
    (document.querySelector("div[contenteditable='true']") ||
      document.querySelector("textarea")) as HTMLElement | null
};

// --- ChatGPT (chatgpt.com / chat.openai.com) -------------------------------

const chatgptAdapter: PlatformAdapter = {
  platform: "chatgpt",

  matchesHost: (hostname) =>
    hostname === "chatgpt.com" ||
    hostname === "www.chatgpt.com" ||
    hostname === "chat.openai.com" ||
    hostname === "www.chat.openai.com",

  // ChatGPT conversation URLs look like /c/<id>.
  conversationId: (url) => url.match(/\/c\/([a-zA-Z0-9-]+)/)?.[1],

  // ChatGPT tags every turn's content node with data-message-author-role, which
  // is the cleanest and most stable hook available. The action bars, the
  // "Thought for…" reasoning toggle, and the "You said:/ChatGPT said:" labels all
  // live OUTSIDE these nodes (or are buttons/sr-only), so extractCleanText drops
  // them. The role attribute also includes "system"/"tool" turns, which we ignore.
  collectCandidates: (root) => {
    const candidates: CandidateMessage[] = [];
    const seenNodes = new Set<Element>();

    for (const node of Array.from(root.querySelectorAll("[data-message-author-role]"))) {
      const role = node.getAttribute("data-message-author-role");
      if (role !== "user" && role !== "assistant") continue;
      if (seenNodes.has(node)) continue;
      seenNodes.add(node);
      candidates.push({ role, node });
    }

    return candidates;
  },

  // ChatGPT's composer is a ProseMirror contenteditable with id "prompt-textarea".
  // Fall back to a generic contenteditable/textarea if the id ever changes.
  findInput: () =>
    (document.querySelector("#prompt-textarea") ||
      document.querySelector("div[contenteditable='true']") ||
      document.querySelector("textarea")) as HTMLElement | null
};

// --- Gemini (gemini.google.com) --------------------------------------------

const geminiAdapter: PlatformAdapter = {
  platform: "gemini",

  matchesHost: (hostname) => hostname === "gemini.google.com",

  // Gemini conversation URLs look like /app/<id>.
  conversationId: (url) => url.match(/\/app\/([a-zA-Z0-9_-]+)/)?.[1],

  // Gemini is an Angular app built from custom elements. User turns live in
  // <user-query-content> (the text in .query-text); model turns render markdown
  // inside <message-content> (.markdown-main-panel). Screen-reader labels use
  // .cdk-visually-hidden and footer controls are <button>/<mat-icon>, all of
  // which extractCleanText strips.
  collectCandidates: (root) => {
    const candidates: CandidateMessage[] = [];
    const seenNodes = new Set<Element>();

    const push = (role: CandidateMessage["role"], node: Element) => {
      if (seenNodes.has(node)) return;
      seenNodes.add(node);
      candidates.push({ role, node });
    };

    // Tight user-text selector, with the whole query container as a fallback.
    for (const node of Array.from(root.querySelectorAll("user-query .query-text"))) {
      push("user", node);
    }
    for (const node of Array.from(root.querySelectorAll("user-query-content"))) {
      push("user", node);
    }

    // Tight assistant-markdown selector, with the response container as a fallback.
    for (const node of Array.from(root.querySelectorAll("message-content .markdown-main-panel"))) {
      push("assistant", node);
    }
    for (const node of Array.from(root.querySelectorAll("model-response message-content"))) {
      push("assistant", node);
    }

    return candidates;
  },

  // Gemini's composer is a Quill-based contenteditable inside <rich-textarea>.
  findInput: () =>
    (document.querySelector("rich-textarea [contenteditable='true']") ||
      document.querySelector(".ql-editor[contenteditable='true']") ||
      document.querySelector("div[contenteditable='true']") ||
      document.querySelector("textarea")) as HTMLElement | null
};

const ADAPTERS: PlatformAdapter[] = [claudeAdapter, chatgptAdapter, geminiAdapter];

// Resolve the adapter for the current page, or null if ContextHub does not
// support this host. Computed lazily so we always reflect the live hostname.
function getActiveAdapter(): PlatformAdapter | null {
  const hostname = window.location.hostname;
  return ADAPTERS.find((adapter) => adapter.matchesHost(hostname)) ?? null;
}

// Remove the mounted sidebar iframe if it exists. This is used both before
// opening a fresh sidebar and when the launcher toggles the sidebar closed.
function removeExistingSidebar() {
  const existing = document.getElementById(sidebarHostId);
  if (existing) {
    existing.remove();
  }
}

// Create the right-side ContextHub sidebar. The sidebar UI itself lives in
// sidebar.html; this function only creates an iframe container inside the page.
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

// Add the floating "ContextHub" launcher button to the page. If the button is
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

// Convert a message DOM node into clean text. We clone the node first so removing
// buttons/icons/action bars does not mutate the real page.
function extractCleanText(node: Element): string {
  const clone = node.cloneNode(true) as Element;

  // These selectors are UI noise, not conversation content. They cover Claude,
  // ChatGPT, and Gemini chrome (action bars, copy/retry/edit controls, the
  // screen-reader "You said:"/"Gemini said" labels, canvas/writing-block toolbars,
  // Material icon glyphs, etc.). `.cdk-visually-hidden` is Angular CDK's
  // screen-reader-only class used by Gemini; `.sr-only` is the Claude/ChatGPT one.
  const noiseSelectors = [
    "button",
    "svg",
    "style",
    "script",
    ".sr-only",
    ".cdk-visually-hidden",
    "mat-icon",
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

// Produce ordered, deduplicated messages from the active adapter's candidates.
function scrapeMessages(adapter: PlatformAdapter): ScrapedMessage[] {
  const root: ParentNode = document.querySelector("main") ?? document;

  // Never scrape ContextHub's own UI as conversation content.
  const candidates = adapter
    .collectCandidates(root)
    .filter(({ node }) => !node.closest(`#${sidebarHostId}`) && !node.closest(`#${launcherId}`));

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

  // Last-resort fallback if a site changes its message selectors: scrape common
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

// Insert text into the page's prompt box. Both Claude and ChatGPT use ProseMirror
// contenteditable editors that reconcile their DOM from internal state, so simply
// assigning textContent is unreliable — they can wipe it or leave Send disabled.
// We prefer execCommand("insertText"), which flows through the editor's own
// beforeinput/input pipeline, and fall back to the textContent + InputEvent path.
function injectIntoInput(editable: HTMLElement, text: string): { ok: true; mode: string } {
  // Textareas need their value set and an input event fired so the page's UI
  // state updates as if a user typed the text.
  if (editable instanceof HTMLTextAreaElement) {
    editable.focus();
    editable.value = text;
    editable.dispatchEvent(new Event("input", { bubbles: true }));
    return { ok: true, mode: "textarea" };
  }

  editable.focus();
  const selection = window.getSelection();
  if (selection) {
    // Replace any existing content/placeholder so we do not append to a draft.
    selection.selectAllChildren(editable);
  }
  const inserted = document.execCommand("insertText", false, text);
  if (inserted) {
    return { ok: true, mode: "contenteditable:insertText" };
  }

  // Fallback for browsers/editors where execCommand is unavailable.
  editable.textContent = text;
  editable.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
  return { ok: true, mode: "contenteditable" };
}

// Main message bridge from the extension/background/sidebar into the page.
// Returning true is not needed here because the responses are synchronous.
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "ctxh:capture") {
    const adapter = getActiveAdapter();
    if (!adapter) {
      sendResponse({ ok: false, message: "ContextHub does not support this page." });
      return;
    }

    const pageUrl = window.location.href;
    const pageTitle = document.title;
    const scrapedMessages = scrapeMessages(adapter);
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
        platform: adapter.platform,
        conversation_id: adapter.conversationId(pageUrl),
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
      platform: adapter.platform,
      pageTitle,
      pageUrl,
      messageCount: conversation.messages.length,
      previewText: scrapedMessages[0]?.text?.slice(0, 200) || "",
      conversation
    });
    return;
  }

  if (message?.type === "ctxh:inject") {
    const adapter = getActiveAdapter();
    if (!adapter) {
      sendResponse({ ok: false, message: "ContextHub does not support this page." });
      return;
    }

    const text = String(message?.text || "");
    const editable = adapter.findInput();
    if (!editable) {
      sendResponse({ ok: false, message: "Could not find the chat input element." });
      return;
    }

    sendResponse(injectIntoInput(editable, text));
    return;
  }
});

// Entry point. If the body exists, install the launcher immediately; otherwise
// wait until DOMContentLoaded so document.body is available. We only activate on
// hosts a PlatformAdapter claims, even though the manifest already restricts
// matches — this guard prevents accidental UI injection if the script ever runs
// elsewhere.
function start() {
  if (!getActiveAdapter()) {
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
