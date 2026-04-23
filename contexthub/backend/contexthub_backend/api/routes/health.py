from fastapi import APIRouter
from contexthub_backend.config import settings

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict:
    return {"version": settings.app_version}
