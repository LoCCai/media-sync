"""Real private manifests and sealed Bili coverage, with no platform traffic."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from media_sync.application.mediacrawler import MediaCrawlerOutputRejected, load_normalized_output
from media_sync.domain import Platform
from media_sync.integrations.mediacrawler.bilibili_scan import (
    BILI_SCAN_COVERAGE_FILENAME,
    BILI_SCAN_IDENTITY_FIELD,
    BiliIdentity,
    BiliPage,
    BiliScanState,
    BiliScanUnit,
)
from media_sync.integrations.mediacrawler.bridge import BridgeConfigurationError, RunnerManifest
from media_sync.integrations.mediacrawler.policies import FullHistoryAcknowledgementRequired, inspect_output
from media_sync.integrations.mediacrawler.receipt import CompletionReceiptError, write_completion_receipt
from tests.contract.test_mediacrawler_bridge import _bridge, _make_fake_project, _request


def _spec(tmp_path: Path, *, cursor: str | None = None):
    project = _make_fake_project(tmp_path / "upstream")
    request = replace(
        _request(project, tmp_path / "runtime", platform=Platform.BILI, creator="252671524"),
        author_remote_id="252671524",
        max_items=1,
        allow_full_history=False,
        bili_bounded_capture=True,
        bili_scan_cursor_before=cursor,
    )
    return _bridge().prepare(request)


def _output(manifest: RunnerManifest, *, empty: bool = False):
    assert manifest.bili_scan is not None
    unit = BiliScanUnit(manifest.bili_scan, manifest.max_items)
    identity = BiliIdentity("1234", "BV1234567890", 1767225600)
    unit.observe_page(BiliPage(1, 0 if empty else 1, () if empty else (identity,)))
    if not empty:
        unit.consume(identity)
    assert unit.next_action().kind == "stop"
    coverage = unit.coverage()
    (manifest.output_root / BILI_SCAN_COVERAGE_FILENAME).write_text(coverage.to_json_line(), encoding="utf-8")
    if not empty:
        (manifest.output_root / "contents.jsonl").write_text(
            json.dumps(
                {
                    "video_id": identity.aid,
                    "create_time": identity.pubdate,
                    "title": "Verified bounded unit",
                    BILI_SCAN_IDENTITY_FIELD: {
                        **identity.as_mapping(),
                        "author_fingerprint_sha256": manifest.author_remote_id_fingerprint_sha256,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    return coverage


def _load(manifest: RunnerManifest):
    return load_normalized_output(
        manifest,
        creator_remote_id="252671524",
        creator_display_name="Fixture creator",
        ingested_at=datetime(2026, 9, 6, tzinfo=UTC),
    )


def test_explicit_bounded_manifest_roundtrip_without_unbounded_ack(tmp_path: Path) -> None:
    spec = _spec(tmp_path, cursor="legacy-opaque-position")
    loaded = RunnerManifest.load(spec.paths.manifest_path)
    assert loaded == spec.manifest
    assert loaded.bili_scan is not None
    assert loaded.bili_scan.head_boundary is None
    assert loaded.bili_scan_input_cursor == "legacy-opaque-position"
    assert "bili-scan" not in repr(loaded)
    legacy = replace(loaded, bili_scan=None, bili_scan_input_cursor=None)
    assert "bili_scan" not in legacy.as_payload()
    spec.paths.manifest_path.write_text(json.dumps(legacy.as_payload()), encoding="utf-8")
    with pytest.raises(FullHistoryAcknowledgementRequired):
        RunnerManifest.load(spec.paths.manifest_path)


@pytest.mark.parametrize("mutation", ["account", "sha", "author", "cursor", "version", "extra", "platform"])
def test_bounded_manifest_rejects_misbound_or_unversioned_contract(tmp_path: Path, mutation: str) -> None:
    spec = _spec(tmp_path)
    payload = spec.manifest.as_payload()
    contract = payload["bili_scan"]
    assert isinstance(contract, dict)
    state = spec.manifest.bili_scan
    assert state is not None
    if mutation == "account":
        contract["state"] = replace(state, account_id=uuid4()).to_cursor()
    elif mutation == "sha":
        contract["state"] = replace(state, upstream_sha="a" * 40).to_cursor()
    elif mutation == "author":
        contract["state"] = replace(state, author_fingerprint_sha256="a" * 64).to_cursor()
    elif mutation == "cursor":
        contract["input_cursor"] = "bili-scan-broken"
    elif mutation == "version":
        contract["schema_version"] = True
    elif mutation == "extra":
        contract["extra"] = 1
    else:
        payload["platform"] = "xhs"
    spec.paths.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((BridgeConfigurationError, ValueError)):
        RunnerManifest.load(spec.paths.manifest_path)


@pytest.mark.parametrize("empty", [False, True])
def test_receipt_seals_coverage_and_normalizer_excludes_owned_sidecar(tmp_path: Path, empty: bool) -> None:
    spec = _spec(tmp_path)
    coverage = _output(spec.manifest, empty=empty)
    write_completion_receipt(
        spec.manifest, inspect_output(spec.manifest.output_root, spec.manifest.watchdogs), known_secrets=()
    )
    output = _load(spec.manifest)
    assert output.bili_coverage == coverage
    assert output.input_records == (0 if empty else 1)
    assert len(output.records) == output.input_records
    assert BiliScanState.from_cursor(coverage.next_state.to_cursor()) == coverage.next_state
    if output.records:
        assert BILI_SCAN_IDENTITY_FIELD not in repr(output.records)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "nested",
        "id",
        "bvid",
        "timestamp",
        "state",
        "extra",
        "unsealed",
        "author",
        "missing_author",
    ],
)
def test_coverage_or_content_tamper_never_grants_checkpoint_authority(tmp_path: Path, mutation: str) -> None:
    spec = _spec(tmp_path)
    _output(spec.manifest)
    sidecar = spec.manifest.output_root / BILI_SCAN_COVERAGE_FILENAME
    content = spec.manifest.output_root / "contents.jsonl"
    if mutation == "missing":
        sidecar.unlink()
    elif mutation == "nested":
        nested = spec.manifest.output_root / "nested"
        nested.mkdir()
        sidecar.rename(nested / sidecar.name)
    elif mutation == "duplicate":
        sidecar.write_text(sidecar.read_text(encoding="utf-8") * 2, encoding="utf-8")
    elif mutation in {"id", "bvid", "timestamp", "author", "missing_author"}:
        raw = json.loads(content.read_text(encoding="utf-8"))
        if mutation == "id":
            raw["video_id"] = "5678"
        elif mutation == "bvid":
            raw[BILI_SCAN_IDENTITY_FIELD]["bvid"] = "BV9999999999"
        elif mutation == "author":
            raw[BILI_SCAN_IDENTITY_FIELD]["author_fingerprint_sha256"] = "0" * 64
        elif mutation == "missing_author":
            del raw[BILI_SCAN_IDENTITY_FIELD]["author_fingerprint_sha256"]
        else:
            raw["create_time"] += 1
        content.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    elif mutation == "state":
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
        raw["next_cursor"] = spec.manifest.bili_scan.to_cursor()
        sidecar.write_text(json.dumps(raw) + "\n", encoding="utf-8")
    elif mutation == "extra":
        extra = spec.manifest.output_root / "extra.jsonl"
        extra.write_bytes(content.read_bytes())
    write_completion_receipt(
        spec.manifest, inspect_output(spec.manifest.output_root, spec.manifest.watchdogs), known_secrets=()
    )
    if mutation == "unsealed":
        sidecar.write_text("{}\n", encoding="utf-8")
    with pytest.raises((CompletionReceiptError, MediaCrawlerOutputRejected, ValueError)):
        _load(spec.manifest)
