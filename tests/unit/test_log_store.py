"""Offline durability, boundedness, closed-schema and filesystem qualification."""

from __future__ import annotations

import json
import multiprocessing
import os
import queue
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from media_sync.infrastructure.observability import store as storage
from media_sync.infrastructure.observability.events import (
    EventValidationError,
    format_time,
    validate_event,
    validate_record,
)
from media_sync.infrastructure.observability.store import LogStore, LogStoreError

BASE = {"event_code": "service_started", "module": "api", "level": "info"}


@pytest.fixture
def factory(tmp_path: Path) -> Iterator[Callable[..., LogStore]]:
    stores: list[LogStore] = []

    def make(root: Path | None = None, **kwargs: Any) -> LogStore:
        result = LogStore(root or tmp_path / "logs", **kwargs)
        stores.append(result)
        return result

    yield make
    for instance in stores:
        instance.close()


@pytest.mark.parametrize(
    "addition",
    [
        {"message": "COOKIE_SECRET_SENTINEL"},
        {"args": ["SECRET"]},
        {"exception": "secret"},
        {"url": "https://secret.invalid"},
        {"module": "SECRET"},
        {"event_code": "SECRET"},
        {"phase": "SECRET"},
        {"action": "SECRET"},
        {"outcome": "SECRET"},
        {"error_type": "SECRET"},
        {"source_frame": "SECRET"},
        {"level": "SECRET"},
        {"platform": "SECRET"},
        {"account_id": "SECRET"},
        {"operation_id": None},
        {"count": True},
        {"count": -1},
        {"count": 2**64},
        {"count": 1.5},
        {"writer_id": str(uuid4())},
        {"sequence": 1},
        {"timestamp": "2026-09-06T00:00:00.000000Z"},
        {"http_status": 99},
        {"http_status": 600},
        {"http_status": True},
    ],
)
def test_rejected_frames_are_not_sanitized_or_retained(
    factory: Callable[..., LogStore], addition: dict[str, object]
) -> None:
    instance = factory()
    assert not instance.emit({**BASE, **addition})
    assert instance.query()["events"] == []
    status = instance.status()
    assert status["invalid"] == status["dropped"] == 1
    assert "SECRET" not in json.dumps(status)
    assert all(b"SECRET" not in file.read_bytes() for file in instance.root.iterdir())


def test_parent_minted_records_survive_restart(factory: Callable[..., LogStore]) -> None:
    instance = factory()
    operation_id = str(uuid4())
    event = {**BASE, "operation_id": operation_id}
    assert instance.emit(event)
    assert instance.flush()
    event["module"] = "SECRET"
    first = instance.query()["events"][0]
    assert first["module"] == "api"
    assert first["operation_id"] == operation_id
    assert first["writer_id"] == instance.writer_id
    assert first["sequence"] == 1
    assert validate_record(first) == first
    instance.close()
    second = factory()
    assert second.query()["events"] == [first]
    assert second.status()["sealed_segments"] == 1
    assert second.status()["active_segments"] == 0


def test_login_schema_requires_complete_closed_stage() -> None:
    stage = {
        **BASE,
        "module": "login",
        "event_code": "login_stage",
        "phase": "qr_image_fetch",
        "action": "fetch",
        "outcome": "failed",
        "error_type": "playwright_timeout",
        "duration_ms": 300,
        "source_frame": "httpx_get",
    }
    assert validate_event(stage) == stage
    for key in ("phase", "action", "outcome", "error_type", "duration_ms"):
        with pytest.raises(EventValidationError, match=r"^log_event_invalid$"):
            validate_event({name: value for name, value in stage.items() if name != key})
    assert validate_event({**stage, "event_code": "login_terminal"})["event_code"] == "login_terminal"
    with pytest.raises(EventValidationError):
        format_time(datetime(2026, 1, 1))


def test_rotation_never_overwrites_and_pages_across_rotated_active_segment(factory: Callable[..., LogStore]) -> None:
    instance = factory(segment_max_bytes=1300, total_max_bytes=30_000)
    for count in range(4):
        assert instance.emit({**BASE, "count": count})
    assert instance.flush()
    page = instance.query(limit=1)
    events = list(page["events"])
    while page["next_cursor"]:
        page = instance.query(limit=1, cursor=page["next_cursor"])
        events.extend(page["events"])
    assert [event["count"] for event in events] == list(range(4))
    assert instance.status()["managed_segments"] >= 2
    assert all(file.stat().st_size <= 1300 for file in instance.root.glob("log-*"))
    instance.close()
    assert instance.status()["active_segments"] == 0


def test_cursor_is_filter_bound_and_stale_after_restart(factory: Callable[..., LogStore]) -> None:
    instance = factory()
    for _ in range(2):
        instance.emit(BASE)
    assert instance.flush()
    token = instance.query(limit=1)["next_cursor"]
    assert token
    with pytest.raises(LogStoreError, match=r"^log_cursor_invalid$"):
        instance.query(cursor=token, module="api")
    second = factory()
    with pytest.raises(LogStoreError, match=r"^log_cursor_stale$"):
        second.query(cursor=token)
    for bad in ("../../outside", "x" * 2049, 5):
        with pytest.raises(LogStoreError, match=r"^log_cursor_invalid$"):
            instance.query(cursor=bad)


@pytest.mark.parametrize(
    "filters",
    [
        {"limit": 0},
        {"limit": 201},
        {"limit": True},
        {"limit": "20"},
        {"module": "secret"},
        {"route": "secret"},
        {"operation_id": "../secret"},
        {"since": "not-time"},
        {"since": "2026-09-07T00:00:00.000000Z", "until": "2026-09-06T00:00:00.000000Z"},
    ],
)
def test_invalid_query_is_fixed_error(factory: Callable[..., LogStore], filters: dict[str, object]) -> None:
    with pytest.raises(LogStoreError, match=r"^log_query_invalid$"):
        factory().query(**filters)


def test_all_correlation_filters_and_time_bounds(factory: Callable[..., LogStore]) -> None:
    instance = factory()
    ids = {
        name: str(uuid4())
        for name in (
            "operation_id",
            "correlation_id",
            "account_id",
            "login_session_id",
            "job_id",
            "run_id",
            "subscription_id",
        )
    }
    before = format_time(datetime.now(UTC) - timedelta(seconds=1))
    instance.emit({**BASE, **ids, "platform": "bili"})
    instance.emit({**BASE, "platform": "dy"})
    assert instance.flush()
    for key, value in ids.items():
        assert len(instance.query(**{key: value})["events"]) == 1
    assert (
        len(
            instance.query(
                platform="bili",
                module="api",
                level="info",
                event_code="service_started",
                since=before,
                until=format_time(datetime.now(UTC)),
            )["events"]
        )
        == 1
    )


def test_global_capacity_prunes_only_sealed_segments(factory: Callable[..., LogStore], tmp_path: Path) -> None:
    first = factory(segment_max_bytes=1300, total_max_bytes=3500)
    assert first.emit({**BASE, "count": 777})
    assert first.flush()
    active = next(first.root.glob("*.open"))
    preserved = active.read_bytes()
    second = factory(segment_max_bytes=1300, total_max_bytes=3500)
    for count in range(20):
        second.emit({**BASE, "count": count})
    assert second.flush(timeout=5)
    assert active.read_bytes() == preserved
    assert second.status()["capacity_deleted"] > 0
    assert second.status()["storage_bytes"] <= 3500
    assert second.query()["coverage"]["retention_may_have_removed"] is True


def test_capacity_exhaustion_drops_without_deleting_active_or_foreign_file(factory: Callable[..., LogStore]) -> None:
    first = factory(segment_max_bytes=1300, total_max_bytes=2100)
    first.emit(BASE)
    assert first.flush()
    active = next(first.root.glob("*.open"))
    foreign = first.root / "notes.txt"
    foreign.write_bytes(b"FOREIGN" * 250)
    first.emit(BASE)
    assert not first.flush()
    assert first.status()["last_error"] == "log_capacity_exhausted"
    assert first.status()["dropped"] == 1
    assert active.exists()
    assert foreign.read_bytes() == b"FOREIGN" * 250


def test_async_queue_acceptance_is_not_durability(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = threading.Event(), threading.Event()
    original = LogStore._append

    def held(instance: LogStore, root: storage._Root, event: dict[str, object]) -> None:
        entered.set()
        assert release.wait(timeout=5)
        original(instance, root, event)

    monkeypatch.setattr(LogStore, "_append", held)
    instance = factory(queue_capacity=1)
    try:
        assert instance.emit(BASE)
        assert entered.wait(timeout=2)
        assert instance.emit(BASE)
        assert not instance.emit(BASE)
        assert instance._written == 0
    finally:
        release.set()
    assert instance.flush()
    assert instance.status()["written"] == 2
    assert instance.status()["dropped"] == 1
    assert instance.status()["last_error"] == "log_queue_full"


def test_unavailable_directory_does_not_raise_from_emit(factory: Callable[..., LogStore], tmp_path: Path) -> None:
    blocked = tmp_path / "file-not-directory"
    blocked.write_bytes(b"SECRET")
    instance = factory(blocked / "logs")
    assert instance.emit(BASE)
    assert not instance.flush()
    assert instance.status()["health"] == "unavailable"
    with pytest.raises(LogStoreError, match=r"^log_store_unavailable$"):
        instance.query()
    assert blocked.read_bytes() == b"SECRET"


def test_corrupt_and_partial_records_are_visible_but_never_returned(factory: Callable[..., LogStore]) -> None:
    instance = factory()
    instance.emit(BASE)
    assert instance.flush()
    active = next(instance.root.glob("*.open"))
    with active.open("ab") as stream:
        stream.write(b'{"message":"COOKIE_SECRET_SENTINEL"}\n{"message":"TRUNCATED_SECRET"')
    page = instance.query()
    assert len(page["events"]) == 1
    assert page["coverage"]["corrupt_records"] == 1
    assert page["coverage"]["truncated_segments"] == 1
    assert "SECRET" not in json.dumps(page)


def test_forged_or_corrupt_seal_is_not_deleted(factory: Callable[..., LogStore]) -> None:
    instance = factory(segment_max_bytes=1300, total_max_bytes=2200)
    instance.emit(BASE)
    assert instance.flush()
    instance.close()
    segment = next(instance.root.glob("*.jsonl"))
    original = segment.read_bytes()
    segment.write_bytes(original[:-10] + b"XXXXXXXXX\n")
    second = factory(segment_max_bytes=1300, total_max_bytes=2200)
    second.emit(BASE)
    assert not second.flush()
    assert second.query()["coverage"]["unavailable_segments"] == 1
    assert segment.read_bytes() == original[:-10] + b"XXXXXXXXX\n"


def test_hardlink_is_not_read_or_deleted(factory: Callable[..., LogStore], tmp_path: Path) -> None:
    instance = factory()
    instance.emit(BASE)
    assert instance.flush()
    instance.close()
    segment = next(instance.root.glob("*.jsonl"))
    outside = tmp_path / "external-copy"
    os.link(segment, outside)
    second = factory()
    assert second.query()["events"] == []
    assert second.query()["coverage"]["unavailable_segments"] == 1
    second.emit(BASE)
    assert not second.flush()
    assert outside.read_bytes() == segment.read_bytes()


def test_symlink_ancestor_rejected_before_creation(factory: Callable[..., LogStore], tmp_path: Path) -> None:
    target = tmp_path / "outside"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted on this host")
    instance = factory(link / "logs")
    instance.emit(BASE)
    assert not instance.flush()
    assert not (target / "logs").exists()


def test_scan_budget_is_explicit_and_does_not_scan_all_files(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = factory()
    instance.emit(BASE)
    assert instance.flush()
    monkeypatch.setattr(storage, "_MAX_ENTRIES", 2)
    assert instance.status()["scan_limited"] is True
    with pytest.raises(LogStoreError, match=r"^log_store_scan_limited$"):
        instance.query()


def test_read_byte_budget_returns_continuation(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = factory()
    for _ in range(4):
        instance.emit(BASE)
    assert instance.flush()
    monkeypatch.setattr(storage, "_MAX_SCAN_BYTES", 250)
    page = instance.query(limit=200)
    assert 0 < len(page["events"]) < 4
    assert page["next_cursor"]
    assert page["coverage"]["scan_limited"] is True


def _process_writer(root: str, result: Any, count: int, total: int = 50_000) -> None:
    instance = LogStore(root, segment_max_bytes=1600, total_max_bytes=total)
    for index in range(count):
        instance.emit({**BASE, "count": index})
    flushed = instance.flush(timeout=5)
    instance.close()
    result.put({"flushed": flushed, "writer_id": instance.writer_id})


def test_process_writers_do_not_overwrite_each_other(factory: Callable[..., LogStore], tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    result = context.Queue()
    root = tmp_path / "process-logs"
    processes = [context.Process(target=_process_writer, args=(str(root), result, 8)) for _ in range(2)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=20)
            assert process.exitcode == 0
        results = [result.get(timeout=2) for _ in processes]
        assert all(item["flushed"] for item in results)
        instance = factory(root, segment_max_bytes=1600, total_max_bytes=50_000)
        events = instance.query(limit=200)["events"]
        assert len(events) == 16
        assert {event["writer_id"] for event in events} == {item["writer_id"] for item in results}
        assert len({(event["writer_id"], event["sequence"]) for event in events}) == 16
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        result.close()


def test_close_rejects_new_events_with_fixed_safe_status(factory: Callable[..., LogStore]) -> None:
    instance = factory()
    instance.close()
    assert not instance.emit(BASE)
    assert instance.status()["health"] == "closed"
    assert instance.status()["last_error"] == "log_store_closed"
    assert "root" not in instance.status()
    assert str(instance.root) not in json.dumps(instance.status())


def test_utc_day_rotation_and_retention_preserve_other_active_writer(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Clock(datetime):
        current = datetime(2026, 8, 1, 23, 59, tzinfo=UTC)

        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return cls.current

    monkeypatch.setattr(storage, "datetime", Clock)
    first = factory()
    first.emit(BASE)
    assert first.flush()
    protected = next(first.root.glob("*.open"))
    protected_data = protected.read_bytes()
    second = factory()
    second.emit(BASE)
    assert second.flush()
    Clock.current += timedelta(minutes=2)
    second.emit(BASE)
    assert second.flush()
    assert second.status()["sealed_segments"] == 1
    assert second.status()["active_segments"] == 2
    second.close()
    Clock.current += timedelta(days=10)
    third = factory()
    third.emit(BASE)
    assert third.flush()
    assert third.status()["retention_deleted"] == 2
    assert protected.read_bytes() == protected_data
    assert len(third.query()["events"]) == 2


def test_cursor_to_pruned_segment_reports_stale(factory: Callable[..., LogStore]) -> None:
    instance = factory(segment_max_bytes=1500, total_max_bytes=2500)
    for _ in range(2):
        instance.emit(BASE)
    assert instance.flush()
    token = instance.query(limit=1)["next_cursor"]
    assert token
    for count in range(15):
        instance.emit({**BASE, "count": count})
    assert instance.flush(timeout=5)
    with pytest.raises(LogStoreError, match=r"^log_cursor_stale$"):
        instance.query(cursor=token)


def test_parent_identity_replacement_rejected_before_unlink(tmp_path: Path) -> None:
    root_path = tmp_path / "logs"
    root_path.mkdir()
    managed = root_path / "managed"
    managed.write_bytes(b"managed")
    with storage._Root(root_path, create=False) as root:
        expected = storage._identity(root.details("managed"))
        if os.name == "nt":
            with pytest.raises(PermissionError):
                root_path.rename(tmp_path / "moved")
        else:
            root_path.rename(tmp_path / "moved")
            root_path.mkdir()
            (root_path / "managed").write_bytes(b"FOREIGN")
            with pytest.raises(LogStoreError):
                root.unlink("managed", expected)
            assert (root_path / "managed").read_bytes() == b"FOREIGN"


def test_leaf_replacement_rejected_before_unlink(tmp_path: Path) -> None:
    root_path = tmp_path / "logs"
    root_path.mkdir()
    managed = root_path / "managed"
    managed.write_bytes(b"managed")
    with storage._Root(root_path, create=False) as root:
        expected = storage._identity(root.details("managed"))
        managed.rename(root_path / "old")
        managed.write_bytes(b"FOREIGN")
        with pytest.raises(LogStoreError):
            root.unlink("managed", expected)
        assert managed.read_bytes() == b"FOREIGN"


def test_unexpected_disk_failure_is_redacted_and_worker_continues(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    original = LogStore._append

    def fail(instance: LogStore, root: storage._Root, event: dict[str, object]) -> None:
        raise RuntimeError("COOKIE_SECRET_SENTINEL")

    monkeypatch.setattr(LogStore, "_append", fail)
    instance = factory()
    instance.emit(BASE)
    assert not instance.flush()
    assert "SECRET" not in json.dumps(instance.status())
    monkeypatch.setattr(LogStore, "_append", original)
    instance.emit(BASE)
    assert not instance.flush()  # The earlier accepted event cannot become durable retroactively.
    assert instance.status()["written"] == 1
    assert len(instance.query()["events"]) == 1


def test_disappearing_segment_is_coverage_loss_not_path_escape(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = factory()
    instance.emit(BASE)
    assert instance.flush()
    instance.close()
    original = storage._read_optional

    def remove(root: storage._Root, name: str) -> Any:
        (root.path / name).unlink()
        return original(root, name)

    monkeypatch.setattr(storage, "_read_optional", remove)
    page = instance.query()
    assert page["events"] == []
    assert page["coverage"]["unavailable_segments"] == 1


def test_lazy_writer_releases_thread_when_idle_and_reuses_same_segment(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage, "_IDLE_SECONDS", 0.05)
    instance = factory()
    assert instance._worker is None
    assert instance.status()["writer_running"] is False
    assert instance.query()["events"] == []
    assert instance._worker is None
    instance.emit(BASE)
    assert instance.flush()
    with instance._condition:
        assert instance._condition.wait_for(lambda: instance._worker is None, timeout=2)
    segment = next(instance.root.glob("*.open"))
    instance.emit(BASE)
    assert instance.flush()
    with instance._condition:
        assert instance._condition.wait_for(lambda: instance._worker is None, timeout=2)
    assert list(instance.root.glob("*.open")) == [segment]
    instance.close()
    assert instance.status()["shutdown_complete"] is True
    assert instance.status()["active_segments"] == 0
    assert len(instance.query()["events"]) == 2


def test_oversized_line_reports_omitted_segment_tail(factory: Callable[..., LogStore]) -> None:
    instance = factory()
    instance.emit(BASE)
    assert instance.flush()
    segment = next(instance.root.glob("*.open"))
    with segment.open("ab") as stream:
        stream.write(b"SECRET" * 2000 + b"\n" + b"{}\n")
    page = instance.query()
    assert len(page["events"]) == 1
    assert page["coverage"]["omitted_segment_tails"] == 1
    assert "SECRET" not in json.dumps(page)


def test_emit_during_idle_transition_never_loses_accepted_event(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage, "_IDLE_SECONDS", 0.01)
    instance = factory()
    for _ in range(6):
        assert instance.emit(BASE)
        assert instance.flush()
        time.sleep(0.06)
    assert len(instance.query()["events"]) == 6
    assert instance.status()["dropped"] == 0


def test_close_timeout_reports_live_writer_and_undrained_queue(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = threading.Event(), threading.Event()
    original = LogStore._append

    def held(instance: LogStore, root: storage._Root, event: dict[str, object]) -> None:
        entered.set()
        assert release.wait(timeout=5)
        original(instance, root, event)

    monkeypatch.setattr(LogStore, "_append", held)
    instance = factory()
    instance.emit(BASE)
    assert entered.wait(timeout=2)
    worker = instance._worker
    assert worker is not None
    join = worker.join
    monkeypatch.setattr(worker, "join", lambda timeout: None)
    try:
        instance.close()
        status = instance.status()
        assert status["writer_running"] is True
        assert status["drained"] is False
        assert status["shutdown_complete"] is False
        assert instance._last_error == "log_flush_timeout"
    finally:
        release.set()
        join(timeout=3)
    assert instance.status()["shutdown_complete"] is True


def test_capacity_is_shared_by_real_processes(factory: Callable[..., LogStore], tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    result = context.Queue()
    root = tmp_path / "bounded-process-logs"
    processes = [context.Process(target=_process_writer, args=(str(root), result, 15, 3500)) for _ in range(2)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=20)
            assert process.exitcode == 0
        for _ in processes:
            result.get(timeout=2)
        instance = factory(root, segment_max_bytes=1600, total_max_bytes=3500)
        assert instance.status()["storage_bytes"] <= 3500
        assert sum(file.stat().st_size for file in root.iterdir()) <= 3500
        page = instance.query()
        assert 0 < len(page["events"]) < 30
        assert page["coverage"]["retention_may_have_removed"] is True
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        result.close()


def test_close_winning_idle_exit_race_always_seals_active_segment(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage, "_IDLE_SECONDS", 0)
    instance = factory()
    entered, release = threading.Event(), threading.Event()
    original_get = instance._queue.get

    def held_get(*args: Any, **kwargs: Any) -> dict[str, object]:
        if instance._queue.empty():
            entered.set()
            assert release.wait(timeout=3)
            raise queue.Empty
        return original_get(*args, **kwargs)

    monkeypatch.setattr(instance._queue, "get", held_get)
    assert instance.emit(BASE)
    assert instance.flush()
    assert entered.wait(timeout=2)
    closer = threading.Thread(target=instance.close)
    closer.start()
    try:
        assert instance._stop.wait(timeout=1)
    finally:
        release.set()
        closer.join(timeout=3)
    assert not closer.is_alive()
    assert instance.status()["shutdown_complete"] is True
    assert instance.status()["active_segments"] == 0
    assert instance.status()["sealed_segments"] == 1


def test_idle_close_sealing_io_stays_in_background_join_budget(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage, "_IDLE_SECONDS", 0.01)
    instance = factory()
    instance.emit(BASE)
    assert instance.flush()
    with instance._condition:
        assert instance._condition.wait_for(lambda: instance._worker is None, timeout=2)
    entered, release = threading.Event(), threading.Event()
    finish = LogStore._finish_writer
    original_join = threading.Thread.join
    finishing_threads: list[int | None] = []

    def held_finish(store: LogStore) -> None:
        finishing_threads.append(threading.current_thread().ident)
        entered.set()
        assert release.wait(timeout=3)
        finish(store)

    def short_join(thread: threading.Thread, timeout: float | None = None) -> None:
        original_join(thread, timeout=0.01)

    monkeypatch.setattr(LogStore, "_finish_writer", held_finish)
    monkeypatch.setattr(threading.Thread, "join", short_join)
    try:
        started = time.monotonic()
        instance.close()
        assert time.monotonic() - started < 0.5
        assert entered.wait(timeout=1)
        assert finishing_threads == [instance._worker.ident]
        assert finishing_threads[0] != threading.current_thread().ident
        assert instance.status()["writer_running"] is True
        assert instance.status()["shutdown_complete"] is False
        assert instance.status()["last_error"] == "log_flush_timeout"
    finally:
        release.set()
        worker = instance._worker
        if worker is not None:
            original_join(worker, timeout=2)
    assert instance.status()["shutdown_complete"] is True
    assert instance.status()["active_segments"] == 0


def test_failed_seal_never_claims_shutdown_complete(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = factory()
    instance.emit(BASE)
    assert instance.flush()

    def fail_seal(store: LogStore, root: storage._Root) -> None:
        raise OSError("SECRET")

    monkeypatch.setattr(LogStore, "_seal_active", fail_seal)
    instance.close()
    status = instance.status()
    assert status["writer_running"] is False
    assert status["drained"] is True
    assert status["shutdown_complete"] is False
    assert status["last_error"] == "log_store_unavailable"
    assert status["active_segments"] == 1
    assert "SECRET" not in json.dumps(status)


def test_transient_rotation_rename_failure_does_not_poison_writer(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = factory(segment_max_bytes=1300, total_max_bytes=10_000)
    instance.emit(BASE)
    assert instance.flush()
    rename = storage._Root.seal
    attempts = 0

    def transient(root: storage._Root, name: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("synthetic Windows reader sharing conflict")
        return rename(root, name)

    monkeypatch.setattr(storage._Root, "seal", transient)
    instance.emit(
        {
            **BASE,
            **{
                name: str(uuid4())
                for name in (
                    "operation_id",
                    "correlation_id",
                    "account_id",
                    "login_session_id",
                    "subscription_id",
                    "job_id",
                )
            },
        }
    )
    assert not instance.flush()
    assert instance._active_sealing is True
    instance.emit(BASE)
    assert not instance.flush()  # The failed accepted event remains visible as loss.
    assert instance.status()["written"] == 2
    assert instance.status()["dropped"] == 1
    assert attempts == 2
    assert instance._active_sealing is False
    assert len(instance.query()["events"]) == 2
    instance.close()
    assert instance.status()["shutdown_complete"] is True


def test_close_can_retry_exact_already_written_footer_without_duplication(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    instance = factory()
    instance.emit(BASE)
    assert instance.flush()
    rename = storage._Root.seal

    def fail(root: storage._Root, name: str) -> str:
        raise PermissionError("SECRET")

    monkeypatch.setattr(storage._Root, "seal", fail)
    instance.close()
    active = next(instance.root.glob("*.open"))
    size_with_footer = active.stat().st_size
    assert instance.status()["shutdown_complete"] is False
    monkeypatch.setattr(storage._Root, "seal", rename)
    instance.close()
    assert instance.status()["shutdown_complete"] is True
    assert next(instance.root.glob("*.jsonl")).stat().st_size == size_with_footer
    assert len(instance.query()["events"]) == 1


def test_transient_thread_start_failure_preserves_queue_and_next_emit_recovers(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch
) -> None:
    original_start = threading.Thread.start
    attempts = 0

    def transient(thread: threading.Thread) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("SECRET thread resource exhaustion")
        original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", transient)
    instance = factory()
    assert instance.emit(BASE)
    assert instance._worker is None
    status = instance.status()
    assert status["queued"] == status["accepted"] == 1
    assert status["written"] == status["dropped"] == 0
    assert status["health"] == "degraded"
    assert status["last_error"] == "log_store_unavailable"
    assert "SECRET" not in json.dumps(status)
    assert instance.emit(BASE)
    assert instance.flush()
    assert instance.status()["written"] == 2
    assert len(instance.query()["events"]) == 2


@pytest.mark.parametrize("recover_via", ["close", "flush"])
def test_retained_queue_can_recover_start_failure_without_new_emit(
    factory: Callable[..., LogStore], monkeypatch: pytest.MonkeyPatch, recover_via: str
) -> None:
    original_start = threading.Thread.start

    def fail(thread: threading.Thread) -> None:
        raise RuntimeError("SECRET")

    monkeypatch.setattr(threading.Thread, "start", fail)
    instance = factory()
    assert instance.emit(BASE)
    assert instance._worker is None
    monkeypatch.setattr(threading.Thread, "start", original_start)
    if recover_via == "close":
        instance.close()
        assert instance.status()["shutdown_complete"] is True
    else:
        assert instance.flush()
    assert len(instance.query()["events"]) == 1
    assert instance.status()["dropped"] == 0
