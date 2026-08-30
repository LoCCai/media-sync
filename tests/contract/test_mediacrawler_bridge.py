from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from media_sync.application.mediacrawler import load_normalized_output
from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler.bridge import (
    LEGACY_MANIFEST_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    BridgeConfigurationError,
    BridgeRequest,
    MediaCrawlerBridge,
    MediaCrawlerRunMode,
    MediaCrawlerRunSpec,
    RunnerManifest,
)
from media_sync.integrations.mediacrawler.checkout import (
    MEDIACRAWLER_LICENSE,
    MEDIACRAWLER_LICENSE_SHA256,
    CheckoutValidationError,
    LicenseAcknowledgementRequired,
    VerifiedPython,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.integrations.mediacrawler.policies import (
    FULL_HISTORY_PLATFORMS,
    PRIVATE_INPUT_ENV,
    FullHistoryAcknowledgementRequired,
    MediaCrawlerPolicyError,
    OutputInspectionError,
    OutputLimitKind,
    WatchdogLimits,
    build_run_paths,
    inspect_output,
    normalize_creator_reference,
)
from media_sync.integrations.mediacrawler.receipt import (
    COMPLETION_RECEIPT_NAME,
    COMPLETION_RECEIPT_SCHEMA_VERSION,
    LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION,
    CompletionReceiptError,
    CompletionReceiptErrorCode,
    completion_receipt_path,
    load_validated_output_snapshot,
    write_completion_receipt,
)
from media_sync.integrations.mediacrawler.runner import (
    MediaCrawlerProcessRunner,
    MediaCrawlerProcessStatus,
)
from media_sync.security import SecretValue

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUALIFIED_LICENSE = PROJECT_ROOT / ".upstream" / "MediaCrawler" / "LICENSE"
ACCOUNT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
COOKIE_SENTINEL = "COOKIE-SENTINEL-9f07c7b6"
CREATOR_SENTINEL = "SIGNED-CREATOR-SENTINEL-3a7a53"

_CONFIG_SOURCE = """
import os

PRIVATE_PRESENT_AT_CONFIG_IMPORT = "MEDIA_SYNC_MEDIACRAWLER_PRIVATE_INPUT" in os.environ
PLATFORM = "xhs"
LOGIN_TYPE = "qrcode"
CRAWLER_TYPE = "search"
COOKIES = "fixture-default-cookie"
XHS_CREATOR_ID_LIST = ["fixture-default"]
DY_CREATOR_ID_LIST = ["fixture-default"]
KS_CREATOR_ID_LIST = ["fixture-default"]
BILI_CREATOR_ID_LIST = ["fixture-default"]
WEIBO_CREATOR_ID_LIST = ["fixture-default"]
TIEBA_CREATOR_URL_LIST = ["fixture-default"]
ZHIHU_CREATOR_URL_LIST = ["fixture-default"]
"""

_MAIN_SOURCE = r"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import config

COOKIE_AT_MAIN_IMPORT = config.COOKIES
CLEANUP_CALLS = 0
ACTIVE_CREATOR = ""
ATTRIBUTES = (
    "XHS_CREATOR_ID_LIST",
    "DY_CREATOR_ID_LIST",
    "KS_CREATOR_ID_LIST",
    "BILI_CREATOR_ID_LIST",
    "WEIBO_CREATOR_ID_LIST",
    "TIEBA_CREATOR_URL_LIST",
    "ZHIHU_CREATOR_URL_LIST",
)


def _selected_creator():
    selected = []
    for attribute in ATTRIBUTES:
        values = getattr(config, attribute, [])
        if values:
            selected.append((attribute, values))
    if len(selected) != 1 or len(selected[0][1]) != 1:
        raise RuntimeError("fixture creator list contract failed")
    return selected[0][0], selected[0][1][0]


def _output_file(name="creator_contents_fixture.jsonl"):
    path = Path(config.SAVE_DATA_PATH) / config.PLATFORM / "jsonl" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append(path, value):
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, separators=(",", ":")) + "\n")


async def main():
    global ACTIVE_CREATOR
    attribute, creator = _selected_creator()
    ACTIVE_CREATOR = creator
    print(f"cookie={config.COOKIES} creator={creator}")
    os.write(2, f"cookie={config.COOKIES} creator={creator}\n".encode("utf-8"))
    grandchild_probe = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import os;print(int('MEDIA_SYNC_MEDIACRAWLER_PRIVATE_INPUT' in os.environ))",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    profile = Path(
        os.path.join(os.getcwd(), "browser_data", config.USER_DATA_DIR % config.PLATFORM)
    ).resolve()
    probe = {
        "probe": True,
        "platform": config.PLATFORM,
        "login_type": config.LOGIN_TYPE,
        "crawler_type": config.CRAWLER_TYPE,
        "creator_attribute": attribute,
        "creator_sha256": hashlib.sha256(creator.encode("utf-8")).hexdigest(),
        "cookie_sha256": hashlib.sha256(config.COOKIES.encode("utf-8")).hexdigest(),
        "private_at_config_import": config.PRIVATE_PRESENT_AT_CONFIG_IMPORT,
        "private_in_main": "MEDIA_SYNC_MEDIACRAWLER_PRIVATE_INPUT" in os.environ,
        "private_in_grandchild": grandchild_probe.stdout.strip() == "1",
        "cookie_at_main_import": COOKIE_AT_MAIN_IMPORT,
        "argv": sys.argv,
        "cwd": os.getcwd(),
        "save_data_path": config.SAVE_DATA_PATH,
        "profile": str(profile),
        "max_items": config.CRAWLER_MAX_NOTES_COUNT,
        "flags": {
            "headless": config.HEADLESS,
            "cdp_headless": config.CDP_HEADLESS,
            "save_login": config.SAVE_LOGIN_STATE,
            "cdp": config.ENABLE_CDP_MODE,
            "connect_existing": config.CDP_CONNECT_EXISTING,
            "comments": config.ENABLE_GET_COMMENTS,
            "sub_comments": config.ENABLE_GET_SUB_COMMENTS,
            "media_typo": config.ENABLE_GET_MEIDAS,
            "media": config.ENABLE_GET_MEDIAS,
            "wordcloud": config.ENABLE_GET_WORDCLOUD,
            "proxy": config.ENABLE_IP_PROXY,
            "concurrency": config.MAX_CONCURRENCY_NUM,
            "creator_mode": config.CREATOR_MODE,
            "ssl_disabled": config.DISABLE_SSL_VERIFY,
        },
    }
    path = _output_file()
    if "mode-empty" in creator:
        return
    if "mode-truncated" in creator:
        path.write_bytes(b'{"partial":')
        return
    if "mode-raise" in creator:
        raise RuntimeError(f"cookie={config.COOKIES} creator={creator}")
    if "mode-bytes" in creator:
        _append(path, {"pad": "x" * 2048})
        return
    if "mode-line" in creator:
        _append(path, {"line": "y" * 1024})
        return
    if "mode-items" in creator:
        for index in range(6):
            _append(path, {"index": index})
        return
    if "mode-files" in creator:
        for index in range(4):
            _append(_output_file(f"fixture_{index}.jsonl"), {"index": index})
        return
    if "mode-extension" in creator:
        bad = Path(config.SAVE_DATA_PATH) / "unexpected.txt"
        bad.write_text("bad", encoding="utf-8")
        return
    if "mode-secret-echo" in creator:
        _append(
            path,
            {
                "title": f"ordinary title echoed {config.COOKIES}",
                "raw": {"ordinary_note": f"ordinary raw echoed {creator}"},
            },
        )
        return
    if "mode-grandchild" in creator:
        grandchild = subprocess.Popen(
            [sys.executable, "-I", "-c", "import time;time.sleep(60)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
        )
        probe["grandchild_pid"] = grandchild.pid
        _append(path, probe)
        return
    _append(path, probe)
    if "mode-sleep" in creator:
        await asyncio.sleep(60)


async def async_cleanup():
    global CLEANUP_CALLS
    if "mode-empty" in ACTIVE_CREATOR or "mode-truncated" in ACTIVE_CREATOR:
        return
    CLEANUP_CALLS += 1
    _append(
        _output_file(),
        {"cleanup_calls": CLEANUP_CALLS, "cookie_cleared": config.COOKIES == ""},
    )
"""


@dataclass(frozen=True)
class FakeProject:
    root: Path
    checkout: Path
    lock_path: Path
    commit: str


def _git(checkout: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(checkout), *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def _write_lock(project: FakeProject, commit: str) -> None:
    project.lock_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "upstreams": [
                    {
                        "name": "MediaCrawler",
                        "repository": "https://github.com/NanmiCoder/MediaCrawler.git",
                        "commit": commit,
                        "license": "NON-COMMERCIAL LEARNING LICENSE 1.1",
                        "local_path": ".upstream/MediaCrawler",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _make_fake_project(root: Path) -> FakeProject:
    checkout = root / ".upstream" / "MediaCrawler"
    (checkout / "config").mkdir(parents=True)
    license_bytes = QUALIFIED_LICENSE.read_bytes()
    assert hashlib.sha256(license_bytes).hexdigest() == MEDIACRAWLER_LICENSE_SHA256
    (checkout / "LICENSE").write_bytes(license_bytes)
    (checkout / "config" / "__init__.py").write_text(textwrap.dedent(_CONFIG_SOURCE).lstrip(), encoding="utf-8")
    (checkout / "main.py").write_text(textwrap.dedent(_MAIN_SOURCE).lstrip(), encoding="utf-8")
    _git(checkout.parent, "init", str(checkout))
    _git(checkout, "add", "LICENSE", "main.py", "config/__init__.py")
    _git(
        checkout,
        "-c",
        "user.name=media-sync-tests",
        "-c",
        "user.email=tests@example.invalid",
        "commit",
        "-m",
        "fake checkout",
    )
    commit = _git(checkout, "rev-parse", "HEAD")
    project = FakeProject(root=root, checkout=checkout.resolve(), lock_path=root / "upstreams.lock.json", commit=commit)
    _write_lock(project, commit)
    return project


@pytest.fixture(scope="module")
def fake_project(tmp_path_factory: pytest.TempPathFactory) -> FakeProject:
    return _make_fake_project(tmp_path_factory.mktemp("fake-mediacrawler"))


def _bridge() -> MediaCrawlerBridge:
    return MediaCrawlerBridge(lambda path: VerifiedPython(path.expanduser().resolve()))


def _request(
    project: FakeProject,
    integration_root: Path,
    *,
    platform: Platform = Platform.XHS,
    login_method: LoginMethod = LoginMethod.QR,
    creator: str | SecretValue = "fixture-creator",
    account_id: UUID = ACCOUNT_ID,
    subscription_id: UUID | None = None,
    job_id: UUID | None = None,
    checkpoint_revision_before: int = 0,
    intended_mode: MediaCrawlerRunMode = MediaCrawlerRunMode.FORWARD,
    cookie: SecretValue | None = None,
    allow_full_history: bool | None = None,
    limits: WatchdogLimits | None = None,
    scheduler_job_id: UUID | None = None,
    schedule_revision: int = 0,
    attempt: int = 1,
    execution_id: UUID | None = None,
    sync_run_id: UUID | None = None,
    request_delay_seconds: float = 2.0,
) -> BridgeRequest:
    durable_job_id = job_id or uuid4()
    return BridgeRequest(
        lock_path=project.lock_path,
        integration_root=integration_root,
        python_executable=Path(sys.executable),
        account_id=account_id,
        subscription_id=subscription_id or uuid4(),
        job_id=durable_job_id,
        checkpoint_revision_before=checkpoint_revision_before,
        intended_mode=intended_mode,
        platform=platform,
        login_method=login_method,
        author_remote_id="fixture-creator",
        creator_reference=creator,
        license_acknowledged=True,
        allow_full_history=(platform in FULL_HISTORY_PLATFORMS) if allow_full_history is None else allow_full_history,
        cookie=cookie,
        max_items=17,
        watchdogs=limits or WatchdogLimits(max_seconds=4, poll_seconds=0.02),
        scheduler_job_id=scheduler_job_id or durable_job_id,
        schedule_revision=schedule_revision,
        attempt=attempt,
        execution_id=execution_id,
        sync_run_id=sync_run_id,
        request_delay_seconds=request_delay_seconds,
    )


def _records(output_root: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in output_root.rglob("*.jsonl"):
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return records


def test_checkout_requires_license_acknowledgement(fake_project: FakeProject) -> None:
    with pytest.raises(LicenseAcknowledgementRequired):
        verify_mediacrawler_checkout(fake_project.lock_path, license_acknowledged=False)


@pytest.mark.parametrize("mutation", ["wrong_sha", "dirty", "untracked", "missing", "license"])
def test_checkout_rejects_unqualified_trees(tmp_path: Path, mutation: str) -> None:
    project = _make_fake_project(tmp_path)
    if mutation == "wrong_sha":
        _write_lock(project, "0" * 40)
    elif mutation == "dirty":
        (project.checkout / "main.py").write_text("raise RuntimeError('dirty')\n", encoding="utf-8")
    elif mutation == "untracked":
        (project.checkout / "sitecustomize.py").write_text("raise RuntimeError\n", encoding="utf-8")
    elif mutation == "missing":
        (project.checkout / "main.py").unlink()
    else:
        (project.checkout / "LICENSE").write_text("NON-COMMERCIAL LEARNING LICENSE 1.1\nchanged\n", encoding="utf-8")
    with pytest.raises(CheckoutValidationError):
        verify_mediacrawler_checkout(project.lock_path, license_acknowledged=True)


@pytest.mark.parametrize("returncode", [41, 42])
def test_runtime_doctor_rejects_version_or_import_probe(monkeypatch: pytest.MonkeyPatch, returncode: int) -> None:
    monkeypatch.setattr(
        "media_sync.integrations.mediacrawler.checkout.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=returncode),
    )
    with pytest.raises(CheckoutValidationError):
        verify_mediacrawler_python(Path(sys.executable))


@pytest.mark.parametrize("platform", list(Platform))
def test_seven_platform_dry_run_is_shell_free_and_checkout_relative(
    fake_project: FakeProject, tmp_path: Path, platform: Platform
) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / "runs", platform=platform))
    assert spec.cwd == fake_project.checkout
    assert spec.command[:4] == (str(Path(sys.executable).resolve()), "-I", "-u", "-B")
    assert "--cookies" not in spec.command
    assert "--creator_id" not in spec.command
    assert spec.command[-2] == "--manifest"
    assert spec.paths.output_root.is_relative_to((tmp_path / "runs").resolve())


@pytest.mark.parametrize("platform", list(Platform))
def test_full_history_acknowledgement_matches_audited_platforms(
    fake_project: FakeProject, tmp_path: Path, platform: Platform
) -> None:
    request = _request(
        fake_project,
        tmp_path / platform.value,
        platform=platform,
        allow_full_history=False,
    )
    if platform in FULL_HISTORY_PLATFORMS:
        with pytest.raises(FullHistoryAcknowledgementRequired):
            _bridge().prepare(request)
    else:
        _bridge().prepare(request)


def test_login_policy_and_secret_channel(fake_project: FakeProject, tmp_path: Path) -> None:
    qr = _bridge().prepare(_request(fake_project, tmp_path / "qr"))
    assert set(name for name in qr.environment if name.startswith("MEDIA_SYNC_")) == {PRIVATE_INPUT_ENV}
    assert qr.known_secrets == ()

    secret = SecretValue(COOKIE_SENTINEL)
    cookie = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "cookie",
            login_method=LoginMethod.COOKIE,
            cookie=secret,
        )
    )
    assert cookie.known_secrets == (secret,)
    assert COOKIE_SENTINEL in cookie.environment[PRIVATE_INPUT_ENV]
    with pytest.raises(BridgeConfigurationError):
        _bridge().prepare(_request(fake_project, tmp_path / "missing", login_method=LoginMethod.COOKIE))
    with pytest.raises(MediaCrawlerPolicyError):
        _bridge().prepare(_request(fake_project, tmp_path / "phone", login_method=LoginMethod.PHONE))


def test_creator_secret_provenance_is_explicit_and_unknown_query_is_fail_closed(
    fake_project: FakeProject,
    tmp_path: Path,
) -> None:
    creator = "https://www.xiaohongshu.com/user/profile/mode-secret-echo?opaque=unknown-secret-value"

    with pytest.raises(BridgeConfigurationError, match="resolved SecretValue"):
        _bridge().prepare(_request(fake_project, tmp_path / "plain", creator=creator))

    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "secret",
            creator=SecretValue(creator),
        )
    )
    assert any(isinstance(value, SecretValue) and value.reveal() == creator for value in spec.known_secrets)
    result = MediaCrawlerProcessRunner().run(spec)
    assert result.status is MediaCrawlerProcessStatus.COMPLETION_FAILED
    assert not completion_receipt_path(spec.paths.job_root).exists()


def test_creator_secret_query_component_is_scanned_independently(
    fake_project: FakeProject,
    tmp_path: Path,
) -> None:
    token = "standalone-signature-component"
    creator = f"https://www.xiaohongshu.com/user/profile/abc?upsig={token}"
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "component",
            creator=SecretValue(creator),
        )
    )

    assert any(isinstance(value, SecretValue) and value.reveal() == creator for value in spec.known_secrets)
    assert token in spec.known_secrets


def test_saved_session_and_profile_path_isolation(fake_project: FakeProject, tmp_path: Path) -> None:
    integration_root = tmp_path / "runs"
    job_id = uuid4()
    paths = build_run_paths(integration_root, Platform.XHS, ACCOUNT_ID, job_id)
    paths.profile_root.mkdir(parents=True)
    (paths.profile_root / "state.json").write_text("{}", encoding="utf-8")
    saved = _bridge().prepare(
        _request(
            fake_project,
            integration_root,
            login_method=LoginMethod.SAVED_SESSION,
            job_id=job_id,
        )
    )
    second = _bridge().prepare(_request(fake_project, integration_root, job_id=uuid4()))
    isolated = _bridge().prepare(_request(fake_project, integration_root, account_id=uuid4()))
    assert saved.paths.profile_root == second.paths.profile_root
    assert saved.paths.output_root != second.paths.output_root
    assert isolated.paths.profile_root != saved.paths.profile_root
    with pytest.raises(BridgeConfigurationError):
        _bridge().prepare(_request(fake_project, tmp_path / "absent", login_method=LoginMethod.SAVED_SESSION))


def test_job_id_reuse_and_manifest_path_tampering_are_rejected(fake_project: FakeProject, tmp_path: Path) -> None:
    job_id = uuid4()
    request = _request(fake_project, tmp_path / "runs", job_id=job_id)
    spec = _bridge().prepare(request)
    with pytest.raises(BridgeConfigurationError):
        _bridge().prepare(request)
    payload = json.loads(spec.paths.manifest_path.read_text(encoding="utf-8"))
    payload["output_root"] = str(tmp_path / "escape")
    spec.paths.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(BridgeConfigurationError):
        RunnerManifest.load(spec.paths.manifest_path)


def test_manifest_v3_binds_scheduler_and_attempt_identity(fake_project: FakeProject, tmp_path: Path) -> None:
    scheduler_job_id = uuid4()
    execution_id = uuid4()
    sync_run_id = uuid4()
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "runs",
            job_id=scheduler_job_id,
            scheduler_job_id=scheduler_job_id,
            schedule_revision=12,
            attempt=3,
            execution_id=execution_id,
            sync_run_id=sync_run_id,
            request_delay_seconds=7.5,
        )
    )

    payload = spec.manifest.as_payload()
    assert payload["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert payload["scheduler_job_id"] == str(scheduler_job_id)
    assert payload["schedule_revision"] == 12
    assert payload["attempt"] == 3
    assert payload["execution_id"] == str(execution_id)
    assert payload["sync_run_id"] == str(sync_run_id)
    assert payload["request_delay_seconds"] == 7.5
    assert payload["license_name"] == MEDIACRAWLER_LICENSE
    assert payload["license_sha256"] == MEDIACRAWLER_LICENSE_SHA256
    assert "job_id" not in payload
    assert spec.paths.job_root.name == str(execution_id)
    assert RunnerManifest.load(spec.paths.manifest_path) == spec.manifest


def test_scheduler_retry_reuses_job_but_not_execution_root(fake_project: FakeProject, tmp_path: Path) -> None:
    scheduler_job_id = uuid4()
    first_execution_id = uuid4()
    second_execution_id = uuid4()
    first = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "runs",
            job_id=scheduler_job_id,
            schedule_revision=4,
            attempt=1,
            execution_id=first_execution_id,
            sync_run_id=uuid4(),
        )
    )
    second = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "runs",
            job_id=scheduler_job_id,
            schedule_revision=4,
            attempt=2,
            execution_id=second_execution_id,
            sync_run_id=uuid4(),
        )
    )

    assert first.manifest.scheduler_job_id == second.manifest.scheduler_job_id == scheduler_job_id
    assert first.paths.job_root != second.paths.job_root
    assert first.paths.job_root.name == str(first_execution_id)
    assert second.paths.job_root.name == str(second_execution_id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("unexpected", True),
        ("schedule_revision", -1),
        ("attempt", 0),
        ("request_delay_seconds", 0),
        ("license_sha256", "0" * 64),
    ],
)
def test_manifest_v3_rejects_unknown_or_unqualified_fields(
    fake_project: FakeProject,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / field))
    payload = spec.manifest.as_payload()
    payload[field] = value
    spec.paths.manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    with pytest.raises(BridgeConfigurationError):
        RunnerManifest.load(spec.paths.manifest_path)


def test_signed_creator_and_cookie_never_reach_persistent_or_display_sinks(
    fake_project: FakeProject, tmp_path: Path
) -> None:
    creator = f"https://www.xiaohongshu.com/user/profile/abc?xsec_token={CREATOR_SENTINEL}"
    secret = SecretValue(COOKIE_SENTINEL)
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "runs",
            creator=SecretValue(creator),
            login_method=LoginMethod.COOKIE,
            cookie=secret,
        )
    )
    manifest_text = spec.paths.manifest_path.read_text(encoding="utf-8")
    visible = " ".join(spec.command) + repr(spec) + manifest_text
    assert COOKIE_SENTINEL not in visible
    assert CREATOR_SENTINEL not in visible
    assert creator not in visible
    assert any(isinstance(value, SecretValue) and value.reveal() == creator for value in spec.known_secrets)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("alice-token", "https://www.zhihu.com/people/alice-token"),
        ("https://zhihu.com/people/alice-token", "https://www.zhihu.com/people/alice-token"),
    ],
)
def test_zhihu_creator_shim(value: str, expected: str) -> None:
    assert normalize_creator_reference(Platform.ZHIHU, value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.invalid/people/alice",
        "https://www.zhihu.com/people/alice?token=secret",
        "https://www.zhihu.com/people/alice/",
        "https://www.zhihu.com/people/",
    ],
)
def test_zhihu_creator_shim_rejects_ambiguous_urls(value: str) -> None:
    with pytest.raises(MediaCrawlerPolicyError):
        normalize_creator_reference(Platform.ZHIHU, value)


def test_fake_child_proves_config_cwd_profile_and_private_env_contract(
    fake_project: FakeProject, tmp_path: Path
) -> None:
    creator = f"https://www.xiaohongshu.com/user/profile/abc?xsec_token={CREATOR_SENTINEL}"
    secret = SecretValue(COOKIE_SENTINEL)
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "runs",
            creator=SecretValue(creator),
            login_method=LoginMethod.COOKIE,
            cookie=secret,
        )
    )
    result = MediaCrawlerProcessRunner().run(spec)
    assert result.status is MediaCrawlerProcessStatus.SUCCEEDED
    receipt_path = completion_receipt_path(spec.paths.job_root)
    assert receipt_path.is_file()
    snapshot = load_validated_output_snapshot(spec.manifest)
    assert snapshot.receipt.account_id == spec.manifest.account_id
    assert snapshot.receipt.subscription_id == spec.manifest.subscription_id
    assert snapshot.receipt.job_id == spec.manifest.job_id
    assert snapshot.receipt.intended_mode is MediaCrawlerRunMode.FORWARD
    assert snapshot.stats.files_written == len(snapshot.files) == 1
    assert all(item.payload.endswith(b"\n") for item in snapshot.files)
    receipt_text = receipt_path.read_text(encoding="utf-8")
    assert str(spec.paths.integration_root) not in receipt_text
    assert COOKIE_SENTINEL not in receipt_text
    assert CREATOR_SENTINEL not in receipt_text
    probe = next(record for record in _records(spec.paths.output_root) if record.get("probe"))
    assert probe["cwd"] == str(fake_project.checkout)
    assert probe["save_data_path"] == str(spec.paths.output_root)
    assert probe["profile"] == str(spec.paths.profile_root)
    assert probe["argv"] == ["mediacrawler"]
    assert probe["private_at_config_import"] is False
    assert probe["private_in_main"] is False
    assert probe["private_in_grandchild"] is False
    assert probe["cookie_at_main_import"] == ""
    assert probe["cookie_sha256"] == hashlib.sha256(COOKIE_SENTINEL.encode()).hexdigest()
    assert probe["creator_sha256"] == hashlib.sha256(creator.encode()).hexdigest()
    flags = probe["flags"]
    assert isinstance(flags, dict)
    assert flags == {
        "headless": False,
        "cdp_headless": False,
        "save_login": True,
        "cdp": False,
        "connect_existing": False,
        "comments": False,
        "sub_comments": False,
        "media_typo": False,
        "media": False,
        "wordcloud": False,
        "proxy": False,
        "concurrency": 1,
        "creator_mode": True,
        "ssl_disabled": False,
    }
    cleanup = next(record for record in _records(spec.paths.output_root) if "cleanup_calls" in record)
    assert cleanup == {"cleanup_calls": 1, "cookie_cleared": True}
    rendered = repr(result) + result.message
    assert COOKIE_SENTINEL not in rendered
    assert CREATOR_SENTINEL not in rendered


def test_parent_rejects_exact_known_secrets_in_ordinary_output_fields(
    fake_project: FakeProject,
    tmp_path: Path,
) -> None:
    cookie = SecretValue("机密曲奇凭据")
    creator = "https://www.xiaohongshu.com/user/profile/mode-secret-echo?upsig=机密创作者签名"
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "secret-output",
            creator=SecretValue(creator),
            login_method=LoginMethod.COOKIE,
            cookie=cookie,
        )
    )

    result = MediaCrawlerProcessRunner().run(spec)

    assert result.status is MediaCrawlerProcessStatus.COMPLETION_FAILED
    assert not completion_receipt_path(spec.paths.job_root).exists()
    assert not spec.paths.job_root.exists()
    retained_bytes = b"".join(path.read_bytes() for path in spec.paths.integration_root.rglob("*") if path.is_file())
    assert cookie.reveal().encode("utf-8") not in retained_bytes
    assert creator.encode("utf-8") not in retained_bytes
    rendered = repr(result) + result.message
    assert cookie.reveal() not in rendered
    assert creator not in rendered


@pytest.mark.parametrize(
    ("record", "secret"),
    [
        ({"title": f"ordinary title echoed {COOKIE_SENTINEL}"}, COOKIE_SENTINEL),
        ({"raw": {"ordinary_note": "ordinary raw echoed 机密值"}}, "机密值"),
    ],
)
def test_receipt_rejects_raw_bytes_and_json_escaped_known_values(
    fake_project: FakeProject,
    tmp_path: Path,
    record: dict[str, object],
    secret: str,
) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / uuid4().hex))
    payload = (json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n").encode("utf-8")
    if secret == "机密值":
        assert secret.encode("utf-8") not in payload
    _write_manual_jsonl(spec, payload)

    with pytest.raises(CompletionReceiptError) as captured:
        write_completion_receipt(
            spec.manifest,
            inspect_output(spec.paths.output_root, spec.manifest.watchdogs),
            known_secrets=(SecretValue(secret),),
        )

    assert captured.value.code is CompletionReceiptErrorCode.KNOWN_SECRET_DISCLOSURE
    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)
    assert not completion_receipt_path(spec.paths.job_root).exists()


@pytest.mark.parametrize(
    ("mode", "limits", "expected"),
    [
        (
            "mode-sleep",
            WatchdogLimits(max_seconds=0.8, poll_seconds=0.02),
            MediaCrawlerProcessStatus.TIMED_OUT,
        ),
        (
            "mode-bytes",
            WatchdogLimits(max_seconds=4, max_output_bytes=300, max_line_bytes=4096, poll_seconds=0.02),
            MediaCrawlerProcessStatus.OUTPUT_BYTES_EXCEEDED,
        ),
        (
            "mode-items",
            WatchdogLimits(max_seconds=4, max_output_items=2, poll_seconds=0.02),
            MediaCrawlerProcessStatus.OUTPUT_ITEMS_EXCEEDED,
        ),
        (
            "mode-files",
            WatchdogLimits(max_seconds=4, max_output_files=2, poll_seconds=0.02),
            MediaCrawlerProcessStatus.OUTPUT_FILES_EXCEEDED,
        ),
        (
            "mode-line",
            WatchdogLimits(max_seconds=4, max_output_bytes=4096, max_line_bytes=128, poll_seconds=0.02),
            MediaCrawlerProcessStatus.OUTPUT_LINE_EXCEEDED,
        ),
        (
            "mode-extension",
            WatchdogLimits(max_seconds=4, poll_seconds=0.02),
            MediaCrawlerProcessStatus.OUTPUT_TREE_INVALID,
        ),
    ],
)
def test_parent_and_child_watchdogs(
    fake_project: FakeProject,
    tmp_path: Path,
    mode: str,
    limits: WatchdogLimits,
    expected: MediaCrawlerProcessStatus,
) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / mode, creator=mode, limits=limits))
    result = MediaCrawlerProcessRunner().run(spec)
    assert result.status is expected
    assert not completion_receipt_path(spec.paths.job_root).exists()


@pytest.mark.parametrize(
    ("creator", "expected"),
    [
        ("mode-empty", MediaCrawlerProcessStatus.SUCCEEDED),
        ("mode-truncated", MediaCrawlerProcessStatus.COMPLETION_FAILED),
        ("mode-raise", MediaCrawlerProcessStatus.UPSTREAM_FAILED),
    ],
)
def test_parent_seals_empty_success_but_not_truncated_or_failed_output(
    fake_project: FakeProject,
    tmp_path: Path,
    creator: str,
    expected: MediaCrawlerProcessStatus,
) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / creator, creator=creator))
    result = MediaCrawlerProcessRunner().run(spec)
    assert result.status is expected
    if expected is MediaCrawlerProcessStatus.SUCCEEDED:
        snapshot = load_validated_output_snapshot(spec.manifest)
        assert snapshot.files == ()
        assert snapshot.receipt.files == ()
        assert snapshot.receipt.directories == ("xhs", "xhs/jsonl")
        assert snapshot.stats == type(snapshot.stats)()
        assert snapshot.receipt.account_id == spec.manifest.account_id
        assert snapshot.receipt.subscription_id == spec.manifest.subscription_id
        assert snapshot.receipt.job_id == spec.manifest.job_id
    else:
        assert not completion_receipt_path(spec.paths.job_root).exists()


def test_child_exception_and_native_output_are_fixed_and_redacted(fake_project: FakeProject, tmp_path: Path) -> None:
    creator = f"mode-raise-{CREATOR_SENTINEL}"
    secret = SecretValue(COOKIE_SENTINEL)
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "direct",
            creator=creator,
            login_method=LoginMethod.COOKIE,
            cookie=secret,
        )
    )
    completed = subprocess.run(
        spec.command,
        cwd=spec.cwd,
        env=dict(spec.environment),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    combined = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert json.loads(completed.stdout) == {"status": "upstream_failed"}
    assert completed.stderr == ""
    assert COOKIE_SENTINEL not in combined
    assert CREATOR_SENTINEL not in combined


def test_account_profile_lock_serializes_same_account(fake_project: FakeProject, tmp_path: Path) -> None:
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "runs",
            creator="mode-sleep",
            limits=WatchdogLimits(max_seconds=1.2, poll_seconds=0.02),
        )
    )
    runner = MediaCrawlerProcessRunner()
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(runner.run, spec)
        deadline = time.monotonic() + 3
        while not any(spec.paths.output_root.rglob("*.jsonl")) and time.monotonic() < deadline:
            time.sleep(0.02)
        second = runner.run(spec)
        first_result = first.result(timeout=5)
    assert second.status is MediaCrawlerProcessStatus.ACCOUNT_BUSY
    assert first_result.status is MediaCrawlerProcessStatus.TIMED_OUT


def _pid_is_alive(process_id: int) -> bool:
    if os.name == "nt":
        completed = subprocess.run(
            ("tasklist.exe", "/FI", f"PID eq {process_id}", "/FO", "CSV", "/NH"),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return any(
            len(row) > 1 and row[1].isdigit() and int(row[1]) == process_id
            for row in csv.reader(completed.stdout.splitlines())
        )
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    return True


def test_process_tree_is_closed_after_direct_child_exits(fake_project: FakeProject, tmp_path: Path) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / "runs", creator="mode-grandchild"))
    result = MediaCrawlerProcessRunner().run(spec)
    assert result.status is MediaCrawlerProcessStatus.SUCCEEDED
    assert load_validated_output_snapshot(spec.manifest).stats.jsonl_items >= 1
    probe = next(record for record in _records(spec.paths.output_root) if record.get("probe"))
    process_id = int(probe["grandchild_pid"])
    deadline = time.monotonic() + 3
    while _pid_is_alive(process_id) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _pid_is_alive(process_id)


def test_output_scanner_detects_open_time_file_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "output"
    output.mkdir()
    target = output / "records.jsonl"
    target.write_text("{}\n", encoding="utf-8")
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_text("{}\n", encoding="utf-8")
    original_open = Path.open
    swapped = False

    def swapping_open(path: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal swapped
        if path == target and not swapped:
            swapped = True
            os.replace(replacement, target)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", swapping_open)
    with pytest.raises(OutputInspectionError) as captured:
        inspect_output(output)
    assert captured.value.kind is OutputLimitKind.TREE


def test_output_scanner_rejects_symlink_or_reparse_points(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    link = output / "linked.jsonl"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(OutputInspectionError) as captured:
        inspect_output(output)
    assert captured.value.kind is OutputLimitKind.TREE


def _write_manual_jsonl(spec: MediaCrawlerRunSpec, payload: bytes = b"{}\n") -> Path:
    target = spec.paths.output_root / "xhs" / "jsonl" / "contents.jsonl"
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    return target


def _seal_manual_output(spec: MediaCrawlerRunSpec) -> None:
    write_completion_receipt(
        spec.manifest,
        inspect_output(spec.paths.output_root, spec.manifest.watchdogs),
        known_secrets=spec.known_secrets,
    )


def _legacy_v2_manifest_payload(manifest: RunnerManifest) -> dict[str, object]:
    payload = manifest.as_payload()
    return {
        "schema_version": LEGACY_MANIFEST_SCHEMA_VERSION,
        "checkout_root": payload["checkout_root"],
        "lock_path": payload["lock_path"],
        "python_executable": payload["python_executable"],
        "integration_root": payload["integration_root"],
        "account_id": payload["account_id"],
        "subscription_id": payload["subscription_id"],
        "job_id": payload["scheduler_job_id"],
        "checkpoint_revision_before": payload["checkpoint_revision_before"],
        "intended_mode": payload["intended_mode"],
        "account_root": payload["account_root"],
        "profile_root": payload["profile_root"],
        "job_root": payload["job_root"],
        "output_root": payload["output_root"],
        "upstream_sha": payload["upstream_sha"],
        "platform": payload["platform"],
        "login_method": payload["login_method"],
        "author_remote_id_fingerprint_sha256": payload["author_remote_id_fingerprint_sha256"],
        "creator_fingerprint_sha256": payload["creator_fingerprint_sha256"],
        "license_acknowledged": payload["license_acknowledged"],
        "allow_full_history": payload["allow_full_history"],
        "headless": payload["headless"],
        "max_items": payload["max_items"],
        "watchdogs": payload["watchdogs"],
    }


def _write_legacy_v1_receipt(manifest: RunnerManifest, target: Path) -> bytes:
    manifest_bytes = (manifest.job_root / "runner-manifest.json").read_bytes()
    relative_path = target.relative_to(manifest.output_root).as_posix()
    directories = sorted(
        {
            parent.relative_to(manifest.output_root).as_posix()
            for parent in target.parents
            if parent != manifest.output_root and parent.is_relative_to(manifest.output_root)
        }
    )
    payload = {
        "schema_version": LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION,
        "status": "succeeded",
        "account_id": str(manifest.account_id),
        "subscription_id": str(manifest.subscription_id),
        "job_id": str(manifest.job_id),
        "checkpoint_revision_before": manifest.checkpoint_revision_before,
        "platform": manifest.platform.value,
        "intended_mode": manifest.intended_mode.value,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "directories": directories,
        "files": [
            {
                "relative_path": relative_path,
                "size_bytes": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        ],
    }
    encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    completion_receipt_path(manifest.job_root).write_bytes(encoded)
    return encoded


def test_sealed_v2_v1_artifacts_round_trip_byte_exact_and_read_only(
    fake_project: FakeProject,
    tmp_path: Path,
) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / "legacy"))
    legacy_output_bytes = (PROJECT_ROOT / "tests/fixtures/mediacrawler/xhs/contents.v1.jsonl").read_bytes()
    target = _write_manual_jsonl(spec, legacy_output_bytes)
    legacy_payload = _legacy_v2_manifest_payload(spec.manifest)
    legacy_manifest_bytes = json.dumps(
        legacy_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    spec.paths.manifest_path.write_bytes(legacy_manifest_bytes)

    legacy_manifest = RunnerManifest.load(spec.paths.manifest_path)
    assert legacy_manifest.schema_version == LEGACY_MANIFEST_SCHEMA_VERSION
    assert (
        json.dumps(legacy_manifest.as_payload(), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        == legacy_manifest_bytes
    )
    with pytest.raises(CompletionReceiptError) as unsealed:
        write_completion_receipt(
            legacy_manifest,
            inspect_output(legacy_manifest.output_root, legacy_manifest.watchdogs),
            known_secrets=(),
        )
    assert unsealed.value.code is CompletionReceiptErrorCode.IDENTITY_MISMATCH
    assert not completion_receipt_path(legacy_manifest.job_root).exists()

    legacy_receipt_bytes = _write_legacy_v1_receipt(legacy_manifest, target)
    snapshot = load_validated_output_snapshot(legacy_manifest)
    assert snapshot.receipt.schema_version == LEGACY_COMPLETION_RECEIPT_SCHEMA_VERSION
    assert snapshot.files[0].payload == legacy_output_bytes
    normalized = load_normalized_output(
        legacy_manifest,
        creator_remote_id="fixture-creator",
        creator_display_name="Legacy fixture creator",
        ingested_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    assert normalized.input_records == len(normalized.records) == 2
    assert {record.content.remote_id for record in normalized.records} == {"xhs-image-002", "xhs-mixed-001"}
    assert spec.paths.manifest_path.read_bytes() == legacy_manifest_bytes
    assert completion_receipt_path(legacy_manifest.job_root).read_bytes() == legacy_receipt_bytes


def test_receipt_distinguishes_missing_empty_and_truncated_output(fake_project: FakeProject, tmp_path: Path) -> None:
    missing = _bridge().prepare(_request(fake_project, tmp_path / "missing"))
    with pytest.raises(CompletionReceiptError):
        load_validated_output_snapshot(missing.manifest)
    _seal_manual_output(missing)
    empty_snapshot = load_validated_output_snapshot(missing.manifest)
    assert empty_snapshot.files == ()
    assert empty_snapshot.receipt.files == ()
    assert empty_snapshot.receipt.directories == ()
    assert (
        empty_snapshot.receipt.manifest_sha256 == hashlib.sha256(missing.paths.manifest_path.read_bytes()).hexdigest()
    )

    zero_file = _bridge().prepare(_request(fake_project, tmp_path / "zero-file"))
    _write_manual_jsonl(zero_file, b"")
    with pytest.raises(CompletionReceiptError) as empty_file:
        _seal_manual_output(zero_file)
    assert empty_file.value.code is CompletionReceiptErrorCode.EMPTY_OUTPUT

    truncated = _bridge().prepare(_request(fake_project, tmp_path / "truncated"))
    _write_manual_jsonl(truncated, b'{"record":true}')
    with pytest.raises(CompletionReceiptError) as incomplete:
        _seal_manual_output(truncated)
    assert incomplete.value.code is CompletionReceiptErrorCode.INCOMPLETE_OUTPUT
    assert not completion_receipt_path(truncated.paths.job_root).exists()


@pytest.mark.parametrize("mutation", ["append", "extra_file", "extra_directory", "manifest", "receipt"])
def test_receipt_snapshot_rejects_post_completion_tampering(
    fake_project: FakeProject,
    tmp_path: Path,
    mutation: str,
) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / mutation))
    target = _write_manual_jsonl(spec, b'{"record":true}\n')
    _seal_manual_output(spec)

    if mutation == "append":
        with target.open("ab") as stream:
            stream.write(b"{}\n")
    elif mutation == "extra_file":
        (target.parent / "extra.jsonl").write_bytes(b"{}\n")
    elif mutation == "extra_directory":
        (spec.paths.output_root / "empty").mkdir()
    elif mutation == "manifest":
        manifest_payload = json.loads(spec.paths.manifest_path.read_text(encoding="utf-8"))
        manifest_payload["headless"] = not manifest_payload["headless"]
        spec.paths.manifest_path.write_text(
            json.dumps(manifest_payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
    else:
        receipt_path = completion_receipt_path(spec.paths.job_root)
        receipt_payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_payload["unexpected"] = True
        receipt_path.write_text(json.dumps(receipt_payload), encoding="utf-8")

    with pytest.raises(CompletionReceiptError):
        load_validated_output_snapshot(spec.manifest)


def test_receipt_snapshot_detects_scan_to_open_file_swap(
    fake_project: FakeProject,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _bridge().prepare(_request(fake_project, tmp_path / "swap"))
    target = _write_manual_jsonl(spec, b'{"record":"original"}\n')
    _seal_manual_output(spec)
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_bytes(b'{"record":"replacement"}\n')
    original_open = os.open
    swapped = False

    def swapping_open(path: str | bytes | os.PathLike[str] | os.PathLike[bytes], flags: int, mode: int = 0o777) -> int:
        nonlocal swapped
        if Path(path) == target and not swapped:
            swapped = True
            os.replace(replacement, target)
        return original_open(path, flags, mode)

    monkeypatch.setattr("media_sync.integrations.mediacrawler.receipt.os.open", swapping_open)
    with pytest.raises(CompletionReceiptError):
        load_validated_output_snapshot(spec.manifest)
    assert swapped


def test_receipt_snapshot_rejects_symlink_or_hardlink_substitution(
    fake_project: FakeProject,
    tmp_path: Path,
) -> None:
    symlink_spec = _bridge().prepare(_request(fake_project, tmp_path / "symlink"))
    symlink_target = _write_manual_jsonl(symlink_spec)
    _seal_manual_output(symlink_spec)
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"{}\n")
    symlink_target.unlink()
    try:
        symlink_target.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(CompletionReceiptError):
        load_validated_output_snapshot(symlink_spec.manifest)

    hardlink_spec = _bridge().prepare(_request(fake_project, tmp_path / "hardlink"))
    hardlink_target = _write_manual_jsonl(hardlink_spec)
    _seal_manual_output(hardlink_spec)
    linked = tmp_path / "linked.jsonl"
    try:
        os.link(hardlink_target, linked)
    except OSError:
        pytest.skip("hardlink creation is unavailable on this host")
    with pytest.raises(CompletionReceiptError):
        load_validated_output_snapshot(hardlink_spec.manifest)


def test_receipt_is_versioned_strict_relative_and_single_use(fake_project: FakeProject, tmp_path: Path) -> None:
    scheduler_job_id = uuid4()
    execution_id = uuid4()
    sync_run_id = uuid4()
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / "strict",
            job_id=scheduler_job_id,
            schedule_revision=9,
            attempt=4,
            execution_id=execution_id,
            sync_run_id=sync_run_id,
            intended_mode=MediaCrawlerRunMode.BACKFILL,
            checkpoint_revision_before=7,
        )
    )
    _write_manual_jsonl(spec, b'{"record":true}\n')
    _seal_manual_output(spec)
    snapshot = load_validated_output_snapshot(spec.manifest)
    receipt_payload = snapshot.receipt.as_payload()
    assert receipt_payload["schema_version"] == COMPLETION_RECEIPT_SCHEMA_VERSION
    assert receipt_payload["status"] == "succeeded"
    assert receipt_payload["scheduler_job_id"] == str(scheduler_job_id)
    assert receipt_payload["schedule_revision"] == 9
    assert receipt_payload["attempt"] == 4
    assert receipt_payload["execution_id"] == str(execution_id)
    assert receipt_payload["sync_run_id"] == str(sync_run_id)
    assert "job_id" not in receipt_payload
    assert receipt_payload["checkpoint_revision_before"] == 7
    assert receipt_payload["intended_mode"] == "backfill"
    assert all(not Path(item.relative_path).is_absolute() for item in snapshot.receipt.files)
    assert completion_receipt_path(spec.paths.job_root).name == COMPLETION_RECEIPT_NAME
    with pytest.raises(CompletionReceiptError) as reused:
        _seal_manual_output(spec)
    assert reused.value.code is CompletionReceiptErrorCode.ALREADY_EXISTS


@pytest.mark.parametrize(
    "field",
    ["scheduler_job_id", "schedule_revision", "attempt", "execution_id", "sync_run_id"],
)
def test_receipt_v2_rejects_every_attempt_identity_mismatch(
    fake_project: FakeProject,
    tmp_path: Path,
    field: str,
) -> None:
    spec = _bridge().prepare(
        _request(
            fake_project,
            tmp_path / field,
            job_id=uuid4(),
            schedule_revision=8,
            attempt=2,
            execution_id=uuid4(),
            sync_run_id=uuid4(),
        )
    )
    _write_manual_jsonl(spec, b'{"record":true}\n')
    _seal_manual_output(spec)
    receipt_path = completion_receipt_path(spec.paths.job_root)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload[field] = payload[field] + 1 if field in {"schedule_revision", "attempt"} else str(uuid4())
    receipt_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(CompletionReceiptError) as mismatch:
        load_validated_output_snapshot(spec.manifest)
    assert mismatch.value.code is CompletionReceiptErrorCode.IDENTITY_MISMATCH
