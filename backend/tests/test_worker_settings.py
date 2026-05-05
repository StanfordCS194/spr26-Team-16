from __future__ import annotations

from contexthub_backend.jobs import tasks as tasks_module
from contexthub_backend.jobs.tasks import (
    WorkerSettings,
    cascade_delete_user,
    detect_stuck_pushes,
    embed_push_summaries,
    embed_summary,
    purge_audit_log,
    purge_failed_pushes,
    purge_revoked_tokens,
    purge_soft_deleted_pushes,
    requeue_push,
    summarize_push,
)


EXPECTED_FUNCTIONS = {
    summarize_push,
    embed_push_summaries,
    embed_summary,
    purge_soft_deleted_pushes,
    purge_failed_pushes,
    purge_audit_log,
    purge_revoked_tokens,
    cascade_delete_user,
    detect_stuck_pushes,
    requeue_push,
}


def test_worker_settings_registers_all_expected_functions():
    registered = set(WorkerSettings.functions)
    assert registered == EXPECTED_FUNCTIONS, (
        f"missing={EXPECTED_FUNCTIONS - registered}, "
        f"extra={registered - EXPECTED_FUNCTIONS}"
    )


def test_worker_settings_has_ten_functions():
    assert len(WorkerSettings.functions) == 10


def test_worker_settings_max_tries_is_three():
    assert WorkerSettings.max_tries == 3


def test_worker_settings_cron_jobs_is_list_of_five():
    assert isinstance(WorkerSettings.cron_jobs, list)
    assert len(WorkerSettings.cron_jobs) == 5


def test_worker_settings_cron_jobs_reference_expected_coroutines():
    expected_coroutines = {
        purge_soft_deleted_pushes,
        purge_failed_pushes,
        purge_audit_log,
        purge_revoked_tokens,
        detect_stuck_pushes,
    }
    referenced = {entry.coroutine for entry in WorkerSettings.cron_jobs}
    assert referenced == expected_coroutines, (
        f"missing={expected_coroutines - referenced}, "
        f"extra={referenced - expected_coroutines}"
    )


def test_worker_settings_each_cron_entry_has_coroutine_attribute():
    for entry in WorkerSettings.cron_jobs:
        assert hasattr(entry, "coroutine")
        assert callable(entry.coroutine)


def test_worker_settings_cron_includes_purge_soft_deleted_pushes():
    names = {entry.coroutine.__name__ for entry in WorkerSettings.cron_jobs}
    assert "purge_soft_deleted_pushes" in names


def test_worker_settings_cron_includes_purge_failed_pushes():
    names = {entry.coroutine.__name__ for entry in WorkerSettings.cron_jobs}
    assert "purge_failed_pushes" in names


def test_worker_settings_cron_includes_purge_audit_log():
    names = {entry.coroutine.__name__ for entry in WorkerSettings.cron_jobs}
    assert "purge_audit_log" in names


def test_worker_settings_cron_includes_purge_revoked_tokens():
    names = {entry.coroutine.__name__ for entry in WorkerSettings.cron_jobs}
    assert "purge_revoked_tokens" in names


def test_worker_settings_cron_includes_detect_stuck_pushes():
    names = {entry.coroutine.__name__ for entry in WorkerSettings.cron_jobs}
    assert "detect_stuck_pushes" in names


def test_worker_settings_cascade_delete_user_is_not_cron():
    cron_coroutines = {entry.coroutine for entry in WorkerSettings.cron_jobs}
    assert cascade_delete_user not in cron_coroutines


def test_worker_settings_requeue_push_is_not_cron():
    cron_coroutines = {entry.coroutine for entry in WorkerSettings.cron_jobs}
    assert requeue_push not in cron_coroutines


def test_worker_settings_summarize_push_is_not_cron():
    cron_coroutines = {entry.coroutine for entry in WorkerSettings.cron_jobs}
    assert summarize_push not in cron_coroutines


def test_worker_settings_module_exports_class():
    assert hasattr(tasks_module, "WorkerSettings")
    assert isinstance(tasks_module.WorkerSettings.functions, list)
