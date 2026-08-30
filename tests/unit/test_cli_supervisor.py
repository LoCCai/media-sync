"""CLI contracts for the bounded foreground scheduler supervisor."""

from __future__ import annotations

import json
import os as os_module
import signal as signal_module
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

import media_sync.interfaces.cli as cli_module
from media_sync.config import get_settings
from media_sync.interfaces.cli import app
from media_sync.scheduler import ResidentSchedulerSupervisor, ResidentSupervisorResult

runner = CliRunner()


@pytest.fixture
def supervisor_cli_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MEDIA_SYNC_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("MEDIA_SYNC_ARCHIVE_DIR", str(tmp_path / "archive"))
    monkeypatch.setenv("MEDIA_SYNC_EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("MEDIA_SYNC_JOB_DIR", str(tmp_path / "jobs"))
    monkeypatch.setenv(
        "MEDIA_SYNC_DATABASE_URL",
        f"sqlite+pysqlite:///{(tmp_path / 'state' / 'supervisor.sqlite3').as_posix()}",
    )
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--accept-mediacrawler-license"],
        ["--xhs-detail-reference-ref", "env:SUPERVISOR_XHS_REFERENCE"],
    ],
)
def test_supervisor_rejects_dependent_controls_before_settings(
    monkeypatch: pytest.MonkeyPatch,
    arguments: list[str],
) -> None:
    def unexpected_settings() -> None:
        raise AssertionError("invalid gates must not open settings or the database")

    monkeypatch.setattr(cli_module, "get_settings", unexpected_settings)

    result = runner.invoke(app, ["scheduler", "supervise", *arguments])

    assert result.exit_code == 2
    assert "Traceback" not in result.output


def test_supervisor_cli_composes_fixed_full_chain_and_emits_only_final_counts(
    supervisor_cli_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del supervisor_cli_settings
    captured: dict[str, Any] = {}
    secret_reference = "env:SUPERVISOR_PRIVATE_XHS_REFERENCE"

    def subscription_worker(database: object, settings: object, **kwargs: object) -> object:
        captured["subscription_builder"] = (database, settings, kwargs)
        return object()

    def pipeline_worker(database: object, settings: object, **kwargs: object) -> object:
        captured["pipeline_builder"] = (database, settings, kwargs)
        return object()

    class _Supervisor:
        def __init__(self, **kwargs: object) -> None:
            captured["supervisor"] = kwargs

        def request_stop(self) -> None:
            captured["stop_requested"] = True

    async def run_supervisor(supervisor: object) -> ResidentSupervisorResult:
        captured["run_supervisor"] = supervisor
        return ResidentSupervisorResult(
            cycles=4,
            login_scanned=3,
            login_recovered=1,
            login_busy=1,
            login_conflicted=1,
            materialized=2,
            subscription_attempts=2,
            pipeline_attempts=1,
            outcome="stopped_during_idle_wait",
        )

    monkeypatch.setattr(cli_module, "_build_subscription_worker", subscription_worker)
    monkeypatch.setattr(cli_module, "_build_pipeline_worker", pipeline_worker)
    monkeypatch.setattr(cli_module, "ResidentSchedulerSupervisor", _Supervisor)
    monkeypatch.setattr(cli_module, "_run_resident_supervisor", run_supervisor)

    result = runner.invoke(
        app,
        [
            "scheduler",
            "supervise",
            "--idle-interval-seconds",
            "2.5",
            "--login-sweep-limit",
            "7",
            "--materialize-limit",
            "8",
            "--subscription-jobs-per-cycle",
            "2",
            "--pipeline-jobs-per-cycle",
            "3",
            "--global-capacity",
            "4",
            "--subscription-lease-seconds",
            "45",
            "--subscription-scan-limit",
            "9",
            "--subscription-heartbeat-interval-seconds",
            "5",
            "--pipeline-lease-seconds",
            "600",
            "--pipeline-scan-limit",
            "10",
            "--pipeline-heartbeat-interval-seconds",
            "20",
            "--pipeline-retry-delay-seconds",
            "11",
            "--enable-mediacrawler",
            "--accept-mediacrawler-license",
            "--xhs-detail-reference-ref",
            secret_reference,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "status": "stopped",
        "outcome": "stopped_during_idle_wait",
        "cycles": 4,
        "login_scanned": 3,
        "login_recovered": 1,
        "login_busy": 1,
        "login_conflicted": 1,
        "materialized": 2,
        "subscription_attempts": 2,
        "pipeline_attempts": 1,
    }
    subscription_kwargs = captured["subscription_builder"][2]
    assert subscription_kwargs == {
        "enable_mediacrawler": True,
        "accept_mediacrawler_license": True,
    }
    pipeline_kwargs = captured["pipeline_builder"][2]
    assert pipeline_kwargs["retry_delay_seconds"] == 11
    assert pipeline_kwargs["enable_mediacrawler"] is True
    assert pipeline_kwargs["accept_mediacrawler_license"] is True
    assert pipeline_kwargs["xhs_detail_reference_ref"] == secret_reference
    supervisor_kwargs = captured["supervisor"]
    config = supervisor_kwargs["config"]
    assert config.idle_interval_seconds == 2.5
    assert config.login_sweep_limit == 7
    assert config.materialize_limit == 8
    assert config.subscription_jobs_per_cycle == 2
    assert config.pipeline_jobs_per_cycle == 3
    assert config.subscription_global_capacity == 4
    assert config.subscription_lease_seconds == 45
    assert config.subscription_scan_limit == 9
    assert config.subscription_heartbeat_interval_seconds == 5
    assert config.pipeline_lease_seconds == 600
    assert config.pipeline_scan_limit == 10
    assert config.pipeline_heartbeat_interval_seconds == 20
    assert supervisor_kwargs["subscription_worker_id"] != supervisor_kwargs["pipeline_worker_id"]
    assert secret_reference not in result.output


def test_resident_signal_scope_stops_then_force_exits_and_restores_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[bool] = []
    forced_exit_codes: list[int] = []
    installed: list[tuple[object, object]] = []
    previous: dict[object, object] = {}

    class _ForcedExit(BaseException):
        pass

    class _Supervisor:
        def request_stop(self) -> None:
            requested.append(True)

    def get_signal(candidate: object) -> object:
        handler = previous.setdefault(candidate, object())
        return handler

    def set_signal(candidate: object, handler: object) -> object:
        installed.append((candidate, handler))
        return previous.get(candidate, object())

    def force_exit(code: int) -> None:
        forced_exit_codes.append(code)
        raise _ForcedExit

    monkeypatch.setattr(signal_module, "getsignal", get_signal)
    monkeypatch.setattr(signal_module, "signal", set_signal)
    monkeypatch.setattr(os_module, "_exit", force_exit)

    with cli_module._resident_stop_signals(cast(ResidentSchedulerSupervisor, _Supervisor())):
        active_handlers = installed.copy()
        assert len(active_handlers) == 2
        first_candidate, first_handler = active_handlers[0]
        second_candidate, second_handler = active_handlers[1]
        assert callable(first_handler) and callable(second_handler)
        first_handler(int(first_candidate), None)
        with pytest.raises(_ForcedExit):
            second_handler(int(second_candidate), None)

    assert requested == [True]
    assert forced_exit_codes == [128 + int(second_candidate)]
    restored = installed[len(active_handlers) :]
    assert restored == [(candidate, previous[candidate]) for candidate, _handler in active_handlers]


def test_supervisor_cli_closes_unexpected_failure_without_leaking_raw_text(
    supervisor_cli_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del supervisor_cli_settings
    sentinel = "SENTINEL-private-resident-handler-and-profile"

    monkeypatch.setattr(cli_module, "_build_subscription_worker", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli_module, "_build_pipeline_worker", lambda *_args, **_kwargs: object())

    class _Supervisor:
        def __init__(self, **_kwargs: object) -> None:
            pass

    async def fail(_supervisor: object) -> ResidentSupervisorResult:
        raise RuntimeError(sentinel)

    monkeypatch.setattr(cli_module, "ResidentSchedulerSupervisor", _Supervisor)
    monkeypatch.setattr(cli_module, "_run_resident_supervisor", fail)

    result = runner.invoke(app, ["scheduler", "supervise"])

    assert result.exit_code == 2
    assert sentinel not in result.output
    assert "Traceback" not in result.output
