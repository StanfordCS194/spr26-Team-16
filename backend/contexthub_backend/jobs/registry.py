from __future__ import annotations

import asyncio
import logging
from typing import Any

from arq.connections import ArqRedis, RedisSettings, create_pool

from contexthub_backend.config import settings

logger = logging.getLogger(__name__)
_pool_lock = asyncio.Lock()
_pool: ArqRedis | None = None


async def get_arq_pool() -> ArqRedis | None:
    global _pool
    if not settings.redis_url:
        return None
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool


async def enqueue_job(job_name: str, **kwargs: Any) -> None:
    pool = await get_arq_pool()
    if pool is None:
        logger.warning("redis not configured, skipping enqueue", extra={"job_name": job_name})
        return
    await pool.enqueue_job(job_name, **kwargs)

