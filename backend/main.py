import os
from dotenv import load_dotenv

load_dotenv()

import json
import uuid
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import engine, Base, get_db
from models import Thread, PullEvent
from extraction import extract_context, load_transcript

app = FastAPI(title="ContextHub API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


def format_summary_context(t: dict) -> str:
    """Format extracted thread data into a compact context block for pasting."""
    output = "[Context from ContextHub]\n"
    output += f"Continuing from a previous conversation: {t['title']}\n\n"
    output += f"{t['summary']}\n"

    takeaways = t.get("key_takeaways", [])
    if takeaways:
        output += "\nKey takeaways:\n"
        for item in takeaways:
            output += f"- {item}\n"

    open_threads = t.get("open_threads", [])
    if open_threads:
        output += "\nStill open:\n"
        for item in open_threads:
            output += f"- {item}\n"

    artifacts = t.get("artifacts", [])
    if artifacts and len(artifacts) <= 3:
        output += "\nArtifacts from that conversation:\n"
        for a in artifacts:
            lang = a.get("language") or ""
            output += f"[{a['description']}]\n```{lang}\n{a['content']}\n```\n"
    elif artifacts and len(artifacts) > 3:
        output += f"\nNote: {len(artifacts)} artifacts were produced. Ask me to share specific ones if needed.\n"

    output += "[End Context]"
    return output


def format_full_context(t: dict, messages: list[dict]) -> str:
    """Format extracted thread data + full raw transcript for pasting."""
    output = "[Full conversation from ContextHub]\n"
    output += f"This is a complete transcript of a previous conversation: {t['title']}\n\n"
    output += f"Summary: {t['summary']}\n"

    takeaways = t.get("key_takeaways", [])
    if takeaways:
        output += "\nKey takeaways:\n"
        for item in takeaways:
            output += f"- {item}\n"

    open_threads = t.get("open_threads", [])
    if open_threads:
        output += "\nStill open:\n"
        for item in open_threads:
            output += f"- {item}\n"

    output += "\n--- Full Transcript ---\n"
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        output += f"{role}: {msg['content']}\n\n"
    output += "--- End Transcript ---\n"
    output += "[End Context]"
    return output


@app.post("/api/threads", status_code=201)
def create_thread(data: dict, db: Session = Depends(get_db)):
    messages = data.get("messages")
    if not messages:
        raise HTTPException(status_code=400, detail="Missing required field: messages")

    thread_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    # Save raw transcript
    from extraction import save_transcript
    transcript_path = save_transcript(thread_id, messages)

    # Create thread record
    thread = Thread(
        id=thread_id,
        source=data.get("source", "claude"),
        source_url=data.get("url"),
        raw_transcript_path=transcript_path,
        extraction_status="processing",
        message_count=len(messages),
        created_at=now,
        updated_at=now,
    )
    db.add(thread)
    db.commit()

    # Run extraction synchronously
    try:
        extracted = extract_context(messages)
        thread.title = extracted["title"]
        thread.conversation_type = extracted["conversation_type"]
        thread.summary = extracted["summary"]
        thread.key_takeaways = json.dumps(extracted["key_takeaways"])
        thread.artifacts = json.dumps(extracted["artifacts"])
        thread.open_threads = json.dumps(extracted["open_threads"])
        thread.tags = json.dumps(extracted["tags"])
        thread.extraction_status = "done"
    except Exception as e:
        thread.extraction_status = "failed"
        thread.extraction_error = str(e)

    thread.updated_at = datetime.utcnow().isoformat()
    db.commit()
    db.refresh(thread)

    return thread.to_dict()


@app.get("/api/threads")
def list_threads(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    total = db.query(Thread).count()
    threads = (
        db.query(Thread)
        .order_by(Thread.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "threads": [t.to_dict() for t in threads],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: str, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread.to_dict()


@app.get("/api/threads/{thread_id}/raw")
def get_raw_transcript(thread_id: str, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if not thread.raw_transcript_path or not os.path.exists(thread.raw_transcript_path):
        raise HTTPException(status_code=404, detail="Raw transcript not found")
    messages = load_transcript(thread.raw_transcript_path)
    return {"messages": messages}


@app.get("/api/threads/{thread_id}/context")
def get_context(
    thread_id: str,
    format: str = Query(default="summary"),
    db: Session = Depends(get_db),
):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    t = thread.to_dict()

    if format == "full":
        if not thread.raw_transcript_path or not os.path.exists(thread.raw_transcript_path):
            raise HTTPException(status_code=404, detail="Raw transcript not found")
        messages = load_transcript(thread.raw_transcript_path)
        formatted = format_full_context(t, messages)
        token_estimate = len(formatted) // 4
        return {
            "formatted_context": formatted,
            "format": "full",
            "estimated_tokens": token_estimate,
        }
    else:
        formatted = format_summary_context(t)
        return {
            "formatted_context": formatted,
            "format": "summary",
        }


@app.post("/api/threads/{thread_id}/pull", status_code=201)
def record_pull(thread_id: str, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    event = PullEvent(
        id=str(uuid.uuid4()),
        thread_id=thread_id,
        pulled_at=datetime.utcnow().isoformat(),
    )
    db.add(event)
    db.commit()

    return {"id": event.id, "thread_id": event.thread_id, "pulled_at": event.pulled_at}


@app.post("/api/threads/{thread_id}/retry", status_code=200)
def retry_extraction(thread_id: str, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if not thread.raw_transcript_path or not os.path.exists(thread.raw_transcript_path):
        raise HTTPException(status_code=404, detail="Raw transcript not found")

    messages = load_transcript(thread.raw_transcript_path)

    thread.extraction_status = "processing"
    db.commit()

    try:
        extracted = extract_context(messages)
        thread.title = extracted["title"]
        thread.conversation_type = extracted["conversation_type"]
        thread.summary = extracted["summary"]
        thread.key_takeaways = json.dumps(extracted["key_takeaways"])
        thread.artifacts = json.dumps(extracted["artifacts"])
        thread.open_threads = json.dumps(extracted["open_threads"])
        thread.tags = json.dumps(extracted["tags"])
        thread.extraction_status = "done"
        thread.extraction_error = None
    except Exception as e:
        thread.extraction_status = "failed"
        thread.extraction_error = str(e)

    thread.updated_at = datetime.utcnow().isoformat()
    db.commit()
    db.refresh(thread)

    return thread.to_dict()


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total_threads = db.query(Thread).count()
    total_pulls = db.query(PullEvent).count()

    one_week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    threads_this_week = (
        db.query(Thread).filter(Thread.created_at >= one_week_ago).count()
    )
    pulls_this_week = (
        db.query(PullEvent).filter(PullEvent.pulled_at >= one_week_ago).count()
    )

    return {
        "total_threads": total_threads,
        "total_pulls": total_pulls,
        "threads_this_week": threads_this_week,
        "pulls_this_week": pulls_this_week,
    }
