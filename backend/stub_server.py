"""Stub ContextHub backend for UX testing.

Listens on http://127.0.0.1:8765 with no DB, no Redis, no Google verification.
Mimics the real backend's response shapes closely enough to drive the extension's
sign-in / list / save / pull / inject flow with mock data.

Start:
    python3 backend/stub_server.py

Routes (matching what the extension actually hits, see packages/extension/src/background.ts):
    POST   /v1/auth/google                       -> mock ch_ token + workspace + user
    GET    /v1/search?q=...&workspace_id=...     -> hardcoded conversation list
    POST   /v1/workspaces/{workspaceId}/pushes   -> records a new fake conversation
    GET    /v1/pushes/{pushId}                   -> push status / detail
    POST   /v1/pulls                             -> markdown blob to inject into Claude
    GET    /v1/health                            -> ok
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PORT = 8765

# In-memory state (resets when the process restarts).
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_state: dict[str, Any] = {
    "user": None,
    "workspace_id": str(uuid.uuid4()),
    "pushes": [
        {
            "push_id": str(uuid.uuid4()),
            "title": "Designing the onboarding flow",
            "summary": (
                "Walked through the new-user onboarding carousel. Decided on three "
                "steps: account creation, workspace setup, and first push. Talked "
                "through copy variations and settled on action-oriented headlines."
            ),
            "snippet": "Onboarding copy and a three-step flow.",
            "score": 0.91,
            "status": "ready",
            "created_at": _now(),
            "updated_at": _now(),
        },
        {
            "push_id": str(uuid.uuid4()),
            "title": "Debugging the auth race condition",
            "summary": (
                "Tracked down a race condition where the JWT was being read before "
                "the session callback fired. Fix was to await the auth state listener "
                "before kicking off any API calls."
            ),
            "snippet": "JWT race condition; fix was to await the session callback.",
            "score": 0.82,
            "status": "ready",
            "created_at": _now(),
            "updated_at": _now(),
        },
        {
            "push_id": str(uuid.uuid4()),
            "title": "Database schema for the audit log",
            "summary": (
                "Settled on a five-column audit log: id, user_id, action, resource_id, "
                "timestamp. Indexes on (user_id, timestamp) and (resource_id, timestamp). "
                "Decided to keep raw payloads in a separate JSONB column."
            ),
            "snippet": "Five-column audit_log table with two composite indexes.",
            "score": 0.74,
            "status": "ready",
            "created_at": _now(),
            "updated_at": _now(),
        },
    ],
}


def _decode_jwt_email(id_token: str) -> str | None:
    """Best-effort: read `email` from the unverified payload of a Google ID token.

    The stub trusts whatever Google sent so the UI can show the user's real email.
    The real backend verifies signature, audience, issuer, etc.
    """
    try:
        import base64

        _, payload_b64, _ = id_token.split(".")
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        email = payload.get("email")
        return str(email) if isinstance(email, str) else None
    except Exception:
        return None


def _push_for(push_id: str) -> dict | None:
    return next((p for p in _state["pushes"] if p["push_id"] == push_id), None)


def _push_with_workspace(push: dict) -> dict:
    return {**push, "workspace_id": _state["workspace_id"]}


def _message_text(message: dict) -> str:
    """Flatten one ch.v0.1 message's content blocks to plain text."""
    parts: list[str] = []
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
    return " ".join(p.strip() for p in parts if p.strip())


def _derive_title(body: dict, turns: list[tuple[str, str]]) -> str:
    meta_title = (body.get("metadata") or {}).get("title")
    if isinstance(meta_title, str) and meta_title.strip():
        return meta_title.strip()
    for role, text in turns:
        if role == "user" and text:
            first_line = text.splitlines()[0].strip()
            return first_line[:80] + ("…" if len(first_line) > 80 else "")
    return "Untitled conversation"


def _derive_summary(turns: list[tuple[str, str]]) -> str:
    """Cheap extractive summary: first user prompt + first assistant reply, truncated."""
    user = next((t for r, t in turns if r == "user" and t), "")
    asst = next((t for r, t in turns if r == "assistant" and t), "")
    out: list[str] = []
    if user:
        out.append(f"User asked: {user[:240]}{'…' if len(user) > 240 else ''}")
    if asst:
        out.append(f"Assistant replied: {asst[:240]}{'…' if len(asst) > 240 else ''}")
    return "  ".join(out) or "(empty conversation)"


def _history_item(push: dict) -> dict:
    """Map internal push → dashboard `ConversationListItem` shape."""
    return {
        "id": push["push_id"],
        "workspace_id": _state["workspace_id"],
        "conversation_title": push.get("title"),
        "status": push.get("status", "ready"),
        "created_at": push.get("created_at"),
        "updated_at": push.get("updated_at") or push.get("created_at"),
        "title": push.get("title"),
        "summary": push.get("summary"),
        "details": {
            "summary": push.get("summary"),
            "key_takeaways": ["This is a stub takeaway.", "Another stub takeaway."],
            "tags": ["demo", "stub"],
        },
    }


_PUSH_DETAIL_RE = re.compile(r"^/v1/pushes/([^/]+)/?$")
_WORKSPACE_PUSHES_RE = re.compile(r"^/v1/workspaces/([^/]+)/pushes/?$")


class StubHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # One-line concise log.
        try:
            print(f"[stub] {self.command:<6} {self.path} -> {args[1]}")
        except Exception:
            pass

    # ----------------------------------------------------------------- utils
    def _send_json(self, status: int, body: dict | list) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _cors_headers(self) -> None:
        # Permissive CORS — the chrome-extension origin needs to call us.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Request-Id, Idempotency-Key",
        )
        self.send_header("Access-Control-Expose-Headers", "X-Request-Id")
        self.send_header("X-Request-Id", str(uuid.uuid4()))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _query(self) -> dict[str, str]:
        from urllib.parse import urlsplit, parse_qsl

        qs = urlsplit(self.path).query
        return dict(parse_qsl(qs))

    def _path_only(self) -> str:
        from urllib.parse import urlsplit

        return urlsplit(self.path).path

    # -------------------------------------------------------------- handlers
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = self._path_only()

        if path == "/v1/health":
            self._send_json(200, {"status": "ok", "stub": True})
            return

        if path == "/v1/pushes/history":
            try:
                limit = int(self._query().get("limit", "50"))
            except ValueError:
                limit = 50
            items = [_history_item(p) for p in _state["pushes"][:limit]]
            self._send_json(200, {"items": items})
            return

        if path == "/v1/search":
            q = self._query().get("q", "").strip()
            items = [_push_with_workspace(p) for p in _state["pushes"]]
            if q and q != "*":
                ql = q.lower()
                items = [
                    p for p in items
                    if ql in (p.get("title") or "").lower() or ql in (p.get("summary") or "").lower()
                ]
            self._send_json(200, {"items": items})
            return

        m = _PUSH_DETAIL_RE.match(path)
        if m:
            push = _push_for(m.group(1))
            if not push:
                self._send_json(404, {"error": {"code": "not_found", "message": "no such push"}})
                return
            stored_messages = push.get("messages")
            if isinstance(stored_messages, list) and stored_messages:
                transcript = json.dumps({"messages": stored_messages})
            else:
                transcript = json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": [{"type": "text", "text": "Sample question."}]},
                            {"role": "assistant", "content": [{"type": "text", "text": "Sample answer."}]},
                        ]
                    }
                )
            self._send_json(
                200,
                {
                    "id": push["push_id"],
                    "workspace_id": _state["workspace_id"],
                    "status": push["status"],
                    "failure_reason": None,
                    "source_platform": "claude_ai",
                    "title": push["title"],
                    "created_at": push.get("created_at"),
                    "updated_at": push.get("updated_at") or push.get("created_at"),
                    "raw_transcript": transcript,
                    "summaries": [
                        {"layer": "summary", "content_json": {"text": push["summary"]}},
                        {
                            "layer": "details",
                            "content_json": {
                                "summary": push["summary"],
                                "key_takeaways": ["This is a stub takeaway.", "Another stub takeaway."],
                                "tags": ["demo", "stub"],
                            },
                        },
                    ],
                },
            )
            return

        self._send_json(404, {"error": {"code": "not_found", "message": f"stub: unknown GET {path}"}})

    def do_POST(self) -> None:  # noqa: N802
        path = self._path_only()
        body = self._read_json()

        if path == "/v1/me/bootstrap":
            email = body.get("email") or "demo@example.com"
            _state["user"] = {
                "user_id": (_state["user"] or {}).get("user_id") or str(uuid.uuid4()),
                "email": email,
                "display_name": body.get("display_name") or email.split("@", 1)[0],
                "avatar_url": body.get("avatar_url"),
            }
            self._send_json(
                200,
                {
                    "workspace_id": _state["workspace_id"],
                    "user": _state["user"],
                },
            )
            return

        if path == "/v1/auth/google":
            id_token = body.get("id_token", "")
            email = _decode_jwt_email(id_token) or "demo@example.com"
            display_name = email.split("@", 1)[0]
            _state["user"] = {
                "user_id": str(uuid.uuid4()),
                "email": email,
                "display_name": display_name,
                "avatar_url": None,
            }
            self._send_json(
                200,
                {
                    "token": f"ch_stub_{uuid.uuid4().hex}",
                    "scopes": ["push", "pull", "search", "read"],
                    "workspace_id": _state["workspace_id"],
                    "user": _state["user"],
                },
            )
            return

        if path == "/v1/pulls":
            selections = body.get("selections", [])
            chunks: list[str] = []
            for s in selections:
                pid = s.get("push_id")
                push = _push_for(pid)
                if not push:
                    continue
                chunks.append(f"## {push['title']}\n\n{push['summary']}\n")
            payload = ("\n\n---\n\n".join(chunks) or "(Stub) no matching context.") + "\n"
            self._send_json(200, {"payload_markdown": payload})
            return

        m = _WORKSPACE_PUSHES_RE.match(path)
        if m:
            messages = body.get("messages") if isinstance(body.get("messages"), list) else []
            turns = [
                (str(msg.get("role") or ""), _message_text(msg))
                for msg in messages
                if isinstance(msg, dict)
            ]
            title = _derive_title(body, turns)
            summary = _derive_summary(turns)
            new_id = str(uuid.uuid4())
            new_push = {
                "push_id": new_id,
                "title": title,
                "summary": summary,
                "snippet": (turns[0][1][:120] if turns else ""),
                "score": 1.0,
                "status": "ready",
                "created_at": _now(),
                "updated_at": _now(),
                "messages": messages,
            }
            _state["pushes"].insert(0, new_push)
            self._send_json(202, {"push_id": new_id, "status": "ready", "scrub_flags": []})
            return

        self._send_json(404, {"error": {"code": "not_found", "message": f"stub: unknown POST {path}"}})

    def do_DELETE(self) -> None:  # noqa: N802
        path = self._path_only()
        m = _PUSH_DETAIL_RE.match(path)
        if m:
            pid = m.group(1)
            before = len(_state["pushes"])
            _state["pushes"] = [p for p in _state["pushes"] if p["push_id"] != pid]
            if len(_state["pushes"]) == before:
                self._send_json(404, {"error": {"code": "not_found", "message": "no such push"}})
                return
            self._send_json(200, None)
            return
        self._send_json(404, {"error": {"code": "not_found", "message": f"stub: unknown DELETE {path}"}})

    def do_PATCH(self) -> None:  # noqa: N802
        path = self._path_only()
        body = self._read_json()
        m = _PUSH_DETAIL_RE.match(path)
        if m:
            push = _push_for(m.group(1))
            if not push:
                self._send_json(404, {"error": {"code": "not_found", "message": "no such push"}})
                return
            title = body.get("title")
            if isinstance(title, str) and title.strip():
                push["title"] = title.strip()
                push["updated_at"] = _now()
            self._send_json(
                200,
                {
                    "id": push["push_id"],
                    "workspace_id": _state["workspace_id"],
                    "status": push["status"],
                    "failure_reason": None,
                    "source_platform": "claude_ai",
                    "title": push["title"],
                    "created_at": push.get("created_at"),
                    "updated_at": push.get("updated_at") or push.get("created_at"),
                    "raw_transcript": None,
                    "summaries": [],
                },
            )
            return
        self._send_json(404, {"error": {"code": "not_found", "message": f"stub: unknown PATCH {path}"}})


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), StubHandler)
    print(f"[stub] ContextHub stub backend listening on http://127.0.0.1:{PORT}")
    print("[stub] No real DB. No real Google verification. Mock data only.")
    print("[stub] Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[stub] shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
