"""Thin observability hook layer (ARCHITECTURE.md §13, TODO.md Module 16).

Retention jobs and other callers emit structured events through this module
without taking a hard dependency on Sentry, PostHog, or any other telemetry
SDK. Today every emission is just a JSON-extra log line on the
``contexthub.retention`` logger; downstream collectors (Loki/Datadog/etc.)
can index those lines until Module 16 wires real Sentry + PostHog clients.

When Module 16 lands, the bodies of these functions get swapped for real
SDK calls — call sites do not change. The ``posthog_event`` helper exists
specifically to let us count events end-to-end before the PostHog client
is configured: the retention emitters bridge through it so the migration
is a one-file swap.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from contexthub_backend.services.retention import PurgeReport, StuckPushReport

from contexthub_backend.config import settings

_logger = logging.getLogger("contexthub.retention")


def _duration_ms(report: "PurgeReport") -> int | None:
    if report.started_at is None or report.finished_at is None:
        return None
    delta = report.finished_at - report.started_at
    return int(delta.total_seconds() * 1000)


def posthog_event(event_name: str, properties: dict[str, Any]) -> None:
    """Stub for the real Module 16 PostHog client.

    Logs a structured DEBUG line so events are countable in log aggregators
    until ``posthog.capture`` replaces this body. Call sites stay stable.
    """
    _logger.debug(
        "posthog_pending:%s",
        event_name,
        extra={
            "event": "posthog_pending",
            "event_name": event_name,
            "properties": properties,
        },
    )


def emit_retention_event(report: "PurgeReport") -> None:
    """Emit a structured event for one retention purge run.

    Bridges through ``posthog_event`` with the same payload so the future
    PostHog migration does not need to touch retention call sites. Also
    fires a WARNING-level "zero_purge_alert" when the run deleted nothing
    (PLAN.md:115 — alerts on retention silently doing no work).
    """
    duration_ms = _duration_ms(report)
    properties: dict[str, Any] = {
        "job": report.job,
        "rows_deleted": report.rows_deleted,
        "rows_by_table": dict(report.rows_by_table),
        "duration_ms": duration_ms,
        "storage_paths_purged": len(report.storage_paths),
        "notes": list(report.notes),
    }

    _logger.info(
        "retention:%s",
        report.job,
        extra={"event": "retention", **properties},
    )
    posthog_event("push_retention_purge", properties)

    if report.rows_deleted == 0:
        _logger.warning(
            "retention_zero_purge:%s",
            report.job,
            extra={
                "event": "retention",
                "zero_purge_alert": True,
                **properties,
            },
        )


def emit_stuck_push_alert(stuck_pushes: list["StuckPushReport"]) -> None:
    """Sentry alert hook for the stuck-push detector (PLAN.md:110, TODO.md:46).

    No-op when nothing is stuck — INFO-level "all clear" pings would just
    drown out real signal.
    """
    if not stuck_pushes:
        return

    properties: dict[str, Any] = {
        "count": len(stuck_pushes),
        "threshold_minutes": settings.stuck_push_minutes,
        "push_ids": [str(s.push_id) for s in stuck_pushes[:50]],
    }
    _logger.warning(
        "stuck_pushes:%d",
        len(stuck_pushes),
        extra={"event": "stuck_pushes", **properties},
    )
    posthog_event("stuck_push_alert", properties)


def emit_user_deletion_receipt(
    report: "PurgeReport",
    user_id: uuid.UUID | str,
) -> None:
    """GDPR erasure receipt — the structured log line *is* the receipt.

    Downstream log collectors index by ``event=user_deletion`` so the
    receipt is queryable without a separate audit store.
    """
    properties: dict[str, Any] = {
        "user_id": str(user_id),
        "rows_by_table": dict(report.rows_by_table),
        "storage_paths_purged": len(report.storage_paths),
        "duration_ms": _duration_ms(report),
    }
    _logger.info(
        "user_deletion:%s",
        user_id,
        extra={"event": "user_deletion", **properties},
    )
    posthog_event("user_deletion", properties)
