"""Safety policy shared by the MediaCrawler bridge and its child runner."""

from __future__ import annotations

import math
import os
import re
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import quote, urlsplit
from uuid import UUID

from media_sync.domain import LoginMethod, Platform

PRIVATE_INPUT_ENV = "MEDIA_SYNC_MEDIACRAWLER_PRIVATE_INPUT"
# Kept as an alias for callers that only need to identify the one private
# channel. The value is a JSON envelope, never a raw Cookie string.
PRIVATE_COOKIE_ENV = PRIVATE_INPUT_ENV
MAX_PRIVATE_INPUT_BYTES = 80 * 1024
RUNNER_MANIFEST_NAME = "runner-manifest.json"

FULL_HISTORY_PLATFORMS = frozenset(
    {
        Platform.DY,
        Platform.KS,
        Platform.BILI,
        Platform.WB,
    }
)

CREATOR_CONFIG_ATTRIBUTES = {
    Platform.XHS: "XHS_CREATOR_ID_LIST",
    Platform.DY: "DY_CREATOR_ID_LIST",
    Platform.KS: "KS_CREATOR_ID_LIST",
    Platform.BILI: "BILI_CREATOR_ID_LIST",
    Platform.WB: "WEIBO_CREATOR_ID_LIST",
    Platform.TIEBA: "TIEBA_CREATOR_URL_LIST",
    Platform.ZHIHU: "ZHIHU_CREATOR_URL_LIST",
}

_UPSTREAM_LOGIN_TYPES = {
    LoginMethod.QR: "qrcode",
    LoginMethod.COOKIE: "cookie",
    # Keep saved-session identity distinct in our manifest/config projection.
    # The pinned CLI parser may coerce unknown values back to QR, so this value
    # is not a security boundary: every saved-session child must additionally
    # fence ``Login.begin`` before invoking the upstream crawler.
    LoginMethod.SAVED_SESSION: "saved_session",
}
_ZHIHU_TOKEN = re.compile(r"[A-Za-z0-9._-]{1,255}\Z")


class MediaCrawlerPolicyError(ValueError):
    """A run violates a local safety boundary before a child starts."""


class PathConfinementError(MediaCrawlerPolicyError):
    """A runtime path escapes its configured integration root."""


class FullHistoryAcknowledgementRequired(MediaCrawlerPolicyError):
    """The selected upstream creator path ignores its configured item cap."""


@dataclass(frozen=True, slots=True)
class WatchdogLimits:
    """Independent resource ceilings enforced around every child process."""

    max_seconds: float = 900.0
    max_output_bytes: int = 64 * 1024 * 1024
    max_output_items: int = 2_000
    max_output_files: int = 64
    max_line_bytes: int = 1024 * 1024
    poll_seconds: float = 0.05

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_seconds, bool)
            or not isinstance(self.max_seconds, int | float)
            or not math.isfinite(self.max_seconds)
            or self.max_seconds <= 0
        ):
            raise MediaCrawlerPolicyError("watchdog max_seconds must be positive")
        if type(self.max_output_bytes) is not int or self.max_output_bytes < 1:
            raise MediaCrawlerPolicyError("watchdog max_output_bytes must be positive")
        if type(self.max_output_items) is not int or self.max_output_items < 1:
            raise MediaCrawlerPolicyError("watchdog max_output_items must be positive")
        if type(self.max_output_files) is not int or self.max_output_files < 1:
            raise MediaCrawlerPolicyError("watchdog max_output_files must be positive")
        if type(self.max_line_bytes) is not int or self.max_line_bytes < 1:
            raise MediaCrawlerPolicyError("watchdog max_line_bytes must be positive")
        if (
            isinstance(self.poll_seconds, bool)
            or not isinstance(self.poll_seconds, int | float)
            or not math.isfinite(self.poll_seconds)
            or not 0 < self.poll_seconds <= 5
        ):
            raise MediaCrawlerPolicyError("watchdog poll_seconds must be between zero and five seconds")


@dataclass(frozen=True, slots=True)
class RunPaths:
    """All mutable upstream paths, derived only from typed local identifiers."""

    integration_root: Path
    account_root: Path
    profile_root: Path
    job_root: Path
    output_root: Path
    manifest_path: Path


@dataclass(frozen=True, slots=True)
class OutputStats:
    bytes_written: int = 0
    jsonl_items: int = 0
    files_written: int = 0


class OutputLimitKind(StrEnum):
    """Stable watchdog reasons that never include an attacker-controlled path."""

    BYTES = "bytes"
    ITEMS = "items"
    FILES = "files"
    LINE_BYTES = "line_bytes"
    TREE = "tree"


class OutputInspectionError(MediaCrawlerPolicyError):
    """The output tree or one of its resource budgets is invalid."""

    def __init__(self, kind: OutputLimitKind, stats: OutputStats | None = None) -> None:
        self.kind = kind
        self.stats = stats or OutputStats()
        super().__init__(f"MediaCrawler output watchdog rejected {kind.value}")


def confined_path(root: Path, *parts: str) -> Path:
    """Resolve a derived path and prove it remains below ``root``."""

    resolved_root = root.expanduser().resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if candidate == resolved_root or not candidate.is_relative_to(resolved_root):
        raise PathConfinementError("runtime path escapes the configured integration root")
    return candidate


def require_confined(root: Path, candidate: Path) -> Path:
    """Resolve an externally supplied path and prove root confinement."""

    resolved_root = root.expanduser().resolve()
    resolved_candidate = candidate.expanduser().resolve()
    if resolved_candidate == resolved_root or not resolved_candidate.is_relative_to(resolved_root):
        raise PathConfinementError("runtime path escapes the configured integration root")
    return resolved_candidate


def build_run_paths(
    integration_root: Path,
    platform: Platform,
    account_id: UUID,
    job_id: UUID,
) -> RunPaths:
    """Build a stable account profile and one UUID-scoped execution root.

    ``job_id`` retains its legacy parameter name for callers that prepared v2
    artifacts. Manifest v3 passes its attempt-scoped ``execution_id`` here.
    """

    root = integration_root.expanduser().resolve()
    account_root = confined_path(root, "accounts", platform.value, str(account_id))
    job_root = confined_path(root, "jobs", str(job_id))
    output_root = confined_path(root, "jobs", str(job_id), "output")
    manifest_path = confined_path(root, "jobs", str(job_id), RUNNER_MANIFEST_NAME)
    profile_root = confined_path(
        root,
        "accounts",
        platform.value,
        str(account_id),
        "browser_data",
        f"{platform.value}_user_data_dir",
    )
    return RunPaths(
        integration_root=root,
        account_root=account_root,
        profile_root=profile_root,
        job_root=job_root,
        output_root=output_root,
        manifest_path=manifest_path,
    )


def require_full_history_acknowledgement(platform: Platform, acknowledged: bool) -> None:
    if platform in FULL_HISTORY_PLATFORMS and not acknowledged:
        raise FullHistoryAcknowledgementRequired(
            f"platform {platform.value!r} creator mode requires allow_full_history acknowledgement"
        )


def upstream_login_type(method: LoginMethod) -> str:
    """Return the qualified upstream value; phone is deliberately unreachable."""

    try:
        return _UPSTREAM_LOGIN_TYPES[method]
    except KeyError as error:
        raise MediaCrawlerPolicyError("MediaCrawler bridge does not support phone login") from error


def normalize_creator_reference(platform: Platform, value: str) -> str:
    """Normalize only compatibility forms required by upstream creator lists."""

    normalized = value.strip()
    if not normalized or len(normalized) > 4_096:
        raise MediaCrawlerPolicyError("creator reference must contain between 1 and 4096 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise MediaCrawlerPolicyError("creator reference contains control characters")

    if platform is Platform.TIEBA and not normalized.lower().startswith(("http://", "https://")):
        return f"https://tieba.baidu.com/home/main?id={quote(normalized, safe='')}"

    if platform is not Platform.ZHIHU:
        return normalized

    if normalized.lower().startswith(("http://", "https://")):
        try:
            parsed = urlsplit(normalized)
            parsed_port = parsed.port
        except ValueError as error:
            raise MediaCrawlerPolicyError("Zhihu creator URL is malformed") from error
        if (
            parsed.hostname not in {"zhihu.com", "www.zhihu.com"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed_port is not None
            or parsed.query
            or parsed.fragment
        ):
            raise MediaCrawlerPolicyError("Zhihu creator URL must use zhihu.com")
        path_parts = parsed.path.split("/")
        if len(path_parts) != 3 or path_parts[0] or path_parts[1] != "people" or not path_parts[2]:
            raise MediaCrawlerPolicyError("Zhihu creator URL must use /people/<url_token>")
        token = path_parts[2]
    else:
        token = normalized
    if _ZHIHU_TOKEN.fullmatch(token) is None:
        raise MediaCrawlerPolicyError("Zhihu creator token contains unsupported characters")
    return f"https://www.zhihu.com/people/{token}"


def _is_reparse(stat_result: os.stat_result) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attributes & reparse_flag)


def inspect_output(root: Path, limits: WatchdogLimits | None = None) -> OutputStats:
    """Validate and count the bounded, JSONL-only child output tree."""

    active_limits = limits or WatchdogLimits()
    declared_root = root.expanduser().absolute()
    if not declared_root.exists():
        return OutputStats()
    try:
        root_stat = declared_root.lstat()
    except OSError as error:
        raise OutputInspectionError(OutputLimitKind.TREE) from error
    if not stat.S_ISDIR(root_stat.st_mode) or _is_reparse(root_stat):
        raise OutputInspectionError(OutputLimitKind.TREE)
    resolved_root = declared_root.resolve()
    if resolved_root != declared_root:
        raise OutputInspectionError(OutputLimitKind.TREE)

    bytes_written = 0
    jsonl_items = 0
    files_written = 0
    pending = [resolved_root]
    try:
        while pending:
            directory = pending.pop()
            directory_stat = directory.lstat()
            if not stat.S_ISDIR(directory_stat.st_mode) or _is_reparse(directory_stat):
                raise OutputInspectionError(OutputLimitKind.TREE)
            require_confined(resolved_root.parent, directory)
            with os.scandir(directory) as entries:
                for entry in entries:
                    candidate = Path(entry.path)
                    entry_stat = candidate.lstat()
                    if entry.is_symlink() or _is_reparse(entry_stat):
                        raise OutputInspectionError(OutputLimitKind.TREE)
                    require_confined(resolved_root, candidate)
                    if stat.S_ISDIR(entry_stat.st_mode):
                        pending.append(candidate)
                        continue
                    if (
                        not stat.S_ISREG(entry_stat.st_mode)
                        or entry_stat.st_nlink != 1
                        or candidate.suffix.lower() != ".jsonl"
                    ):
                        raise OutputInspectionError(OutputLimitKind.TREE)

                    files_written += 1
                    if files_written > active_limits.max_output_files:
                        stats = OutputStats(bytes_written, jsonl_items, files_written)
                        raise OutputInspectionError(OutputLimitKind.FILES, stats)

                    with candidate.open("rb") as stream:
                        opened_stat = os.fstat(stream.fileno())
                        if (
                            not stat.S_ISREG(opened_stat.st_mode)
                            or _is_reparse(opened_stat)
                            or opened_stat.st_nlink != 1
                            or (opened_stat.st_dev, opened_stat.st_ino) != (entry_stat.st_dev, entry_stat.st_ino)
                        ):
                            raise OutputInspectionError(OutputLimitKind.TREE)
                        bytes_written += opened_stat.st_size
                        stats = OutputStats(bytes_written, jsonl_items, files_written)
                        if bytes_written > active_limits.max_output_bytes:
                            raise OutputInspectionError(OutputLimitKind.BYTES, stats)
                        while line := stream.readline(active_limits.max_line_bytes + 1):
                            if len(line) > active_limits.max_line_bytes:
                                raise OutputInspectionError(OutputLimitKind.LINE_BYTES, stats)
                            jsonl_items += 1
                            stats = OutputStats(bytes_written, jsonl_items, files_written)
                            if jsonl_items > active_limits.max_output_items:
                                raise OutputInspectionError(OutputLimitKind.ITEMS, stats)
    except OutputInspectionError:
        raise
    except OSError as error:
        raise OutputInspectionError(
            OutputLimitKind.TREE,
            OutputStats(bytes_written, jsonl_items, files_written),
        ) from error
    return OutputStats(
        bytes_written=bytes_written,
        jsonl_items=jsonl_items,
        files_written=files_written,
    )


__all__ = [
    "CREATOR_CONFIG_ATTRIBUTES",
    "FULL_HISTORY_PLATFORMS",
    "MAX_PRIVATE_INPUT_BYTES",
    "PRIVATE_COOKIE_ENV",
    "PRIVATE_INPUT_ENV",
    "RUNNER_MANIFEST_NAME",
    "FullHistoryAcknowledgementRequired",
    "MediaCrawlerPolicyError",
    "OutputInspectionError",
    "OutputLimitKind",
    "OutputStats",
    "PathConfinementError",
    "RunPaths",
    "WatchdogLimits",
    "build_run_paths",
    "confined_path",
    "inspect_output",
    "normalize_creator_reference",
    "require_confined",
    "require_full_history_acknowledgement",
    "upstream_login_type",
]
