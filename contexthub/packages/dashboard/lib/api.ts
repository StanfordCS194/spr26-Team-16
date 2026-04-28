export type ApiErrorEnvelope = {
  error: { code: string; message: string; request_id?: string };
};

function isLikelyJwtToken(token: string) {
  const parts = token.split(".");
  return parts.length === 3 && parts.every((part) => part.length > 0);
}

function stripWrappingQuotes(value: string) {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'")) ||
    (value.startsWith("`") && value.endsWith("`"))
  ) {
    return value.slice(1, -1).trim();
  }
  return value;
}

function extractTokenLikeValue(value: string) {
  const exportMatch = value.match(/^export\s+\w+\s*=\s*(.+)$/i);
  if (exportMatch) return stripWrappingQuotes(exportMatch[1].trim());

  const assignMatch = value.match(/^\w+\s*=\s*(.+)$/);
  if (assignMatch) return stripWrappingQuotes(assignMatch[1].trim());

  return stripWrappingQuotes(value);
}

export function getDashboardApiBaseUrl() {
  if (typeof window === "undefined") return "http://localhost:8000";
  return localStorage.getItem("ctxh_api_base_url") || "http://localhost:8000";
}

export function normalizeAuthHeader(value: string) {
  const trimmed = value.trim().replace(/^Authorization:\s*/i, "");
  if (!trimmed) return "";

  const normalizedCandidate = extractTokenLikeValue(trimmed);

  const bearerMatch = normalizedCandidate.match(/^bearer\s+(.+)$/i);
  if (bearerMatch) return `Bearer ${bearerMatch[1].trim()}`;

  if (normalizedCandidate.startsWith("ch_") || isLikelyJwtToken(normalizedCandidate)) {
    return `Bearer ${normalizedCandidate}`;
  }

  return normalizedCandidate;
}

export function isJwtAuthHeader(value: string) {
  const normalized = normalizeAuthHeader(value);
  if (!normalized.startsWith("Bearer ")) return false;
  return isLikelyJwtToken(normalized.slice("Bearer ".length).trim());
}

export function isApiTokenAuthHeader(value: string) {
  const normalized = normalizeAuthHeader(value);
  if (!normalized.startsWith("Bearer ")) return false;
  return normalized.slice("Bearer ".length).trim().startsWith("ch_");
}

export function getDashboardAuthHeader() {
  if (typeof window === "undefined") return "";
  return normalizeAuthHeader(localStorage.getItem("ctxh_auth_header") || "");
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<{ ok: true; data: T; requestId?: string } | { ok: false; message: string; requestId?: string }> {
  const baseUrl = getDashboardApiBaseUrl().replace(/\/+$/, "");
  const headers = new Headers(init?.headers);

  const authHeader = getDashboardAuthHeader();
  if (authHeader) {
    headers.set("Authorization", authHeader);
  }
  if (!headers.has("Content-Type") && init?.body) {
    headers.set("Content-Type", "application/json");
  }

  let resp: Response;
  try {
    resp = await fetch(`${baseUrl}${path}`, { ...init, headers });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Network request failed";
    return {
      ok: false,
      message: `${message}. Check that the backend is running at ${baseUrl} and that CORS is enabled.`
    };
  }
  const requestId = resp.headers.get("X-Request-Id") ?? undefined;

  if (!resp.ok) {
    let message = `Request failed (${resp.status})`;
    try {
      const json = (await resp.json()) as ApiErrorEnvelope;
      if (json?.error?.message) message = json.error.message;
    } catch {
      // ignore
    }
    return { ok: false, message, requestId };
  }

  const data = (await resp.json()) as T;
  return { ok: true, data, requestId };
}
