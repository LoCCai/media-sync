"""Small bootstrap for the pinned MediaCrawler WebUI child process.

The upstream WebUI manager normally launches ``uv run`` and places Cookie
material on the process command line.  media-sync launches this file with the
already-qualified upstream interpreter instead.  The bootstrap keeps the
upstream crawler/login implementation intact while applying deployment-only
settings that the upstream WebUI does not expose.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import os
import stat
import sys
from pathlib import Path
from typing import Any

# An isolated upstream interpreter starts with this file's directory only.
if __name__ == "__main__" and (__package__ is None or __package__ == ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from media_sync.integrations.mediacrawler.browser_policy import install_bundled_chromium_policy
from media_sync.integrations.mediacrawler.login_runner import _disable_qr_export

_MAX_COOKIE_BYTES = 64 * 1024


class _ChildConfigurationError(RuntimeError):
    pass


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--profile-root", required=True)
    parser.add_argument("--qr-path", required=True)
    parser.add_argument("--cookie-file")
    parser.add_argument("upstream_args", nargs=argparse.REMAINDER)
    values = parser.parse_args(argv)
    if values.upstream_args[:1] == ["--"]:
        values.upstream_args = values.upstream_args[1:]
    return values


def _regular_private_cookie(path: Path) -> str:
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_COOKIE_BYTES:
            raise _ChildConfigurationError
        if os.name != "nt" and metadata.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise _ChildConfigurationError
        value = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise _ChildConfigurationError from error
    finally:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
    if not value or len(value.encode("utf-8")) > _MAX_COOKIE_BYTES:
        raise _ChildConfigurationError
    return value


def _module_in_checkout(module: Any, checkout: Path) -> bool:
    location = getattr(module, "__file__", None)
    if not isinstance(location, str):
        return False
    try:
        return Path(location).resolve().is_relative_to(checkout)
    except OSError:
        return False


def _prepare_directory(path: Path, checkout: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved == checkout or resolved.is_relative_to(checkout):
        raise _ChildConfigurationError
    resolved.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        resolved.chmod(0o700)
    return resolved


def run(argv: list[str] | None = None) -> None:
    values = _arguments(argv)
    checkout = Path(values.checkout).expanduser().resolve()
    if not (checkout / "main.py").is_file() or not (checkout / "config" / "__init__.py").is_file():
        raise _ChildConfigurationError
    output_root = _prepare_directory(Path(values.output_root), checkout)
    profile_root = _prepare_directory(Path(values.profile_root), checkout)
    qr_path = Path(values.qr_path).expanduser().resolve()
    if qr_path.parent != profile_root.parent or qr_path == checkout or qr_path.is_relative_to(checkout):
        raise _ChildConfigurationError
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        qr_path.unlink(missing_ok=True)

    cookie = _regular_private_cookie(Path(values.cookie_file).expanduser().resolve()) if values.cookie_file else None
    os.chdir(checkout)
    if str(checkout) not in sys.path:
        sys.path.insert(0, str(checkout))
    importlib.invalidate_caches()
    config: Any = importlib.import_module("config")
    if not _module_in_checkout(config, checkout):
        raise _ChildConfigurationError

    # These settings are deployment policy, not a replacement crawler.
    config.SAVE_DATA_PATH = str(output_root)
    config.USER_DATA_DIR = str(profile_root / "%s_user_data_dir")
    config.SAVE_LOGIN_STATE = True
    config.AUTO_CLOSE_BROWSER = True
    config.ENABLE_CDP_MODE = False
    config.ENABLE_GET_MEIDAS = True  # spelling used by the pinned upstream
    config.ENABLE_GET_MEDIAS = True  # forward-compatible spelling
    config.ENABLE_GET_WORDCLOUD = False
    config.MAX_CONCURRENCY_NUM = 1

    upstream_args = list(values.upstream_args)
    upstream_args.extend(("--save_data_path", str(output_root)))
    if cookie is not None:
        upstream_args.extend(("--cookies", cookie))
    sys.argv = ["mediacrawler", *upstream_args]
    upstream_main: Any = importlib.import_module("main")
    app_runner: Any = importlib.import_module("tools.app_runner")
    if not _module_in_checkout(upstream_main, checkout) or not _module_in_checkout(app_runner, checkout):
        raise _ChildConfigurationError
    main = getattr(upstream_main, "main", None)
    cleanup = getattr(upstream_main, "async_cleanup", None)
    runner = getattr(app_runner, "run", None)
    if not callable(main) or not callable(cleanup) or not callable(runner):
        raise _ChildConfigurationError
    install_bundled_chromium_policy(upstream_main)
    try:
        with _disable_qr_export(checkout, qr_path):
            runner(main, cleanup, cleanup_timeout_seconds=15.0)
    finally:
        with contextlib.suppress(OSError):
            qr_path.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
