"""Bounded MediaCrawler detail-mode execution returning ephemeral JSONL bytes.

The production runner uses the locked upstream checkout, the account's stable
browser profile and a short-lived attempt directory.  Detail JSONL is read
back into memory and the attempt directory is removed before this API returns;
callers never receive a path that could accidentally become durable state.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MethodType
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

# ``-I path/to/detail_runner.py --child`` intentionally starts without the
# repository on sys.path.  Bootstrap only this package root before importing
# media-sync; private inputs still arrive over stdin, never the environment.
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from media_sync.domain import LoginMethod, Platform
from media_sync.integrations.mediacrawler.bilibili_media import (
    BILIBILI_DASH_PAGE_FIELD,
    BILIBILI_MAX_DURL_SEGMENTS,
    BILIBILI_PAGES_FIELD,
    BILIBILI_PROGRESSIVE_BACKUPS_FIELD,
    BILIBILI_PROGRESSIVE_FORMAT_FIELD,
    BILIBILI_PROGRESSIVE_PAGE_FIELD,
    BILIBILI_PROGRESSIVE_SEGMENTS_FIELD,
    BilibiliPageIdentity,
    parse_bilibili_view_pages,
)
from media_sync.integrations.mediacrawler.browser_environment import browser_child_environment
from media_sync.integrations.mediacrawler.browser_policy import install_bundled_chromium_policy
from media_sync.integrations.mediacrawler.checkout import (
    VerifiedCheckout,
    VerifiedPython,
    normalize_python_executable,
    verify_mediacrawler_checkout,
    verify_mediacrawler_python,
)
from media_sync.integrations.mediacrawler.kuaishou_media import install_kuaishou_media_capture
from media_sync.integrations.mediacrawler.normalizers import _BILI_PROGRESSIVE_FIELD
from media_sync.integrations.mediacrawler.policies import (
    CREATOR_CONFIG_ATTRIBUTES,
    RunPaths,
    WatchdogLimits,
    build_run_paths,
    inspect_output,
    upstream_login_type,
)
from media_sync.integrations.mediacrawler.runner import (
    _AccountFileLock,
    _close_process_tree,
    _WindowsJob,
)
from media_sync.integrations.mediacrawler.tieba_media import (
    install_tieba_media_capture,
    validate_tieba_thread_url,
)
from media_sync.integrations.mediacrawler.weibo_media import (
    install_weibo_media_capture,
    is_weibo_numeric_note_id,
)
from media_sync.integrations.mediacrawler.xhs_authority import (
    validate_xhs_creator_reference,
    validate_xhs_detail_reference,
)
from media_sync.integrations.mediacrawler.xhs_live import install_xhs_live_capture
from media_sync.integrations.mediacrawler.zhihu_media import (
    install_zhihu_media_capture,
    validate_zhihu_answer_url,
)
from media_sync.media import (
    MediaRequestProfile,
    ResolvedDashLocator,
    ResolvedFlvLocator,
    ResolvedFlvSegmentsLocator,
    ResolvedLocator,
    ResolvedMediaTarget,
    ResolvedSegmentsLocator,
)
from media_sync.media.errors import MediaDownloadError
from media_sync.security import SecretValue
from media_sync.security.secrets import MAX_SECRET_BYTES

DETAIL_RUNNER_SCHEMA_VERSION = 10
MAX_DETAIL_REQUEST_BYTES = 128 * 1024
MAX_DETAIL_FRAME_OVERHEAD = 8 * 1024

_SUPPORTED_PLATFORMS = frozenset(
    {Platform.XHS, Platform.DY, Platform.KS, Platform.BILI, Platform.WB, Platform.TIEBA, Platform.ZHIHU}
)
_DETAIL_CONFIG_ATTRIBUTES = {
    Platform.XHS: "XHS_SPECIFIED_NOTE_URL_LIST",
    Platform.DY: "DY_SPECIFIED_ID_LIST",
    Platform.KS: "KS_SPECIFIED_ID_LIST",
    Platform.BILI: "BILI_SPECIFIED_ID_LIST",
    Platform.WB: "WEIBO_SPECIFIED_ID_LIST",
    Platform.TIEBA: "TIEBA_SPECIFIED_ID_LIST",
    Platform.ZHIHU: "ZHIHU_SPECIFIED_ID_LIST",
}


class MediaCrawlerDetailPayloadRunner(Protocol):
    """Dependency-injection boundary used by the context-aware refresher."""

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        """Return bounded content JSONL in memory or one fixed download error."""
        ...


def _is_weibo_detail_reference(value: object, content_remote_id: str) -> bool:
    """Accept only the implicit ID or the exact same non-secret Weibo ID."""

    return is_weibo_numeric_note_id(content_remote_id) and (
        value is None or (type(value) is str and value == content_remote_id)
    )


def _is_zhihu_detail_reference(value: object, content_remote_id: str) -> bool:
    """Accept only one canonical, non-secret Answer URL bound to this ID."""

    if type(value) is not str:
        return False
    try:
        return validate_zhihu_answer_url(value, answer_id=content_remote_id) == value
    except ValueError:
        return False


def _is_tieba_detail_reference(value: object, content_remote_id: str) -> bool:
    """Accept only one canonical, non-secret Tieba thread URL bound to this ID."""

    if type(value) is not str:
        return False
    try:
        return validate_tieba_thread_url(value, note_id=content_remote_id) == value
    except ValueError:
        return False


def _validate_bili_dynamic_mode(
    *,
    enabled: object,
    platform: Platform,
    did: str,
    author: str,
    dynamic_type: object,
    pub_ts: object,
    detail_reference: object,
    progressive: bool,
    cid: int | None,
) -> None:
    """A numeric DID is meaningful only with an explicit, fenced namespace."""

    if type(enabled) is not bool:
        raise ValueError("invalid Bilibili dynamic mode")
    if not enabled:
        if dynamic_type is not None or pub_ts is not None:
            raise ValueError("unexpected Bilibili dynamic identity")
        return
    if (
        platform is not Platform.BILI
        or progressive
        or cid is not None
        or dynamic_type not in {"DYNAMIC_TYPE_WORD", "DYNAMIC_TYPE_DRAW"}
        or type(pub_ts) is not int
        or not 1 <= pub_ts <= 253_402_300_799
        or (detail_reference is not None and (type(detail_reference) is not str or detail_reference != did))
    ):
        raise ValueError("invalid Bilibili dynamic identity")
    for identifier in (did, author):
        if (
            not identifier.isascii()
            or not identifier.isdecimal()
            or not 1 <= int(identifier) <= 2**63 - 1
            or str(int(identifier)) != identifier
        ):
            raise ValueError("invalid Bilibili dynamic identity")


def _validate_xhs_request_authority(
    *,
    detail_reference: object,
    creator_reference: object,
    creator_max_items: object,
    content_remote_id: str,
    author_remote_id: str,
    watchdogs: WatchdogLimits,
) -> None:
    try:
        if detail_reference is not None:
            if not isinstance(detail_reference, SecretValue):
                raise ValueError
            if creator_reference is not None or creator_max_items is not None:
                raise ValueError
            validate_xhs_detail_reference(detail_reference.reveal(), content_remote_id)
            return
        if not isinstance(creator_reference, SecretValue):
            raise ValueError
        if type(creator_max_items) is not int or not 1 <= creator_max_items <= 1_000:
            raise ValueError
        if creator_max_items > watchdogs.max_output_items:
            raise ValueError
        validate_xhs_creator_reference(creator_reference.reveal(), author_remote_id)
    except ValueError as exc:
        raise MediaDownloadError("locator_refresh_configuration_invalid") from exc


@dataclass(frozen=True, slots=True)
class MediaCrawlerDetailRequest:
    """One frozen, account-bound detail lookup with no database dependency."""

    account_id: UUID
    subscription_id: UUID
    platform: Platform
    login_method: LoginMethod
    content_remote_id: str
    author_remote_id: str
    detail_reference: str | SecretValue | None = field(default=None, repr=False)
    creator_reference: SecretValue | None = field(default=None, repr=False)
    creator_max_items: int | None = None
    cookie: SecretValue | None = field(default=None, repr=False)
    headless: bool = True
    request_delay_seconds: float = 2.0
    bili_progressive_detail: bool = False
    bili_video_cid: int | None = None
    watchdogs: WatchdogLimits = field(default_factory=WatchdogLimits)
    bili_dynamic_detail: bool = False
    bili_dynamic_type: str | None = None
    bili_dynamic_pub_ts: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, UUID) or not isinstance(self.subscription_id, UUID):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        try:
            platform = Platform(self.platform)
            login_method = LoginMethod(self.login_method)
        except (TypeError, ValueError) as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
        content_remote_id = _bounded_text(self.content_remote_id)
        author_remote_id = _bounded_text(self.author_remote_id, maximum=255)
        if platform not in _SUPPORTED_PLATFORMS or login_method is LoginMethod.PHONE:
            raise MediaDownloadError("locator_refresh_unsupported")
        if self.detail_reference is not None and not isinstance(self.detail_reference, str | SecretValue):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if isinstance(self.detail_reference, str):
            _bounded_text(self.detail_reference, maximum=4_096)
        if self.creator_reference is not None and not isinstance(self.creator_reference, SecretValue):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.watchdogs, WatchdogLimits):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.XHS:
            _validate_xhs_request_authority(
                detail_reference=self.detail_reference,
                creator_reference=self.creator_reference,
                creator_max_items=self.creator_max_items,
                content_remote_id=content_remote_id,
                author_remote_id=author_remote_id,
                watchdogs=self.watchdogs,
            )
        elif self.creator_reference is not None or self.creator_max_items is not None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.WB and not _is_weibo_detail_reference(self.detail_reference, content_remote_id):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.TIEBA and not _is_tieba_detail_reference(self.detail_reference, content_remote_id):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if platform is Platform.ZHIHU and not _is_zhihu_detail_reference(self.detail_reference, content_remote_id):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if login_method is LoginMethod.COOKIE and self.cookie is None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if login_method is not LoginMethod.COOKIE and self.cookie is not None:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.headless, bool):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if not isinstance(self.bili_progressive_detail, bool) or (
            self.bili_progressive_detail and platform is not Platform.BILI
        ):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        if self.bili_video_cid is not None and (
            type(self.bili_video_cid) is not int
            or not 1 <= self.bili_video_cid <= 2**63 - 1
            or not self.bili_progressive_detail
        ):
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        try:
            _validate_bili_dynamic_mode(
                enabled=self.bili_dynamic_detail,
                platform=platform,
                did=content_remote_id,
                author=author_remote_id,
                dynamic_type=self.bili_dynamic_type,
                pub_ts=self.bili_dynamic_pub_ts,
                detail_reference=self.detail_reference,
                progressive=self.bili_progressive_detail,
                cid=self.bili_video_cid,
            )
        except (TypeError, ValueError) as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
        delay = self.request_delay_seconds
        if isinstance(delay, bool) or not isinstance(delay, int | float) or not 0 < float(delay) <= 60:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        object.__setattr__(self, "platform", platform)
        object.__setattr__(self, "login_method", login_method)
        object.__setattr__(self, "content_remote_id", content_remote_id)
        object.__setattr__(self, "author_remote_id", author_remote_id)
        object.__setattr__(self, "request_delay_seconds", float(delay))

    def resolved_detail_reference(self) -> str | None:
        """Reveal an explicit reference only at the child-request boundary."""

        value = self.detail_reference
        if self.platform is Platform.XHS and self.creator_reference is not None:
            return None
        if self.platform is Platform.WB:
            if not _is_weibo_detail_reference(value, self.content_remote_id):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            if value is None:
                return self.content_remote_id
            if not isinstance(value, str):  # Defensive narrowing after the exact-type predicate.
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            return value
        if self.platform is Platform.ZHIHU:
            if not _is_zhihu_detail_reference(value, self.content_remote_id):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            if type(value) is not str:  # Defensive narrowing after the exact-type predicate.
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            return value
        if self.platform is Platform.TIEBA:
            if not _is_tieba_detail_reference(value, self.content_remote_id):
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            if type(value) is not str:  # Defensive narrowing after the exact-type predicate.
                raise MediaDownloadError("locator_refresh_configuration_invalid")
            return value
        if isinstance(value, SecretValue):
            resolved = _bounded_text(value.reveal(), maximum=4_096)
        elif isinstance(value, str):
            resolved = _bounded_text(value, maximum=4_096)
        else:
            resolved = self.content_remote_id
        return resolved

    def resolved_creator_reference(self) -> str | None:
        """Reveal creator authority only for an already-validated XHS lookup."""

        value = self.creator_reference
        if value is None:
            return None
        try:
            return validate_xhs_creator_reference(value.reveal(), self.author_remote_id)
        except ValueError as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc


@dataclass(frozen=True, slots=True)
class MediaCrawlerDetailResult:
    """An in-memory result tied to the verified upstream revision."""

    jsonl: bytes = field(repr=False)
    upstream_sha: str

    def __post_init__(self) -> None:
        if not isinstance(self.jsonl, bytes):
            raise TypeError("jsonl must be bytes")
        sha = self.upstream_sha.strip().lower()
        if len(sha) != 40 or any(character not in "0123456789abcdef" for character in sha):
            raise ValueError("upstream_sha must be a full Git SHA")
        object.__setattr__(self, "upstream_sha", sha)


CheckoutVerifier = Callable[[Path, bool], VerifiedCheckout]
PythonVerifier = Callable[[Path], VerifiedPython]


def _default_checkout_verifier(lock_path: Path, license_acknowledged: bool) -> VerifiedCheckout:
    return verify_mediacrawler_checkout(lock_path, license_acknowledged=license_acknowledged)


class MediaCrawlerDetailProcessRunner:
    """Run the pinned MediaCrawler detail mode in a supervised local child."""

    def __init__(
        self,
        *,
        lock_path: Path,
        integration_root: Path,
        python_executable: Path,
        license_acknowledged: bool,
        checkout_verifier: CheckoutVerifier = _default_checkout_verifier,
        python_verifier: PythonVerifier = verify_mediacrawler_python,
    ) -> None:
        self._lock_path = lock_path.expanduser().resolve()
        self._integration_root = integration_root.expanduser().resolve()
        self._python_executable = normalize_python_executable(python_executable)
        self._license_acknowledged = license_acknowledged
        self._checkout_verifier = checkout_verifier
        self._python_verifier = python_verifier

    def run(self, request: MediaCrawlerDetailRequest) -> MediaCrawlerDetailResult:
        """Return content JSONL, cleaning only this invocation's attempt root."""

        try:
            checkout = self._checkout_verifier(self._lock_path, self._license_acknowledged)
            runtime = self._python_verifier(self._python_executable)
        except Exception as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc

        execution_id = uuid4()
        try:
            paths = build_run_paths(self._integration_root, request.platform, request.account_id, execution_id)
            paths.account_root.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError) as exc:
            raise MediaDownloadError("locator_refresh_configuration_invalid") from exc
        account_lock = _AccountFileLock(paths.account_root)
        if not account_lock.acquire():
            raise MediaDownloadError("locator_refresh_temporary")
        try:
            try:
                if request.login_method is LoginMethod.SAVED_SESSION and (
                    not paths.profile_root.is_dir() or not any(paths.profile_root.iterdir())
                ):
                    raise MediaDownloadError("locator_refresh_auth_expired")
                paths.output_root.mkdir(parents=True, exist_ok=False)
                child_payload = self._child_payload(request, checkout, paths)
                output = self._execute(runtime.executable, checkout.root, child_payload, request.watchdogs)
                return MediaCrawlerDetailResult(jsonl=output, upstream_sha=checkout.commit)
            except MediaDownloadError:
                raise
            except OSError as exc:
                raise MediaDownloadError("locator_refresh_temporary") from exc
            except Exception as exc:
                raise MediaDownloadError("locator_refresh_result_invalid") from exc
        finally:
            # The stable account profile and its lock file deliberately remain.
            # Only the UUID-scoped detail attempt can contain signed JSONL.
            cleanup_error: OSError | None = None
            try:
                shutil.rmtree(paths.job_root)
            except FileNotFoundError:
                pass
            except OSError as exc:
                cleanup_error = exc
            finally:
                account_lock.release()
            if cleanup_error is not None:
                raise MediaDownloadError("locator_refresh_result_invalid") from cleanup_error

    @staticmethod
    def _child_payload(
        request: MediaCrawlerDetailRequest,
        checkout: VerifiedCheckout,
        paths: RunPaths,
    ) -> bytes:
        limits = request.watchdogs
        cookie = request.cookie.reveal() if request.cookie is not None else None
        payload = json.dumps(
            {
                "schema_version": DETAIL_RUNNER_SCHEMA_VERSION,
                "checkout_root": str(checkout.root),
                "account_root": str(paths.account_root),
                "profile_root": str(paths.profile_root),
                "job_root": str(paths.job_root),
                "output_root": str(paths.output_root),
                "platform": request.platform.value,
                "login_method": request.login_method.value,
                "content_remote_id": request.content_remote_id,
                "author_remote_id": request.author_remote_id,
                "detail_reference": request.resolved_detail_reference(),
                "creator_reference": request.resolved_creator_reference(),
                "creator_max_items": request.creator_max_items,
                "cookie": cookie,
                "headless": request.headless,
                "request_delay_seconds": request.request_delay_seconds,
                "bili_progressive_detail": request.bili_progressive_detail,
                "bili_video_cid": request.bili_video_cid,
                "bili_dynamic_detail": request.bili_dynamic_detail,
                "bili_dynamic_type": request.bili_dynamic_type,
                "bili_dynamic_pub_ts": request.bili_dynamic_pub_ts,
                "watchdogs": {
                    "max_seconds": limits.max_seconds,
                    "max_output_bytes": limits.max_output_bytes,
                    "max_output_items": limits.max_output_items,
                    "max_output_files": limits.max_output_files,
                    "max_line_bytes": limits.max_line_bytes,
                    "poll_seconds": limits.poll_seconds,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > MAX_DETAIL_REQUEST_BYTES:
            raise MediaDownloadError("locator_refresh_configuration_invalid")
        return payload

    @staticmethod
    def _execute(
        executable: Path,
        checkout_root: Path,
        child_payload: bytes,
        limits: WatchdogLimits,
    ) -> bytes:
        command = (str(executable), "-I", "-u", "-B", str(Path(__file__).resolve()), "--child")
        environment = browser_child_environment()
        environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"})
        try:
            if os.name == "nt":
                process = subprocess.Popen(
                    command,
                    cwd=checkout_root,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    close_fds=True,
                    creationflags=(
                        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    ),
                )
            else:
                process = subprocess.Popen(
                    command,
                    cwd=checkout_root,
                    env=environment,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    close_fds=True,
                    start_new_session=True,
                )
        except OSError as exc:
            raise MediaDownloadError("locator_refresh_temporary") from exc

        windows_job = _WindowsJob.attach(process)
        if os.name == "nt" and windows_job is None:
            _close_process_tree(process, None)
            raise MediaDownloadError("locator_refresh_temporary")

        cleanup_reserve = max(5.0, min(15.0, limits.max_seconds * 0.1))
        tree_closed = False
        try:
            frame, _stderr = process.communicate(child_payload, timeout=limits.max_seconds + cleanup_reserve)
        except subprocess.TimeoutExpired as exc:
            tree_closed = _close_process_tree(process, windows_job)
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                process.communicate(timeout=2)
            raise MediaDownloadError("locator_refresh_temporary") from exc
        finally:
            child_payload = b""
            if not tree_closed:
                tree_closed = _close_process_tree(process, windows_job)

        if not tree_closed:
            raise MediaDownloadError("locator_refresh_result_invalid")

        maximum_frame = ((limits.max_output_bytes + 2) // 3 * 4) + MAX_DETAIL_FRAME_OVERHEAD
        if len(frame) > maximum_frame:
            raise MediaDownloadError("locator_refresh_result_invalid")
        status, payload = _parse_child_frame(frame)
        if process.returncode != 0 or status != "succeeded":
            code = {
                "configuration_invalid": "locator_refresh_configuration_invalid",
                "temporary": "locator_refresh_temporary",
                "auth_expired": "locator_refresh_auth_expired",
                "unsupported": "locator_refresh_unsupported",
            }.get(status, "locator_refresh_result_invalid")
            raise MediaDownloadError(code)
        try:
            decoded = base64.b64decode(payload, validate=True)
        except (ValueError, UnicodeError) as exc:
            raise MediaDownloadError("locator_refresh_result_invalid") from exc
        if len(decoded) > limits.max_output_bytes:
            raise MediaDownloadError("locator_refresh_result_invalid")
        return decoded


def _bounded_text(value: object, *, maximum: int = 512) -> str:
    if not isinstance(value, str):
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    normalized = value.strip()
    if not normalized or normalized != value or len(normalized) > maximum:
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in normalized):
        raise MediaDownloadError("locator_refresh_configuration_invalid")
    return normalized


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-standard JSON number")


def _parse_child_frame(frame: bytes) -> tuple[str, str]:
    try:
        decoded = json.loads(frame, object_pairs_hook=_strict_object)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise MediaDownloadError("locator_refresh_result_invalid") from exc
    if not isinstance(decoded, Mapping) or set(decoded) != {"schema_version", "status", "payload"}:
        raise MediaDownloadError("locator_refresh_result_invalid")
    if decoded.get("schema_version") != DETAIL_RUNNER_SCHEMA_VERSION:
        raise MediaDownloadError("locator_refresh_result_invalid")
    status = decoded.get("status")
    payload = decoded.get("payload")
    if status not in {
        "succeeded",
        "configuration_invalid",
        "temporary",
        "result_invalid",
        "auth_expired",
        "unsupported",
    }:
        raise MediaDownloadError("locator_refresh_result_invalid")
    if not isinstance(status, str) or not isinstance(payload, str):
        raise MediaDownloadError("locator_refresh_result_invalid")
    return status, payload


class _ChildConfigurationError(RuntimeError):
    """A private child request is invalid; its text never crosses the process."""


class _ChildAuthExpiredError(RuntimeError):
    """The expected saved profile disappeared before the child could probe it."""


class _ChildTemporaryError(RuntimeError):
    """A bounded upstream lookup failed without returning a usable response."""


class _ChildUnsupportedError(RuntimeError):
    """The current media shape is intentionally outside the closed contract."""


@dataclass(frozen=True, slots=True)
class _BiliPlaybackResult:
    """One current page tuple and optional selected target kept only in memory."""

    aid: int
    pages: tuple[BilibiliPageIdentity, ...]
    cid: int | None
    target: ResolvedMediaTarget | None = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.aid) is not int
            or self.aid <= 0
            or type(self.pages) is not tuple
            or not self.pages
            or any(not isinstance(page, BilibiliPageIdentity) for page in self.pages)
        ):
            raise ValueError("invalid Bilibili identity")
        if self.cid is None:
            if self.target is not None:
                raise ValueError("invalid Bilibili playback result")
            return
        if (
            type(self.cid) is not int
            or self.cid not in {page.cid for page in self.pages}
            or not isinstance(
                self.target,
                ResolvedLocator
                | ResolvedFlvLocator
                | ResolvedDashLocator
                | ResolvedSegmentsLocator
                | ResolvedFlvSegmentsLocator,
            )
            or (
                isinstance(self.target, ResolvedLocator)
                and self.target.request_profile is not MediaRequestProfile.BILIBILI_MEDIA
            )
            or (
                isinstance(self.target, ResolvedFlvLocator)
                and self.target.source.request_profile is not MediaRequestProfile.BILIBILI_MEDIA
            )
        ):
            raise ValueError("invalid Bilibili identity")


@dataclass(frozen=True, slots=True)
class _ChildRequest:
    checkout_root: Path
    account_root: Path
    profile_root: Path
    job_root: Path
    output_root: Path
    platform: Platform
    login_method: LoginMethod
    content_remote_id: str
    detail_reference: str | None = field(repr=False)
    author_remote_id: str = "unknown"
    creator_reference: str | None = field(default=None, repr=False)
    creator_max_items: int | None = None
    cookie: str | None = field(default=None, repr=False)
    headless: bool = True
    request_delay_seconds: float = 2.0
    bili_progressive_detail: bool = False
    bili_video_cid: int | None = None
    watchdogs: WatchdogLimits = field(default_factory=WatchdogLimits)
    bili_dynamic_detail: bool = False
    bili_dynamic_type: str | None = None
    bili_dynamic_pub_ts: int | None = None

    @classmethod
    def load(cls, payload: bytes) -> _ChildRequest:
        try:
            raw = json.loads(payload, object_pairs_hook=_strict_object)
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise _ChildConfigurationError from exc
        expected = {
            "schema_version",
            "checkout_root",
            "account_root",
            "profile_root",
            "job_root",
            "output_root",
            "platform",
            "login_method",
            "content_remote_id",
            "author_remote_id",
            "detail_reference",
            "creator_reference",
            "creator_max_items",
            "cookie",
            "headless",
            "request_delay_seconds",
            "bili_progressive_detail",
            "bili_video_cid",
            "bili_dynamic_detail",
            "bili_dynamic_type",
            "bili_dynamic_pub_ts",
            "watchdogs",
        }
        if (
            not isinstance(raw, Mapping)
            or set(raw) != expected
            or raw.get("schema_version") != DETAIL_RUNNER_SCHEMA_VERSION
        ):
            raise _ChildConfigurationError
        try:
            platform = Platform(raw["platform"])
            login_method = LoginMethod(raw["login_method"])
            checkout_root = Path(_child_text(raw["checkout_root"], 32_767)).resolve()
            account_root = Path(_child_text(raw["account_root"], 32_767)).resolve()
            profile_root = Path(_child_text(raw["profile_root"], 32_767)).resolve()
            job_root = Path(_child_text(raw["job_root"], 32_767)).resolve()
            output_root = Path(_child_text(raw["output_root"], 32_767)).resolve()
            content_remote_id = _child_text(raw["content_remote_id"], 512)
            author_remote_id = _child_text(raw["author_remote_id"], 255)
            detail_value = raw["detail_reference"]
            detail_reference = None if detail_value is None else _child_text(detail_value, 4_096)
            creator_value = raw["creator_reference"]
            creator_reference = None if creator_value is None else _child_text(creator_value, 4_096)
            creator_max_items = raw["creator_max_items"]
            cookie_value = raw["cookie"]
            cookie = None if cookie_value is None else _child_text(cookie_value, MAX_SECRET_BYTES)
            watchdog_values = raw["watchdogs"]
            if not isinstance(watchdog_values, Mapping) or set(watchdog_values) != {
                "max_seconds",
                "max_output_bytes",
                "max_output_items",
                "max_output_files",
                "max_line_bytes",
                "poll_seconds",
            }:
                raise _ChildConfigurationError
            watchdogs = WatchdogLimits(**dict(watchdog_values))
            delay = raw["request_delay_seconds"]
            if isinstance(delay, bool) or not isinstance(delay, int | float) or not 0 < float(delay) <= 60:
                raise _ChildConfigurationError
            headless = raw["headless"]
            if not isinstance(headless, bool):
                raise _ChildConfigurationError
            bili_progressive_detail = raw["bili_progressive_detail"]
            if not isinstance(bili_progressive_detail, bool) or (
                bili_progressive_detail and platform is not Platform.BILI
            ):
                raise _ChildConfigurationError
            bili_video_cid = raw["bili_video_cid"]
            if bili_video_cid is not None and (
                type(bili_video_cid) is not int or not 1 <= bili_video_cid <= 2**63 - 1 or not bili_progressive_detail
            ):
                raise _ChildConfigurationError
            bili_dynamic_detail = raw["bili_dynamic_detail"]
            bili_dynamic_type = raw["bili_dynamic_type"]
            bili_dynamic_pub_ts = raw["bili_dynamic_pub_ts"]
            _validate_bili_dynamic_mode(
                enabled=bili_dynamic_detail,
                platform=platform,
                did=content_remote_id,
                author=author_remote_id,
                dynamic_type=bili_dynamic_type,
                pub_ts=bili_dynamic_pub_ts,
                detail_reference=detail_reference,
                progressive=bili_progressive_detail,
                cid=bili_video_cid,
            )
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise _ChildConfigurationError from exc
        if platform not in _SUPPORTED_PLATFORMS or login_method is LoginMethod.PHONE:
            raise _ChildConfigurationError
        if (login_method is LoginMethod.COOKIE) != (cookie is not None):
            raise _ChildConfigurationError
        if platform is Platform.XHS:
            try:
                if detail_reference is not None:
                    if creator_reference is not None or creator_max_items is not None:
                        raise ValueError
                    validate_xhs_detail_reference(detail_reference, content_remote_id)
                else:
                    if creator_reference is None:
                        raise ValueError
                    if type(creator_max_items) is not int or not 1 <= creator_max_items <= 1_000:
                        raise ValueError
                    if creator_max_items > watchdogs.max_output_items:
                        raise ValueError
                    validate_xhs_creator_reference(creator_reference, author_remote_id)
            except ValueError as exc:
                raise _ChildConfigurationError from exc
        elif creator_reference is not None or creator_max_items is not None or detail_reference is None:
            raise _ChildConfigurationError
        if platform is Platform.WB and not _is_weibo_detail_reference(detail_reference, content_remote_id):
            raise _ChildConfigurationError
        if platform is Platform.TIEBA and not _is_tieba_detail_reference(detail_reference, content_remote_id):
            raise _ChildConfigurationError
        if platform is Platform.ZHIHU and not _is_zhihu_detail_reference(detail_reference, content_remote_id):
            raise _ChildConfigurationError
        if bili_progressive_detail and content_remote_id != detail_reference:
            raise _ChildConfigurationError
        if profile_root.parent.parent != account_root or output_root.parent != job_root:
            raise _ChildConfigurationError
        if checkout_root != Path.cwd().resolve():
            raise _ChildConfigurationError
        return cls(
            checkout_root=checkout_root,
            account_root=account_root,
            profile_root=profile_root,
            job_root=job_root,
            output_root=output_root,
            platform=platform,
            login_method=login_method,
            content_remote_id=content_remote_id,
            author_remote_id=author_remote_id,
            detail_reference=detail_reference,
            creator_reference=creator_reference,
            creator_max_items=creator_max_items,
            cookie=cookie,
            headless=headless,
            request_delay_seconds=float(delay),
            bili_progressive_detail=bili_progressive_detail,
            bili_video_cid=bili_video_cid,
            bili_dynamic_detail=bili_dynamic_detail,
            bili_dynamic_type=bili_dynamic_type,
            bili_dynamic_pub_ts=bili_dynamic_pub_ts,
            watchdogs=watchdogs,
        )


def _child_text(value: object, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\0" in value:
        raise _ChildConfigurationError
    return value


@contextlib.contextmanager
def _silenced_upstream() -> Iterator[None]:
    stdout_copy = os.dup(1)
    stderr_copy = os.dup(2)
    with open(os.devnull, "w", encoding="utf-8") as sink:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                yield
        finally:
            with contextlib.suppress(OSError):
                sink.flush()
            os.dup2(stdout_copy, 1)
            os.dup2(stderr_copy, 2)
            os.close(stdout_copy)
            os.close(stderr_copy)


def _module_belongs_to_checkout(module: Any, checkout: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str):
        return False
    try:
        return Path(module_file).resolve().is_relative_to(checkout)
    except OSError:
        return False


def _configure_upstream(config: Any, request: _ChildRequest) -> None:
    profile_parent = request.profile_root.parent
    profile_parent.mkdir(parents=True, exist_ok=True)
    template = f"{str(profile_parent).replace('%', '%%')}{os.sep}%s_user_data_dir"
    calculated_profile = Path(
        os.path.join(request.checkout_root, "browser_data", template % request.platform.value)
    ).resolve()
    if calculated_profile != request.profile_root:
        raise _ChildConfigurationError
    if request.login_method is LoginMethod.SAVED_SESSION and (
        not request.profile_root.is_dir() or not any(request.profile_root.iterdir())
    ):
        raise _ChildAuthExpiredError

    config.PLATFORM = request.platform.value
    config.LOGIN_TYPE = upstream_login_type(request.login_method)
    config.COOKIES = request.cookie or ""
    config.SAVE_DATA_PATH = str(request.output_root)
    config.USER_DATA_DIR = template
    config.START_PAGE = 1
    config.SAVE_DATA_OPTION = "jsonl"
    config.ENABLE_CDP_MODE = False
    config.CDP_CONNECT_EXISTING = False
    config.SAVE_LOGIN_STATE = True
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_SUB_COMMENTS = False
    config.ENABLE_GET_MEIDAS = False
    config.ENABLE_GET_MEDIAS = False
    config.ENABLE_GET_WORDCLOUD = False
    config.ENABLE_IP_PROXY = False
    config.STATIC_PROXY_URL = ""
    config.MAX_CONCURRENCY_NUM = 1
    config.CRAWLER_MAX_SLEEP_SEC = request.request_delay_seconds
    headless = True if request.login_method is LoginMethod.SAVED_SESSION else request.headless
    config.HEADLESS = headless
    config.CDP_HEADLESS = headless
    config.AUTO_CLOSE_BROWSER = True
    config.XHS_INTERNATIONAL = False
    config.DISABLE_SSL_VERIFY = False
    for attribute in CREATOR_CONFIG_ATTRIBUTES.values():
        setattr(config, attribute, [])
    for attribute in _DETAIL_CONFIG_ATTRIBUTES.values():
        setattr(config, attribute, [])
    if request.platform is Platform.XHS and request.creator_reference is not None:
        if request.creator_max_items is None:
            raise _ChildConfigurationError
        config.CRAWLER_TYPE = "creator"
        config.CREATOR_MODE = True
        config.CRAWLER_MAX_NOTES_COUNT = request.creator_max_items
        config.XHS_CREATOR_ID_LIST = [request.creator_reference]
    else:
        if request.detail_reference is None:
            raise _ChildConfigurationError
        config.CRAWLER_TYPE = "detail"
        config.CREATOR_MODE = False
        config.CRAWLER_MAX_NOTES_COUNT = 1
        detail_value = request.content_remote_id if request.platform is Platform.TIEBA else request.detail_reference
        setattr(config, _DETAIL_CONFIG_ATTRIBUTES[request.platform], [detail_value])


def _positive_bili_id(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("invalid Bilibili identity")
    return value


def _first_bili_cid(view: Mapping[str, object]) -> int:
    return parse_bilibili_view_pages(view)[0].cid


_BILI_VIDEO_QUALITIES = frozenset({16, 32, 64, 80, 112, 116, 120, 125, 126, 127})
_BILI_AUDIO_QUALITIES = frozenset({30216, 30232, 30250, 30251, 30255, 30280})
_BILI_CODEC_BY_ID = {7: "avc", 12: "hev", 13: "av1"}
_BILI_CODEC_PREFERENCE = {"avc": 0, "hev": 1, "av1": 2}
_BILI_MAX_DASH_STREAMS = 64


def _bili_stream_locator(stream: Mapping[str, object]) -> ResolvedLocator:
    primary_values = [stream[key] for key in ("base_url", "baseUrl") if key in stream]
    if not primary_values or any(value != primary_values[0] for value in primary_values):
        raise ValueError("invalid Bilibili stream URL")
    backup_values = [stream[key] for key in ("backup_url", "backupUrl") if key in stream]
    if backup_values and any(value != backup_values[0] for value in backup_values):
        raise ValueError("invalid Bilibili backup URLs")
    raw_backups = backup_values[0] if backup_values else []
    if (
        type(primary_values[0]) is not str
        or not isinstance(raw_backups, Sequence)
        or isinstance(raw_backups, bytes | bytearray | str)
        or len(raw_backups) > 8
        or any(type(item) is not str for item in raw_backups)
    ):
        raise ValueError("invalid Bilibili stream URL")
    try:
        return ResolvedLocator(
            primary_values[0],
            MediaRequestProfile.BILIBILI_MEDIA,
            tuple(raw_backups),
        )
    except MediaDownloadError as exc:
        raise ValueError("invalid Bilibili stream URL") from exc


def _bili_progressive_locator(segment: Mapping[str, object]) -> ResolvedLocator:
    """Validate one single-segment progressive primary/backup target."""

    primary = segment.get("url")
    backup_values = [segment[key] for key in ("backup_url", "backupUrl") if key in segment]
    if backup_values and any(value != backup_values[0] for value in backup_values):
        raise ValueError("invalid Bilibili progressive backup URLs")
    raw_backups = backup_values[0] if backup_values else []
    if (
        type(primary) is not str
        or not isinstance(raw_backups, Sequence)
        or isinstance(raw_backups, bytes | bytearray | str)
        or len(raw_backups) > 8
        or any(type(item) is not str for item in raw_backups)
    ):
        raise ValueError("invalid Bilibili progressive URL")
    try:
        return ResolvedLocator(primary, MediaRequestProfile.BILIBILI_MEDIA, tuple(raw_backups))
    except MediaDownloadError as exc:
        raise ValueError("invalid Bilibili progressive URL") from exc


def _bili_progressive_format(play: Mapping[str, object]) -> str | None:
    """Classify one closed top-level progressive format without URL inference."""

    raw = play.get("format")
    if raw is None:
        return None
    if (
        type(raw) is not str
        or raw != raw.strip()
        or not 1 <= len(raw) <= 128
        or not raw.isascii()
        or any(not (character.isalnum() or character in {",", ".", "_", "-"}) for character in raw)
    ):
        raise ValueError("invalid Bilibili progressive format")
    lowered = raw.lower()
    is_flv = "flv" in lowered
    is_mp4 = "mp4" in lowered
    if is_flv and is_mp4:
        raise ValueError("invalid Bilibili progressive format")
    if is_flv:
        return "flv"
    if is_mp4:
        return None
    raise _ChildUnsupportedError


def _bili_audio_sort_key(quality: int) -> int:
    return quality + 40 if quality in {30250, 30251, 30255} else quality


def _bili_dash_result(
    dash: object,
    *,
    aid: int,
    pages: tuple[BilibiliPageIdentity, ...],
    cid: int,
) -> _BiliPlaybackResult:
    if not isinstance(dash, Mapping):
        raise ValueError("invalid Bilibili DASH response")
    raw_videos = dash.get("video")
    if (
        not isinstance(raw_videos, Sequence)
        or isinstance(raw_videos, bytes | bytearray | str)
        or len(raw_videos) > _BILI_MAX_DASH_STREAMS
    ):
        raise ValueError("invalid Bilibili DASH video response")
    videos: list[tuple[int, int, ResolvedLocator, str]] = []
    for item in raw_videos:
        if not isinstance(item, Mapping):
            raise ValueError("invalid Bilibili DASH video stream")
        quality = item.get("id")
        codec_id = item.get("codecid")
        if type(quality) is not int or type(codec_id) is not int:
            raise ValueError("invalid Bilibili DASH video stream")
        codec = _BILI_CODEC_BY_ID.get(codec_id)
        if quality not in _BILI_VIDEO_QUALITIES or codec is None:
            continue
        videos.append((quality, -_BILI_CODEC_PREFERENCE[codec], _bili_stream_locator(item), codec))
    if not videos:
        raise _ChildUnsupportedError
    video_quality, _preference, video, video_codec = max(videos, key=lambda item: (item[0], item[1]))

    raw_audio_groups: list[object] = []
    ordinary = dash.get("audio")
    if ordinary is not None:
        if (
            not isinstance(ordinary, Sequence)
            or isinstance(ordinary, bytes | bytearray | str)
            or len(ordinary) > _BILI_MAX_DASH_STREAMS
        ):
            raise ValueError("invalid Bilibili DASH audio response")
        raw_audio_groups.extend(ordinary)
    dolby = dash.get("dolby")
    if dolby is not None:
        if not isinstance(dolby, Mapping):
            raise ValueError("invalid Bilibili Dolby response")
        dolby_audio = dolby.get("audio")
        if dolby_audio is not None:
            if (
                not isinstance(dolby_audio, Sequence)
                or isinstance(dolby_audio, bytes | bytearray | str)
                or len(dolby_audio) > _BILI_MAX_DASH_STREAMS
            ):
                raise ValueError("invalid Bilibili Dolby response")
            raw_audio_groups.extend(dolby_audio)
    flac = dash.get("flac")
    if flac is not None:
        if not isinstance(flac, Mapping):
            raise ValueError("invalid Bilibili FLAC response")
        flac_audio = flac.get("audio")
        if flac_audio is not None:
            raw_audio_groups.append(flac_audio)
    if len(raw_audio_groups) > _BILI_MAX_DASH_STREAMS:
        raise ValueError("invalid Bilibili DASH audio response")

    audios: list[tuple[int, int, ResolvedLocator]] = []
    for item in raw_audio_groups:
        if not isinstance(item, Mapping):
            raise ValueError("invalid Bilibili DASH audio stream")
        quality = item.get("id")
        if type(quality) is not int:
            raise ValueError("invalid Bilibili DASH audio stream")
        if quality not in _BILI_AUDIO_QUALITIES:
            continue
        audios.append((_bili_audio_sort_key(quality), quality, _bili_stream_locator(item)))
    selected_audio = max(audios, key=lambda item: item[0]) if audios else None
    return _BiliPlaybackResult(
        aid=aid,
        pages=pages,
        cid=cid,
        target=ResolvedDashLocator(
            video=video,
            audio=None if selected_audio is None else selected_audio[2],
            video_quality=video_quality,
            video_codec=video_codec,
            audio_quality=None if selected_audio is None else selected_audio[1],
        ),
    )


def _bili_playback_result(
    play: object,
    *,
    aid: int,
    pages: tuple[BilibiliPageIdentity, ...],
    cid: int,
) -> _BiliPlaybackResult:
    if not isinstance(play, Mapping):
        raise ValueError("invalid Bilibili play response")
    if "dash" in play and play.get("dash") is not None:
        return _bili_dash_result(play["dash"], aid=aid, pages=pages, cid=cid)
    if "durl" not in play or play.get("durl") is None:
        raise _ChildUnsupportedError
    durl = play["durl"]
    if not isinstance(durl, list):
        raise ValueError("invalid Bilibili durl response")
    if len(durl) == 1:
        segment = durl[0]
        if not isinstance(segment, Mapping):
            raise ValueError("invalid Bilibili durl segment")
        source = _bili_progressive_locator(segment)
        target: ResolvedMediaTarget = ResolvedFlvLocator(source) if _bili_progressive_format(play) == "flv" else source
        return _BiliPlaybackResult(aid=aid, pages=pages, cid=cid, target=target)
    format_marker = _bili_progressive_format(play)
    if not 2 <= len(durl) <= BILIBILI_MAX_DURL_SEGMENTS:
        raise _ChildUnsupportedError
    try:
        segments = tuple(_bili_progressive_locator(segment) for segment in durl)
        base = ResolvedSegmentsLocator(segments)
        multi_target: ResolvedMediaTarget = ResolvedFlvSegmentsLocator(base) if format_marker == "flv" else base
    except (TypeError, ValueError, MediaDownloadError) as exc:
        raise ValueError("invalid Bilibili durl response") from exc
    return _BiliPlaybackResult(aid=aid, pages=pages, cid=cid, target=multi_target)


async def _run_bilibili_aid(upstream_main: Any, request: _ChildRequest) -> _BiliPlaybackResult | None:
    """Use the pinned client's aid-capable detail entry when discovery stored av."""

    crawler = upstream_main.CrawlerFactory.create_crawler(platform=request.platform.value)
    if request.detail_reference is None:
        raise _ChildConfigurationError
    try:
        requested_aid = int(request.detail_reference)
    except ValueError as exc:
        raise _ChildConfigurationError from exc
    if requested_aid <= 0 or requested_aid > 2**63 - 1 or str(requested_aid) != request.detail_reference:
        raise _ChildConfigurationError
    playback: _BiliPlaybackResult | None = None
    callback_called = False

    async def get_specified_videos(instance: Any, _references: list[str]) -> None:
        nonlocal callback_called, playback
        callback_called = True
        semaphore = asyncio.Semaphore(1)
        detail = await instance.get_video_info_task(
            aid=requested_aid,
            bvid="",
            semaphore=semaphore,
        )
        if detail is None:
            if request.bili_progressive_detail:
                raise _ChildTemporaryError
            return
        if not isinstance(detail, Mapping) or not isinstance(detail.get("View"), Mapping):
            raise ValueError("invalid Bilibili detail response")
        view = detail["View"]
        returned_aid = _positive_bili_id(view.get("aid"))
        if returned_aid != requested_aid:
            raise ValueError("Bilibili aid mismatch")
        store = importlib.import_module("store.bilibili")
        await store.update_bilibili_video(detail)
        await store.update_up_info(detail)
        if request.bili_progressive_detail:
            pages = parse_bilibili_view_pages(view, expected_aid=request.content_remote_id)
            cid = request.bili_video_cid
            if cid is None:
                cid = pages[0].cid if len(pages) == 1 else None
            elif cid not in {page.cid for page in pages}:
                cid = None
            if cid is None:
                playback = _BiliPlaybackResult(
                    aid=requested_aid,
                    pages=pages,
                    cid=None,
                    target=None,
                )
                return
            try:
                client = getattr(instance, "bili_client", None)
                get = getattr(client, "get", None)
                if not callable(get):
                    raise _ChildConfigurationError
                async with semaphore:
                    play = await get(
                        "/x/player/wbi/playurl",
                        {
                            "avid": requested_aid,
                            "cid": cid,
                            "qn": 127,
                            "fourk": 1,
                            "fnval": 4048,
                            "platform": "pc",
                        },
                        enable_params_sign=True,
                    )
            except Exception as exc:
                if isinstance(exc, _ChildConfigurationError):
                    raise
                raise _ChildTemporaryError from exc
            if play is None:
                raise _ChildTemporaryError
            playback = _bili_playback_result(
                play,
                aid=requested_aid,
                pages=pages,
                cid=cid,
            )

    crawler.get_specified_videos = MethodType(get_specified_videos, crawler)
    upstream_main.crawler = crawler
    await crawler.start()
    if not callback_called:
        raise RuntimeError("Bilibili detail callback did not run")
    return playback


@dataclass(frozen=True, slots=True)
class _BiliDynamicDetailResult:
    jsonl: bytes = field(repr=False)


async def _run_bilibili_dynamic(upstream_main: Any, request: _ChildRequest) -> _BiliDynamicDetailResult:
    """One DID detail and, only for OPUS, its same-DID full attachment.

    The locked crawler still owns account authentication and browser cleanup;
    its content callback is replaced before start so no AID, author feed,
    comments, store or ordinary View request is reachable from this callback.
    """

    from media_sync.integrations.mediacrawler.bilibili_dynamic import (
        BILI_DYNAMIC_DETAIL_FEATURES,
        BILI_DYNAMIC_DETAIL_PATH,
        BILI_OPUS_DETAIL_FEATURES,
        BILI_OPUS_DETAIL_PATH,
        BiliDynamicUnsupportedError,
        parse_bili_dynamic_detail,
        parse_dynamic_identity,
    )

    _validate_bili_dynamic_mode(
        enabled=request.bili_dynamic_detail,
        platform=request.platform,
        did=request.content_remote_id,
        author=request.author_remote_id,
        dynamic_type=request.bili_dynamic_type,
        pub_ts=request.bili_dynamic_pub_ts,
        detail_reference=request.detail_reference,
        progressive=request.bili_progressive_detail,
        cid=request.bili_video_cid,
    )
    if not request.bili_dynamic_detail:
        raise _ChildConfigurationError
    crawler = upstream_main.CrawlerFactory.create_crawler(platform=request.platform.value)
    result: _BiliDynamicDetailResult | None = None
    callback_called = False

    async def get_specified_videos(instance: Any, references: list[str]) -> None:
        nonlocal result, callback_called
        if callback_called or references != [request.content_remote_id]:
            raise ValueError("invalid Bilibili dynamic dispatch")
        callback_called = True
        client = getattr(instance, "bili_client", None)
        if client is None:
            raise _ChildConfigurationError
        get = getattr(client, "get", None)
        original_request = getattr(client, "request", None)
        original_keys = getattr(client, "get_wbi_keys", None)
        if not callable(get) or not callable(original_request) or not callable(original_keys):
            raise _ChildConfigurationError
        request_started = False
        nav_seen = False
        keys: tuple[str, str] | None = None

        async def cached_keys() -> tuple[str, str]:
            nonlocal keys
            if keys is None:
                candidate = await original_keys()
                if (
                    not isinstance(candidate, tuple)
                    or len(candidate) != 2
                    or any(
                        type(value) is not str
                        or len(value) != 32
                        or any(character not in "0123456789abcdefABCDEF" for character in value)
                        for value in candidate
                    )
                ):
                    raise ValueError("invalid Bilibili dynamic signing keys")
                keys = candidate
            return keys

        async def fetch_item(path: str, features: str) -> Mapping[str, Any]:
            endpoint_seen = False

            async def guarded_request(method: str, url: str, **kwargs: Any) -> Any:
                nonlocal nav_seen, endpoint_seen, request_started
                parsed_url = urlsplit(url)
                query = parse_qs(parsed_url.query, keep_blank_values=True)
                if (
                    method != "GET"
                    or parsed_url.scheme != "https"
                    or parsed_url.netloc != "api.bilibili.com"
                    or parsed_url.fragment
                    or any(len(values) != 1 for values in query.values())
                ):
                    raise ValueError("invalid Bilibili dynamic request")
                if parsed_url.path == "/x/web-interface/nav":
                    if nav_seen or endpoint_seen or query or keys is not None:
                        raise ValueError("Bilibili dynamic signing budget exceeded")
                    nav_seen = True
                elif (
                    parsed_url.path != path
                    or endpoint_seen
                    or set(query) != {"id", "features", "wts", "w_rid"}
                    or query.get("id") != [request.content_remote_id]
                    or query.get("features") != [features]
                    or len(query["w_rid"][0]) != 32
                    or any(character not in "0123456789abcdef" for character in query["w_rid"][0])
                    or not 1 <= len(query["wts"][0]) <= 12
                    or not query["wts"][0].isascii()
                    or not query["wts"][0].isdecimal()
                ):
                    raise ValueError("invalid Bilibili dynamic request")
                else:
                    endpoint_seen = True
                if request_started:
                    await asyncio.sleep(request.request_delay_seconds)
                request_started = True
                return await original_request(method=method, url=url, **kwargs)

            client.request, client.get_wbi_keys = guarded_request, cached_keys
            try:
                response = await get(
                    path,
                    {"id": request.content_remote_id, "features": features},
                    enable_params_sign=True,
                )
                if not endpoint_seen:
                    raise ValueError("Bilibili dynamic request was not observed")
            finally:
                client.request, client.get_wbi_keys = original_request, original_keys
            if response is None:
                raise _ChildTemporaryError
            if not isinstance(response, Mapping):
                raise ValueError("invalid Bilibili dynamic response")
            serialized = json.dumps(response, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()
            if len(serialized) > request.watchdogs.max_output_bytes:
                raise ValueError("Bilibili dynamic response budget exceeded")
            item = response.get("item")
            if not isinstance(item, Mapping):
                raise ValueError("invalid Bilibili dynamic response")
            return item

        item = await fetch_item(BILI_DYNAMIC_DETAIL_PATH, BILI_DYNAMIC_DETAIL_FEATURES)
        identity = parse_dynamic_identity(item, creator_id=int(request.author_remote_id))
        if (identity.did, identity.dynamic_type, identity.pub_ts) != (
            request.content_remote_id,
            request.bili_dynamic_type,
            request.bili_dynamic_pub_ts,
        ):
            raise ValueError("Bilibili dynamic identity changed")
        modules = item.get("modules")
        module_dynamic = modules.get("module_dynamic") if isinstance(modules, Mapping) else None
        major = module_dynamic.get("major") if isinstance(module_dynamic, Mapping) else None
        opus_item = None
        if isinstance(major, Mapping) and major.get("type") == "MAJOR_TYPE_OPUS":
            if (
                identity.dynamic_type not in {"DYNAMIC_TYPE_WORD", "DYNAMIC_TYPE_DRAW"}
                or item.get("orig") is not None
                or item.get("visible") is not True
                or not isinstance(module_dynamic, Mapping)
                or module_dynamic.get("additional") is not None
            ):
                raise BiliDynamicUnsupportedError
            cookies = getattr(client, "cookie_dict", None)
            if not isinstance(cookies, dict) or type(cookies.get("buvid3")) is not str or not cookies["buvid3"]:
                raise _ChildConfigurationError
            opus_item = await fetch_item(BILI_OPUS_DETAIL_PATH, BILI_OPUS_DETAIL_FEATURES)
        parsed = parse_bili_dynamic_detail(
            item, creator_id=int(request.author_remote_id), expected_identity=identity, opus_item=opus_item
        )
        if not parsed.images or parsed.video_reference is not None:
            raise ValueError("Bilibili dynamic image attachment is unavailable")
        payload = (
            json.dumps(parsed.to_record(), ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
        ).encode()
        if len(payload) > min(request.watchdogs.max_line_bytes, request.watchdogs.max_output_bytes):
            raise ValueError("Bilibili dynamic detail output budget exceeded")
        result = _BiliDynamicDetailResult(payload)

    crawler.get_specified_videos = MethodType(get_specified_videos, crawler)
    upstream_main.crawler = crawler
    await crawler.start()
    if not callback_called or result is None:
        raise ValueError("Bilibili dynamic detail callback did not complete")
    return result


async def _run_upstream(request: _ChildRequest) -> tuple[Any, _BiliPlaybackResult | _BiliDynamicDetailResult | None]:
    os.chdir(request.checkout_root)
    if str(request.checkout_root) not in sys.path:
        sys.path.insert(0, str(request.checkout_root))
    importlib.invalidate_caches()
    if "config" in sys.modules or "main" in sys.modules:
        raise _ChildConfigurationError
    sys.argv = ["mediacrawler"]
    config = importlib.import_module("config")
    if not _module_belongs_to_checkout(config, request.checkout_root):
        raise _ChildConfigurationError
    _configure_upstream(config, request)
    upstream_main = importlib.import_module("main")
    if not _module_belongs_to_checkout(upstream_main, request.checkout_root):
        raise _ChildConfigurationError
    install_bundled_chromium_policy(upstream_main)
    if request.platform is Platform.WB:
        install_weibo_media_capture(request.checkout_root)
    elif request.platform is Platform.TIEBA:
        install_tieba_media_capture(request.checkout_root)
    elif request.platform is Platform.ZHIHU:
        install_zhihu_media_capture(request.checkout_root)
    elif request.platform is Platform.KS:
        install_kuaishou_media_capture(request.checkout_root)
    elif request.platform is Platform.XHS:
        install_xhs_live_capture(request.checkout_root)
    if request.login_method is LoginMethod.COOKIE:
        from media_sync.integrations.mediacrawler.cookie_reuse import install_cookie_reuse

        install_cookie_reuse(request.checkout_root, request.platform, request.cookie or "")

    async def dispatch() -> _BiliPlaybackResult | _BiliDynamicDetailResult | None:
        if request.bili_dynamic_detail:
            return await _run_bilibili_dynamic(upstream_main, request)
        if (
            request.platform is Platform.BILI
            and request.detail_reference is not None
            and request.detail_reference.isdigit()
        ):
            return await _run_bilibili_aid(upstream_main, request)
        await upstream_main.main()
        return None

    try:
        if request.login_method is LoginMethod.SAVED_SESSION:
            from media_sync.integrations.mediacrawler.login_runner import (
                fence_saved_session_qr_fallback,
            )

            with fence_saved_session_qr_fallback(request.platform):
                progressive = await dispatch()
        else:
            progressive = await dispatch()
    except SystemExit as error:
        raise RuntimeError("upstream exited without a successful result") from error
    return upstream_main, progressive


async def _watch_upstream(request: _ChildRequest) -> tuple[Any, _BiliPlaybackResult | _BiliDynamicDetailResult | None]:
    deadline = time.monotonic() + request.watchdogs.max_seconds
    task = asyncio.create_task(_run_upstream(request))
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            done, _pending = await asyncio.wait(
                {task},
                timeout=min(request.watchdogs.poll_seconds, remaining),
            )
            inspect_output(request.output_root, request.watchdogs)
            if task in done:
                return await task
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(task, timeout=min(5.0, request.watchdogs.max_seconds * 0.1))


def _read_content_jsonl(request: _ChildRequest) -> bytes:
    inspect_output(request.output_root, request.watchdogs)
    payload = bytearray()
    for path in sorted(request.output_root.rglob("*.jsonl")):
        if "_contents_" not in path.name and not path.name.startswith("contents"):
            continue
        data = path.read_bytes()
        payload.extend(data)
        if data and not data.endswith(b"\n"):
            payload.extend(b"\n")
        if len(payload) > request.watchdogs.max_output_bytes:
            raise ValueError("detail payload exceeds output limit")
    return bytes(payload)


def _augment_bili_progressive_jsonl(
    payload: bytes,
    progressive: _BiliPlaybackResult,
    limits: WatchdogLimits,
) -> bytes:
    """Inject current pages and at most one URL into in-memory JSONL only."""

    lines = payload.splitlines()
    if len(lines) > limits.max_output_items:
        raise ValueError("detail payload exceeds record limit")
    output = bytearray()
    matches = 0
    for raw_line in lines:
        if len(raw_line) + 1 > limits.max_line_bytes:
            raise ValueError("detail payload exceeds line limit")
        encoded = raw_line
        if raw_line.strip():
            try:
                decoded = json.loads(
                    raw_line,
                    object_pairs_hook=_strict_object,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                raise ValueError("invalid detail JSONL") from exc
            if not isinstance(decoded, Mapping):
                raise ValueError("invalid detail JSONL record")
            if _contains_private_detail_field(decoded):
                raise ValueError("private detail field collision")
            if decoded.get("video_id") == str(progressive.aid):
                matches += 1
                enriched = dict(decoded)
                enriched[BILIBILI_PAGES_FIELD] = [page.as_mapping() for page in progressive.pages]
                if isinstance(progressive.target, ResolvedLocator | ResolvedFlvLocator):
                    source = (
                        progressive.target.source
                        if isinstance(progressive.target, ResolvedFlvLocator)
                        else progressive.target
                    )
                    format_marker = "flv" if isinstance(progressive.target, ResolvedFlvLocator) else None
                    if len(progressive.pages) == 1:
                        enriched[_BILI_PROGRESSIVE_FIELD] = source.url
                        if source.backup_urls:
                            enriched[BILIBILI_PROGRESSIVE_BACKUPS_FIELD] = list(source.backup_urls)
                        if format_marker is not None:
                            enriched[BILIBILI_PROGRESSIVE_FORMAT_FIELD] = format_marker
                    else:
                        assert progressive.cid is not None
                        page_target: dict[str, object] = {
                            "cid": progressive.cid,
                            "url": source.url,
                        }
                        if source.backup_urls:
                            page_target["backup_urls"] = list(source.backup_urls)
                        if format_marker is not None:
                            page_target["format"] = format_marker
                        enriched[BILIBILI_PROGRESSIVE_PAGE_FIELD] = page_target
                elif isinstance(progressive.target, ResolvedSegmentsLocator | ResolvedFlvSegmentsLocator):
                    assert progressive.cid is not None
                    active_segments = (
                        progressive.target.source.segments
                        if isinstance(progressive.target, ResolvedFlvSegmentsLocator)
                        else progressive.target.segments
                    )
                    segments_payload: dict[str, object] = {
                        "cid": progressive.cid,
                        "segments": [
                            (
                                {"url": segment.url, "backup_urls": list(segment.backup_urls)}
                                if segment.backup_urls
                                else {"url": segment.url}
                            )
                            for segment in active_segments
                        ],
                    }
                    if isinstance(progressive.target, ResolvedFlvSegmentsLocator):
                        segments_payload["format"] = "flv"
                    enriched[BILIBILI_PROGRESSIVE_SEGMENTS_FIELD] = segments_payload
                elif isinstance(progressive.target, ResolvedDashLocator):
                    assert progressive.cid is not None
                    target = progressive.target
                    enriched[BILIBILI_DASH_PAGE_FIELD] = {
                        "cid": progressive.cid,
                        "video": {
                            "url": target.video.url,
                            "backup_urls": list(target.video.backup_urls),
                            "quality": target.video_quality,
                            "codec": target.video_codec,
                        },
                        "audio": (
                            None
                            if target.audio is None
                            else {
                                "url": target.audio.url,
                                "backup_urls": list(target.audio.backup_urls),
                                "quality": target.audio_quality,
                            }
                        ),
                    }
                encoded = json.dumps(
                    enriched,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                if len(encoded) + 1 > limits.max_line_bytes:
                    raise ValueError("detail payload exceeds line limit")
        output.extend(encoded)
        output.extend(b"\n")
        if len(output) > limits.max_output_bytes:
            raise ValueError("detail payload exceeds output limit")
    if matches != 1:
        raise ValueError("Bilibili detail record mismatch")
    return bytes(output)


def _contains_private_detail_field(value: object) -> bool:
    if isinstance(value, Mapping):
        return bool(
            {
                BILIBILI_DASH_PAGE_FIELD,
                BILIBILI_PAGES_FIELD,
                BILIBILI_PROGRESSIVE_BACKUPS_FIELD,
                BILIBILI_PROGRESSIVE_FORMAT_FIELD,
                BILIBILI_PROGRESSIVE_PAGE_FIELD,
                BILIBILI_PROGRESSIVE_SEGMENTS_FIELD,
                _BILI_PROGRESSIVE_FIELD,
            }
            & set(value)
        ) or any(_contains_private_detail_field(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_private_detail_field(item) for item in value)
    return False


async def _execute_child(request: _ChildRequest) -> tuple[str, bytes]:
    upstream_main: Any | None = None
    try:
        upstream_main, progressive = await _watch_upstream(request)
        payload = _read_content_jsonl(request)
        if request.bili_dynamic_detail:
            if not isinstance(progressive, _BiliDynamicDetailResult) or payload:
                raise ValueError("invalid Bilibili dynamic detail result")
            payload = progressive.jsonl
        elif request.bili_progressive_detail:
            if not isinstance(progressive, _BiliPlaybackResult):
                raise _ChildTemporaryError
            else:
                payload = _augment_bili_progressive_jsonl(payload, progressive, request.watchdogs)
        elif progressive is not None:
            raise ValueError("unexpected Bilibili progressive result")
        return "succeeded", payload
    except _ChildConfigurationError:
        return "configuration_invalid", b""
    except _ChildAuthExpiredError:
        return "auth_expired", b""
    except _ChildTemporaryError:
        return "temporary", b""
    except _ChildUnsupportedError:
        return "unsupported", b""
    except TimeoutError:
        return "temporary", b""
    except Exception as error:
        from media_sync.integrations.mediacrawler.bilibili_dynamic import BiliDynamicUnsupportedError

        if request.bili_dynamic_detail and isinstance(error, BiliDynamicUnsupportedError):
            return "unsupported", b""
        if request.login_method is LoginMethod.SAVED_SESSION:
            from media_sync.integrations.mediacrawler.login_runner import (
                SavedSessionQrFallbackBlocked,
            )

            if isinstance(error, SavedSessionQrFallbackBlocked):
                return "auth_expired", b""
        return "result_invalid", b""
    finally:
        cleanup_module = upstream_main or sys.modules.get("main")
        if cleanup_module is not None and _module_belongs_to_checkout(cleanup_module, request.checkout_root):
            config = sys.modules.get("config")
            if config is not None:
                config.__dict__["COOKIES"] = ""
            cleanup = getattr(cleanup_module, "async_cleanup", None)
            if callable(cleanup):
                with contextlib.suppress(asyncio.TimeoutError, Exception):
                    await asyncio.wait_for(cleanup(), timeout=5.0)


def _emit_child_frame(status: str, payload: bytes = b"") -> None:
    encoded = json.dumps(
        {
            "schema_version": DETAIL_RUNNER_SCHEMA_VERSION,
            "status": status,
            "payload": base64.b64encode(payload).decode("ascii"),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("ascii")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _child_entry() -> int:
    try:
        payload = sys.stdin.buffer.read(MAX_DETAIL_REQUEST_BYTES + 1)
        if len(payload) > MAX_DETAIL_REQUEST_BYTES:
            raise _ChildConfigurationError
        request = _ChildRequest.load(payload)
        payload = b""
        with _silenced_upstream():
            status, output = asyncio.run(_execute_child(request))
    except Exception:
        status, output = "configuration_invalid", b""
    _emit_child_frame(status, output)
    return 0 if status == "succeeded" else 20


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "--child":
        raise SystemExit(20)
    raise SystemExit(_child_entry())


__all__ = [
    "DETAIL_RUNNER_SCHEMA_VERSION",
    "MediaCrawlerDetailPayloadRunner",
    "MediaCrawlerDetailProcessRunner",
    "MediaCrawlerDetailRequest",
    "MediaCrawlerDetailResult",
]
