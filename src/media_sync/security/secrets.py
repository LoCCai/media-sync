"""Typed secret references and local secret-provider boundaries."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from importlib import import_module
from pathlib import Path, PureWindowsPath
from typing import Protocol, cast

MAX_SECRET_BYTES = 65_536
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_KEYRING_LOCATOR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@:+/-]*\Z")


class SecretError(RuntimeError):
    """Base error whose message is always safe for operators and logs."""


class InvalidSecretReferenceError(SecretError):
    """A reference is malformed or resembles inline credential material."""


class SecretResolutionError(SecretError):
    """A provider could not return a usable secret."""


class SecretScheme(StrEnum):
    """Supported non-secret lookup mechanisms."""

    ENV = "env"
    FILE = "file"
    KEYRING = "keyring"


@dataclass(frozen=True, slots=True)
class SecretReference:
    """A persistable provider locator that never contains the secret value."""

    scheme: SecretScheme
    locator: str = field(repr=False)

    @classmethod
    def parse(cls, value: str) -> SecretReference:
        normalized = value.strip()
        if not normalized or len(normalized) > 512:
            raise InvalidSecretReferenceError("secret reference must contain between 1 and 512 characters")
        if any(marker in normalized for marker in ("\r", "\n", "\0", ";", "=")):
            raise InvalidSecretReferenceError("inline credential material is not a valid secret reference")

        raw_scheme, separator, raw_locator = normalized.partition(":")
        try:
            scheme = SecretScheme(raw_scheme.lower())
        except ValueError as error:
            raise InvalidSecretReferenceError("unsupported secret reference scheme") from error
        locator = raw_locator.strip()
        if not separator or not locator:
            raise InvalidSecretReferenceError("secret reference locator must not be empty")
        if scheme is SecretScheme.ENV and _ENV_NAME.fullmatch(locator) is None:
            raise InvalidSecretReferenceError("environment secret reference must name one variable")
        if scheme is SecretScheme.KEYRING:
            if _KEYRING_LOCATOR.fullmatch(locator) is None or "/" not in locator:
                raise InvalidSecretReferenceError("keyring secret reference must use service/account")
            service, account = locator.split("/", maxsplit=1)
            if not service or not account:
                raise InvalidSecretReferenceError("keyring secret reference must use service/account")
        if scheme is SecretScheme.FILE:
            candidate = Path(locator)
            windows_candidate = PureWindowsPath(locator)
            if (
                candidate.is_absolute()
                or windows_candidate.is_absolute()
                or windows_candidate.drive
                or any(part == ".." for part in candidate.parts)
                or any(part == ".." for part in windows_candidate.parts)
            ):
                raise InvalidSecretReferenceError("file secret reference must be a confined relative path")
        return cls(scheme=scheme, locator=locator)

    def serialize(self) -> str:
        """Return the non-secret representation allowed in configuration/SQLite."""

        return f"{self.scheme.value}:{self.locator}"

    def __str__(self) -> str:
        return f"{self.scheme.value}:[REFERENCE]"


@dataclass(frozen=True, slots=True)
class SecretValue:
    """A deliberately awkward wrapper that prevents accidental display."""

    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self._value or "\0" in self._value:
            raise SecretResolutionError("secret provider returned an empty or invalid value")
        if len(self._value.encode("utf-8")) > MAX_SECRET_BYTES:
            raise SecretResolutionError("secret provider returned a value above the configured size limit")

    def reveal(self) -> str:
        """Return the value only at the final integration boundary."""

        return self._value

    def __str__(self) -> str:
        return "[SECRET]"


class SecretProvider(Protocol):
    """Resolve one already-validated provider-specific locator."""

    scheme: SecretScheme

    def resolve(self, reference: SecretReference) -> SecretValue:
        """Resolve a secret or raise a message-safe :class:`SecretError`."""
        ...


class EnvironmentSecretProvider:
    """Read a secret from the current process environment."""

    scheme = SecretScheme.ENV

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def resolve(self, reference: SecretReference) -> SecretValue:
        if reference.scheme is not self.scheme:
            raise InvalidSecretReferenceError("secret reference was sent to the wrong provider")
        value = self._environ.get(reference.locator)
        if value is None:
            raise SecretResolutionError("environment secret is unavailable")
        return SecretValue(value)


class FileSecretProvider:
    """Read a small UTF-8 secret file confined beneath one configured root."""

    scheme = SecretScheme.FILE

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def resolve(self, reference: SecretReference) -> SecretValue:
        if reference.scheme is not self.scheme:
            raise InvalidSecretReferenceError("secret reference was sent to the wrong provider")
        candidate = (self.root / reference.locator).resolve()
        if not candidate.is_relative_to(self.root):
            raise SecretResolutionError("secret file escapes the configured root")
        try:
            if not candidate.is_file():
                raise SecretResolutionError("secret file is unavailable")
            size = candidate.stat().st_size
            if size < 1 or size > MAX_SECRET_BYTES:
                raise SecretResolutionError("secret file size is outside the allowed range")
            value = candidate.read_text(encoding="utf-8").rstrip("\r\n")
        except (OSError, UnicodeError) as error:
            raise SecretResolutionError("secret file could not be read safely") from error
        return SecretValue(value)


class _KeyringModule(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...


class KeyringSecretProvider:
    """Resolve OS-keyring entries through an optional lazy dependency."""

    scheme = SecretScheme.KEYRING

    def __init__(self, module: _KeyringModule | None = None) -> None:
        self._module = module

    def _keyring(self) -> _KeyringModule:
        if self._module is not None:
            return self._module
        try:
            module = cast(_KeyringModule, import_module("keyring"))
        except ImportError as error:
            raise SecretResolutionError("OS keyring support is not installed") from error
        self._module = module
        return module

    def resolve(self, reference: SecretReference) -> SecretValue:
        if reference.scheme is not self.scheme:
            raise InvalidSecretReferenceError("secret reference was sent to the wrong provider")
        service, account = reference.locator.split("/", maxsplit=1)
        try:
            value = self._keyring().get_password(service, account)
        except Exception as error:
            raise SecretResolutionError("OS keyring lookup failed") from error
        if value is None:
            raise SecretResolutionError("OS keyring secret is unavailable")
        return SecretValue(value)


class SecretResolver:
    """Dispatch typed references to an explicit provider registry."""

    def __init__(self, providers: Mapping[SecretScheme, SecretProvider]) -> None:
        self._providers = dict(providers)

    @classmethod
    def local(cls, *, file_root: Path) -> SecretResolver:
        return cls(
            {
                SecretScheme.ENV: EnvironmentSecretProvider(),
                SecretScheme.FILE: FileSecretProvider(file_root),
                SecretScheme.KEYRING: KeyringSecretProvider(),
            }
        )

    def resolve(self, reference: SecretReference | str) -> SecretValue:
        parsed = SecretReference.parse(reference) if isinstance(reference, str) else reference
        provider = self._providers.get(parsed.scheme)
        if provider is None:
            raise SecretResolutionError("secret provider is not configured")
        return provider.resolve(parsed)


__all__ = [
    "MAX_SECRET_BYTES",
    "EnvironmentSecretProvider",
    "FileSecretProvider",
    "InvalidSecretReferenceError",
    "KeyringSecretProvider",
    "SecretError",
    "SecretProvider",
    "SecretReference",
    "SecretResolutionError",
    "SecretResolver",
    "SecretScheme",
    "SecretValue",
]
