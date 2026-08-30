from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import stat
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler import bridge as bridge_module
from media_sync.integrations.mediacrawler import policies as policies_module
from media_sync.integrations.mediacrawler import receipt as receipt_module
from media_sync.integrations.mediacrawler import runner as runner_module
from media_sync.integrations.mediacrawler.policies import PRIVATE_INPUT_ENV, WatchdogLimits, build_run_paths
from media_sync.integrations.mediacrawler.runner import (
    AttemptCleanupError,
    AttemptCleanupStatus,
    MediaCrawlerProcessRunner,
    MediaCrawlerProcessStatus,
    attempt_cleanup_incident_paths,
    cleanup_attempt_root,
    is_attempt_cleanup_blocked,
)
from media_sync.security import SecretValue
from tests.contract.test_mediacrawler_bridge import (
    ACCOUNT_ID,
    FakeProject,
    _bridge,
    _git,
    _make_fake_project,
    _pid_is_alive,
    _records,
    _request,
    _write_lock,
)

_HELPER_SOURCE = r"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

PRIVATE_INPUT_ENV = "MEDIA_SYNC_MEDIACRAWLER_PRIVATE_INPUT"
START = b"media-sync-start-v1\n"

mode = os.environ.pop("MEDIA_SYNC_TEST_HELPER_MODE")
probe_path = Path(os.environ.pop("MEDIA_SYNC_TEST_HELPER_PROBE"))
private_payload = os.environ.pop(PRIVATE_INPUT_ENV, None)
prestart_path = probe_path.with_suffix(".prestart")
poststart_path = probe_path.with_suffix(".poststart")
prestart_path.write_text("waiting", encoding="utf-8")
if sys.stdin.buffer.readline(64) != START:
    raise SystemExit(20)
poststart_path.write_text("started", encoding="utf-8")

manifest = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
output_root = Path(manifest["output_root"])
if mode == "success":
    target = output_root / "xhs" / "jsonl" / "success.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"note_id": "offline-success"}) + "\n", encoding="utf-8")
    probe_path.write_text(json.dumps({"child_pid": os.getpid()}), encoding="utf-8")
    raise SystemExit(0)
if mode == "secret-success":
    private = json.loads(private_payload)
    target = output_root / "xhs" / "jsonl" / "secret.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"title": private["cookie"]}) + "\n", encoding="utf-8")
    raise SystemExit(0)
if mode == "grandchild":
    grandchild = subprocess.Popen(
        [sys.executable, "-I", "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    probe_path.write_text(
        json.dumps({"child_pid": os.getpid(), "grandchild_pid": grandchild.pid}),
        encoding="utf-8",
    )
    while True:
        time.sleep(1)
raise SystemExit(30)
"""


@pytest.fixture(scope="module")
def supervision_project(tmp_path_factory: pytest.TempPathFactory) -> FakeProject:
    return _make_fake_project(tmp_path_factory.mktemp("supervision-mediacrawler"))


def _write_helper(path: Path) -> Path:
    path.write_text(textwrap.dedent(_HELPER_SOURCE).lstrip(), encoding="utf-8")
    return path.resolve()


def _use_helper(
    monkeypatch: pytest.MonkeyPatch,
    spec: bridge_module.MediaCrawlerRunSpec,
    helper: Path,
    *,
    mode: str,
    probe: Path,
) -> bridge_module.MediaCrawlerRunSpec:
    monkeypatch.setattr(bridge_module, "RUNNER_SCRIPT", helper)
    environment = dict(spec.environment)
    environment.update(
        {
            "MEDIA_SYNC_TEST_HELPER_MODE": mode,
            "MEDIA_SYNC_TEST_HELPER_PROBE": str(probe),
        }
    )
    return replace(
        spec,
        command=(
            str(spec.manifest.python_executable),
            "-I",
            "-u",
            "-B",
            str(helper),
            "--manifest",
            str(spec.paths.manifest_path),
        ),
        environment=MappingProxyType(environment),
    )


def _wait_for_json(path: Path, timeout: float = 10.0) -> dict[str, int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            time.sleep(0.02)
            continue
        if isinstance(raw, dict) and all(isinstance(value, int) for value in raw.values()):
            return raw
        time.sleep(0.02)
    raise AssertionError("helper probe was not written within the deadline")


def _wait_for_pids_to_exit(*process_ids: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and any(_pid_is_alive(process_id) for process_id in process_ids):
        time.sleep(0.05)
    assert all(not _pid_is_alive(process_id) for process_id in process_ids)


def test_pre_cancel_does_not_spawn_and_deletes_only_owned_attempt(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_root = tmp_path / "runs"
    spec = _bridge().prepare(_request(supervision_project, integration_root))
    sibling = _bridge().prepare(_request(supervision_project, integration_root))
    sibling_marker = sibling.paths.job_root / "keep.txt"
    sibling_marker.write_text("keep", encoding="utf-8")
    profile_marker = spec.paths.account_root / "profile-owner.txt"
    profile_marker.write_text("keep", encoding="utf-8")
    cancellation = threading.Event()
    cancellation.set()

    def unexpected_spawn(*_args: object, **_kwargs: object) -> subprocess.Popen[bytes]:
        raise AssertionError("pre-cancelled run must not spawn")

    monkeypatch.setattr(runner_module.subprocess, "Popen", unexpected_spawn)
    result = MediaCrawlerProcessRunner().run(spec, cancellation)

    assert result.status is MediaCrawlerProcessStatus.CANCELLED
    assert not spec.paths.job_root.exists()
    assert sibling_marker.read_text(encoding="utf-8") == "keep"
    assert profile_marker.read_text(encoding="utf-8") == "keep"


def test_start_token_is_sent_only_after_tree_attachment(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _write_helper(tmp_path / "handshake-helper.py")
    probe = tmp_path / "handshake.json"
    spec = _use_helper(
        monkeypatch,
        _bridge().prepare(_request(supervision_project, tmp_path / "runs")),
        helper,
        mode="fail",
        probe=probe,
    )
    original_attach = runner_module._WindowsJob.attach.__func__
    observed_before_attach_return = False

    def delayed_attach(
        cls: type[runner_module._WindowsJob],
        process: subprocess.Popen[bytes],
    ) -> runner_module._WindowsJob | None:
        nonlocal observed_before_attach_return
        deadline = time.monotonic() + 2
        while not probe.with_suffix(".prestart").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        observed_before_attach_return = probe.with_suffix(".prestart").exists()
        assert not probe.with_suffix(".poststart").exists()
        return original_attach(cls, process)

    monkeypatch.setattr(runner_module._WindowsJob, "attach", classmethod(delayed_attach))
    result = MediaCrawlerProcessRunner().run(spec)

    assert observed_before_attach_return
    assert probe.with_suffix(".poststart").is_file()
    assert result.status is MediaCrawlerProcessStatus.UPSTREAM_FAILED
    assert not spec.paths.job_root.exists()


def test_running_cancel_joins_child_and_grandchild_before_cleanup(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _write_helper(tmp_path / "grandchild-helper.py")
    probe = tmp_path / "grandchild.json"
    integration_root = tmp_path / "runs"
    spec = _use_helper(
        monkeypatch,
        _bridge().prepare(
            _request(
                supervision_project,
                integration_root,
                limits=WatchdogLimits(max_seconds=30, poll_seconds=0.02),
            )
        ),
        helper,
        mode="grandchild",
        probe=probe,
    )
    sibling = _bridge().prepare(_request(supervision_project, integration_root))
    sibling_marker = sibling.paths.job_root / "keep.txt"
    sibling_marker.write_text("keep", encoding="utf-8")
    cancellation = threading.Event()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(MediaCrawlerProcessRunner().run, spec, cancellation)
        pids = _wait_for_json(probe)
        cancellation.set()
        result = future.result(timeout=15)

    assert result.status is MediaCrawlerProcessStatus.CANCELLED
    assert not spec.paths.job_root.exists()
    assert sibling_marker.read_text(encoding="utf-8") == "keep"
    _wait_for_pids_to_exit(pids["child_pid"], pids["grandchild_pid"])


def test_cancel_after_successful_tree_join_never_starts_receipt_seal(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _write_helper(tmp_path / "pre-seal-helper.py")
    probe = tmp_path / "pre-seal.json"
    spec = _use_helper(
        monkeypatch,
        _bridge().prepare(
            _request(
                supervision_project,
                tmp_path / "runs",
                limits=WatchdogLimits(max_seconds=10, poll_seconds=0.02),
            )
        ),
        helper,
        mode="success",
        probe=probe,
    )
    cancellation = threading.Event()
    tree_joined = threading.Event()
    final_inspection_started = threading.Event()
    release_final_inspection = threading.Event()
    receipt_started = threading.Event()
    original_close = runner_module._close_process_tree
    original_inspect = policies_module.inspect_output
    original_write_receipt = receipt_module.write_completion_receipt

    def observe_tree_join(
        process: subprocess.Popen[bytes],
        windows_job: runner_module._WindowsJob | None,
    ) -> bool:
        closed = original_close(process, windows_job)
        assert closed
        assert process.poll() == 0
        tree_joined.set()
        return closed

    def block_final_inspection(
        root: Path,
        limits: WatchdogLimits | None = None,
    ) -> policies_module.OutputStats:
        if tree_joined.is_set():
            final_inspection_started.set()
            assert release_final_inspection.wait(timeout=10)
        return original_inspect(root, limits)

    def observe_receipt_start(
        manifest: bridge_module.RunnerManifest,
        inspected_stats: policies_module.OutputStats,
        *,
        known_secrets: Sequence[str | SecretValue],
    ) -> receipt_module.CompletionReceipt:
        receipt_started.set()
        return original_write_receipt(
            manifest,
            inspected_stats,
            known_secrets=known_secrets,
        )

    monkeypatch.setattr(runner_module, "_close_process_tree", observe_tree_join)
    monkeypatch.setattr(policies_module, "inspect_output", block_final_inspection)
    monkeypatch.setattr(receipt_module, "write_completion_receipt", observe_receipt_start)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(MediaCrawlerProcessRunner().run, spec, cancellation)
        try:
            pids = _wait_for_json(probe)
            assert final_inspection_started.wait(timeout=10)
            assert tree_joined.is_set()
            cancellation.set()
        finally:
            release_final_inspection.set()
        result = future.result(timeout=15)

    assert result.status is MediaCrawlerProcessStatus.CANCELLED
    assert not receipt_started.is_set()
    assert not spec.paths.job_root.exists()
    _wait_for_pids_to_exit(pids["child_pid"])
    account_lock = runner_module._AccountFileLock(spec.paths.account_root)
    assert account_lock.acquire()
    account_lock.release()


def test_receipt_failure_removes_secret_bytes_but_preserves_profile(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_text = "SUPERVISION-COOKIE-SENTINEL-a84f83"
    helper = _write_helper(tmp_path / "secret-helper.py")
    probe = tmp_path / "secret.json"
    spec = _use_helper(
        monkeypatch,
        _bridge().prepare(
            _request(
                supervision_project,
                tmp_path / "runs",
                login_method=LoginMethod.COOKIE,
                cookie=SecretValue(secret_text),
            )
        ),
        helper,
        mode="secret-success",
        probe=probe,
    )
    spec.paths.profile_root.mkdir(parents=True, exist_ok=True)
    profile_marker = spec.paths.profile_root / "keep.txt"
    profile_marker.write_text("profile", encoding="utf-8")

    result = MediaCrawlerProcessRunner().run(spec)

    assert result.status is MediaCrawlerProcessStatus.COMPLETION_FAILED
    assert not spec.paths.job_root.exists()
    assert profile_marker.read_text(encoding="utf-8") == "profile"
    assert secret_text.encode() not in b"".join(
        path.read_bytes() for path in spec.paths.integration_root.rglob("*") if path.is_file()
    )


def test_control_pipe_eof_before_start_never_loads_manifest(tmp_path: Path) -> None:
    missing_manifest = tmp_path / "missing.json"
    environment = dict(os.environ)
    environment[runner_module._CONTROL_ENV] = runner_module._CONTROL_VERSION
    process = subprocess.Popen(
        (
            sys.executable,
            "-I",
            "-u",
            "-B",
            str(Path(runner_module.__file__).resolve()),
            "--manifest",
            str(missing_manifest),
        ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        start_new_session=os.name != "nt",
        close_fds=True,
    )
    assert process.stdin is not None
    time.sleep(0.2)
    assert process.poll() is None
    process.stdin.close()
    returncode = process.wait(timeout=5)
    assert process.stdout is not None
    assert process.stderr is not None
    process.stdout.close()
    process.stderr.close()

    assert returncode == runner_module.EXIT_CONFIGURATION
    assert not missing_manifest.exists()


def test_public_cleanup_unlinks_links_without_touching_link_target(
    supervision_project: FakeProject,
    tmp_path: Path,
) -> None:
    spec = _bridge().prepare(_request(supervision_project, tmp_path / "runs"))
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    link = spec.paths.output_root / "outside-link"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")

    assert cleanup_attempt_root(spec.paths) is AttemptCleanupStatus.REMOVED
    assert not spec.paths.job_root.exists()
    assert outside.read_text(encoding="utf-8") == "keep"


def test_runner_hard_stops_and_records_redacted_block_when_attempt_cleanup_is_unresolved(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_text = "CLEANUP-FAILURE-COOKIE-SENTINEL-0007"
    spec = _bridge().prepare(
        _request(
            supervision_project,
            tmp_path / "runs",
            login_method=LoginMethod.COOKIE,
            cookie=SecretValue(secret_text),
        )
    )
    leaked_output = spec.paths.output_root / "xhs" / "jsonl" / "unresolved.jsonl"
    leaked_output.parent.mkdir(parents=True, exist_ok=True)
    leaked_output.write_text(secret_text, encoding="utf-8")
    cancellation = threading.Event()
    cancellation.set()
    monkeypatch.setattr(
        runner_module,
        "_cleanup_failed_attempt",
        lambda _spec: AttemptCleanupStatus.UNRESOLVED,
    )

    with pytest.raises(AttemptCleanupError) as raised:
        MediaCrawlerProcessRunner().run(spec, cancellation)

    assert spec.paths.job_root.is_dir()
    assert secret_text not in repr(raised.value)
    account_block, incident = attempt_cleanup_incident_paths(spec.paths)
    assert account_block.is_file() and incident.is_file()
    assert is_attempt_cleanup_blocked(spec.paths)
    expected = {
        "schema_version": 1,
        "code": "mediacrawler_attempt_cleanup_unresolved",
        "scope": {
            "platform": spec.manifest.platform.value,
            "account_id": str(spec.manifest.account_id),
            "execution_id": str(spec.paths.job_root.name),
        },
        "summary": {
            "attempt_cleanup": "unresolved",
            "account_access": "blocked",
        },
    }
    assert json.loads(account_block.read_text(encoding="utf-8")) == expected
    assert json.loads(incident.read_text(encoding="utf-8")) == expected
    marker_bytes = account_block.read_bytes() + incident.read_bytes()
    assert secret_text.encode() not in marker_bytes


def test_cleanup_is_unresolved_when_atomic_quarantine_and_direct_removal_both_fail(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _bridge().prepare(_request(supervision_project, tmp_path / "runs"))

    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("fixture denial")

    monkeypatch.setattr(runner_module, "_quarantine_attempt_root", denied)
    monkeypatch.setattr(runner_module, "_remove_directory_no_follow", denied)

    assert cleanup_attempt_root(spec.paths) is AttemptCleanupStatus.UNRESOLVED
    assert spec.paths.job_root.is_dir()


def test_cleanup_quarantines_when_post_move_scrub_is_denied(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _bridge().prepare(_request(supervision_project, tmp_path / "runs"))
    secret_text = "QUARANTINED-OUTPUT-SENTINEL-0007"
    leaked_output = spec.paths.output_root / "xhs" / "jsonl" / "leak.jsonl"
    leaked_output.parent.mkdir(parents=True, exist_ok=True)
    leaked_output.write_text(secret_text, encoding="utf-8")
    original_remove = runner_module._remove_directory_no_follow

    def deny_quarantine_scrub(path: Path) -> None:
        if ".quarantine" in path.parts:
            raise PermissionError("fixture sharing denial")
        original_remove(path)

    monkeypatch.setattr(runner_module, "_remove_directory_no_follow", deny_quarantine_scrub)

    status = cleanup_attempt_root(spec.paths)

    assert status is AttemptCleanupStatus.QUARANTINED
    assert not spec.paths.job_root.exists()
    quarantine_files = tuple((spec.paths.integration_root / ".quarantine").rglob("*"))
    assert any(path.is_file() and secret_text.encode() in path.read_bytes() for path in quarantine_files)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not the Windows ACL boundary")
def test_existing_quarantine_directory_mode_is_tightened_before_isolation(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _bridge().prepare(_request(supervision_project, tmp_path / "runs"))
    quarantine_root = spec.paths.integration_root / ".quarantine"
    quarantine_root.mkdir(mode=0o777)
    quarantine_root.chmod(0o777)
    original_remove = runner_module._remove_directory_no_follow

    def retain_quarantine(path: Path) -> None:
        if quarantine_root in path.parents or path == quarantine_root:
            raise PermissionError("fixture retention")
        original_remove(path)

    monkeypatch.setattr(runner_module, "_remove_directory_no_follow", retain_quarantine)

    assert cleanup_attempt_root(spec.paths) is AttemptCleanupStatus.QUARANTINED
    assert stat.S_IMODE(os.lstat(quarantine_root).st_mode) == 0o700


def test_quarantined_cleanup_returns_only_fixed_operator_status(
    supervision_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "QUARANTINE-OPERATOR-OUTPUT-SENTINEL-0007"
    spec = _bridge().prepare(
        _request(
            supervision_project,
            tmp_path / "runs",
            login_method=LoginMethod.COOKIE,
            cookie=SecretValue(secret),
        )
    )
    cancellation = threading.Event()
    cancellation.set()
    monkeypatch.setattr(
        runner_module,
        "_cleanup_failed_attempt",
        lambda _spec: AttemptCleanupStatus.QUARANTINED,
    )

    result = MediaCrawlerProcessRunner().run(spec, cancellation)

    assert result.status is MediaCrawlerProcessStatus.COMPLETION_FAILED
    assert secret not in repr(result)
    assert ".quarantine" not in repr(result)


def _run_hard_death_parent(
    project: FakeProject,
    integration_root: Path,
    job_id: UUID,
    parent_probe: Path,
) -> None:
    parent_probe.write_text(json.dumps({"parent_pid": os.getpid()}), encoding="utf-8")
    spec = _bridge().prepare(
        _request(
            project,
            integration_root,
            creator="mode-grandchild",
            job_id=job_id,
            limits=WatchdogLimits(max_seconds=60, poll_seconds=0.02),
        )
    )
    MediaCrawlerProcessRunner().run(spec)


def _hard_kill_process(process_id: int) -> None:
    if os.name == "nt":
        completed = subprocess.run(
            ("taskkill.exe", "/PID", str(process_id), "/F"),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            shell=False,
        )
        assert completed.returncode == 0
        return
    os.kill(process_id, 9)


def _make_long_grandchild_project(root: Path) -> FakeProject:
    project = _make_fake_project(root)
    main_path = project.checkout / "main.py"
    source = main_path.read_text(encoding="utf-8")
    old = """        probe["grandchild_pid"] = grandchild.pid
        _append(path, probe)
        return
"""
    new = """        probe["grandchild_pid"] = grandchild.pid
        probe["child_pid"] = os.getpid()
        _append(path, probe)
        await asyncio.sleep(60)
        return
"""
    assert old in source
    main_path.write_text(source.replace(old, new, 1), encoding="utf-8")
    _git(project.checkout, "add", "main.py")
    _git(
        project.checkout,
        "-c",
        "user.name=media-sync-tests",
        "-c",
        "user.email=tests@example.invalid",
        "commit",
        "-m",
        "long grandchild fixture",
    )
    commit = _git(project.checkout, "rev-parse", "HEAD")
    _write_lock(project, commit)
    return replace(project, commit=commit)


def test_hard_parent_death_stops_real_child_tree_and_allows_safe_recovery(tmp_path: Path) -> None:
    project = _make_long_grandchild_project(tmp_path / "project")
    integration_root = (tmp_path / "runs").resolve()
    job_id = uuid4()
    paths = build_run_paths(integration_root, Platform.XHS, ACCOUNT_ID, job_id)
    parent_probe = tmp_path / "parent.json"
    context = multiprocessing.get_context("spawn")
    parent = context.Process(
        target=_run_hard_death_parent,
        args=(project, integration_root, job_id, parent_probe),
    )
    parent.start()
    try:
        target_parent_pid = _wait_for_json(parent_probe)["parent_pid"]
        deadline = time.monotonic() + 20
        probe: dict[str, object] | None = None
        while time.monotonic() < deadline:
            try:
                records = _records(paths.output_root) if paths.output_root.exists() else []
            except (json.JSONDecodeError, OSError):
                records = []
            probe = next((record for record in records if "grandchild_pid" in record), None)
            if probe is not None:
                break
            if parent.exitcode is not None:
                raise AssertionError(f"hard-death parent exited early with {parent.exitcode}")
            time.sleep(0.05)
        assert probe is not None
        child_pid = int(probe["child_pid"])
        grandchild_pid = int(probe["grandchild_pid"])
        _hard_kill_process(target_parent_pid)
        parent.join(timeout=5)
        assert parent.exitcode is not None
        _wait_for_pids_to_exit(child_pid, grandchild_pid)
        assert cleanup_attempt_root(paths) is AttemptCleanupStatus.REMOVED
        assert not paths.job_root.exists()
        assert paths.account_root.is_dir()
    finally:
        if parent.is_alive():
            parent.kill()
            parent.join(timeout=5)


def test_pinned_shape_parse_cmd_preserves_cookie_delay_and_single_concurrency(tmp_path: Path) -> None:
    project = _make_fake_project(tmp_path / "project")
    cmd_arg = project.checkout / "cmd_arg"
    cmd_arg.mkdir()
    (cmd_arg / "__init__.py").write_text("", encoding="utf-8")
    (cmd_arg / "arg.py").write_text(
        textwrap.dedent(
            """
            import config

            async def parse_cmd():
                def callback(
                    cookies=config.COOKIES,
                    max_concurrency_num=config.MAX_CONCURRENCY_NUM,
                ):
                    config.COOKIES = cookies
                    config.MAX_CONCURRENCY_NUM = max_concurrency_num
                    return cookies, max_concurrency_num
                return callback()
            """
        ).lstrip(),
        encoding="utf-8",
    )
    main_path = project.checkout / "main.py"
    source = main_path.read_text(encoding="utf-8")
    source = source.replace("import config\n", "import config\nfrom cmd_arg.arg import parse_cmd\n", 1)
    source = source.replace(
        "    attribute, creator = _selected_creator()\n",
        "    attribute, creator = _selected_creator()\n    parsed_cookie, parsed_concurrency = await parse_cmd()\n",
        1,
    )
    source = source.replace(
        '        "cookie_sha256": hashlib.sha256(config.COOKIES.encode("utf-8")).hexdigest(),\n',
        '        "cookie_sha256": hashlib.sha256(config.COOKIES.encode("utf-8")).hexdigest(),\n'
        '        "parsed_cookie_sha256": hashlib.sha256(parsed_cookie.encode("utf-8")).hexdigest(),\n'
        '        "parsed_concurrency": parsed_concurrency,\n'
        '        "configured_concurrency": config.MAX_CONCURRENCY_NUM,\n'
        '        "configured_delay": config.CRAWLER_MAX_SLEEP_SEC,\n',
        1,
    )
    main_path.write_text(source, encoding="utf-8")
    _git(project.checkout, "add", "main.py", "cmd_arg/__init__.py", "cmd_arg/arg.py")
    _git(
        project.checkout,
        "-c",
        "user.name=media-sync-tests",
        "-c",
        "user.email=tests@example.invalid",
        "commit",
        "-m",
        "parse callback fixture",
    )
    commit = _git(project.checkout, "rev-parse", "HEAD")
    _write_lock(project, commit)
    project = replace(project, commit=commit)
    secret = "PARSE-CALL-COOKIE-3ebc62"
    spec = _bridge().prepare(
        _request(
            project,
            tmp_path / "runs",
            login_method=LoginMethod.COOKIE,
            cookie=SecretValue(secret),
            request_delay_seconds=7.25,
        )
    )

    result = MediaCrawlerProcessRunner().run(spec)

    assert result.status is MediaCrawlerProcessStatus.SUCCEEDED
    probe = next(record for record in _records(spec.paths.output_root) if record.get("probe"))
    assert probe["parsed_cookie_sha256"] == hashlib.sha256(secret.encode()).hexdigest()
    assert probe["parsed_concurrency"] == probe["configured_concurrency"] == 1
    assert probe["configured_delay"] == 7.25
    assert secret not in spec.paths.manifest_path.read_text(encoding="utf-8")
    assert PRIVATE_INPUT_ENV not in str(probe)
