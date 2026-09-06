"""Manual CLI actions retain safe command lifecycles, not fabricated Operations."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from media_sync.config import Settings
from media_sync.infrastructure.observability.store import LogStore
from media_sync.interfaces import cli


@pytest.mark.parametrize("ok", [True, False])
def test_manual_asset_result_is_preserved_and_logged_without_raw_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ok: bool,
) -> None:
    settings = Settings(state_dir=tmp_path / "state", _env_file=None)
    asset_id, job_id = str(uuid4()), str(uuid4())
    payload = {"job_id": job_id, "private": "PRIVATE-CLI-PAYLOAD"}
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli, "_execute_asset_download", lambda **_: (payload, ok))
    result = CliRunner().invoke(cli.app, ["asset", "download", "--asset-id", asset_id, "--json"])
    assert result.exit_code == (0 if ok else 1), result.exception
    assert json.loads(result.output) == payload
    store = LogStore(settings.state_dir / "logs")
    try:
        events = store.query(module="download")["events"]
        assert [event["event_code"] for event in events] == ["command_started", "command_finished"]
        assert all(event["asset_id"] == asset_id and "operation_id" not in event for event in events)
        assert events[0]["correlation_id"] == events[1]["correlation_id"]
        assert events[1]["job_id"] == job_id
        assert events[1]["outcome"] == ("succeeded" if ok else "failed")
        assert "PRIVATE-CLI-PAYLOAD" not in json.dumps(events)
    finally:
        store.close()


def test_manual_export_records_real_returned_job_but_not_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(state_dir=tmp_path / "state", _env_file=None)
    author_id, job_id = str(uuid4()), str(uuid4())
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr(cli.OutputDirectoryService, "bind_author_root", lambda *_: tmp_path / "media")
    monkeypatch.setattr(
        cli.EmbyExportService,
        "export_author",
        lambda *_: SimpleNamespace(
            job_id=job_id,
            already_exported=False,
            output_path="PRIVATE-CLI-OUTPUT",
            source_fingerprint="a" * 64,
            rendered_fingerprint="b" * 64,
            managed_file_count=1,
        ),
    )
    result = CliRunner().invoke(cli.app, ["emby", "export", "--author-id", author_id, "--json"])
    assert result.exit_code == 0, result.exception
    assert json.loads(result.output)["output_path"] == "PRIVATE-CLI-OUTPUT"
    store = LogStore(settings.state_dir / "logs")
    try:
        events = store.query(module="exporter")["events"]
        assert len(events) == 2
        assert events[0]["author_id"] == author_id
        assert events[1]["job_id"] == job_id and events[1]["outcome"] == "succeeded"
        assert "PRIVATE-CLI-OUTPUT" not in json.dumps(events)
    finally:
        store.close()
