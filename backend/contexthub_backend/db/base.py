import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_sync_engine(url: str | None = None):
    url = url or os.environ["DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True)


def make_async_engine(url: str | None = None) -> AsyncEngine:
    url = url or os.environ["DATABASE_URL"]
    return create_async_engine(url, pool_pre_ping=True)
