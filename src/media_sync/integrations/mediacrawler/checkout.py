"""Pinned-checkout discovery and validation for the external MediaCrawler process."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .policies import require_confined

MEDIACRAWLER_NAME = "MediaCrawler"
MEDIACRAWLER_REPOSITORY = "https://github.com/NanmiCoder/MediaCrawler.git"
MEDIACRAWLER_LICENSE = "NON-COMMERCIAL LEARNING LICENSE 1.1"
MEDIACRAWLER_LICENSE_SHA256 = "9a2eed2fd5410cc59cfceae5d965c2a13d36907caa8bc6316d71e67391bbd5aa"
MAX_LOCK_BYTES = 1_048_576
MINIMUM_PYTHON = (3, 11)

_REQUIRED_TRACKED_FILES = ("LICENSE", "main.py", "config/__init__.py")
_RUNTIME_IMPORT_PROBE = """
import sys
if sys.version_info < (3, 11):
    raise SystemExit(41)
try:
    import aiofiles
    import playwright.async_api
    import tenacity
    import typer
except Exception:
    raise SystemExit(42)
raise SystemExit(0)
"""

_BROWSER_PROBE = """
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    print(browser.version)
    browser.close()
"""

_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")


class CheckoutValidationCode(StrEnum):
    """Stable, redaction-safe reasons for a checkout/runtime preflight failure."""

    UNKNOWN = "checkout_validation_failed"
    LICENSE_ACKNOWLEDGEMENT_REQUIRED = "license_acknowledgement_required"
    LOCK_MISSING = "lock_missing"
    LOCK_INVALID = "lock_invalid"
    LOCK_REPOSITORY_MISMATCH = "lock_repository_mismatch"
    LOCK_LICENSE_MISMATCH = "lock_license_mismatch"
    LOCK_COMMIT_INVALID = "lock_commit_invalid"
    LOCK_PATH_INVALID = "lock_path_invalid"
    CHECKOUT_MISSING = "checkout_missing"
    NOT_REPOSITORY_ROOT = "not_repository_root"
    REQUIRED_FILE_MISSING = "required_file_missing"
    LICENSE_UNAVAILABLE = "license_unavailable"
    LICENSE_HEADER_MISMATCH = "license_header_mismatch"
    LICENSE_DIGEST_MISMATCH = "license_digest_mismatch"
    REVISION_MISMATCH = "revision_mismatch"
    REQUIRED_FILE_NOT_TRACKED = "required_file_not_tracked"
    TRACKED_BLOB_MISMATCH = "tracked_blob_mismatch"
    WORKTREE_DIRTY = "worktree_dirty"
    GIT_INSPECTION_FAILED = "git_inspection_failed"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    RUNTIME_PROBE_FAILED = "runtime_probe_failed"
    RUNTIME_PYTHON_TOO_OLD = "runtime_python_too_old"
    RUNTIME_IMPORTS_MISSING = "runtime_imports_missing"
    BROWSER_LAUNCH_FAILED = "browser_launch_failed"


class CheckoutValidationError(RuntimeError):
    """The external source tree is absent, altered, or does not match its lock."""

    def __init__(
        self,
        message: str,
        code: CheckoutValidationCode | str = CheckoutValidationCode.UNKNOWN,
    ) -> None:
        self.code = code.value if isinstance(code, CheckoutValidationCode) else str(code)
        super().__init__(message)


class LicenseAcknowledgementRequired(CheckoutValidationError):
    """The caller has not explicitly accepted the restricted upstream license."""

    def __init__(self, message: str) -> None:
        super().__init__(message, CheckoutValidationCode.LICENSE_ACKNOWLEDGEMENT_REQUIRED)


@dataclass(frozen=True, slots=True)
class MediaCrawlerLock:
    repository: str
    commit: str
    license_name: str
    checkout_path: Path
    lock_path: Path


@dataclass(frozen=True, slots=True)
class VerifiedCheckout:
    root: Path
    commit: str
    repository: str
    license_name: str
    lock_path: Path


@dataclass(frozen=True, slots=True)
class VerifiedPython:
    """An explicit interpreter with the minimum upstream runtime imports."""

    executable: Path


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CheckoutValidationError(f"{name} must be a JSON object", CheckoutValidationCode.LOCK_INVALID)
    return {str(key): item for key, item in value.items()}


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckoutValidationError(f"{name} must be a non-empty string", CheckoutValidationCode.LOCK_INVALID)
    return value.strip()


def load_mediacrawler_lock(lock_path: Path) -> MediaCrawlerLock:
    """Load exactly one qualified MediaCrawler entry from ``upstreams.lock.json``."""

    resolved_lock = lock_path.expanduser().resolve()
    try:
        if not resolved_lock.is_file():
            raise CheckoutValidationError("upstream lock is missing", CheckoutValidationCode.LOCK_MISSING)
        if resolved_lock.stat().st_size > MAX_LOCK_BYTES:
            raise CheckoutValidationError("upstream lock exceeds the size limit", CheckoutValidationCode.LOCK_INVALID)
        payload = _mapping(json.loads(resolved_lock.read_text(encoding="utf-8")), "upstream lock")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CheckoutValidationError(
            "upstream lock could not be read safely", CheckoutValidationCode.LOCK_INVALID
        ) from error

    if payload.get("schema_version") != 1:
        raise CheckoutValidationError("unsupported upstream lock schema", CheckoutValidationCode.LOCK_INVALID)
    raw_upstreams = payload.get("upstreams")
    if not isinstance(raw_upstreams, list):
        raise CheckoutValidationError(
            "upstream lock must contain an upstreams list", CheckoutValidationCode.LOCK_INVALID
        )
    matches = [
        _mapping(item, "upstream entry")
        for item in raw_upstreams
        if isinstance(item, Mapping) and item.get("name") == MEDIACRAWLER_NAME
    ]
    if len(matches) != 1:
        raise CheckoutValidationError(
            "upstream lock must contain exactly one MediaCrawler entry",
            CheckoutValidationCode.LOCK_INVALID,
        )

    entry = matches[0]
    repository = _required_text(entry.get("repository"), "MediaCrawler repository")
    commit = _required_text(entry.get("commit"), "MediaCrawler commit").lower()
    license_name = _required_text(entry.get("license"), "MediaCrawler license")
    local_path = _required_text(entry.get("local_path"), "MediaCrawler local_path")
    if repository != MEDIACRAWLER_REPOSITORY:
        raise CheckoutValidationError(
            "MediaCrawler repository does not match the qualified source",
            CheckoutValidationCode.LOCK_REPOSITORY_MISMATCH,
        )
    if license_name != MEDIACRAWLER_LICENSE:
        raise CheckoutValidationError(
            "MediaCrawler license does not match the qualified source",
            CheckoutValidationCode.LOCK_LICENSE_MISMATCH,
        )
    if _FULL_SHA.fullmatch(commit) is None:
        raise CheckoutValidationError(
            "MediaCrawler commit must be a full lowercase Git SHA",
            CheckoutValidationCode.LOCK_COMMIT_INVALID,
        )

    project_root = resolved_lock.parent
    try:
        checkout_path = require_confined(project_root, project_root / local_path)
    except ValueError as error:
        raise CheckoutValidationError(
            "MediaCrawler local_path is outside the project root",
            CheckoutValidationCode.LOCK_PATH_INVALID,
        ) from error
    return MediaCrawlerLock(
        repository=repository,
        commit=commit,
        license_name=license_name,
        checkout_path=checkout_path,
        lock_path=resolved_lock,
    )


def _git_environment() -> dict[str, str]:
    allowed = {
        "HOME",
        "LANG",
        "LC_ALL",
        "DISPLAY",
        "PATH",
        "PATHEXT",
        "PLAYWRIGHT_BROWSERS_PATH",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    environment = {name: value for name, value in os.environ.items() if name.upper() in allowed}
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    return environment


def _git_output(checkout: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ("git", "-C", str(checkout), *arguments),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=_git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckoutValidationError(
            "Git could not inspect the MediaCrawler checkout",
            CheckoutValidationCode.GIT_INSPECTION_FAILED,
        ) from error
    if completed.returncode != 0:
        raise CheckoutValidationError(
            "Git rejected the MediaCrawler checkout", CheckoutValidationCode.GIT_INSPECTION_FAILED
        )
    return completed.stdout.strip()


def _tracked_blob(checkout: Path, relative_path: str) -> str:
    """Prove a required path is a regular tracked blob identical to locked HEAD."""

    stage = _git_output(checkout, "ls-files", "--stage", "--", relative_path)
    fields = stage.split(maxsplit=3)
    if len(fields) != 4 or fields[0] not in {"100644", "100755"} or fields[3] != relative_path:
        raise CheckoutValidationError(
            "MediaCrawler required entry is not a tracked regular file",
            CheckoutValidationCode.REQUIRED_FILE_NOT_TRACKED,
        )
    committed_blob = _git_output(checkout, "rev-parse", f"HEAD:{relative_path}").lower()
    working_blob = _git_output(
        checkout,
        "-c",
        "core.autocrlf=input",
        "hash-object",
        f"--path={relative_path}",
        "--",
        relative_path,
    ).lower()
    if fields[1].lower() != committed_blob or working_blob != committed_blob:
        raise CheckoutValidationError(
            "MediaCrawler required entry differs from the locked commit",
            CheckoutValidationCode.TRACKED_BLOB_MISMATCH,
        )
    return committed_blob


def verify_mediacrawler_python(python_executable: Path) -> VerifiedPython:
    """Doctor an explicitly configured Python without importing upstream source."""

    executable = python_executable.expanduser().resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise CheckoutValidationError(
            "MediaCrawler Python executable is unavailable", CheckoutValidationCode.RUNTIME_UNAVAILABLE
        )
    try:
        completed = subprocess.run(
            (str(executable), "-I", "-c", _RUNTIME_IMPORT_PROBE),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            env=_git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckoutValidationError(
            "MediaCrawler Python runtime probe could not complete",
            CheckoutValidationCode.RUNTIME_PROBE_FAILED,
        ) from error
    if completed.returncode == 41:
        raise CheckoutValidationError(
            "MediaCrawler Python must be version 3.11 or newer",
            CheckoutValidationCode.RUNTIME_PYTHON_TOO_OLD,
        )
    if completed.returncode != 0:
        raise CheckoutValidationError(
            "MediaCrawler Python is missing required runtime imports",
            CheckoutValidationCode.RUNTIME_IMPORTS_MISSING,
        )
    return VerifiedPython(executable=executable)


def verify_mediacrawler_browser(python_executable: Path) -> str:
    """Launch the configured Playwright Chromium once and return its version."""

    executable = python_executable.expanduser().resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise CheckoutValidationError(
            "MediaCrawler Python executable is unavailable", CheckoutValidationCode.RUNTIME_UNAVAILABLE
        )
    try:
        completed = subprocess.run(
            (str(executable), "-I", "-c", _BROWSER_PROBE),
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            env=_git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckoutValidationError(
            "MediaCrawler Chromium launch probe could not complete",
            CheckoutValidationCode.BROWSER_LAUNCH_FAILED,
        ) from error
    if completed.returncode != 0 or not completed.stdout.strip():
        raise CheckoutValidationError(
            "MediaCrawler Chromium could not launch",
            CheckoutValidationCode.BROWSER_LAUNCH_FAILED,
        )
    return completed.stdout.strip().splitlines()[-1][:128]


def verify_mediacrawler_checkout(
    lock_path: Path,
    *,
    license_acknowledged: bool,
) -> VerifiedCheckout:
    """Verify license acknowledgement, exact revision, shape, and tracked cleanliness."""

    if not license_acknowledged:
        raise LicenseAcknowledgementRequired(
            "MediaCrawler's non-commercial learning license must be acknowledged explicitly"
        )
    lock = load_mediacrawler_lock(lock_path)
    checkout = lock.checkout_path.resolve()
    if not checkout.is_dir():
        raise CheckoutValidationError("MediaCrawler checkout is unavailable", CheckoutValidationCode.CHECKOUT_MISSING)
    repository_root = Path(_git_output(checkout, "rev-parse", "--show-toplevel")).resolve()
    if repository_root != checkout:
        raise CheckoutValidationError(
            "MediaCrawler checkout path is not the Git repository root",
            CheckoutValidationCode.NOT_REPOSITORY_ROOT,
        )
    if not (checkout / "main.py").is_file() or not (checkout / "config" / "__init__.py").is_file():
        raise CheckoutValidationError(
            "MediaCrawler checkout is missing required entry points",
            CheckoutValidationCode.REQUIRED_FILE_MISSING,
        )
    license_path = checkout / "LICENSE"
    try:
        license_bytes = license_path.read_bytes()
        license_header = license_bytes.decode("utf-8")[:512].splitlines()[0].strip()
    except (OSError, UnicodeError, IndexError) as error:
        raise CheckoutValidationError(
            "MediaCrawler license file is unavailable", CheckoutValidationCode.LICENSE_UNAVAILABLE
        ) from error
    if license_header != lock.license_name:
        raise CheckoutValidationError(
            "MediaCrawler checkout license does not match the lock",
            CheckoutValidationCode.LICENSE_HEADER_MISMATCH,
        )
    if hashlib.sha256(license_bytes).hexdigest() != MEDIACRAWLER_LICENSE_SHA256:
        raise CheckoutValidationError(
            "MediaCrawler checkout license digest is not qualified",
            CheckoutValidationCode.LICENSE_DIGEST_MISMATCH,
        )

    revision = _git_output(checkout, "rev-parse", "HEAD").lower()
    if revision != lock.commit:
        raise CheckoutValidationError(
            "MediaCrawler checkout revision does not match the lock",
            CheckoutValidationCode.REVISION_MISMATCH,
        )
    for relative_path in _REQUIRED_TRACKED_FILES:
        _tracked_blob(checkout, relative_path)
    if _git_output(
        checkout,
        "-c",
        "core.autocrlf=input",
        "status",
        "--porcelain",
        "--untracked-files=all",
    ):
        raise CheckoutValidationError(
            "MediaCrawler checkout contains modifications or untracked files",
            CheckoutValidationCode.WORKTREE_DIRTY,
        )
    return VerifiedCheckout(
        root=checkout,
        commit=revision,
        repository=lock.repository,
        license_name=lock.license_name,
        lock_path=lock.lock_path,
    )


__all__ = [
    "MAX_LOCK_BYTES",
    "MEDIACRAWLER_LICENSE",
    "MEDIACRAWLER_LICENSE_SHA256",
    "MEDIACRAWLER_NAME",
    "MEDIACRAWLER_REPOSITORY",
    "MINIMUM_PYTHON",
    "CheckoutValidationCode",
    "CheckoutValidationError",
    "LicenseAcknowledgementRequired",
    "MediaCrawlerLock",
    "VerifiedCheckout",
    "VerifiedPython",
    "load_mediacrawler_lock",
    "verify_mediacrawler_browser",
    "verify_mediacrawler_checkout",
    "verify_mediacrawler_python",
]
