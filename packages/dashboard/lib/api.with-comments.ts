import { getSupabaseAccessToken } from "@/lib/supabase";

export type ApiErrorEnvelope = {
  error: { code: string; message: string; request_id?: string };
};

// Heuristic for recognizing JWTs. Supabase access tokens are JWTs, and JWTs
// are encoded as three dot-separated sections: header.payload.signature.
// This does not verify the token cryptographically; it only helps decide
// whether a pasted value should be wrapped as "Bearer <token>".
function isLikelyJwtToken(token: string) {
  const parts = token.split(".");
  return parts.length === 3 && parts.every((part) => part.length > 0);
}

// Users often paste tokens copied from env files or terminals, where the value
// may be surrounded by quotes/backticks. Remove only matching wrapping
// characters and leave the token body untouched.
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

// Normalize common pasted formats into the raw token-like value. This lets the
// dashboard accept inputs such as:
//   export CONTEXTHUB_TOKEN="ch_..."
//   CONTEXTHUB_TOKEN=ch_...
//   "ch_..."
// instead of requiring the user to manually trim everything down first.
function extractTokenLikeValue(value: string) {
  const exportMatch = value.match(/^export\s+\w+\s*=\s*(.+)$/i);
  if (exportMatch) return stripWrappingQuotes(exportMatch[1].trim());

  const assignMatch = value.match(/^\w+\s*=\s*(.+)$/);
  if (assignMatch) return stripWrappingQuotes(assignMatch[1].trim());

  return stripWrappingQuotes(value);
}

const DEFAULT_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8765";

// Decide which backend API URL the dashboard should call. In production this
// can come from NEXT_PUBLIC_API_BASE_URL; in local dev it defaults to
// localhost:8765. In the browser, users can override it in localStorage.
export function getDashboardApiBaseUrl() {
  if (typeof window === "undefined") return DEFAULT_API_BASE_URL;
  const stored = localStorage.getItem("ctxh_api_base_url");
  // Migration: an earlier build defaulted to :8000. Force the new default
  // so users who set it before don't get stuck on a stale port.
  if (!stored || stored === "http://localhost:8000") return DEFAULT_API_BASE_URL;
  return stored;
}

// Convert pasted tokens or Authorization headers into the exact form expected
// by the backend. The backend wants:
//   Authorization: Bearer <jwt-or-ch-token>
//
// This accepts several user-friendly inputs:
//   Authorization: Bearer ch_...  -> Bearer ch_...
//   bearer ch_...                 -> Bearer ch_...
//   ch_...                        -> Bearer ch_...
//   <jwt>                         -> Bearer <jwt>
//
// If the value is not recognizable as a JWT or ContextHub API token, return it
// unchanged after trimming so the caller can still attempt the request.
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

// Tell the UI whether the current auth value is a JWT after normalization.
// This is useful for labeling auth mode or deciding which UX to show.
export function isJwtAuthHeader(value: string) {
  const normalized = normalizeAuthHeader(value);
  if (!normalized.startsWith("Bearer ")) return false;
  return isLikelyJwtToken(normalized.slice("Bearer ".length).trim());
}

// Tell the UI whether the current auth value is a ContextHub API token after
// normalization. ContextHub API tokens use the "ch_" prefix.
export function isApiTokenAuthHeader(value: string) {
  const normalized = normalizeAuthHeader(value);
  if (!normalized.startsWith("Bearer ")) return false;
  return normalized.slice("Bearer ".length).trim().startsWith("ch_");
}

// Read the manually configured auth header from browser storage and normalize
// it before use. This is the fallback path when the dashboard does not have an
// active Supabase session.
export function getDashboardAuthHeader() {
  if (typeof window === "undefined") return "";
  return normalizeAuthHeader(localStorage.getItem("ctxh_auth_header") || "");
}

// Shared fetch wrapper for dashboard API calls.
//
// Components call apiFetch<T> instead of fetch directly so every request gets
// the same base URL handling, auth header behavior, JSON content type, backend
// error parsing, and request-id propagation. The function returns a discriminated
// result object:
//   { ok: true, data, requestId }
//   { ok: false, message, requestId }
//
// That keeps UI code simple: it can branch on res.ok without try/catch for
// expected HTTP errors.
export async function apiFetch<T>(
  path: string,
  init?: RequestInit
): Promise<{ ok: true; data: T; requestId?: string } | { ok: false; message: string; requestId?: string }> {
  // Remove trailing slashes from the base URL so callers can pass paths that
  // start with "/v1/..." and avoid double slashes in the final URL.
  const baseUrl = getDashboardApiBaseUrl().replace(/\/+$/, "");

  // Start from any headers the caller passed, then add/override the shared
  // headers this wrapper owns.
  const headers = new Headers(init?.headers);

  // Prefer the active Supabase session because that is the normal dashboard
  // auth flow. If there is no Supabase token, fall back to a manually pasted
  // ContextHub API token/JWT from localStorage.
  const supabaseToken = await getSupabaseAccessToken();
  if (supabaseToken) {
    headers.set("Authorization", `Bearer ${supabaseToken}`);
  } else {
    const authHeader = getDashboardAuthHeader();
    if (authHeader) {
      headers.set("Authorization", authHeader);
    }
  }

  // If the caller supplied a request body, assume it is JSON unless they already
  // specified a Content-Type. This preserves flexibility for future non-JSON
  // requests.
  if (!headers.has("Content-Type") && init?.body) {
    headers.set("Content-Type", "application/json");
  }

  let resp: Response;
  try {
    // The caller passes paths like "/v1/pushes/history"; this wrapper combines
    // them with the configured API base URL.
    resp = await fetch(`${baseUrl}${path}`, { ...init, headers });
  } catch (err) {
    // Network failures do not produce an HTTP response, so convert them into the
    // same ok:false shape used for backend errors.
    const message = err instanceof Error ? err.message : "Network request failed";
    return {
      ok: false,
      message: `${message}. Check that the backend is running at ${baseUrl} and that CORS is enabled.`
    };
  }

  // The backend middleware attaches X-Request-Id to every response. Returning it
  // lets the UI display/debug the exact request that failed.
  const requestId = resp.headers.get("X-Request-Id") ?? undefined;

  // Backend errors usually use ApiErrorEnvelope:
  //   { error: { code, message, request_id } }
  // Prefer that message when present; otherwise keep a generic status message.
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

  // Successful endpoints are expected to return JSON matching the generic type
  // requested by the caller, for example apiFetch<PushHistoryResponse>(...).
  const data = (await resp.json()) as T;
  return { ok: true, data, requestId };
}
