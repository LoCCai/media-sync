"""Fail-closed configuration checks for background saved-session reuse."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler import detail_runner, login_runner, runner
from media_sync.integrations.mediacrawler.detail_runner import _ChildRequest
from media_sync.integrations.mediacrawler.detail_runner import (
    _configure_upstream as configure_detail,
)
from media_sync.integrations.mediacrawler.policies import (
    WatchdogLimits,
    build_run_paths,
    upstream_login_type,
)
from media_sync.integrations.mediacrawler.runner import _configure_upstream as configure_forward
from media_sync.media import MediaDownloadError

_DETAIL_PLATFORMS = (Platform.XHS, Platform.DY, Platform.KS, Platform.BILI)


def _config() -> SimpleNamespace:
    return SimpleNamespace()


def test_saved_session_uses_noninteractive_upstream_fence() -> None:
    assert upstream_login_type(LoginMethod.SAVED_SESSION) == "saved_session"
    assert upstream_login_type(LoginMethod.SAVED_SESSION) != upstream_login_type(LoginMethod.QR)


@pytest.mark.parametrize("platform", list(Platform))
def test_forward_saved_session_forces_headless_without_qr(tmp_path: Path, platform: Platform) -> None:
    paths = build_run_paths(tmp_path / "runtime", platform, uuid4(), uuid4())
    manifest = cast(
        Any,
        SimpleNamespace(
            account_root=paths.account_root,
            profile_root=paths.profile_root,
            output_root=paths.output_root,
            platform=platform,
            login_method=LoginMethod.SAVED_SESSION,
            max_items=10,
            request_delay_seconds=1.0,
            headless=False,
        ),
    )
    config = _config()

    configure_forward(config, manifest, "creator-reference")

    assert config.LOGIN_TYPE == "saved_session"
    assert config.HEADLESS is config.CDP_HEADLESS is True
    assert config.CRAWLER_TYPE == "creator"


@pytest.mark.parametrize("platform", _DETAIL_PLATFORMS)
def test_detail_saved_session_forces_headless_without_qr(tmp_path: Path, platform: Platform) -> None:
    paths = build_run_paths(tmp_path / "runtime", platform, uuid4(), uuid4())
    paths.profile_root.mkdir(parents=True)
    (paths.profile_root / "state.json").write_text("{}", encoding="utf-8")
    request = _ChildRequest(
        checkout_root=tmp_path.resolve(),
        account_root=paths.account_root,
        profile_root=paths.profile_root,
        job_root=paths.job_root,
        output_root=paths.output_root,
        platform=platform,
        login_method=LoginMethod.SAVED_SESSION,
        content_remote_id="BV1fixture",
        detail_reference="BV1fixture",
        headless=False,
        watchdogs=WatchdogLimits(max_seconds=1),
    )
    config = _config()

    configure_detail(config, request)

    assert config.LOGIN_TYPE == "saved_session"
    assert config.HEADLESS is config.CDP_HEADLESS is True
    assert config.CRAWLER_TYPE == "detail"


@pytest.mark.parametrize("platform", list(Platform))
def test_forward_fence_blocks_qr_after_upstream_coerces_unknown_login_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: Platform,
) -> None:
    """The pinned parser defaults an unknown saved-session token to QR."""

    module_name, class_name = login_runner._LOGIN_CLASSES[platform]
    qr_calls: list[str] = []

    class FakeLogin:
        async def begin(self) -> None:
            qr_calls.append("interactive-qr")

    core_module = ModuleType(module_name)
    setattr(core_module, class_name, FakeLogin)
    monkeypatch.setitem(sys.modules, module_name, core_module)
    config = SimpleNamespace(LOGIN_TYPE=upstream_login_type(LoginMethod.SAVED_SESSION))

    async def upstream_main() -> None:
        # Mirrors MediaCrawler cmd_arg._coerce_enum(..., QRCODE): the unknown
        # defensive token is not itself a sufficient fail-closed boundary.
        if config.LOGIN_TYPE not in {"qrcode", "phone", "cookie"}:
            config.LOGIN_TYPE = "qrcode"
        assert config.LOGIN_TYPE == "qrcode"
        await FakeLogin().begin()

    output_root = tmp_path / "output"
    output_root.mkdir()
    manifest = cast(
        Any,
        SimpleNamespace(
            platform=platform,
            login_method=LoginMethod.SAVED_SESSION,
            output_root=output_root,
            watchdogs=WatchdogLimits(max_seconds=1, poll_seconds=0.01),
        ),
    )

    with pytest.raises(login_runner.SavedSessionQrFallbackBlocked):
        asyncio.run(runner._watch_upstream(SimpleNamespace(main=upstream_main), manifest, None))

    assert qr_calls == []


def test_detail_maps_only_the_qr_fence_to_auth_expired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def blocked(*_args: object, **_kwargs: object) -> None:
        raise login_runner.SavedSessionQrFallbackBlocked

    async def unrelated(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("unrelated upstream failure")

    detail_paths = build_run_paths(tmp_path / "detail", Platform.XHS, uuid4(), uuid4())
    detail_request = _ChildRequest(
        checkout_root=tmp_path.resolve(),
        account_root=detail_paths.account_root,
        profile_root=detail_paths.profile_root,
        job_root=detail_paths.job_root,
        output_root=detail_paths.output_root,
        platform=Platform.XHS,
        login_method=LoginMethod.SAVED_SESSION,
        content_remote_id="fixture",
        detail_reference="fixture",
        headless=False,
        watchdogs=WatchdogLimits(max_seconds=1, poll_seconds=0.01),
    )
    monkeypatch.setattr(detail_runner, "_watch_upstream", blocked)
    assert asyncio.run(detail_runner._execute_child(detail_request)) == ("auth_expired", b"")
    monkeypatch.setattr(detail_runner, "_watch_upstream", unrelated)
    assert asyncio.run(detail_runner._execute_child(detail_request)) == ("result_invalid", b"")


def test_detail_qr_fence_still_runs_upstream_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = (tmp_path / "checkout").resolve()
    checkout.mkdir()
    paths = build_run_paths(tmp_path / "runtime", Platform.XHS, uuid4(), uuid4())
    paths.output_root.mkdir(parents=True)
    request = _ChildRequest(
        checkout_root=checkout,
        account_root=paths.account_root,
        profile_root=paths.profile_root,
        job_root=paths.job_root,
        output_root=paths.output_root,
        platform=Platform.XHS,
        login_method=LoginMethod.SAVED_SESSION,
        content_remote_id="fixture",
        detail_reference="fixture",
        headless=True,
        watchdogs=WatchdogLimits(max_seconds=1, poll_seconds=0.01),
    )
    cleanup_calls: list[str] = []
    config = ModuleType("config")
    config.__file__ = str(checkout / "config.py")
    config.COOKIES = "must-be-cleared"
    upstream = ModuleType("main")
    upstream.__file__ = str(checkout / "main.py")

    async def cleanup() -> None:
        cleanup_calls.append("cleanup")

    async def blocked(_request: object) -> None:
        raise login_runner.SavedSessionQrFallbackBlocked

    upstream.async_cleanup = cleanup
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setitem(sys.modules, "main", upstream)
    monkeypatch.setattr(detail_runner, "_run_upstream", blocked)

    assert asyncio.run(detail_runner._execute_child(request)) == ("auth_expired", b"")
    assert cleanup_calls == ["cleanup"]
    assert config.COOKIES == ""


def test_forward_maps_only_qr_fence_to_auth_expired_and_system_exit_cannot_succeed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = (tmp_path / "checkout").resolve()
    checkout.mkdir()
    paths = build_run_paths(tmp_path / "runtime", Platform.XHS, uuid4(), uuid4())
    paths.profile_root.mkdir(parents=True)
    (paths.profile_root / "authenticated.state").write_text("ok", encoding="utf-8")
    paths.output_root.mkdir(parents=True)
    manifest = cast(
        Any,
        SimpleNamespace(
            request_delay_seconds=1.0,
            python_executable=Path(sys.executable).resolve(),
            checkout_root=checkout,
            account_root=paths.account_root,
            profile_root=paths.profile_root,
            output_root=paths.output_root,
            platform=Platform.XHS,
            login_method=LoginMethod.SAVED_SESSION,
            max_items=1,
            headless=False,
            watchdogs=WatchdogLimits(max_seconds=1, poll_seconds=0.01),
        ),
    )
    from media_sync.integrations.mediacrawler import bridge

    monkeypatch.setattr(bridge, "verify_manifest_checkout", lambda _manifest: SimpleNamespace(root=checkout))
    monkeypatch.setattr(runner, "_configure_upstream", lambda *_args: None)
    monkeypatch.delitem(sys.modules, "config", raising=False)
    monkeypatch.delitem(sys.modules, "main", raising=False)

    async def cleanup() -> None:
        return None

    async def no_op_main() -> None:
        return None

    config = SimpleNamespace(__file__=str(checkout / "config.py"), COOKIES="")
    upstream = SimpleNamespace(__file__=str(checkout / "main.py"), main=no_op_main, async_cleanup=cleanup)
    original_import = runner.importlib.import_module

    async def _store_content(_instance: object, _item: object) -> None:
        return None

    async def _update_note(_item: object) -> None:
        return None

    jsonl_store = SimpleNamespace(store_content=_store_content)
    store_xhs_impl = SimpleNamespace(
        __file__=str(checkout / "store" / "xhs" / "_store_impl.py"),
        XhsJsonlStoreImplement=jsonl_store,
    )
    store_xhs = SimpleNamespace(
        __file__=str(checkout / "store" / "xhs" / "__init__.py"),
        update_xhs_note=_update_note,
        XhsJsonlStoreImplement=jsonl_store,
    )

    def fake_import(name: str) -> Any:
        if name == "config":
            return config
        if name == "main":
            return upstream
        if name == "store.xhs":
            return store_xhs
        if name == "store.xhs._store_impl":
            return store_xhs_impl
        return original_import(name)

    monkeypatch.setattr(runner.importlib, "import_module", fake_import)
    original_watch = runner._watch_upstream
    original_cwd = Path.cwd()
    original_argv = list(sys.argv)
    original_sys_path = list(sys.path)
    try:

        async def blocked(*_args: object, **_kwargs: object) -> None:
            raise login_runner.SavedSessionQrFallbackBlocked

        monkeypatch.setattr(runner, "_watch_upstream", blocked)
        assert asyncio.run(runner._execute_child(manifest, "creator", None, None)) == runner.EXIT_AUTH_EXPIRED

        async def unrelated(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("unrelated upstream failure")

        monkeypatch.setattr(runner, "_watch_upstream", unrelated)
        assert asyncio.run(runner._execute_child(manifest, "creator", None, None)) == runner.EXIT_UPSTREAM

        module_name, class_name = login_runner._LOGIN_CLASSES[Platform.XHS]

        class FakeLogin:
            async def begin(self) -> None:
                raise AssertionError("SystemExit test must fail before login")

        core_module = ModuleType(module_name)
        setattr(core_module, class_name, FakeLogin)
        monkeypatch.setitem(sys.modules, module_name, core_module)

        async def exit_zero() -> None:
            raise SystemExit(0)

        upstream.main = exit_zero
        monkeypatch.setattr(runner, "_watch_upstream", original_watch)
        assert asyncio.run(runner._execute_child(manifest, "creator", None, None)) == runner.EXIT_UPSTREAM
    finally:
        os.chdir(original_cwd)
        sys.argv[:] = original_argv
        sys.path[:] = original_sys_path


def test_forward_child_missing_saved_profile_is_auth_expired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    paths = build_run_paths(tmp_path / "runtime", Platform.XHS, uuid4(), uuid4())
    paths.output_root.mkdir(parents=True)
    manifest = cast(
        Any,
        SimpleNamespace(
            request_delay_seconds=1.0,
            python_executable=Path(sys.executable).resolve(),
            checkout_root=checkout.resolve(),
            output_root=paths.output_root,
            profile_root=paths.profile_root,
            login_method=LoginMethod.SAVED_SESSION,
            watchdogs=WatchdogLimits(max_seconds=1, poll_seconds=0.01),
        ),
    )
    from media_sync.integrations.mediacrawler import bridge

    monkeypatch.setattr(bridge, "verify_manifest_checkout", lambda _manifest: SimpleNamespace(root=checkout.resolve()))
    monkeypatch.delitem(sys.modules, "config", raising=False)
    monkeypatch.delitem(sys.modules, "main", raising=False)
    original_cwd = Path.cwd()
    try:
        result = asyncio.run(runner._execute_child(manifest, "creator", None, None))
    finally:
        # The isolated production child may chdir permanently; keep this unit
        # test from changing the host pytest process for later cases.
        os.chdir(original_cwd)

    assert result == runner.EXIT_AUTH_EXPIRED


def test_detail_child_missing_saved_profile_is_auth_expired(tmp_path: Path) -> None:
    paths = build_run_paths(tmp_path / "runtime", Platform.XHS, uuid4(), uuid4())
    request = _ChildRequest(
        checkout_root=tmp_path.resolve(),
        account_root=paths.account_root,
        profile_root=paths.profile_root,
        job_root=paths.job_root,
        output_root=paths.output_root,
        platform=Platform.XHS,
        login_method=LoginMethod.SAVED_SESSION,
        content_remote_id="fixture",
        detail_reference="fixture",
        headless=False,
        watchdogs=WatchdogLimits(max_seconds=1, poll_seconds=0.01),
    )

    with pytest.raises(detail_runner._ChildAuthExpiredError):
        configure_detail(_config(), request)


def test_detail_child_frame_accepts_only_exact_auth_expired_status() -> None:
    valid = json.dumps(
        {
            "schema_version": detail_runner.DETAIL_RUNNER_SCHEMA_VERSION,
            "status": "auth_expired",
            "payload": "",
        },
        separators=(",", ":"),
    ).encode("ascii")

    assert detail_runner._parse_child_frame(valid) == ("auth_expired", "")
    with pytest.raises(MediaDownloadError):
        detail_runner._parse_child_frame(valid + valid)
    with pytest.raises(MediaDownloadError):
        detail_runner._parse_child_frame(
            b'{"schema_version":1,"status":"auth_expired","status":"succeeded","payload":""}'
        )
