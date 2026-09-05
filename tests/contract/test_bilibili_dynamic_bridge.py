"""Sealed dynamic identity, namespace and persisted-snapshot authority, offline."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from media_sync.application.mediacrawler import load_normalized_output
from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.bilibili_dynamic import (
    BILI_DYNAMIC_FIELD,
    parse_bili_dynamic_detail,
)
from media_sync.integrations.mediacrawler.bilibili_multifeed import (
    BiliDynamicSnapshotStore,
    BiliDynamicUnit,
    BiliMultiFeedState,
)
from media_sync.integrations.mediacrawler.bilibili_scan import BILI_SCAN_COVERAGE_FILENAME
from media_sync.integrations.mediacrawler.bridge import BridgeRequest, RunnerManifest
from media_sync.integrations.mediacrawler.policies import inspect_output
from media_sync.integrations.mediacrawler.receipt import write_completion_receipt
from tests.contract.test_mediacrawler_bridge import _bridge, _make_fake_project, _request


def dynamic_item(did: str = "1234", *, mid: int = 252671524) -> dict:
    return {
        "id_str": did,
        "type": "DYNAMIC_TYPE_WORD",
        "visible": True,
        "modules": {
            "module_author": {"type": "AUTHOR_TYPE_NORMAL", "mid": mid, "pub_ts": 1788650000, "name": "Fixture"},
            "module_dynamic": {"desc": {"text": "完整的合成文字"}},
        },
    }


def dynamic_output(manifest: RunnerManifest, *, tamper: str | None = None):
    state = manifest.bili_scan
    assert isinstance(state, BiliMultiFeedState)
    store = BiliDynamicSnapshotStore(
        manifest.account_root,
        account_id=manifest.account_id,
        author_fingerprint_sha256=manifest.author_remote_id_fingerprint_sha256,
        upstream_sha=manifest.upstream_sha,
        creator_id=252671524,
    )
    unit = BiliDynamicUnit(state, manifest.max_items)
    rows = []
    while (action := unit.next_action()).kind != "stop":
        if action.kind == "list":
            unit.observe_page(store.persist(action.offset, {"items": [dynamic_item()], "has_more": 0, "offset": ""}))
        elif action.kind == "load":
            unit.observe_page(store.load(action.snapshot))
        else:
            payload = parse_bili_dynamic_detail(dynamic_item(), creator_id=252671524, expected_identity=action.identity)
            record = payload.to_record()
            if tamper == "identity":
                record[BILI_DYNAMIC_FIELD]["identity"]["author_mid"] = 2
            elif tamper == "legacy":
                del record[BILI_DYNAMIC_FIELD]
            elif tamper == "body":
                record["text"] = "a different raw body"
            rows.append(record)
            unit.consume(action.identity)
    coverage = unit.coverage()
    if rows:
        (manifest.output_root / "dynamics.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    (manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).write_text(coverage.to_json_line(), encoding="utf-8")
    write_completion_receipt(manifest, inspect_output(manifest.output_root, manifest.watchdogs), known_secrets=())
    if tamper == "snapshot":
        snapshot = next(manifest.account_root.rglob(f"{coverage.page.ref.digest}.json"))
        snapshot.write_text("{}", encoding="utf-8")
    return coverage


def dynamic_spec(tmp_path: Path):
    project = _make_fake_project(tmp_path / "upstream")
    request = replace(
        _request(project, tmp_path / "runtime", platform=Platform.BILI, creator="252671524"),
        author_remote_id="252671524",
        max_items=2,
        allow_full_history=False,
        bili_bounded_capture=True,
        bili_scope="dynamics",
    )
    return _bridge().prepare(request)


def load(manifest: RunnerManifest):
    return load_normalized_output(
        manifest,
        creator_remote_id="252671524",
        creator_display_name="Fixture",
        ingested_at=datetime.now(UTC),
    )


def continue_manifest(manifest: RunnerManifest, state: BiliMultiFeedState) -> RunnerManifest:
    return (
        _bridge()
        .prepare(
            BridgeRequest(
                lock_path=manifest.lock_path,
                integration_root=manifest.integration_root,
                python_executable=manifest.python_executable,
                account_id=manifest.account_id,
                subscription_id=manifest.subscription_id,
                job_id=uuid4(),
                checkpoint_revision_before=1,
                intended_mode=manifest.intended_mode,
                platform=manifest.platform,
                login_method=manifest.login_method,
                author_remote_id="252671524",
                creator_reference="252671524",
                license_acknowledged=True,
                max_items=2,
                bili_bounded_capture=True,
                bili_scope="dynamics",
                bili_scan_cursor_before=state.to_cursor(),
            )
        )
        .manifest
    )


def test_dynamic_discovery_then_exact_snapshot_consumption(tmp_path: Path) -> None:
    spec = dynamic_spec(tmp_path)
    assert RunnerManifest.load(spec.paths.manifest_path) == spec.manifest
    discovered = dynamic_output(spec.manifest)
    assert not load(spec.manifest).records
    # Head/history alternate, so select the preserved head lane to test the
    # exact same immutable snapshot independently of worker scheduling.
    pending = replace(discovered.next_state, dynamics=replace(discovered.next_state.dynamics, next_lane="head"))
    continued = continue_manifest(spec.manifest, pending)
    consumed = dynamic_output(continued)
    result = load(continued)
    assert result.bili_coverage == consumed
    assert [(row.content.remote_type, row.content.remote_id) for row in result.records] == [("dynamic", "1234")]
    assert result.records[0].content.body == "完整的合成文字"
    assert consumed.record_keys == (("dynamic", "1234"),)


@pytest.mark.parametrize("tamper", ["identity", "legacy", "body", "snapshot"])
def test_dynamic_sealed_mismatch_is_rejected(tmp_path: Path, tamper: str) -> None:
    spec = dynamic_spec(tmp_path)
    first = dynamic_output(spec.manifest)
    pending = replace(first.next_state, dynamics=replace(first.next_state.dynamics, next_lane="head"))
    continued = continue_manifest(spec.manifest, pending)
    dynamic_output(continued, tamper=tamper)
    with pytest.raises(ValueError):
        load(continued)
