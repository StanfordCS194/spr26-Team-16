import json
from sqlalchemy import Column, Text, Integer, ForeignKey
from database import Base


class Thread(Base):
    __tablename__ = "threads"

    id = Column(Text, primary_key=True)
    source = Column(Text, nullable=False, default="claude")
    source_url = Column(Text)
    title = Column(Text)
    conversation_type = Column(Text)  # decision|build|research|brainstorm|debug|planning|learning|writing|other
    summary = Column(Text)
    key_takeaways = Column(Text)  # JSON array of strings
    artifacts = Column(Text)  # JSON array of {type, language, description, content}
    open_threads = Column(Text)  # JSON array of strings
    tags = Column(Text)  # JSON array of strings
    raw_transcript_path = Column(Text)
    extraction_status = Column(Text, default="pending")
    extraction_error = Column(Text)
    message_count = Column(Integer)
    folder = Column(Text)  # nullable; threads with NULL show under "Unfiled"
    created_at = Column(Text)
    updated_at = Column(Text)

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "source_url": self.source_url,
            "title": self.title,
            "conversation_type": self.conversation_type,
            "summary": self.summary,
            "key_takeaways": json.loads(self.key_takeaways) if self.key_takeaways else [],
            "artifacts": json.loads(self.artifacts) if self.artifacts else [],
            "open_threads": json.loads(self.open_threads) if self.open_threads else [],
            "tags": json.loads(self.tags) if self.tags else [],
            "raw_transcript_path": self.raw_transcript_path,
            "extraction_status": self.extraction_status,
            "extraction_error": self.extraction_error,
            "message_count": self.message_count,
            "folder": self.folder,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class PullEvent(Base):
    __tablename__ = "pull_events"

    id = Column(Text, primary_key=True)
    thread_id = Column(Text, ForeignKey("threads.id"))
    pulled_at = Column(Text)
