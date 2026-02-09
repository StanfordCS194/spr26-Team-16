// ============================================================
// ContextHub: ChatGPT Conversation Scraper
// ============================================================
// Primary: Fetches conversation data via ChatGPT's internal API
//   (reliable, returns structured JSON with full message content)
// Fallback: DOM scraping with ChatGPT-specific selectors
//   (less reliable, used if API approach fails)
// ============================================================

async function scrapeConversation() {
  const url = window.location.href;

  if (!url.includes("/c/")) {
    return { error: "Not on a conversation page. Open a ChatGPT conversation first.", url };
  }

  // Extract conversation ID from URL: /c/{conversation_id}
  const match = url.match(/\/c\/([a-f0-9-]+)/);
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
// STRATEGY 1: ChatGPT Internal API
// ============================================================

async function scrapeViaAPI(conversationId, pageUrl) {
  const apiUrl = `https://chatgpt.com/backend-api/conversation/${conversationId}`;
  const response = await fetch(apiUrl, {
    credentials: "include",
    headers: { "Accept": "application/json" },
  });

  if (!response.ok) {
    throw new Error(`API returned ${response.status}`);
  }

  const data = await response.json();

  if (!data.mapping || !data.current_node) {
    throw new Error("Invalid conversation data: missing mapping or current_node");
  }

  const messages = extractMessagesFromMapping(data);

  return {
    source: "chatgpt",
    url: pageUrl,
    scraped_at: new Date().toISOString(),
    messages: messages,
  };
}

function extractMessagesFromMapping(data) {
  const mapping = data.mapping;

  // Walk from current_node backwards via parent to build message chain
  const chain = [];
  let nodeId = data.current_node;

  while (nodeId && mapping[nodeId]) {
    const node = mapping[nodeId];
    if (node.message && node.message.author && node.message.content) {
      const role = node.message.author.role;
      // Skip system messages
      if (role === "user" || role === "assistant") {
        const parts = node.message.content.parts || [];
        const content = parts
          .filter((p) => typeof p === "string")
          .join("\n");
        if (content.trim().length > 0) {
          chain.unshift({ role, content });
        }
      }
    }
    nodeId = node.parent;
  }

  return chain;
}


// ============================================================
// STRATEGY 2: DOM Scraping Fallback
// ============================================================

function scrapeViaDOM(url) {
  const messages = [];

  // ChatGPT uses data-message-author-role attributes
  const userElements = document.querySelectorAll('[data-message-author-role="user"]');
  const assistantElements = document.querySelectorAll('[data-message-author-role="assistant"]');

  // Collect all message elements with their positions for ordering
  const allElements = [];

  for (const el of userElements) {
    allElements.push({ el, role: "user" });
  }
  for (const el of assistantElements) {
    allElements.push({ el, role: "assistant" });
  }

  // Sort by DOM order
  allElements.sort((a, b) => {
    const pos = a.el.compareDocumentPosition(b.el);
    if (pos & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
    if (pos & Node.DOCUMENT_POSITION_PRECEDING) return 1;
    return 0;
  });

  for (const { el, role } of allElements) {
    const content = el.innerText.trim();
    if (!content) continue;
    messages.push({ role, content });
  }

  return {
    source: "chatgpt",
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
    '#prompt-textarea',
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
      // contenteditable — set content as <p> elements
      const paragraphs = text.split("\n").map((line) => {
        const p = document.createElement("p");
        p.textContent = line;
        return p;
      });
      input.innerHTML = "";
      paragraphs.forEach((p) => input.appendChild(p));

      // Dispatch InputEvent to sync React state
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
    'button[aria-label="Send prompt"]',
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

  // Wait for React state to sync
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
    let count = 0;

    for (const item of items) {
      const response = await fetch(
        "https://chatgpt.com/backend-api/memories",
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
    const prefix = `[ContextHub: ${title}]`;

    // List all memories
    const listResponse = await fetch(
      "https://chatgpt.com/backend-api/memories",
      {
        credentials: "include",
        headers: { "Accept": "application/json" },
      }
    );

    if (!listResponse.ok) {
      throw new Error(`Failed to list memories (${listResponse.status})`);
    }

    const data = await listResponse.json();

    // Handle both array and { items: [...] } response shapes
    const memories = Array.isArray(data) ? data : (data.items || []);

    // Filter for ContextHub memories matching this title
    const toDelete = memories.filter(
      (m) => m.content && m.content.startsWith(prefix)
    );

    // Delete each matching memory (ChatGPT uses `id` not `uuid`)
    for (const memory of toDelete) {
      await fetch(
        `https://chatgpt.com/backend-api/memories/${memory.id}`,
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
