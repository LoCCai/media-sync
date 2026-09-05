"""Immutable private credentials use synthetic values in temporary directories."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from media_sync.config import Settings
from media_sync.security.managed_credentials import ManagedCredentialStore, _WindowsPrivacy
from media_sync.security.secrets import (
    MAX_SECRET_BYTES,
    InvalidSecretReferenceError,
    SecretReference,
    SecretResolutionError,
    SecretResolver,
    SecretScheme,
    SecretValue,
)

SENTINEL = "SESSDATA=SYNTHETIC-COOKIE-ONLY==; account=fake"


def test_immutable_versions_private_resolution_and_fresh_process(tmp_path: Path) -> None:
    store = ManagedCredentialStore(tmp_path / "credentials")
    original = store.write(SecretValue(SENTINEL))
    newer = store.write(SecretValue("synthetic=new"))
    assert original != newer and original.scheme is SecretScheme.MANAGED
    assert store.resolve(original).reveal() == SENTINEL
    assert store.resolve(newer).reveal() == "synthetic=new"
    assert original.locator not in repr(original) and original.locator not in str(original)
    resolver = SecretResolver.local(file_root=tmp_path / "read-only", managed_root=store.root)
    assert resolver.resolve(original.serialize()).reveal() == SENTINEL
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; from media_sync.security.secrets import SecretResolver; "
            "r=SecretResolver.local(file_root=Path(sys.argv[1])/'unused',managed_root=Path(sys.argv[1])); "
            "print('ok' if r.resolve(sys.argv[2]).reveal()==sys.stdin.read() else 'bad')",
            str(store.root),
            original.serialize(),
        ],
        input=SENTINEL,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert child.returncode == 0 and child.stdout.strip() == "ok" and child.stderr == ""
    if os.name != "nt":
        assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in store.root.iterdir())


@pytest.mark.parametrize(
    "locator", ["../outside", "/tmp/secret", "C:\\secret", "{00000000-0000-0000-0000-000000000000}", "bad", "a" * 32]
)
def test_managed_reference_has_only_canonical_uuid(locator: str) -> None:
    with pytest.raises(InvalidSecretReferenceError):
        SecretReference.parse(f"managed:{locator}")


def test_no_implicit_managed_root_and_settings_independent_of_secret_mount(tmp_path: Path) -> None:
    settings = Settings(state_dir=tmp_path / "state", secret_file_dir=tmp_path / "mounted", _env_file=None)
    assert settings.resolved_managed_credential_dir == tmp_path / "state" / "credentials"
    resolver = SecretResolver.local(file_root=tmp_path / "mounted")
    with pytest.raises(SecretResolutionError, match="provider is not configured"):
        resolver.resolve(f"managed:{uuid4()}")
    assert not (tmp_path / "mounted").exists()


def test_read_never_creates_root_and_rejects_forged_locator(tmp_path: Path) -> None:
    store = ManagedCredentialStore(tmp_path / "credentials")
    with pytest.raises(SecretResolutionError):
        store.resolve(SecretReference.parse(f"managed:{uuid4()}"))
    assert not store.root.exists()
    with pytest.raises(InvalidSecretReferenceError):
        store.resolve(SecretReference(SecretScheme.MANAGED, "../outside"))


def test_uuid_collision_does_not_overwrite_existing_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    identity = uuid4()
    monkeypatch.setattr("media_sync.security.managed_credentials.uuid4", lambda: identity)
    store = ManagedCredentialStore(tmp_path / "credentials")
    reference = store.write(SecretValue(SENTINEL))
    with pytest.raises(SecretResolutionError):
        store.write(SecretValue("replacement=fake"))
    assert store.resolve(reference).reveal() == SENTINEL
    assert len(list(store.root.iterdir())) == 1


def test_fsync_failure_retains_unreferenced_file_without_exposing_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ManagedCredentialStore(tmp_path / "credentials")

    def failed_sync(_descriptor: int) -> None:
        raise OSError(SENTINEL)

    monkeypatch.setattr("media_sync.security.managed_credentials.os.fsync", failed_sync)
    with pytest.raises(SecretResolutionError) as caught:
        store.write(SecretValue(SENTINEL))
    assert SENTINEL not in str(caught.value)
    assert len(list(store.root.iterdir())) == 1


@pytest.mark.parametrize(
    "replacement", [b"", b"\xff", b"a\0b", b"x" * (MAX_SECRET_BYTES + 1)], ids=["empty", "utf8", "nul", "oversize"]
)
def test_invalid_stored_bytes_fail_closed(tmp_path: Path, replacement: bytes) -> None:
    store = ManagedCredentialStore(tmp_path / "credentials")
    reference = store.write(SecretValue(SENTINEL))
    path = store.root / f"{reference.locator}.secret"
    path.write_bytes(replacement)
    with pytest.raises(SecretResolutionError):
        store.resolve(reference)


def test_hardlinked_version_is_rejected(tmp_path: Path) -> None:
    store = ManagedCredentialStore(tmp_path / "credentials")
    reference = store.write(SecretValue(SENTINEL))
    os.link(store.root / f"{reference.locator}.secret", tmp_path / "extra-link")
    with pytest.raises(SecretResolutionError):
        store.resolve(reference)


def test_symlinked_root_or_version_is_not_followed(tmp_path: Path) -> None:
    original = ManagedCredentialStore(tmp_path / "original")
    reference = original.write(SecretValue(SENTINEL))
    linked = tmp_path / "link"
    try:
        linked.symlink_to(original.root, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation requires a platform privilege")
    with pytest.raises(SecretResolutionError):
        ManagedCredentialStore(linked).resolve(reference)
    with pytest.raises(SecretResolutionError):
        ManagedCredentialStore(linked).write(SecretValue("other=fake"))
    second = original.root / f"{uuid4()}.secret"
    second.symlink_to(original.root / f"{reference.locator}.secret")
    with pytest.raises(SecretResolutionError):
        original.resolve(SecretReference.parse(f"managed:{second.stem}"))


def test_existing_nonprivate_directory_is_not_silently_repermissioned(tmp_path: Path) -> None:
    root = tmp_path / "credentials"
    root.mkdir(mode=0o755)
    if os.name != "nt":
        root.chmod(0o755)
    with pytest.raises(SecretResolutionError):
        ManagedCredentialStore(root).write(SecretValue(SENTINEL))
    assert list(root.iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode qualification; Windows uses a protected DACL")
def test_widened_posix_file_permissions_are_rejected(tmp_path: Path) -> None:
    store = ManagedCredentialStore(tmp_path / "credentials")
    reference = store.write(SecretValue(SENTINEL))
    (store.root / f"{reference.locator}.secret").chmod(0o644)
    with pytest.raises(SecretResolutionError):
        store.resolve(reference)


@pytest.mark.skipif(os.name != "nt", reason="Windows native protected-DACL qualification")
def test_windows_broad_file_ace_is_rejected(tmp_path: Path) -> None:
    store = ManagedCredentialStore(tmp_path / "credentials")
    reference = store.write(SecretValue(SENTINEL))
    path = store.root / f"{reference.locator}.secret"
    completed = subprocess.run(
        ["icacls", str(path), "/grant", "*S-1-1-0:(R)"], capture_output=True, timeout=10, check=False
    )
    assert completed.returncode == 0
    with pytest.raises(SecretResolutionError):
        store.resolve(reference)


@pytest.mark.skipif(os.name != "nt", reason="Windows directory-handle rename exclusion")
def test_windows_pins_root_before_any_secret_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ManagedCredentialStore(tmp_path / "credentials")
    original_create = _WindowsPrivacy.create

    def attempt_replacement(privacy: _WindowsPrivacy, path: Path) -> int:
        with pytest.raises(PermissionError):
            store.root.rename(tmp_path / "unexpected-move")
        return original_create(privacy, path)

    monkeypatch.setattr(_WindowsPrivacy, "create", attempt_replacement)
    reference = store.write(SecretValue(SENTINEL))
    assert store.resolve(reference).reveal() == SENTINEL
    assert not (tmp_path / "unexpected-move").exists()


def test_symlinked_parent_does_not_create_descendants_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "link"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation requires a platform privilege")
    store = ManagedCredentialStore(linked / "new-parent" / "credentials")
    with pytest.raises(SecretResolutionError):
        store.write(SecretValue(SENTINEL))
    assert list(outside.iterdir()) == []
