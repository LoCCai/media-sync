"""Closed MediaCrawler failure-type x sink acceptance matrix."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Literal
from urllib.parse import quote
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from media_sync.domain import Platform
from media_sync.infrastructure.db import Database
from media_sync.infrastructure.db.models import Asset, Content, Job, Subscription, SyncRun
from media_sync.integrations.mediacrawler import runner as runner_module
from media_sync.integrations.mediacrawler.bridge import MediaCrawlerRunSpec
from media_sync.integrations.mediacrawler.policies import RunPaths, WatchdogLimits
from media_sync.integrations.mediacrawler.runner import (
    MediaCrawlerProcessResult,
    MediaCrawlerProcessRunner,
    MediaCrawlerProcessStatus,
)
from media_sync.interfaces.cli import (
    _emit_record,
    _scheduler_job_payload,
    _scheduler_lane_payload,
    _scheduler_worker_payload,
)
from media_sync.scheduler import mediacrawler_handler as mediacrawler_handler_module
from media_sync.scheduler.handlers import SubscriptionHandlerRegistry
from media_sync.scheduler.mediacrawler_handler import MediaCrawlerScheduledHandler
from media_sync.scheduler.repository import SchedulerRepository
from media_sync.scheduler.service import (
    DurableSchedulerService,
    SchedulerWorkerResult,
    SubscriptionWorker,
)
from media_sync.security import SecretValue
from tests.contract.test_mediacrawler_bridge import (
    FakeProject,
    _bridge,
    _make_fake_project,
)
from tests.integration.test_mediacrawler_scheduler_handler import _Clock, _seed

FailureControl = Literal["normal", "task_cancel", "lease_loss", "receipt_tamper"]
SinkName = Literal["filesystem", "sqlite", "operator"]

_SINKS: frozenset[SinkName] = frozenset({"filesystem", "sqlite", "operator"})


@dataclass(frozen=True, slots=True)
class _FailureCase:
    name: str
    creator: str
    limits: WatchdogLimits
    expected_process: MediaCrawlerProcessStatus
    expected_job: str
    expected_run: str
    expected_code: str | None
    control: FailureControl = "normal"
    sinks: frozenset[SinkName] = _SINKS


_DEFAULT_LIMITS = WatchdogLimits(max_seconds=8, poll_seconds=0.01)
_BLOCKING_LIMITS = WatchdogLimits(max_seconds=30, poll_seconds=0.01)
_FAILURE_CASES = (
    _FailureCase(
        "known_secret_echo",
        "mode-secret-echo",
        _DEFAULT_LIMITS,
        MediaCrawlerProcessStatus.COMPLETION_FAILED,
        "failed_terminal",
        "failed_terminal",
        "output_security_failed",
    ),
    _FailureCase(
        "nonzero_exit",
        "mode-raise",
        _DEFAULT_LIMITS,
        MediaCrawlerProcessStatus.UPSTREAM_FAILED,
        "retry_wait",
        "failed_retryable",
        "temporary_upstream",
    ),
    _FailureCase(
        "timeout",
        "mode-sleep",
        WatchdogLimits(max_seconds=4.0, poll_seconds=0.01),
        MediaCrawlerProcessStatus.TIMED_OUT,
        "retry_wait",
        "failed_retryable",
        "upstream_timeout",
    ),
    _FailureCase(
        "output_bytes",
        "mode-bytes",
        WatchdogLimits(max_seconds=8, max_output_bytes=256, poll_seconds=0.01),
        MediaCrawlerProcessStatus.OUTPUT_BYTES_EXCEEDED,
        "failed_terminal",
        "failed_terminal",
        "output_security_failed",
    ),
    _FailureCase(
        "output_items",
        "mode-items",
        WatchdogLimits(max_seconds=8, max_output_items=2, poll_seconds=0.01),
        MediaCrawlerProcessStatus.OUTPUT_ITEMS_EXCEEDED,
        "failed_terminal",
        "failed_terminal",
        "output_security_failed",
    ),
    _FailureCase(
        "output_files",
        "mode-files",
        WatchdogLimits(max_seconds=8, max_output_files=2, poll_seconds=0.01),
        MediaCrawlerProcessStatus.OUTPUT_FILES_EXCEEDED,
        "failed_terminal",
        "failed_terminal",
        "output_security_failed",
    ),
    _FailureCase(
        "output_line_bytes",
        "mode-line",
        WatchdogLimits(max_seconds=8, max_line_bytes=128, poll_seconds=0.01),
        MediaCrawlerProcessStatus.OUTPUT_LINE_EXCEEDED,
        "failed_terminal",
        "failed_terminal",
        "output_security_failed",
    ),
    _FailureCase(
        "output_tree",
        "mode-extension",
        _DEFAULT_LIMITS,
        MediaCrawlerProcessStatus.OUTPUT_TREE_INVALID,
        "failed_terminal",
        "failed_terminal",
        "output_security_failed",
    ),
    _FailureCase(
        "receipt_rejected",
        "mode-empty",
        _DEFAULT_LIMITS,
        MediaCrawlerProcessStatus.SUCCEEDED,
        "failed_terminal",
        "failed_terminal",
        "output_security_failed",
        control="receipt_tamper",
    ),
    _FailureCase(
        "cancellation",
        "mode-sleep",
        _BLOCKING_LIMITS,
        MediaCrawlerProcessStatus.CANCELLED,
        "running",
        "running",
        None,
        control="task_cancel",
    ),
    _FailureCase(
        "lease_loss",
        "mode-sleep",
        _BLOCKING_LIMITS,
        MediaCrawlerProcessStatus.CANCELLED,
        "cancelled",
        "cancelled",
        None,
        control="lease_loss",
    ),
)

_REQUIRED_FAILURE_CASES = frozenset(
    {
        "known_secret_echo",
        "nonzero_exit",
        "timeout",
        "output_bytes",
        "output_items",
        "output_files",
        "output_line_bytes",
        "output_tree",
        "receipt_rejected",
        "cancellation",
        "lease_loss",
    }
)
_DECLARED_MATRIX_CELLS = frozenset((case.name, sink) for case in _FAILURE_CASES for sink in case.sinks)
_REQUIRED_MATRIX_CELLS = frozenset((case_name, sink) for case_name in _REQUIRED_FAILURE_CASES for sink in _SINKS)


class _SentinelResolver:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls: list[str] = []

    def resolve(self, reference: str) -> SecretValue:
        self.calls.append(reference)
        return SecretValue(self.value)


class _MatrixRunner:
    """Expose a start barrier while retaining only fixed public results."""

    def __init__(self, *, tamper_sentinel: str | None = None) -> None:
        self.entered = Event()
        self.release = Event()
        self.specs: list[MediaCrawlerRunSpec] = []
        self.results: list[MediaCrawlerProcessResult] = []
        self.tamper_sentinel = tamper_sentinel
        self.inner = MediaCrawlerProcessRunner()

    def run(
        self,
        spec: MediaCrawlerRunSpec,
        cancellation: Event | None = None,
    ) -> MediaCrawlerProcessResult:
        self.specs.append(spec)
        self.entered.set()
        assert self.release.wait(timeout=5)
        result = self.inner.run(spec, cancellation)
        if self.tamper_sentinel is not None and result.succeeded:
            target = spec.paths.output_root / "xhs" / "jsonl" / "post-seal-tamper.jsonl"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(
                    {"private_runtime_value": self.tamper_sentinel},
                    ensure_ascii=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
                newline="\n",
            )
        self.results.append(result)
        return result


@pytest.fixture(scope="module")
def matrix_project(tmp_path_factory: pytest.TempPathFactory) -> FakeProject:
    return _make_fake_project(tmp_path_factory.mktemp("matrix-mediacrawler"))


def _runtime_contains(root: Path, needle: bytes) -> bool:
    try:
        root_metadata = root.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise AssertionError("filesystem scan could not inspect the retained root") from error
    if _metadata_is_link_or_reparse(root_metadata):
        raise AssertionError("filesystem scan root is a link or reparse point")
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise AssertionError("filesystem scan root is not a directory")
    if needle in os.fsencode(root.name):
        return True

    def fail_walk(error: OSError) -> None:
        raise AssertionError("filesystem scan could not traverse a retained directory") from error

    for directory, subdirectories, filenames in os.walk(
        root,
        followlinks=False,
        onerror=fail_walk,
    ):
        if any(needle in os.fsencode(name) for name in (*subdirectories, *filenames)):
            return True
        for name in subdirectories:
            metadata = _lstat_for_filesystem_scan(Path(directory) / name)
            if _metadata_is_link_or_reparse(metadata):
                raise AssertionError("filesystem scan encountered a symbolic-link directory")
            if not stat.S_ISDIR(metadata.st_mode):
                raise AssertionError("filesystem scan encountered a non-directory tree entry")
        for filename in filenames:
            path = Path(directory) / filename
            metadata = _lstat_for_filesystem_scan(path)
            if _metadata_is_link_or_reparse(metadata):
                raise AssertionError("filesystem scan encountered a symbolic-link file")
            if not stat.S_ISREG(metadata.st_mode):
                raise AssertionError("filesystem scan encountered a non-regular file")
            try:
                if needle in path.read_bytes():
                    return True
            except OSError as error:
                raise AssertionError("filesystem scan could not read a retained file") from error
    return False


def _lstat_for_filesystem_scan(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as error:
        raise AssertionError("filesystem scan could not inspect a retained path") from error


def _metadata_is_link_or_reparse(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(reparse_flag and file_attributes & reparse_flag)


def _wait_for_file_value(path: Path, value: str, *, timeout: float = 10.0) -> bool:
    needle = value.encode("utf-8")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if needle in path.read_bytes():
                return True
        except OSError:
            pass
        time.sleep(0.01)
    try:
        return needle in path.read_bytes()
    except OSError:
        return False


def _path_text_variants(path: Path) -> frozenset[str]:
    resolved = path.resolve()
    native = str(resolved)
    return frozenset(
        {
            native,
            resolved.as_posix(),
            json.dumps(native, ensure_ascii=True)[1:-1],
            quote(native, safe=""),
            quote(resolved.as_posix(), safe=""),
            resolved.as_uri(),
        }
    )


def _require_secret_absent(haystack: str | bytes, needle: str | bytes, *, sink: SinkName) -> None:
    if isinstance(haystack, str):
        if not isinstance(needle, str):
            raise TypeError("secret scan requires matching text or byte inputs")
        present = needle in haystack
    elif isinstance(needle, bytes):
        present = needle in haystack
    else:
        raise TypeError("secret scan requires matching text or byte inputs")
    if present:
        raise AssertionError(f"runtime secret reached the {sink} sink")


def _sqlite_logical_bytes(path: Path) -> bytes:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        chunks: list[bytes] = []
        table_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for table_name in table_names:
            quoted = '"' + str(table_name).replace('"', '""') + '"'
            for row in connection.execute(f"SELECT * FROM {quoted}"):
                for value in row:
                    if value is None:
                        continue
                    if isinstance(value, bytes):
                        chunks.append(value)
                    else:
                        chunks.append(str(value).encode("utf-8", errors="surrogatepass"))
        return b"\n".join(chunks)
    finally:
        connection.close()


def _sqlite_file_bytes(path: Path) -> bytes:
    chunks: list[bytes] = []
    for index, candidate in enumerate((path, Path(f"{path}-wal"), Path(f"{path}-shm"))):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            if index == 0:
                raise AssertionError("retained SQLite database is missing") from None
            continue
        except OSError as error:
            raise AssertionError("retained SQLite path could not be inspected") from error
        if _metadata_is_link_or_reparse(metadata):
            raise AssertionError("retained SQLite path is a link or reparse point")
        if not stat.S_ISREG(metadata.st_mode):
            raise AssertionError("retained SQLite path is not a regular file")
        try:
            chunks.append(candidate.read_bytes())
        except OSError as error:
            raise AssertionError("retained SQLite file could not be read") from error
    return b"".join(chunks)


def _assert_matrix_contract() -> None:
    assert frozenset(case.name for case in _FAILURE_CASES) == _REQUIRED_FAILURE_CASES
    assert len(_REQUIRED_FAILURE_CASES) == 11
    assert _DECLARED_MATRIX_CELLS == _REQUIRED_MATRIX_CELLS
    assert len(_REQUIRED_MATRIX_CELLS) == 33


def test_mediacrawler_security_matrix_declares_exactly_thirty_three_cells() -> None:
    _assert_matrix_contract()


def test_filesystem_sink_scanner_checks_path_names_and_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path_probe = "PATH_ONLY_SCAN_PROBE"
    (tmp_path / path_probe).write_bytes(b"ordinary content")
    assert _runtime_contains(tmp_path, path_probe.encode("utf-8"))
    named_root = tmp_path / "ROOT_NAME_SCAN_PROBE"
    named_root.mkdir()
    assert _runtime_contains(named_root, b"ROOT_NAME_SCAN_PROBE")

    non_directory_root = tmp_path / "ordinary-file"
    non_directory_root.write_bytes(b"ordinary content")
    with pytest.raises(AssertionError, match="filesystem scan root is not a directory"):
        _runtime_contains(non_directory_root, b"absent probe")

    def broken_walk(*args: object, **kwargs: object):
        del args
        onerror = kwargs.get("onerror")
        assert callable(onerror)
        onerror(PermissionError("fixed traversal failure"))
        return iter(())

    monkeypatch.setattr(os, "walk", broken_walk)
    with pytest.raises(
        AssertionError,
        match="filesystem scan could not traverse a retained directory",
    ):
        _runtime_contains(tmp_path, b"absent probe")


def test_sqlite_sink_scanner_requires_a_regular_database_and_sidecars(tmp_path: Path) -> None:
    database_path = tmp_path / "scan.sqlite3"
    with pytest.raises(AssertionError, match="retained SQLite database is missing"):
        _sqlite_file_bytes(database_path)

    database_path.write_bytes(b"sqlite probe")
    Path(f"{database_path}-wal").mkdir()
    with pytest.raises(AssertionError, match="retained SQLite path is not a regular file"):
        _sqlite_file_bytes(database_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _FAILURE_CASES, ids=lambda case: case.name)
async def test_mediacrawler_failure_matrix_checks_every_sink(
    case: _FailureCase,
    matrix_project: FakeProject,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_matrix_contract()
    sentinel = f"MATRIX_SECRET_{uuid4().hex}"
    sentinel_bytes = sentinel.encode("utf-8")
    runtime_root = tmp_path / "runtime"
    database_path = tmp_path / "matrix.sqlite3"
    database = Database(f"sqlite+pysqlite:///{database_path.as_posix()}")
    database.create_schema()
    disposed = False
    checked_cells: set[tuple[str, SinkName]] = set()
    sentinel_observed_before_cleanup = Event()
    original_runner_cleanup = runner_module._cleanup_failed_attempt
    original_handler_cleanup = mediacrawler_handler_module._cleanup_exact_attempt

    def observe_runner_cleanup(
        spec: MediaCrawlerRunSpec,
    ) -> runner_module.AttemptCleanupStatus:
        if _runtime_contains(spec.paths.job_root, sentinel_bytes):
            sentinel_observed_before_cleanup.set()
        return original_runner_cleanup(spec)

    def observe_handler_cleanup(paths: RunPaths) -> runner_module.AttemptCleanupStatus:
        if _runtime_contains(paths.job_root, sentinel_bytes):
            sentinel_observed_before_cleanup.set()
        return original_handler_cleanup(paths)

    monkeypatch.setattr(runner_module, "_cleanup_failed_attempt", observe_runner_cleanup)
    monkeypatch.setattr(
        mediacrawler_handler_module,
        "_cleanup_exact_attempt",
        observe_handler_cleanup,
    )

    try:
        _seed(
            database,
            platform=Platform.XHS,
            creator_remote_id=case.creator,
        )
        clock = _Clock()
        resolver_value = "matrix-benign-cookie" if case.control == "receipt_tamper" else sentinel
        resolver = _SentinelResolver(resolver_value)
        runner = _MatrixRunner(tamper_sentinel=sentinel if case.control == "receipt_tamper" else None)
        handler = MediaCrawlerScheduledHandler(
            database,
            lock_path=matrix_project.lock_path,
            integration_root=runtime_root,
            python_executable=Path(sys.executable),
            secret_resolver=resolver,
            enabled=True,
            license_acknowledged=True,
            bridge=_bridge(),
            runner=runner,
            clock=clock,
            watchdogs=case.limits,
        )
        scheduler = DurableSchedulerService(database, clock=clock)
        scheduler.tick(limit=1)
        worker_id = f"matrix-owner-{case.name}"
        worker = SubscriptionWorker(
            database,
            SubscriptionHandlerRegistry({"mediacrawler": handler}),
            clock=clock,
            random_fraction=lambda: 0.0,
        )
        task = asyncio.create_task(
            worker.run_once(
                worker_id=worker_id,
                heartbeat_interval_seconds=0.02,
            )
        )
        assert await asyncio.to_thread(runner.entered.wait, 5)
        with database.session() as session:
            running_job = session.scalar(select(Job).where(Job.job_type == "sync.subscription"))
            assert running_job is not None
            job_id = running_job.id
            lease_token = running_job.lease_token
            assert running_job.lease_owner == worker_id
            assert lease_token is not None
        runner.release.set()

        worker_result: SchedulerWorkerResult | None = None
        cancelled_error: asyncio.CancelledError | None = None
        if case.control in {"task_cancel", "lease_loss"}:
            output_probe = (
                runner.specs[0].paths.output_root / Platform.XHS.value / "jsonl" / "creator_contents_fixture.jsonl"
            )
            injection_ready = await asyncio.to_thread(
                _wait_for_file_value,
                output_probe,
                sentinel,
            )
            if not injection_ready:
                raise AssertionError("runtime secret injection did not become observable")
            if case.control == "task_cancel":
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=10)
                except asyncio.CancelledError as error:
                    cancelled_error = error
                else:  # pragma: no cover - the assertion below documents the public contract
                    raise AssertionError("task cancellation did not propagate")
            else:
                scheduler.cancel_job(job_id)
                worker_result = await asyncio.wait_for(task, timeout=10)
        else:
            worker_result = await asyncio.wait_for(task, timeout=15)

        assert len(runner.specs) == len(runner.results) == 1
        assert runner.results[0].status is case.expected_process
        spec = runner.specs[0]
        if not sentinel_observed_before_cleanup.is_set():
            raise AssertionError("runtime secret injection was not observed before cleanup")
        assert not spec.paths.job_root.exists() and not spec.paths.job_root.is_symlink()

        with database.session() as session:
            job = session.get(Job, job_id)
            run = session.scalar(select(SyncRun))
            subscription = session.scalar(select(Subscription))
            assert job is not None and run is not None and subscription is not None
            assert job.status == case.expected_job
            assert run.status == case.expected_run
            assert job.last_error_code == case.expected_code
            if case.control == "lease_loss":
                assert run.error_code == "scheduler_cancelled"
            else:
                assert run.error_code == case.expected_code
            assert session.scalar(select(func.count()).select_from(Content)) == 0
            assert session.scalar(select(func.count()).select_from(Asset)) == 0
            assert subscription.checkpoint_revision == 0
            if case.control == "task_cancel":
                assert job.lease_owner == worker_id
                assert job.lease_token == lease_token
            else:
                assert job.lease_owner is None
                assert job.lease_token is None
            repository = SchedulerRepository(session)
            job_snapshot = repository.get_job(job_id)
            lane_snapshots = repository.list_lanes()
            assert len(lane_snapshots) == 2
            assert {
                (lane.policy.scope_type, lane.policy.platform, lane.policy.account_id) for lane in lane_snapshots
            } == {
                ("platform", Platform.XHS.value, None),
                ("account", Platform.XHS.value, subscription.account_id),
            }
            expected_lane_failures = 0 if case.control in {"task_cancel", "lease_loss"} else 1
            for lane in lane_snapshots:
                assert lane.consecutive_failures == expected_lane_failures
                assert lane.circuit_state == "closed"
                assert lane.circuit_open_until is None
                assert lane.half_open_job_id is None
            operator_payloads = [_scheduler_job_payload(job_snapshot)]
            if worker_result is not None:
                operator_payloads.append(_scheduler_worker_payload(worker_result))
            operator_payloads.extend(_scheduler_lane_payload(lane) for lane in lane_snapshots)
            operator_objects = (job_snapshot, *lane_snapshots)

        for operator_payload in operator_payloads:
            _emit_record(operator_payload, json_output=True, label="matrix operator result")
        captured = capsys.readouterr()
        operator_text = "\n".join(
            (
                json.dumps(operator_payloads, ensure_ascii=True, sort_keys=True),
                captured.out,
                captured.err,
                *(repr(item) for item in operator_objects),
                *(str(item) for item in operator_objects),
                repr(worker_result),
                str(worker_result),
                repr(cancelled_error),
                str(cancelled_error),
                repr(runner.results[0]),
                str(runner.results[0]),
            )
        )
        _require_secret_absent(operator_text, sentinel, sink="operator")
        if worker_id in operator_text:
            raise AssertionError("lease owner reached the operator sink")
        if str(lease_token) in operator_text:
            raise AssertionError("lease token reached the operator sink")
        for private_root in (tmp_path, matrix_project.root):
            if any(variant in operator_text for variant in _path_text_variants(private_root)):
                raise AssertionError("local private root reached the operator sink")
        if ".quarantine" in operator_text:
            raise AssertionError("quarantine location reached the operator sink")
        if "Traceback" in operator_text:
            raise AssertionError("raw failure detail reached the operator sink")
        checked_cells.add((case.name, "operator"))

        database.dispose()
        disposed = True
        _require_secret_absent(
            _sqlite_logical_bytes(database_path),
            sentinel_bytes,
            sink="sqlite",
        )
        _require_secret_absent(
            _sqlite_file_bytes(database_path),
            sentinel_bytes,
            sink="sqlite",
        )
        checked_cells.add((case.name, "sqlite"))

        if _runtime_contains(tmp_path, sentinel_bytes):
            raise AssertionError("runtime secret reached the filesystem sink")
        checked_cells.add((case.name, "filesystem"))
        assert checked_cells == {(case.name, sink) for sink in _SINKS}
    finally:
        if not disposed:
            database.dispose()
