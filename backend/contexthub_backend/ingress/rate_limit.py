from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from contexthub_backend.api.errors import ForbiddenError


class RateLimiter:
    def __init__(self, per_minute: int, redis: Redis | None = None) -> None:
        self._per_minute = per_minute
        self._redis = redis
        self._counters: dict[str, list[datetime]] = defaultdict(list)

    async def check(self, *, user_id: str, bucket: str = "push", window_seconds: int = 60) -> None:
        key = f"rl:{user_id}:{bucket}:{window_seconds}"
        if self._redis is not None:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, window_seconds)
            if count > self._per_minute:
                raise ForbiddenError("rate limit exceeded")
            return

        now = datetime.now(UTC)
        window_start = now - timedelta(seconds=window_seconds)
        self._counters[key] = [t for t in self._counters[key] if t >= window_start]
        if len(self._counters[key]) >= self._per_minute:
            raise ForbiddenError("rate limit exceeded")
        self._counters[key].append(now)

