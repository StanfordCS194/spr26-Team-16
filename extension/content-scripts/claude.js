// ============================================================
// ContextHub: Claude.ai Conversation Scraper
// ============================================================
// Primary: Fetches conversation data via Claude's internal API
//   (reliable, returns structured JSON with full message content)
// Fallback: DOM scraping with multiple selector strategies
//   (less reliable, used if API approach fails)
// ============================================================

async function scrapeConversation() {
  const url = window.location.href;

  if (!url.includes("/chat/")) {
    return { error: "Not on a conversation page. Open a Claude conversation first.", url };
  }

  // Extract conversation ID from URL: /chat/{uuid}
  const match = url.match(/\/chat\/([a-f0-9-]+)/);
  if (!match) {
    return { error: "Could not find conversation ID in URL.", url };
  }
  const conversationId = match[1];

  // Try API-based extraction first (preferred)
  try {
    const result = await scrapeViaAPI(conversationId, url);
    if (result.messages.length > 0) return result;
  } catch (e) {
    console.log("ContextHub: API scrape failed, trying DOM fallback:", e.message);
  }

  // Fallback to DOM-based extraction
  return scrapeViaDOM(url);
}


// ============================================================
// STRATEGY 1: Claude Internal API
// ============================================================

async function scrapeViaAPI(conversationId, pageUrl) {
  const orgId = await getOrganizationId();

  const apiUrl = `https://claude.ai/api/organizations/${orgId}/chat_conversations/${conversationId}?tree=True&rendering_mode=messages&render_all_tools=true`;
  const response = await fetch(apiUrl, {
    credentials: "include",
    headers: { "Accept": "application/json" },
  });

  if (!response.ok) {
    throw new Error(`API returned ${response.status}`);
  }

  const data = await response.json();

  if (!data.chat_messages || !Array.isArray(data.chat_messages)) {
    throw new Error("Invalid conversation data: missing chat_messages");
  }

  const messages = extractMessagesFromTree(data);

  return {
    source: "claude",
    url: pageUrl,
    scraped_at: new Date().toISOString(),
    messages: messages,
  };
}

async function getOrganizationId() {
  const resp = await fetch("https://claude.ai/api/organizations", {
    credentials: "include",
    headers: { "Accept": "application/json" },
  });
  if (!resp.ok) {
    throw new Error(`Could not fetch organizations (${resp.status})`);
  }
  const orgs = await resp.json();
  if (!Array.isArray(orgs) || orgs.length === 0) {
    throw new Error("No organizations found");
  }
  return orgs[0].uuid;
}

function extractMessagesFromTree(data) {
  // Build lookup map
  const byId = {};
  for (const msg of data.chat_messages) {
    byId[msg.uuid] = msg;
  }

  // Walk from leaf to root, then reverse to get chronological order
  const leafId = data.current_leaf_message_uuid;
  const chain = [];
  let current = byId[leafId];

  while (current) {
    chain.unshift(current);
    current = current.parent_message_uuid
      ? byId[current.parent_message_uuid]
      : null;
  }

  // Convert to {role, content} format
  return chain
    .map((msg) => {
      const role = msg.sender === "human" ? "user" : "assistant";

      let content = "";
      if (msg.content && Array.isArray(msg.content)) {
        // Modern format: content is an array of blocks
        content = msg.content
          .filter((block) => block.type === "text")
          .map((block) => block.text || "")
          .join("\n");
      } else if (msg.text) {
        // Legacy format: plain text field
        content = msg.text;
      }

      return { role, content };
    })
    .filter((msg) => msg.content.trim().length > 0);
}


// ============================================================
// STRATEGY 2: DOM Scraping Fallback
// ============================================================

function scrapeViaDOM(url) {
  const messages = [];

  // Try data-testid attributes (claude.ai web)
  let elements = document.querySelectorAll('[data-testid*="message"]');

  // Try class-based selectors
  if (elements.length === 0) {
    elements = document.querySelectorAll(
      '.font-user-message, .font-claude-response, [class*="font-user"], [class*="font-claude"]'
    );
  }

  // Try generic message container patterns
  if (elements.length === 0) {
    elements = document.querySelectorAll('[class*="Message"], [class*="message-"]');
  }

  for (const el of elements) {
    let role = null;

    const testId = el.getAttribute("data-testid") || "";
    const classes = el.className || "";

    if (
      testId.includes("human") || testId.includes("user") ||
      classes.includes("font-user") || classes.includes("human")
    ) {
      role = "user";
    } else if (
      testId.includes("assistant") || testId.includes("claude") ||
      classes.includes("font-claude") || classes.includes("assistant")
    ) {
      role = "assistant";
    }

    if (!role) continue;

    const content = el.innerText.trim();
    if (!content) continue;

    messages.push({ role, content });
  }

  return {
    source: "claude",
    url: url,
    scraped_at: new Date().toISOString(),
    messages: messages,
  };
}


// ============================================================
// Input Field Injection (Pull into Chat)
// ============================================================

function findInputField() {
  const selectors = [
    '[data-testid="composer-input"]',
    '.ProseMirror[contenteditable="true"]',
    'div[contenteditable="true"]',
    'textarea',
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

function injectIntoInput(text) {
  const input = findInputField();
  if (!input) {
    return { success: false, error: "Could not find chat input field" };
  }

  try {
    input.focus();

    if (input.tagName === "TEXTAREA") {
      input.value = text;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      // ProseMirror contenteditable — set content as <p> elements
      const paragraphs = text.split("\n").map((line) => {
        const p = document.createElement("p");
        p.textContent = line;
        return p;
      });
      input.innerHTML = "";
      paragraphs.forEach((p) => input.appendChild(p));

      // Dispatch InputEvent to sync React/ProseMirror state
      input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText" }));
    }

    // Move cursor to end
    const selection = window.getSelection();
    selection.selectAllChildren(input);
    selection.collapseToEnd();

    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

function findSendButton() {
  const selectors = [
    '[data-testid="send-button"]',
    'button[aria-label="Send Message"]',
    'button[aria-label*="Send"]',
    'form button[type="submit"]',
  ];
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && !el.disabled) return el;
  }
  return null;
}

async function injectAndSend(text) {
  const injectResult = injectIntoInput(text);
  if (!injectResult.success) return injectResult;

  // Wait for React/ProseMirror state to sync
  await new Promise((resolve) => setTimeout(resolve, 100));

  try {
    const sendBtn = findSendButton();
    if (sendBtn) {
      sendBtn.click();
      return { success: true, sent: true };
    }

    // Fallback: dispatch Enter keypress on the input field
    const input = findInputField();
    if (input) {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
      return { success: true, sent: true };
    }

    return { success: false, error: "Could not find send button or input field" };
  } catch (err) {
    return { success: false, error: err.message };
  }
}


// ============================================================
// Memory Writing (Pull into Memory)
// ============================================================

async function writeMemoryItems(items) {
  try {
    const orgId = await getOrganizationId();
    let count = 0;

    for (const item of items) {
      const response = await fetch(
        `https://claude.ai/api/organizations/${orgId}/user/memories`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ content: item.content }),
        }
      );

      if (!response.ok) {
        throw new Error(`Memory API returned ${response.status}`);
      }

      count++;
      // Small delay between writes to avoid rate limits
      if (count < items.length) {
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
    }

    return { success: true, count };
  } catch (err) {
    return { success: false, error: err.message };
  }
}

async function clearContextHubMemories(title) {
  try {
    const orgId = await getOrganizationId();
    const prefix = `[ContextHub: ${title}]`;

    // List all memories
    const listResponse = await fetch(
      `https://claude.ai/api/organizations/${orgId}/user/memories`,
      {
        credentials: "include",
        headers: { "Accept": "application/json" },
      }
    );

    if (!listResponse.ok) {
      throw new Error(`Failed to list memories (${listResponse.status})`);
    }

    const memories = await listResponse.json();

    // Filter for ContextHub memories matching this title
    const toDelete = (memories || []).filter(
      (m) => m.content && m.content.startsWith(prefix)
    );

    // Delete each matching memory
    for (const memory of toDelete) {
      await fetch(
        `https://claude.ai/api/organizations/${orgId}/user/memories/${memory.uuid}`,
        {
          method: "DELETE",
          credentials: "include",
          headers: { "Accept": "application/json" },
        }
      );
      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    return { success: true, deleted: toDelete.length };
  } catch (err) {
    return { success: false, error: err.message };
  }
}


// ============================================================
// Message Listener
// ============================================================

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "scrape") {
    scrapeConversation()
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ error: err.message }));
    return true; // Keep channel open for async response
  }

  if (request.action === "inject_context") {
    injectAndSend(request.text)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // Keep channel open for async response
  }

  if (request.action === "inject_memory") {
    (async () => {
      // Clear existing memories for this thread title first
      await clearContextHubMemories(request.title);

      // Write new memory items
      const items = request.items.map((text) => ({ content: text }));
      const result = await writeMemoryItems(items);
      sendResponse(result);
    })().catch((err) => sendResponse({ success: false, error: err.message }));
    return true; // Keep channel open for async response
  }
});
