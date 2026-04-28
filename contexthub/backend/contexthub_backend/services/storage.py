from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from supabase import Client

from contexthub_interchange.models import ConversationV0


@dataclass(slots=True)
class StoredTranscript:
    storage_path: str
    sha256: str
    size_bytes: int
    message_count: int


class TranscriptStorageService:
    def __init__(
        self,
        *,
        bucket: str,
        supabase_client: Client | None = None,
        local_root: Path | None = None,
    ) -> None:
        self._bucket = bucket
        self._supabase_client = supabase_client
        self._local_root = local_root or Path(".contexthub_storage")
        self._local_root.mkdir(parents=True, exist_ok=True)

    async def store_transcript(
        self,
        *,
        workspace_id: str,
        push_id: str,
        conversation: ConversationV0,
    ) -> StoredTranscript:
        payload = json.dumps(conversation.model_dump(mode="json"), separators=(",", ":")).encode()
        digest = hashlib.sha256(payload).hexdigest()
        path = f"{workspace_id}/{push_id}.json"
        if self._supabase_client:
            self._supabase_client.storage.from_(self._bucket).upload(
                path=path,
                file=payload,
                file_options={"content-type": "application/json", "upsert": "true"},
            )
        else:
            target = self._local_root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        return StoredTranscript(
            storage_path=path,
            sha256=digest,
            size_bytes=len(payload),
            message_count=len(conversation.messages),
        )

    async def load_transcript(self, storage_path: str) -> ConversationV0:
        if self._supabase_client:
            payload = self._supabase_client.storage.from_(self._bucket).download(storage_path)
            if isinstance(payload, str):
                payload_bytes = payload.encode()
            else:
                payload_bytes = payload
        else:
            payload_bytes = (self._local_root / storage_path).read_bytes()
        data = json.loads(payload_bytes.decode())
        return ConversationV0.model_validate(data)

