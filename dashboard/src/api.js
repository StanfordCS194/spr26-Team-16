const API_BASE = "http://localhost:8000";

export async function fetchThreads(limit = 20, offset = 0) {
  const res = await fetch(`${API_BASE}/api/threads?limit=${limit}&offset=${offset}`);
  if (!res.ok) throw new Error(`Failed to fetch threads: ${res.status}`);
  return res.json();
}

export async function fetchThread(id) {
  const res = await fetch(`${API_BASE}/api/threads/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch thread: ${res.status}`);
  return res.json();
}

export async function fetchRawTranscript(id) {
  const res = await fetch(`${API_BASE}/api/threads/${id}/raw`);
  if (!res.ok) throw new Error(`Failed to fetch raw transcript: ${res.status}`);
  return res.json();
}

export async function fetchContext(id) {
  const res = await fetch(`${API_BASE}/api/threads/${id}/context`);
  if (!res.ok) throw new Error(`Failed to fetch context: ${res.status}`);
  return res.json();
}

export async function recordPull(id) {
  const res = await fetch(`${API_BASE}/api/threads/${id}/pull`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to record pull: ${res.status}`);
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${API_BASE}/api/stats`);
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.status}`);
  return res.json();
}

export async function retryExtraction(id) {
  const res = await fetch(`${API_BASE}/api/threads/${id}/retry`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to retry extraction: ${res.status}`);
  return res.json();
}
