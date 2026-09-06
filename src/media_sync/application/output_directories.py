"""Shared, revisioned compatible-library roots; private archives never move."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from media_sync.config import Settings
from media_sync.exporters.emby import EmbyExporter
from media_sync.infrastructure.db import (
    Author,
    AuthorOutputBinding,
    Content,
    Database,
    ExportRecord,
    Job,
    LibraryOutputPolicy,
    utc_now,
)
from media_sync.infrastructure.db.database import SQLITE_IMMEDIATE_OPTION
from media_sync.infrastructure.db.models import PLATFORMS

_PLATFORMS = tuple(sorted(PLATFORMS))
_LAYOUTS = frozenset({"legacy_flat", "platform_subdirectories"})
_MAX_REVISION = 9_007_199_254_740_991
_CODES = frozenset(
    {
        "output_directory_invalid",
        "output_directory_unsafe",
        "output_directory_overlap",
        "output_directory_conflict",
        "output_directory_migration_required",
        "output_directory_author_not_found",
        "output_directory_unavailable",
    }
)
_SOURCE_DIRECTORIES = ("src", "tests", "docs", "web", "scripts", "docker", ".git", ".upstream", ".venv")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"} | {f"{prefix}{n}" for prefix in ("com", "lpt") for n in range(1, 10)}
)


class OutputDirectoryError(RuntimeError):
    """Fixed-safe errors; only public platform names accompany a failure."""

    def __init__(self, code: str, platforms: tuple[str, ...] = ()) -> None:
        self.code = code if code in _CODES else "output_directory_unavailable"
        self.platforms = tuple(sorted({value for value in platforms if value in PLATFORMS}))
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class _Policy:
    revision: int
    initialized: bool
    shared_root: str = field(repr=False)
    layout: str
    overrides: Mapping[str, str | None] = field(repr=False)

    def roots(self) -> dict[str, str]:
        return {
            platform: self.overrides[platform]
            or str(
                Path(self.shared_root) / platform
                if self.layout == "platform_subdirectories"
                else Path(self.shared_root)
            )
            for platform in _PLATFORMS
        }


def _absolute(value: Path) -> Path:
    return Path(os.path.abspath(value.expanduser()))


def _contains(parent: Path, child: Path) -> bool:
    first = Path(os.path.normcase(str(parent)))
    second = Path(os.path.normcase(str(child)))
    return second == first or first in second.parents


def _overlaps(first: Path, second: Path) -> bool:
    return _contains(first, second) or _contains(second, first)


def _native_root(value: object) -> Path:
    if not isinstance(value, str) or not value or value != value.strip():
        raise OutputDirectoryError("output_directory_invalid")
    try:
        bounded = len(value.encode("utf-8")) <= 4096
    except UnicodeError:
        bounded = False
    if not bounded or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise OutputDirectoryError("output_directory_invalid")
    if any(part in {".", ".."} for part in re.split(r"[\\/]", value)):
        raise OutputDirectoryError("output_directory_invalid")
    path = Path(value)
    if not path.is_absolute() or path == Path(path.anchor):
        raise OutputDirectoryError("output_directory_invalid")
    if os.name == "nt":
        if re.fullmatch(r"[A-Za-z]:", path.drive) is None:
            raise OutputDirectoryError("output_directory_invalid")
        for component in path.parts[1:]:
            if (
                any(character in '<>:"|?*' for character in component)
                or component.endswith((".", " "))
                or component.split(".", 1)[0].casefold() in _WINDOWS_RESERVED
            ):
                raise OutputDirectoryError("output_directory_invalid")
    elif "\\" in value or value.startswith("//"):
        raise OutputDirectoryError("output_directory_invalid")
    return Path(os.path.normcase(os.path.abspath(value)))


def _validate_existing_ancestors(path: Path) -> None:
    """Read-only validation before any resolve/mkdir can erase link evidence."""

    for current in reversed((path, *path.parents)):
        try:
            details = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise OutputDirectoryError("output_directory_unavailable") from None
        if (
            not stat.S_ISDIR(details.st_mode)
            or stat.S_ISLNK(details.st_mode)
            or getattr(details, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise OutputDirectoryError("output_directory_unsafe")


class OutputDirectoryService:
    """Own short DB transactions, never file creation, migration or credentials."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self._database = database
        self._settings = settings

    def _protected_paths(self) -> tuple[tuple[Path, ...], Path]:
        settings = self._settings
        state = _absolute(settings.state_dir)
        paths = [
            state,
            _absolute(settings.archive_dir),
            _absolute(settings.job_dir),
            _absolute(settings.secret_file_dir or settings.state_dir / "secrets"),
            _absolute(settings.state_dir / "credentials"),
            _absolute(settings.mediacrawler_runtime_dir or settings.state_dir / "mediacrawler"),
            _absolute(settings.mediacrawler_lock_path),
        ]
        if os.name == "nt":
            system_drive = os.environ.get("SYSTEMDRIVE", Path(os.path.abspath(os.sep)).drive or "C:")
            windows_defaults = {
                "SYSTEMROOT": f"{system_drive}/Windows",
                "WINDIR": f"{system_drive}/Windows",
                "PROGRAMFILES": f"{system_drive}/Program Files",
                "PROGRAMFILES(X86)": f"{system_drive}/Program Files (x86)",
                "PROGRAMW6432": f"{system_drive}/Program Files",
                "PROGRAMDATA": f"{system_drive}/ProgramData",
            }
            paths.extend(_absolute(Path(os.environ.get(name) or default)) for name, default in windows_defaults.items())
        else:
            paths.extend(
                Path(name)
                for name in (
                    "/bin",
                    "/sbin",
                    "/etc",
                    "/usr",
                    "/lib",
                    "/lib64",
                    "/boot",
                    "/proc",
                    "/sys",
                    "/dev",
                    "/run",
                )
            )
        database_url = make_url(self._database.url)
        if database_url.get_backend_name() == "sqlite" and database_url.database not in {None, "", ":memory:"}:
            assert database_url.database is not None
            paths.append(_absolute(Path(database_url.database)))
        repository = _absolute(settings.mediacrawler_lock_path).parent
        paths.extend(repository / name for name in _SOURCE_DIRECTORIES)
        # Installed code remains private even when the configured lock lives elsewhere.
        paths.append(Path(__file__).absolute().parents[1])
        canonical = [path.resolve(strict=False) for path in paths]
        return tuple((*paths, *canonical)), repository

    def _safe_root(self, value: object) -> Path:
        path = _native_root(value)
        protected, repository = self._protected_paths()
        if _contains(path, repository) or any(_overlaps(path, private) for private in protected):
            raise OutputDirectoryError("output_directory_unsafe")
        _validate_existing_ancestors(path)
        return path

    def _policy(
        self, revision: int, initialized: bool, shared_root: object, overrides: object, layout: object
    ) -> _Policy:
        if (
            type(revision) is not int
            or not 0 <= revision <= _MAX_REVISION
            or not isinstance(layout, str)
            or layout not in _LAYOUTS
            or not isinstance(overrides, Mapping)
            or any(key not in PLATFORMS for key in overrides)
        ):
            raise OutputDirectoryError("output_directory_invalid")
        root = str(self._safe_root(shared_root))
        normalized: dict[str, str | None] = {}
        for platform in _PLATFORMS:
            value = overrides.get(platform)
            normalized[platform] = None if value is None else str(self._safe_root(value))
        policy = _Policy(revision, initialized, root, layout, normalized)
        effective = {platform: self._safe_root(value) for platform, value in policy.roots().items()}
        for index, platform in enumerate(_PLATFORMS):
            for other in _PLATFORMS[index + 1 :]:
                if effective[platform] == effective[other] and layout == "legacy_flat":
                    continue
                if _overlaps(effective[platform], effective[other]):
                    raise OutputDirectoryError("output_directory_overlap", (platform, other))
        return policy

    @staticmethod
    def _protected_platforms(session: Session) -> tuple[str, ...]:
        result = set(session.scalars(select(AuthorOutputBinding.platform).distinct()))
        result.update(
            session.scalars(
                select(Author.platform)
                .join(Content, Content.author_id == Author.id)
                .join(ExportRecord, ExportRecord.content_id == Content.id)
                .where(ExportRecord.exporter == "emby")
                .distinct()
            )
        )
        result.update(
            session.scalars(
                select(Author.platform)
                .join(Job, Job.payload["author_id"].as_string() == Author.id)
                .where(Job.job_type == "export.emby")
                .distinct()
            )
        )
        return tuple(sorted(result & PLATFORMS))

    def _read(self, session: Session, *, locked: bool = False) -> _Policy:
        statement = select(LibraryOutputPolicy).where(LibraryOutputPolicy.id == 1)
        if locked:
            statement = statement.with_for_update()
        row = session.scalar(statement.execution_options(populate_existing=True))
        if row is None:
            layout = "legacy_flat" if self._protected_platforms(session) else "platform_subdirectories"
            candidate = self._policy(0, False, str(_absolute(self._settings.export_dir)), {}, layout)
            if layout == "legacy_flat":
                self._check_legacy_scopes(session, candidate)
            return candidate
        return self._policy(
            row.revision,
            True,
            row.shared_root,
            {platform: getattr(row, f"{platform}_root") for platform in _PLATFORMS},
            row.layout,
        )

    @staticmethod
    def _check_legacy_scopes(session: Session, policy: _Policy) -> None:
        """Never bind a changed environment root over a provably different old scope.

        Older records without a persisted scope cannot reconstruct an absolute
        location. Their existing environment root retains the legacy flat shape;
        this is compatibility, not evidence that the old files were inspected.
        """

        expected = EmbyExporter(Path(policy.shared_root)).coordination_scope
        rows = session.execute(
            select(Author.platform, Job.payload["publication_scope"].as_string())
            .join(Job, Job.payload["author_id"].as_string() == Author.id)
            .where(Job.job_type == "export.emby")
            .distinct()
        )
        mismatched = tuple(sorted({platform for platform, scope in rows if scope is not None and scope != expected}))
        if mismatched:
            raise OutputDirectoryError("output_directory_migration_required", mismatched)

    def _locked(self, session: Session) -> _Policy:
        dialect = session.get_bind().dialect.name
        if dialect == "sqlite":
            # This must be the first connection use, before any read snapshot.
            options: Mapping[str, Any] = {SQLITE_IMMEDIATE_OPTION: True}
            session.connection(execution_options=options)
        policy = self._read(session, locked=True)
        if policy.initialized:
            return policy
        values: dict[str, Any] = {
            "id": 1,
            "revision": 0,
            "shared_root": policy.shared_root,
            "layout": policy.layout,
        }
        insert = sqlite_insert if dialect == "sqlite" else postgresql_insert if dialect == "postgresql" else None
        if insert is None:
            raise OutputDirectoryError("output_directory_unavailable")
        session.execute(insert(LibraryOutputPolicy).values(**values).on_conflict_do_nothing(index_elements=["id"]))
        return self._read(session, locked=True)

    @staticmethod
    def _payload(policy: _Policy, protected: tuple[str, ...]) -> dict[str, object]:
        return {
            "revision": policy.revision,
            "initialized": policy.initialized,
            "shared_root": policy.shared_root,
            "layout": policy.layout,
            "platform_overrides": dict(policy.overrides),
            "effective_roots": policy.roots(),
            "protected_platforms": list(protected),
        }

    @staticmethod
    def _check_change(current: _Policy, proposed: _Policy, protected: tuple[str, ...]) -> None:
        before, after = current.roots(), proposed.roots()
        changed = tuple(platform for platform in protected if before[platform] != after[platform])
        if changed:
            raise OutputDirectoryError("output_directory_migration_required", changed)

    def get_policy(self) -> dict[str, object]:
        try:
            with self._database.session() as session:
                return self._payload(self._read(session), self._protected_platforms(session))
        except (OSError, SQLAlchemyError, ValueError):
            raise OutputDirectoryError("output_directory_unavailable") from None

    def preview(self, shared_root: str, platform_overrides: Mapping[str, str | None], layout: str) -> dict[str, object]:
        try:
            with self._database.session() as session:
                current = self._read(session)
                proposed = self._policy(current.revision, current.initialized, shared_root, platform_overrides, layout)
                protected = self._protected_platforms(session)
                self._check_change(current, proposed, protected)
                return self._payload(proposed, protected)
        except (OSError, SQLAlchemyError, ValueError):
            raise OutputDirectoryError("output_directory_unavailable") from None

    def update(
        self, expected_revision: int, shared_root: str, platform_overrides: Mapping[str, str | None], layout: str
    ) -> dict[str, object]:
        if type(expected_revision) is not int or not 0 <= expected_revision < _MAX_REVISION:
            raise OutputDirectoryError("output_directory_invalid")
        try:
            with self._database.session() as session:
                current = self._locked(session)
                if current.revision != expected_revision:
                    raise OutputDirectoryError("output_directory_conflict")
                proposed = self._policy(expected_revision + 1, True, shared_root, platform_overrides, layout)
                protected = self._protected_platforms(session)
                self._check_change(current, proposed, protected)
                values: dict[str, Any] = {
                    "revision": proposed.revision,
                    "shared_root": proposed.shared_root,
                    "layout": proposed.layout,
                    "updated_at": utc_now(),
                    **{f"{platform}_root": proposed.overrides[platform] for platform in _PLATFORMS},
                }
                changed = session.execute(
                    update(LibraryOutputPolicy)
                    .where(LibraryOutputPolicy.id == 1, LibraryOutputPolicy.revision == expected_revision)
                    .values(**values)
                )
                if cast(CursorResult[Any], changed).rowcount != 1:
                    raise OutputDirectoryError("output_directory_conflict")
                return self._payload(proposed, protected)
        except (OSError, SQLAlchemyError, ValueError):
            raise OutputDirectoryError("output_directory_unavailable") from None

    @staticmethod
    def _author(session: Session, author_id: str) -> Author:
        try:
            if str(UUID(author_id)) != author_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise OutputDirectoryError("output_directory_author_not_found") from None
        author = session.get(Author, author_id)
        if author is None or author.platform not in PLATFORMS:
            raise OutputDirectoryError("output_directory_author_not_found")
        return author

    def _author_root(self, session: Session, policy: _Policy, author: Author) -> Path:
        binding = session.get(AuthorOutputBinding, author.id)
        current = policy.roots()[author.platform]
        if binding is not None:
            if (
                not policy.initialized
                or binding.platform != author.platform
                or binding.policy_revision > policy.revision
                or binding.canonical_root != current
            ):
                raise OutputDirectoryError("output_directory_unavailable")
            return self._safe_root(binding.canonical_root)
        return self._safe_root(current)

    def resolve_author_root(self, author_id: str) -> Path:
        try:
            with self._database.session() as session:
                return self._author_root(session, self._read(session), self._author(session, author_id))
        except (OSError, SQLAlchemyError, ValueError):
            raise OutputDirectoryError("output_directory_unavailable") from None

    def bind_author_root(self, author_id: str) -> Path:
        try:
            with self._database.session() as session:
                policy = self._locked(session)
                author = self._author(session, author_id)
                root = self._author_root(session, policy, author)
                if session.get(AuthorOutputBinding, author_id) is None:
                    session.add(
                        AuthorOutputBinding(
                            author_id=author_id,
                            platform=author.platform,
                            canonical_root=str(root),
                            policy_revision=policy.revision,
                        )
                    )
                    session.flush()
                return root
        except (OSError, SQLAlchemyError, ValueError):
            raise OutputDirectoryError("output_directory_unavailable") from None


__all__ = ["OutputDirectoryError", "OutputDirectoryService"]
