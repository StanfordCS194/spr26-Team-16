"""SQLAlchemy ORM models for all §5 tables (ARCHITECTURE.md)."""

import uuid
from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pgvector.sqlalchemy import Vector

from contexthub_backend.db.base import Base
from contexthub_backend.db.short_id import uuid7


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid7() -> uuid.UUID:
    return uuid7()


# ---------------------------------------------------------------------------
# profiles
# ---------------------------------------------------------------------------

class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# api_tokens
# ---------------------------------------------------------------------------

class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))


# ---------------------------------------------------------------------------
# workspaces
# ---------------------------------------------------------------------------

class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    settings_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))

    pushes: Mapped[list["Push"]] = relationship(back_populates="workspace")
    tags: Mapped[list["Tag"]] = relationship(back_populates="workspace")


# ---------------------------------------------------------------------------
# interchange_format_versions
# ---------------------------------------------------------------------------

class InterchangeFormatVersion(Base):
    __tablename__ = "interchange_format_versions"

    version: Mapped[str] = mapped_column(Text, primary_key=True)
    json_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))


# ---------------------------------------------------------------------------
# pushes
# ---------------------------------------------------------------------------

class Push(Base):
    __tablename__ = "pushes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_platform: Mapped[str] = mapped_column(
        sa.Enum("claude_ai", "chatgpt", "gemini", name="source_platform"),
        nullable=False,
    )
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    source_conversation_id: Mapped[Optional[str]] = mapped_column(Text)
    interchange_version: Mapped[str] = mapped_column(
        Text,
        ForeignKey("interchange_format_versions.version"),
        nullable=False,
        server_default="ch.v0.1",
    )
    title: Mapped[Optional[str]] = mapped_column(Text)
    commit_message: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        sa.Enum("pending", "processing", "ready", "failed", name="push_status"),
        nullable=False,
        server_default="pending",
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    idempotency_key: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True))

    workspace: Mapped["Workspace"] = relationship(back_populates="pushes")
    summaries: Mapped[list["Summary"]] = relationship(back_populates="push")
    transcript: Mapped[Optional["Transcript"]] = relationship(back_populates="push", uselist=False)
    push_tags: Mapped[list["PushTag"]] = relationship(back_populates="push")
    from_relationships: Mapped[list["PushRelationship"]] = relationship(
        back_populates="from_push", foreign_keys="PushRelationship.from_push_id"
    )
    to_relationships: Mapped[list["PushRelationship"]] = relationship(
        back_populates="to_push", foreign_keys="PushRelationship.to_push_id"
    )


# ---------------------------------------------------------------------------
# summaries
# ---------------------------------------------------------------------------

class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    push_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pushes.id", ondelete="CASCADE"),
        nullable=False,
    )
    layer: Mapped[str] = mapped_column(
        sa.Enum(
            "commit_message",
            "structured_block",
            "raw_transcript",
            name="summary_layer",
        ),
        nullable=False,
    )
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_markdown: Mapped[Optional[str]] = mapped_column(Text)
    content_tsv: Mapped[Optional[Any]] = mapped_column(TSVECTOR)
    model: Mapped[Optional[str]] = mapped_column(Text)
    prompt_version: Mapped[Optional[str]] = mapped_column(Text)
    latency_ms: Mapped[Optional[int]] = mapped_column(sa.Integer)
    input_tokens: Mapped[Optional[int]] = mapped_column(sa.Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(sa.Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(sa.Numeric(12, 6))
    quality_score: Mapped[Optional[float]] = mapped_column(sa.Float)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    superseded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("summaries.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    push: Mapped["Push"] = relationship(back_populates="summaries")
    embedding: Mapped[Optional["SummaryEmbedding"]] = relationship(
        back_populates="summary", uselist=False
    )
    feedback: Mapped[list["SummaryFeedback"]] = relationship(back_populates="summary")


# ---------------------------------------------------------------------------
# summary_embeddings
# ---------------------------------------------------------------------------

class SummaryEmbedding(Base):
    __tablename__ = "summary_embeddings"

    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("summaries.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding: Mapped[Any] = mapped_column(Vector(1024), nullable=False)
    embedding_model: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="voyage-3-large"
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    summary: Mapped["Summary"] = relationship(back_populates="embedding")


# ---------------------------------------------------------------------------
# transcripts
# ---------------------------------------------------------------------------

class Transcript(Base):
    __tablename__ = "transcripts"

    push_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pushes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger, nullable=False)
    message_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    push: Mapped["Push"] = relationship(back_populates="transcript")


# ---------------------------------------------------------------------------
# tags + push_tags
# ---------------------------------------------------------------------------

class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="tags")
    push_tags: Mapped[list["PushTag"]] = relationship(back_populates="tag")


class PushTag(Base):
    __tablename__ = "push_tags"

    push_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pushes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    push: Mapped["Push"] = relationship(back_populates="push_tags")
    tag: Mapped["Tag"] = relationship(back_populates="push_tags")


# ---------------------------------------------------------------------------
# push_relationships
# ---------------------------------------------------------------------------

class PushRelationship(Base):
    __tablename__ = "push_relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    from_push_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pushes.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_push_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pushes.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(
        sa.Enum("continuation", "reference", "supersession", name="relation_type"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    from_push: Mapped["Push"] = relationship(
        back_populates="from_relationships", foreign_keys=[from_push_id]
    )
    to_push: Mapped["Push"] = relationship(
        back_populates="to_relationships", foreign_keys=[to_push_id]
    )


# ---------------------------------------------------------------------------
# summary_feedback
# ---------------------------------------------------------------------------

class SummaryFeedback(Base):
    __tablename__ = "summary_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("summaries.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    score: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    summary: Mapped["Summary"] = relationship(back_populates="feedback")


# ---------------------------------------------------------------------------
# pulls
# ---------------------------------------------------------------------------

class Pull(Base):
    __tablename__ = "pulls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_platform: Mapped[str] = mapped_column(
        sa.Enum("claude_ai", name="target_platform"), nullable=False
    )
    origin: Mapped[str] = mapped_column(
        sa.Enum("extension", "dashboard", name="pull_origin"), nullable=False
    )
    resolution: Mapped[str] = mapped_column(
        sa.Enum(
            "commit_message",
            "structured_block",
            "raw_transcript",
            name="pull_resolution",
        ),
        nullable=False,
    )
    push_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    workspace_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    token_estimate: Mapped[Optional[int]] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# audit_log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid7
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("auth.users.id", ondelete="SET NULL"),
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(Text)
    resource_id: Mapped[Optional[str]] = mapped_column(Text)
    request_id: Mapped[Optional[str]] = mapped_column(Text)
    ip: Mapped[Optional[str]] = mapped_column(Text)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now(), nullable=False
    )
