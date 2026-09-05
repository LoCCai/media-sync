"""Offline Bili v2 cursor/coverage budgets, pending retention and snapshot isolation."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

import media_sync.integrations.mediacrawler.bilibili_multifeed as multifeed_module
from media_sync.integrations.mediacrawler.bilibili_dynamic import BiliDynamicIdentity
from media_sync.integrations.mediacrawler.bilibili_multifeed import (
    BILI_DYNAMIC_SNAPSHOT_MAX_BYTES,
    BILI_MULTIFEED_CURSOR_PREFIX,
    BiliDynamicLane,
    BiliDynamicPage,
    BiliDynamicSnapshotRef,
    BiliDynamicSnapshotStore,
    BiliDynamicState,
    BiliDynamicUnit,
    BiliMultiFeedCoverage,
    BiliMultiFeedState,
    coverage_from_json_line,
    state_for_cursor,
    state_from_cursor,
    wrap_upload_coverage,
)
from media_sync.integrations.mediacrawler.bilibili_scan import BiliIdentity, BiliPage, BiliScanState, BiliScanUnit
from media_sync.security.paths import PathSecurityError

ACCOUNT = UUID("a45dd777-9633-4168-b432-677e6c7b97be")
BINDING = {"account_id": ACCOUNT, "author_fingerprint_sha256": "a" * 64, "upstream_sha": "b" * 40}


def dynamic(number: int, kind: str = "WORD", timestamp: int = 1000) -> BiliDynamicIdentity:
    return BiliDynamicIdentity(str(number), f"DYNAMIC_TYPE_{kind}", timestamp, 123)


def video(number: int) -> BiliIdentity:
    return BiliIdentity(str(number), f"BV{number:010d}", 500)


def initial(scope: str = "dynamics") -> BiliMultiFeedState:
    state = state_for_cursor(None, **BINDING, scope=scope)
    assert type(state) is BiliMultiFeedState
    return state


def page(identities: tuple[BiliDynamicIdentity, ...], offset: str = "", next_offset: str = "") -> BiliDynamicPage:
    digest = hashlib.sha256(repr((identities, offset, next_offset)).encode()).hexdigest()
    return BiliDynamicPage(
        BiliDynamicSnapshotRef(digest, offset, next_offset, not next_offset, len(identities)), identities
    )


def discover(state: BiliMultiFeedState, observation: BiliDynamicPage, maximum: int = 2) -> BiliMultiFeedCoverage:
    unit = BiliDynamicUnit(state, maximum)
    assert unit.next_action().kind == "list"
    unit.observe_page(observation)
    coverage = unit.coverage()
    assert coverage.stop_reason == "snapshot_saved" and not coverage.dynamic_consumed
    coverage.validate(state, maximum, normalized_records=())
    return coverage


def pending(observation: BiliDynamicPage) -> BiliMultiFeedState:
    state = discover(initial(), observation).next_state
    return replace(state, dynamics=replace(state.dynamics, next_lane="head"))


def consume(
    state: BiliMultiFeedState,
    observation: BiliDynamicPage,
    maximum: int = 2,
    references: dict[str, BiliIdentity] | None = None,
) -> BiliMultiFeedCoverage:
    unit = BiliDynamicUnit(state, maximum)
    assert unit.next_action().snapshot == observation.ref
    unit.observe_page(observation)
    while (action := unit.next_action()).kind != "stop":
        assert action.kind == "detail" and action.identity is not None
        unit.consume(action.identity, (references or {}).get(action.identity.did))
    result = unit.coverage()
    result.validate(state, maximum, normalized_records=tuple(reversed(result.record_keys)))
    assert coverage_from_json_line(result.to_json_line()) == result
    assert state_from_cursor(result.next_state.to_cursor()) == result.next_state
    return result


def test_legacy_v1_cursor_is_unchanged_and_explicit_upgrade_preserves_upload_bytes() -> None:
    original = BiliScanState.initial(**BINDING)
    unit = BiliScanUnit(original, 1)
    unit.observe_page(BiliPage(1, 2, (video(1), video(2))))
    unit.consume(video(1))
    progressed = unit.coverage().next_state
    assert state_for_cursor(progressed.to_cursor(), **BINDING) == progressed
    for scope in ("uploads", "dynamics", "both"):
        upgraded = state_for_cursor(progressed.to_cursor(), **BINDING, scope=scope)
        assert type(upgraded) is BiliMultiFeedState
        assert upgraded.uploads.to_cursor() == progressed.to_cursor()
        assert upgraded.scope == scope and upgraded.dynamics == BiliDynamicState()


def test_scope_disable_and_reenable_preserves_inactive_dynamic_pending() -> None:
    state = pending(page((dynamic(1), dynamic(2))))
    disabled = state_for_cursor(state.to_cursor(), **BINDING, scope="uploads")
    assert type(disabled) is BiliMultiFeedState and disabled.next_feed == "uploads"
    assert disabled.dynamics == state.dynamics
    legacy_policy = state_for_cursor(state.to_cursor(), **BINDING)
    assert legacy_policy == disabled
    restored = state_for_cursor(disabled.to_cursor(), **BINDING, scope="dynamics")
    assert restored == state


@pytest.mark.parametrize("changed", ["account_id", "author_fingerprint_sha256", "upstream_sha"])
def test_cursor_binding_is_exact_for_upgrade_and_scope_change(changed: str) -> None:
    binding = {
        **BINDING,
        changed: UUID(int=1) if changed == "account_id" else "c" * (40 if changed == "upstream_sha" else 64),
    }
    for cursor in (initial().to_cursor(), BiliScanState.initial(**BINDING).to_cursor()):
        with pytest.raises(ValueError):
            state_for_cursor(cursor, **binding, scope="both")


@pytest.mark.parametrize("cursor", ["bili-multifeed-v3:{}", "bili-multifeed-v2:[]", "bili-scan-v2:{}"])
def test_unknown_bili_versions_never_silently_restart(cursor: str) -> None:
    with pytest.raises(ValueError):
        state_for_cursor(cursor, **BINDING, scope="both")


def test_state_and_coverage_reject_duplicate_json_fields_and_noncanonical_cursor() -> None:
    with pytest.raises(ValueError):
        state_from_cursor(initial().to_cursor() + " ")
    with pytest.raises(ValueError):
        state_from_cursor(BILI_MULTIFEED_CURSOR_PREFIX + '{"scope":"uploads","scope":"both"}')
    result = discover(initial(), page((dynamic(1),)))
    for line in (
        result.to_json_line() * 2,
        result.to_json_line().rstrip(),
        '{"schema_version":2,"schema_version":2}\n',
    ):
        with pytest.raises(ValueError):
            coverage_from_json_line(line)


def test_both_scope_fairly_alternates_feeds_and_dynamic_lanes() -> None:
    state = initial("both")
    lanes = []
    for _index in range(4):
        upload = BiliScanUnit(state.uploads, 2)
        upload.observe_page(BiliPage(1, 0, ()))
        wrapped = wrap_upload_coverage(state, upload.coverage())
        wrapped.validate(state, 2, normalized_records=())
        assert wrapped.next_state.next_feed == "dynamics"
        assert wrapped.next_state.dynamics == state.dynamics
        state = wrapped.next_state
        lanes.append(state.dynamics.next_lane)
        unit = BiliDynamicUnit(state, 2)
        observation = page(())
        unit.observe_page(observation)
        state = unit.coverage().next_state
        assert state.next_feed == "uploads"
    assert lanes == ["head", "history", "head", "history"]


def test_discovery_is_durable_without_consuming_detail_and_retains_all_page_entries() -> None:
    observation = page(tuple(dynamic(number) for number in range(1, 31)), next_offset="next-page")
    first = discover(initial(), observation)
    assert first.next_state.dynamics.head.snapshot == observation.ref
    assert first.next_state.dynamics.head.index == 0 and first.detail_attempts == 0 and first.list_attempts == 1
    state = replace(first.next_state, dynamics=replace(first.next_state.dynamics, next_lane="head"))
    result = consume(state, observation)
    assert result.record_keys == (("dynamic", "1"), ("dynamic", "2"))
    assert result.next_state.dynamics.head.index == 2
    assert result.next_state.dynamics.head.offset == ""
    assert result.next_state.dynamics.head.snapshot == observation.ref


def test_tail_av_reserves_two_records_and_is_left_pending() -> None:
    observation = page((dynamic(1), dynamic(2, "AV"), dynamic(3)))
    first = consume(pending(observation), observation, references={"2": video(20)})
    assert first.stop_reason == "item_limit" and first.record_keys == (("dynamic", "1"),)
    state = replace(first.next_state, dynamics=replace(first.next_state.dynamics, next_lane="head"))
    second = consume(state, observation, references={"2": video(20)})
    assert second.record_keys == (("dynamic", "2"), ("content", "20"))
    assert second.next_state.dynamics.head.index == 2


def test_same_numeric_dynamic_and_video_ids_are_distinct_and_jsonl_order_is_irrelevant() -> None:
    observation = page((dynamic(10, "AV"),))
    result = consume(pending(observation), observation, references={"10": video(10)})
    assert result.record_keys == (("dynamic", "10"), ("content", "10"))
    result.validate(result.input_state, 2, normalized_records=(("content", "10"), ("dynamic", "10")))
    with pytest.raises(ValueError):
        result.validate(result.input_state, 2, normalized_remote_ids=("10", "10"))
    with pytest.raises(ValueError):
        result.validate(result.input_state, 2, normalized_records=(("dynamic", "10"), ("dynamic", "10")))


def test_duplicate_av_references_deduplicate_outputs_but_each_reserves_two_records() -> None:
    observation = page((dynamic(1, "AV"), dynamic(2, "AV"), dynamic(3)))
    result = consume(pending(observation), observation, 4, {"1": video(20), "2": video(20)})
    assert result.record_keys == (("dynamic", "1"), ("content", "20"), ("dynamic", "2"))
    assert result.next_state.dynamics.head.index == 2
    with pytest.raises(ValueError):
        consume(pending(observation), observation, 4, {"1": video(20), "2": replace(video(20), pubdate=600)})


@pytest.mark.parametrize("kind", ["WORD", "DRAW", "AV", "UNKNOWN"])
def test_detail_mismatch_or_unsupported_component_never_advances_pending(kind: str) -> None:
    observation = page((dynamic(1, kind),))
    state = pending(observation)
    unit = BiliDynamicUnit(state, 2)
    unit.observe_page(observation)
    with pytest.raises(ValueError):
        unit.consume(dynamic(2, kind))
    if kind in {"AV", "UNKNOWN"}:
        with pytest.raises(ValueError):
            unit.consume(dynamic(1, kind))
    assert unit.current.index == 0
    with pytest.raises(ValueError):
        unit.coverage()


@pytest.mark.parametrize("maximum", [True, 0, 1, -1, 1001])
def test_dynamic_units_require_a_closed_record_budget(maximum: int) -> None:
    with pytest.raises(ValueError):
        BiliDynamicUnit(initial(), maximum)


def test_head_and_history_reach_all_pages_without_timestamp_order_assumptions() -> None:
    observations = {
        "": page((dynamic(1, timestamp=100), dynamic(2, timestamp=200)), next_offset="p2"),
        "p2": page((dynamic(3, timestamp=50), dynamic(4, timestamp=200)), "p2", "p3"),
        "p3": page((dynamic(5),), "p3"),
    }
    state = initial()
    seen: dict[str, set[str]] = {"head": set(), "history": set()}
    ends: set[str] = set()
    for _ in range(12):
        unit = BiliDynamicUnit(state, 2)
        action = unit.next_action()
        observation = observations[action.offset if action.kind == "list" else action.snapshot.offset]
        unit.observe_page(observation)
        while (action := unit.next_action()).kind != "stop":
            unit.consume(action.identity)
        result = unit.coverage()
        result.validate(state, 2)
        seen[result.lane].update(row.identity.did for row in result.dynamic_consumed)
        if result.stop_reason == "source_end":
            ends.add(result.lane)
        state = result.next_state
    assert seen == {"head": {"1", "2", "3", "4", "5"}, "history": {"1", "2", "3", "4", "5"}}
    assert ends == {"head", "history"}


@pytest.mark.parametrize("next_offset", ["here", "seen-before"])
def test_repeated_offset_restarts_conservatively_after_consumption(next_offset: str) -> None:
    observation = page((dynamic(1),), "here", next_offset)
    lane = BiliDynamicLane("here", observation.ref, seen_offsets=(hashlib.sha256(b"seen-before").hexdigest(),))
    state = replace(initial(), dynamics=BiliDynamicState(head=lane))
    result = consume(state, observation)
    assert result.stop_reason == "restarted" and result.next_state.dynamics.head == BiliDynamicLane()
    assert result.public_summary()["source_end_observed"] is False


@pytest.mark.parametrize("mutation", ["scope", "next_state", "reason", "consumed", "page_ref", "observation"])
def test_coverage_replay_rejects_altered_transitions(mutation: str) -> None:
    observation = page((dynamic(1), dynamic(2), dynamic(3)))
    result = consume(pending(observation), observation)
    changed = {
        "scope": replace(result, input_state=result.input_state.with_scope("uploads")),
        "next_state": replace(result, next_state=result.input_state),
        "reason": replace(result, reason="source_end"),
        "consumed": replace(result, dynamic_consumed=result.dynamic_consumed[:1]),
        "page_ref": replace(result, page=replace(observation, ref=replace(observation.ref, digest="0" * 64))),
        "observation": replace(result, observation="list"),
    }[mutation]
    with pytest.raises(ValueError):
        changed.validate(result.input_state, 2)


def raw_page(number: int = 1) -> dict[str, Any]:
    return {
        "has_more": False,
        "offset": "",
        "items": [
            {
                "id_str": str(number),
                "type": "DYNAMIC_TYPE_WORD",
                "modules": {
                    "module_author": {"type": "AUTHOR_TYPE_NORMAL", "mid": 123, "pub_ts": 1000},
                    "module_dynamic": {
                        "desc": {"text": "private-source-body", "url": "https://private.example/retained-source"}
                    },
                },
            }
        ],
    }


def store(root: Path, **binding: Any) -> BiliDynamicSnapshotStore:
    return BiliDynamicSnapshotStore(root, **{**BINDING, **binding}, creator_id=123)


def test_snapshot_is_private_immutable_digest_bound_and_cursor_does_not_leak_body(tmp_path: Path) -> None:
    snapshots = store(tmp_path)
    observation = snapshots.persist("", raw_page())
    assert snapshots.load(observation.ref) == observation
    assert snapshots.persist("", raw_page()) == observation
    paths = list(tmp_path.rglob("*.json"))
    assert len(paths) == 1
    assert "private-source-body" in paths[0].read_text(encoding="utf-8")
    public = discover(initial(), observation).to_json_line()
    assert "private-source-body" not in public and "private.example" not in public
    assert observation.ref.digest in public
    if os.name != "nt":
        assert paths[0].stat().st_mode & 0o777 == 0o600
        assert paths[0].parent.stat().st_mode & 0o777 == 0o700


def test_snapshot_tamper_missing_and_cross_binding_are_rejected(tmp_path: Path) -> None:
    snapshots = store(tmp_path)
    observation = snapshots.persist("", raw_page())
    for altered in ({"account_id": UUID(int=1)}, {"author_fingerprint_sha256": "c" * 64}, {"upstream_sha": "c" * 40}):
        with pytest.raises((ValueError, PathSecurityError)):
            store(tmp_path, **altered).load(observation.ref)
    with pytest.raises(PathSecurityError):
        snapshots.load(replace(observation.ref, digest="0" * 64))
    path = next(tmp_path.rglob("*.json"))
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        snapshots.load(observation.ref)
    with pytest.raises(ValueError):
        snapshots.persist("", raw_page())


@pytest.mark.parametrize("failure", ["partial_write", "fsync", "before_publish", "after_publish"])
def test_interrupted_snapshot_publication_can_retry_without_partial_final_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    snapshots = store(tmp_path)
    create = multifeed_module.create_regular_file
    rename = multifeed_module._rename_snapshot_no_replace
    fsync = os.fsync

    @contextmanager
    def interrupted_write(path, *, root):
        with create(path, root=root) as handle:

            class PartialWriter:
                def fileno(self):
                    return handle.fileno()

                def write(self, payload):
                    handle.write(payload[: len(payload) // 2])
                    handle.flush()
                    raise OSError("synthetic interrupted snapshot write")

            yield PartialWriter()

    def interrupted_publish(source, destination):
        if failure == "after_publish":
            rename(source, destination)
        raise OSError("synthetic interrupted snapshot publication")

    with monkeypatch.context() as patch:
        if failure == "partial_write":
            patch.setattr(multifeed_module, "create_regular_file", interrupted_write)
        elif failure == "fsync":

            def failed_fsync(descriptor):
                if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                    return fsync(descriptor)
                raise OSError("synthetic failed file fsync")

            patch.setattr(multifeed_module.os, "fsync", failed_fsync)
        else:
            patch.setattr(multifeed_module, "_rename_snapshot_no_replace", interrupted_publish)
        with pytest.raises(OSError):
            snapshots.persist("", raw_page())
    assert len(list(tmp_path.rglob("*.json"))) == (1 if failure == "after_publish" else 0)
    assert not list(tmp_path.rglob("*.tmp"))
    observation = snapshots.persist("", raw_page())
    assert snapshots.load(observation.ref) == observation
    assert next(tmp_path.rglob("*.json")).stat().st_nlink == 1


@pytest.mark.parametrize("stage", ["partial_write", "before_publish", "after_publish"])
def test_killed_snapshot_never_leaves_partial_final_or_adopts_stale_staging(tmp_path: Path, stage: str) -> None:
    script = textwrap.dedent("""
        import os
        import sys
        from contextlib import contextmanager
        from pathlib import Path
        import media_sync.integrations.mediacrawler.bilibili_multifeed as module
        from tests.unit.test_bilibili_multifeed import raw_page, store

        create = module.create_regular_file
        @contextmanager
        def killed_writer(path, *, root):
            with create(path, root=root) as handle:
                class Writer:
                    def fileno(self):
                        return handle.fileno()
                    def write(self, payload):
                        handle.write(payload[:len(payload) // 2])
                        handle.flush()
                        os.fsync(handle.fileno())
                        os._exit(93)
                yield Writer()
        module.create_regular_file = killed_writer
        if sys.argv[2] != 'partial_write':
            module.create_regular_file = create
            rename = module._rename_snapshot_no_replace
            def killed_publish(source, destination):
                if sys.argv[2] == 'after_publish':
                    rename(source, destination)
                os._exit(93)
            module._rename_snapshot_no_replace = killed_publish
        store(Path(sys.argv[1])).persist('', raw_page())
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path), stage],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 93, result.stderr
    staged = list(tmp_path.rglob("*.tmp"))
    assert len(staged) == (0 if stage == "after_publish" else 1)
    assert len(list(tmp_path.rglob("*.json"))) == (1 if stage == "after_publish" else 0)
    original_staging = {path: path.read_bytes() for path in staged}
    assert all(original_staging.values())
    snapshots = store(tmp_path)
    # A killed writer leaves either staging or a complete single-link final,
    # never a reference to staging. Another attempt does not adopt random .tmp.
    observation = snapshots.persist("", raw_page())
    assert snapshots.load(observation.ref) == observation
    assert {path: path.read_bytes() for path in staged} == original_staging
    assert next(tmp_path.rglob("*.json")).stat().st_nlink == 1
    if os.name != "nt":
        assert all(path.stat().st_mode & 0o777 == 0o600 for path in staged)


@pytest.mark.skipif(os.name == "nt", reason="native POSIX directory fsync requires POSIX")
def test_snapshot_syncs_parent_chain_and_existing_final_directory_on_posix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshots = store(tmp_path)
    synced = []
    original = multifeed_module._fsync_snapshot_directory

    def sync_directory(path):
        original(path)
        synced.append(path)

    monkeypatch.setattr(multifeed_module, "_fsync_snapshot_directory", sync_directory)
    observation = snapshots.persist("", raw_page())
    expected = [tmp_path]
    for component in snapshots.relative.parts:
        expected.append(expected[-1] / component)
    assert synced == expected
    synced.clear()
    assert snapshots.persist("", raw_page()) == observation
    assert synced == expected


@pytest.mark.parametrize("same_payload", [False, True])
def test_snapshot_publish_race_never_overwrites_existing_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    same_payload: bool,
) -> None:
    snapshots = store(tmp_path)
    rename = multifeed_module._rename_snapshot_no_replace
    winner_bytes = b""

    def another_publisher_wins(source, destination):
        nonlocal winner_bytes
        winner_bytes = source.read_bytes() if same_payload else b"existing-invalid-blob-preserved"
        with multifeed_module.create_regular_file(destination, root=tmp_path) as handle:
            handle.write(winner_bytes)
        rename(source, destination)

    monkeypatch.setattr(multifeed_module, "_rename_snapshot_no_replace", another_publisher_wins)
    if same_payload:
        observation = snapshots.persist("", raw_page())
        assert snapshots.load(observation.ref) == observation
    else:
        with pytest.raises(ValueError):
            snapshots.persist("", raw_page())
    assert next(tmp_path.rglob("*.json")).read_bytes() == winner_bytes
    assert not list(tmp_path.rglob("*.tmp"))


def test_snapshot_identity_and_bounds_are_checked_before_any_file_is_published(tmp_path: Path) -> None:
    snapshots = store(tmp_path)
    for raw in (
        {**raw_page(), "items": raw_page()["items"] * 31},
        {**raw_page(), "has_more": "false"},
        {**raw_page(), "has_more": True, "offset": ""},
        {**raw_page(), "offset": "https://private.example/token"},
        {**raw_page(), "padding": "x" * BILI_DYNAMIC_SNAPSHOT_MAX_BYTES},
    ):
        with pytest.raises(ValueError):
            snapshots.persist("", raw)
    assert not list(tmp_path.rglob("*.json"))


def test_snapshot_ref_is_closed_and_rejects_path_or_url_material() -> None:
    for digest in ("../escape", "c" * 63, "https://private.example"):
        with pytest.raises(ValueError):
            BiliDynamicSnapshotRef(digest, "", "", True, 0)
    with pytest.raises(ValueError):
        BiliDynamicSnapshotRef.from_mapping(
            {"digest": "c" * 64, "offset": "", "next_offset": "", "source_end": True, "count": 0, "path": "/tmp"}
        )


def test_snapshot_existing_symlink_is_not_followed(tmp_path: Path) -> None:
    snapshots = store(tmp_path)
    observation = snapshots.persist("", raw_page())
    path = next(tmp_path.rglob("*.json"))
    target = tmp_path / "outside.txt"
    target.write_text("outside-unchanged", encoding="utf-8")
    path.unlink()
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links unavailable for this Windows account")
    with pytest.raises(PathSecurityError):
        snapshots.load(observation.ref)
    with pytest.raises(PathSecurityError):
        snapshots.persist("", raw_page())
    assert target.read_text(encoding="utf-8") == "outside-unchanged"


def test_snapshot_existing_hardlink_is_not_read_or_overwritten(tmp_path: Path) -> None:
    snapshots = store(tmp_path)
    observation = snapshots.persist("", raw_page())
    path = next(tmp_path.rglob("*.json"))
    link = tmp_path / "other-link.json"
    try:
        os.link(path, link)
    except OSError:
        pytest.skip("hard links unavailable on this test filesystem")
    original = link.read_bytes()
    with pytest.raises(PathSecurityError):
        snapshots.load(observation.ref)
    with pytest.raises(PathSecurityError):
        snapshots.persist("", raw_page())
    assert link.read_bytes() == original


def test_public_scope_state_distinguishes_retained_pending_from_active_capture() -> None:
    state = pending(page((dynamic(1), dynamic(2))))
    summary = state.with_scope("uploads").public_summary()
    dynamic_summary = summary["dynamics"]
    assert dynamic_summary["active"] is False
    assert dynamic_summary["head_pending_count"] == dynamic_summary["pending_count"] == 2
    assert dynamic_summary["history_pending_count"] == 0
    assert dynamic_summary["head_has_offset"] is False
    assert "source_end_observed" not in dynamic_summary


@pytest.mark.parametrize("field", ["scope", "next_feed", "next_lane"])
@pytest.mark.parametrize("value", [[], {}, True, None, "invalid"])
def test_cursor_discriminators_reject_malformed_types(field: str, value: object) -> None:
    payload = json.loads(initial().to_cursor().removeprefix(BILI_MULTIFEED_CURSOR_PREFIX))
    if field == "next_lane":
        payload["dynamics"][field] = value
    else:
        payload[field] = value
    with pytest.raises(ValueError):
        state_from_cursor(BILI_MULTIFEED_CURSOR_PREFIX + json.dumps(payload, separators=(",", ":"), sort_keys=True))


def test_both_scope_upload_coverage_still_rejects_one_record_budget() -> None:
    state = initial("both")
    unit = BiliScanUnit(state.uploads, 1)
    unit.observe_page(BiliPage(1, 0, ()))
    wrapped = wrap_upload_coverage(state, unit.coverage())
    with pytest.raises(ValueError):
        wrapped.validate(state, 1)
