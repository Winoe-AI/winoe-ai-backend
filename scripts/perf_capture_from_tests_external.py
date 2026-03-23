from __future__ import annotations

import inspect
import time

from perf_capture_from_tests_common import _REQUEST_PERF_CTX


def _add_external_wait(elapsed_ms: float) -> None:
    tracker = _REQUEST_PERF_CTX.get()
    if tracker is None:
        return
    tracker.external_wait_ms += elapsed_ms


def _wrap_async_method(plugin, cls: type, method_name: str) -> None:
    original = getattr(cls, method_name, None)
    if original is None or not inspect.iscoroutinefunction(original):
        return

    async def wrapped(*args, __orig=original, **kwargs):
        started_at = time.perf_counter()
        try:
            return await __orig(*args, **kwargs)
        finally:
            _add_external_wait((time.perf_counter() - started_at) * 1000.0)

    setattr(cls, method_name, wrapped)
    plugin._patched_external_methods.append((cls, method_name, original))


def _wrap_sync_method(plugin, cls: type, method_name: str) -> None:
    original = getattr(cls, method_name, None)
    if original is None or inspect.iscoroutinefunction(original):
        return

    def wrapped(*args, __orig=original, **kwargs):
        started_at = time.perf_counter()
        try:
            return __orig(*args, **kwargs)
        finally:
            _add_external_wait((time.perf_counter() - started_at) * 1000.0)

    setattr(cls, method_name, wrapped)
    plugin._patched_external_methods.append((cls, method_name, original))


def _wrap_many(plugin, cls: type, names: tuple[str, ...], *, async_methods: bool) -> None:
    wrapper = _wrap_async_method if async_methods else _wrap_sync_method
    for name in names:
        wrapper(plugin, cls, name)


def wrap_external_methods(plugin) -> None:
    from app.integrations.github.actions_runner import GithubActionsRunner
    from app.integrations.github.client import GithubClient
    from app.integrations.notifications.email_provider.memory import MemoryEmailProvider
    from app.integrations.storage_media.fake_provider import FakeStorageMediaProvider
    from app.services.notifications.email_sender import EmailSender

    _wrap_many(plugin, GithubClient, (
        "generate_repo_from_template", "add_collaborator", "remove_collaborator",
        "get_branch", "get_repo", "get_file_contents", "get_compare",
        "list_commits", "get_ref", "get_commit", "create_blob", "create_tree",
        "create_commit", "update_ref", "delete_repo", "archive_repo",
        "trigger_workflow_dispatch", "list_workflow_runs", "list_artifacts",
        "download_artifact_zip",
    ), async_methods=True)
    _wrap_many(plugin, GithubActionsRunner, ("dispatch_and_wait", "fetch_run_result"), async_methods=True)
    _wrap_many(plugin, EmailSender, ("send_email",), async_methods=True)
    _wrap_many(plugin, MemoryEmailProvider, ("send",), async_methods=True)
    _wrap_many(plugin, FakeStorageMediaProvider, (
        "create_signed_upload_url", "create_signed_download_url", "get_object_metadata", "delete_object"
    ), async_methods=False)


def restore_external_methods(plugin) -> None:
    for cls, method_name, original in reversed(plugin._patched_external_methods):
        setattr(cls, method_name, original)
    plugin._patched_external_methods.clear()


__all__ = ["restore_external_methods", "wrap_external_methods"]
