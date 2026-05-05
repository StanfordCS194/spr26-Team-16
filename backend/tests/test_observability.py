"""Unit tests for contexthub_backend.services.observability.

Pure unit, no DB. Each test sets caplog level on the
``contexthub.retention`` logger and asserts log records + structured extras.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from contexthub_backend.services.observability import (
    emit_retention_event,
    emit_stuck_push_alert,
    emit_user_deletion_receipt,
    posthog_event,
)
from contexthub_backend.services.retention import PurgeReport, StuckPushReport

LOGGER_NAME = "contexthub.retention"


def _records_for(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == LOGGER_NAME]


def _find_record(
    caplog: pytest.LogCaptureFixture,
    *,
    level: int | None = None,
    event: str | None = None,
    extra_key: str | None = None,
) -> logging.LogRecord | None:
    for r in _records_for(caplog):
        if level is not None and r.levelno != level:
            continue
        if event is not None and getattr(r, "event", None) != event:
            continue
        if extra_key is not None and not hasattr(r, extra_key):
            continue
        return r
    return None


# ---------------------------------------------------------------------------
# posthog_event
# ---------------------------------------------------------------------------


def test_posthog_event_logs_at_debug_with_structured_extra(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    posthog_event("some_event_name", {"a": 1, "b": "two"})

    records = _records_for(caplog)
    assert len(records) == 1
    rec = records[0]
    assert rec.levelno == logging.DEBUG
    assert rec.event == "posthog_pending"
    assert rec.event_name == "some_event_name"
    assert rec.properties == {"a": 1, "b": "two"}


def test_posthog_event_with_empty_properties_still_logs(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    posthog_event("empty_props", {})

    records = _records_for(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].event == "posthog_pending"
    assert records[0].properties == {}


# ---------------------------------------------------------------------------
# emit_retention_event
# ---------------------------------------------------------------------------


def _build_report(
    *,
    job: str = "test_job",
    rows_deleted: int = 5,
    started: datetime | None = None,
    finished: datetime | None = None,
    rows_by_table: dict[str, int] | None = None,
    storage_paths: list[str] | None = None,
    notes: list[str] | None = None,
) -> PurgeReport:
    rep = PurgeReport(job=job)
    rep.rows_deleted = rows_deleted
    rep.started_at = started
    rep.finished_at = finished
    if rows_by_table is not None:
        rep.rows_by_table = dict(rows_by_table)
    if storage_paths is not None:
        rep.storage_paths = list(storage_paths)
    if notes is not None:
        rep.notes = list(notes)
    return rep


def test_emit_retention_event_logs_info_with_full_payload(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    started = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(milliseconds=2500)
    report = _build_report(
        job="purge_failed_pushes",
        rows_deleted=5,
        started=started,
        finished=finished,
        rows_by_table={"pushes": 5},
        storage_paths=["a/b.json", "c/d.json"],
        notes=["ok"],
    )

    emit_retention_event(report)

    info = _find_record(caplog, level=logging.INFO, event="retention")
    debug = _find_record(caplog, level=logging.DEBUG, event="posthog_pending")
    assert info is not None
    assert debug is not None
    assert info.job == "purge_failed_pushes"
    assert info.rows_deleted == 5
    assert info.duration_ms == 2500
    assert info.rows_by_table == {"pushes": 5}
    assert info.storage_paths_purged == 2
    assert info.notes == ["ok"]
    # posthog stub mirrors the same payload
    assert debug.properties["job"] == "purge_failed_pushes"
    assert debug.properties["rows_deleted"] == 5
    assert debug.properties["duration_ms"] == 2500


def test_emit_retention_event_zero_rows_emits_warning(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    started = datetime(2026, 5, 1, tzinfo=timezone.utc)
    finished = started + timedelta(seconds=1)
    report = _build_report(
        job="purge_audit_log",
        rows_deleted=0,
        started=started,
        finished=finished,
        rows_by_table={},
    )

    emit_retention_event(report)

    records = _records_for(caplog)
    levels = sorted(r.levelno for r in records)
    assert levels == sorted([logging.INFO, logging.DEBUG, logging.WARNING])

    warning = _find_record(caplog, level=logging.WARNING, event="retention")
    assert warning is not None
    assert getattr(warning, "zero_purge_alert", None) is True
    assert warning.job == "purge_audit_log"
    assert warning.rows_deleted == 0


def test_emit_retention_event_no_timestamps_handles_none_duration(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    report = _build_report(
        job="purge_revoked_tokens",
        rows_deleted=3,
        started=None,
        finished=None,
    )

    emit_retention_event(report)

    info = _find_record(caplog, level=logging.INFO, event="retention")
    assert info is not None
    assert info.duration_ms is None


def test_emit_retention_event_only_started_set_handles_none_duration(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    report = _build_report(
        rows_deleted=2,
        started=datetime(2026, 5, 1, tzinfo=timezone.utc),
        finished=None,
    )

    emit_retention_event(report)

    info = _find_record(caplog, level=logging.INFO, event="retention")
    assert info is not None
    assert info.duration_ms is None


# ---------------------------------------------------------------------------
# emit_stuck_push_alert
# ---------------------------------------------------------------------------


def _stuck(idx: int = 0) -> StuckPushReport:
    return StuckPushReport(
        push_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        status="processing",
        minutes_stuck=10 + idx,
        failure_reason=None,
    )


def test_emit_stuck_push_alert_empty_list_no_op(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    emit_stuck_push_alert([])
    assert _records_for(caplog) == []


def test_emit_stuck_push_alert_with_pushes_warning(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    pushes = [_stuck(i) for i in range(3)]

    emit_stuck_push_alert(pushes)

    warning = _find_record(caplog, level=logging.WARNING, event="stuck_pushes")
    debug = _find_record(caplog, level=logging.DEBUG, event="posthog_pending")
    assert warning is not None
    assert debug is not None
    assert warning.count == 3
    assert isinstance(warning.threshold_minutes, int)
    assert isinstance(warning.push_ids, list)
    assert len(warning.push_ids) == 3
    for pid in warning.push_ids:
        # uuid.UUID(<str>) round-trips iff each entry is a stringified uuid
        uuid.UUID(pid)
    # posthog mirror
    assert debug.properties["count"] == 3
    assert len(debug.properties["push_ids"]) == 3


def test_emit_stuck_push_alert_truncates_at_50(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    pushes = [_stuck(i) for i in range(60)]

    emit_stuck_push_alert(pushes)

    warning = _find_record(caplog, level=logging.WARNING, event="stuck_pushes")
    assert warning is not None
    assert warning.count == 60
    assert len(warning.push_ids) == 50

    debug = _find_record(caplog, level=logging.DEBUG, event="posthog_pending")
    assert debug is not None
    assert debug.properties["count"] == 60
    assert len(debug.properties["push_ids"]) == 50


def test_emit_stuck_push_alert_single_item(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    pushes = [_stuck(0)]

    emit_stuck_push_alert(pushes)

    warning = _find_record(caplog, level=logging.WARNING, event="stuck_pushes")
    assert warning is not None
    assert warning.count == 1
    assert len(warning.push_ids) == 1


# ---------------------------------------------------------------------------
# emit_user_deletion_receipt
# ---------------------------------------------------------------------------


def test_emit_user_deletion_receipt_info_log(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    user_id = uuid.uuid4()
    started = datetime(2026, 5, 5, 10, 0, 0, tzinfo=timezone.utc)
    finished = started + timedelta(milliseconds=1234)
    report = _build_report(
        job="cascade_delete_user",
        rows_deleted=10,
        started=started,
        finished=finished,
        rows_by_table={"pushes": 4, "tags": 1, "workspaces": 1, "profiles": 1},
        storage_paths=["foo.json"],
    )

    emit_user_deletion_receipt(report, user_id)

    info = _find_record(caplog, level=logging.INFO, event="user_deletion")
    debug = _find_record(caplog, level=logging.DEBUG, event="posthog_pending")
    assert info is not None
    assert debug is not None
    assert info.user_id == str(user_id)
    assert info.rows_by_table == {
        "pushes": 4,
        "tags": 1,
        "workspaces": 1,
        "profiles": 1,
    }
    assert info.storage_paths_purged == 1
    assert info.duration_ms == 1234

    # posthog mirror fires with same shape
    assert debug.properties["user_id"] == str(user_id)
    assert debug.properties["duration_ms"] == 1234
    assert debug.properties["storage_paths_purged"] == 1


def test_emit_user_deletion_receipt_accepts_string_user_id(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    user_id_str = "11111111-2222-3333-4444-555555555555"
    report = _build_report(
        job="cascade_delete_user",
        rows_deleted=0,
        rows_by_table={},
    )

    emit_user_deletion_receipt(report, user_id_str)

    info = _find_record(caplog, level=logging.INFO, event="user_deletion")
    assert info is not None
    assert info.user_id == user_id_str
    assert info.duration_ms is None


def test_emit_user_deletion_receipt_no_timestamps_duration_none(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    user_id = uuid.uuid4()
    report = _build_report(
        rows_deleted=1,
        started=None,
        finished=None,
        rows_by_table={"pushes": 1},
    )

    emit_user_deletion_receipt(report, user_id)

    info = _find_record(caplog, level=logging.INFO, event="user_deletion")
    debug = _find_record(caplog, level=logging.DEBUG, event="posthog_pending")
    assert info is not None
    assert debug is not None
    assert info.duration_ms is None
    assert debug.properties["duration_ms"] is None
