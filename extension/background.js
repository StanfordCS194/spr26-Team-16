const API_BASE = "http://localhost:8000";

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "push") {
    fetch(`${API_BASE}/api/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request.data),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        return res.json();
      })
      .then((data) => sendResponse({ success: true, thread: data }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (request.action === "get_recent") {
    fetch(`${API_BASE}/api/threads?limit=5`)
      .then((res) => res.json())
      .then((data) => sendResponse({ success: true, threads: data.threads }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (request.action === "get_thread") {
    fetch(`${API_BASE}/api/threads/${request.thread_id}`)
      .then((res) => res.json())
      .then((data) => sendResponse({ success: true, thread: data }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (request.action === "get_context") {
    Promise.all([
      fetch(`${API_BASE}/api/threads/${request.thread_id}/context`).then((r) =>
        r.json()
      ),
      fetch(`${API_BASE}/api/threads/${request.thread_id}/pull`, {
        method: "POST",
      }),
    ])
      .then(([contextData]) =>
        sendResponse({ success: true, context: contextData.formatted_context })
      )
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (request.action === "get_thread_for_memory") {
    fetch(`${API_BASE}/api/threads/${request.thread_id}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        return res.json();
      })
      .then((thread) => {
        const title = thread.title || "Untitled";
        const items = [];

        // Key takeaways as memory items
        if (Array.isArray(thread.key_takeaways)) {
          for (const takeaway of thread.key_takeaways) {
            items.push(`[ContextHub: ${title}] ${takeaway}`);
          }
        }

        // Open threads as memory items
        if (Array.isArray(thread.open_threads)) {
          for (const openThread of thread.open_threads) {
            items.push(`[ContextHub: ${title}] Open: ${openThread}`);
          }
        }

        sendResponse({ success: true, title, items });
      })
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }
});
