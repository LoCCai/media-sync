"""Account exclusion and failure cleanup without platform or browser IO."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from media_sync.integrations.mediacrawler.runner import _AccountFileLock


def test_repeated_acquire_cannot_lose_owned_descriptor(tmp_path: Path) -> None:
    owner = _AccountFileLock(tmp_path)
    contender = _AccountFileLock(tmp_path)
    assert owner.acquire()
    descriptor = owner.descriptor
    try:
        assert not owner.acquire()
        assert owner.descriptor == descriptor
        for _ in range(20):
            assert not contender.acquire()
        assert os.fstat(descriptor).st_nlink == 1
    finally:
        owner.release()
    owner.release()
    for _ in range(20):
        assert contender.acquire()
        contender.release()


def test_rejected_hardlink_does_not_hold_a_native_handle(tmp_path: Path) -> None:
    owner = _AccountFileLock(tmp_path)
    target = tmp_path / "target"
    target.write_bytes(b"private-target")
    os.link(target, owner.path)
    assert not owner.acquire()
    assert target.read_bytes() == b"private-target"
    # Windows cannot remove an exclusively open file. This also exercises
    # cleanup of the rejected native HANDLE, not only a false return value.
    owner.path.unlink()
    assert owner.acquire()
    owner.release()


def test_rejected_symlink_is_never_followed(tmp_path: Path) -> None:
    owner = _AccountFileLock(tmp_path)
    target = tmp_path / "target"
    target.write_bytes(b"private-target")
    try:
        owner.path.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    assert not owner.acquire()
    assert target.read_bytes() == b"private-target"


def test_initialization_failure_releases_native_handle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _AccountFileLock(tmp_path)

    def failed_write(*_args):
        raise OSError("synthetic write failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", failed_write)
        assert not owner.acquire()
    assert owner.acquire()
    owner.release()


@pytest.mark.skipif(os.name != "nt", reason="Windows native HANDLE conversion contract")
def test_crt_conversion_failure_closes_native_handle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import msvcrt

    owner = _AccountFileLock(tmp_path)

    def failed_conversion(*_args):
        raise OSError("synthetic CRT conversion failure")

    with monkeypatch.context() as patch:
        patch.setattr(msvcrt, "open_osfhandle", failed_conversion)
        assert not owner.acquire()
    assert owner.acquire()
    owner.release()
