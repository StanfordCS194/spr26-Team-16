function timeAgo(dateString) {
  const now = new Date();
  const date = new Date(dateString + (dateString.endsWith("Z") ? "" : "Z"));
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  return `${weeks}w ago`;
}

const pushBtn = document.getElementById("push-btn");
const statusEl = document.getElementById("status");
const recentList = document.getElementById("recent-list");
const dashboardLink = document.getElementById("dashboard-link");

// Open dashboard in new tab
dashboardLink.addEventListener("click", (e) => {
  e.preventDefault();
  chrome.tabs.create({ url: "http://localhost:3000" });
});

// Push button handler
pushBtn.addEventListener("click", async () => {
  pushBtn.textContent = "Pushing...";
  pushBtn.className = "push-btn pushing";
  statusEl.textContent = "";
  statusEl.className = "status";

  try {
    // Get active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!getSupportedSite(tab.url)) {
      throw new Error("Not on a supported site (claude.ai or chatgpt.com)");
    }

    // Send scrape message to content script
    const scraped = await chrome.tabs.sendMessage(tab.id, { action: "scrape" });

    if (scraped.error) {
      throw new Error(scraped.error);
    }

    if (!scraped.messages || scraped.messages.length === 0) {
      throw new Error("No messages found. Try refreshing the page.");
    }

    // Send to backend via background script
    const result = await chrome.runtime.sendMessage({
      action: "push",
      data: scraped,
    });

    if (!result.success) {
      throw new Error(result.error || "Push failed");
    }

    pushBtn.textContent = "\u2713 Pushed!";
    pushBtn.className = "push-btn success";
    setTimeout(() => {
      pushBtn.textContent = "Push This Conversation";
      pushBtn.className = "push-btn";
    }, 2000);

    // Refresh recent list
    loadRecent();
  } catch (err) {
    let message = err.message;
    if (message.includes("Could not establish connection") || message.includes("Receiving end does not exist")) {
      message = "Can't reach ContextHub. Is the server running?";
    }

    pushBtn.textContent = "\u2717 Failed \u2014 try again";
    pushBtn.className = "push-btn error";
    statusEl.textContent = message;
    statusEl.className = "status error";

    setTimeout(() => {
      pushBtn.textContent = "Push This Conversation";
      pushBtn.className = "push-btn";
    }, 3000);
  }
});

// Load recent contexts
async function loadRecent() {
  try {
    const result = await chrome.runtime.sendMessage({ action: "get_recent" });

    if (!result.success) {
      recentList.innerHTML = '<div class="empty">Could not load recent contexts</div>';
      return;
    }

    const threads = result.threads || [];

    if (threads.length === 0) {
      recentList.innerHTML = '<div class="empty">No contexts yet</div>';
      return;
    }

    recentList.innerHTML = threads
      .map(
        (t) => `
      <div class="context-card" data-id="${t.id}">
        <div class="title">${escapeHtml(t.title || "Untitled")}</div>
        <div class="meta">${timeAgo(t.created_at)} \u00B7 ${t.source}</div>
        <div class="card-actions">
          <button class="memory-btn" data-thread-id="${t.id}">Pull into Memory</button>
          <button class="pull-btn" data-thread-id="${t.id}">Pull into Chat</button>
          <button class="copy-btn" data-thread-id="${t.id}">Copy Context</button>
        </div>
      </div>
    `
      )
      .join("");

    // Attach pull handlers
    recentList.querySelectorAll(".pull-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const threadId = btn.dataset.threadId;

        // Check active tab is on claude.ai
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!getSupportedSite(tab.url)) {
          btn.textContent = "Open claude.ai or chatgpt.com";
          btn.className = "pull-btn pull-error";
          setTimeout(() => {
            btn.textContent = "Pull into Chat";
            btn.className = "pull-btn";
          }, 2000);
          return;
        }

        btn.textContent = "Pulling...";
        btn.className = "pull-btn pulling";

        try {
          const result = await chrome.runtime.sendMessage({
            action: "get_context",
            thread_id: threadId,
          });

          if (!result.success) throw new Error(result.error);

          const injectResult = await chrome.tabs.sendMessage(tab.id, {
            action: "inject_context",
            text: result.context,
          });

          if (!injectResult.success) throw new Error(injectResult.error);

          btn.textContent = "\u2713 Sent!";
          btn.className = "pull-btn sent";
          setTimeout(() => {
            btn.textContent = "Pull into Chat";
            btn.className = "pull-btn";
          }, 2000);
        } catch (err) {
          let message = "Failed";
          if (err.message && (err.message.includes("Receiving end does not exist") || err.message.includes("Could not establish connection"))) {
            message = "Refresh the page and try again";
          }
          btn.textContent = message;
          btn.className = "pull-btn pull-error";
          setTimeout(() => {
            btn.textContent = "Pull into Chat";
            btn.className = "pull-btn";
          }, 3000);
        }
      });
    });

    // Attach memory handlers
    recentList.querySelectorAll(".memory-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const threadId = btn.dataset.threadId;

        // Check active tab is on claude.ai
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!getSupportedSite(tab.url)) {
          btn.textContent = "Open claude.ai or chatgpt.com";
          btn.className = "memory-btn memory-error";
          setTimeout(() => {
            btn.textContent = "Pull into Memory";
            btn.className = "memory-btn";
          }, 2000);
          return;
        }

        btn.textContent = "Saving...";
        btn.className = "memory-btn saving";

        try {
          const result = await chrome.runtime.sendMessage({
            action: "get_thread_for_memory",
            thread_id: threadId,
          });

          if (!result.success) throw new Error(result.error);

          if (result.items.length === 0) {
            throw new Error("No takeaways to save");
          }

          const injectResult = await chrome.tabs.sendMessage(tab.id, {
            action: "inject_memory",
            title: result.title,
            items: result.items,
          });

          if (!injectResult.success) throw new Error(injectResult.error);

          btn.textContent = "Saved to Memory!";
          btn.className = "memory-btn memorized";
          setTimeout(() => {
            btn.textContent = "Pull into Memory";
            btn.className = "memory-btn";
          }, 2000);
        } catch (err) {
          let message = "Failed";
          if (err.message && (err.message.includes("Receiving end does not exist") || err.message.includes("Could not establish connection"))) {
            message = "Refresh the page and try again";
          }
          btn.textContent = message;
          btn.className = "memory-btn memory-error";
          setTimeout(() => {
            btn.textContent = "Pull into Memory";
            btn.className = "memory-btn";
          }, 3000);
        }
      });
    });

    // Attach copy handlers
    recentList.querySelectorAll(".copy-btn").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const threadId = btn.dataset.threadId;

        try {
          const result = await chrome.runtime.sendMessage({
            action: "get_context",
            thread_id: threadId,
          });

          if (!result.success) throw new Error(result.error);

          await navigator.clipboard.writeText(result.context);
          btn.textContent = "\u2713 Copied!";
          btn.classList.add("copied");
          setTimeout(() => {
            btn.textContent = "Copy Context";
            btn.classList.remove("copied");
          }, 2000);
        } catch {
          btn.textContent = "Failed";
          setTimeout(() => {
            btn.textContent = "Copy Context";
          }, 2000);
        }
      });
    });
  } catch {
    recentList.innerHTML =
      '<div class="empty">Can\'t reach server. Is the backend running?</div>';
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Site detection helper
function getSupportedSite(url) {
  if (!url) return null;
  if (url.includes("claude.ai")) return "claude.ai";
  if (url.includes("chatgpt.com")) return "chatgpt.com";
  return null;
}

// Load recent contexts on popup open
loadRecent();
