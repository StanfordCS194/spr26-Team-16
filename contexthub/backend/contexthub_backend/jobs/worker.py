from __future__ import annotations

from arq.connections import RedisSettings
from arq.worker import run_worker

from contexthub_backend.config import settings
from contexthub_backend.jobs.tasks import WorkerSettings


def start_worker() -> None:
    redis_dsn = settings.redis_url or "redis://localhost:6379"
    WorkerSettings.redis_settings = RedisSettings.from_dsn(redis_dsn)
    run_worker(WorkerSettings)
