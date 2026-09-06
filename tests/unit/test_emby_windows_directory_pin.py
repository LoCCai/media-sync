"""Directory pin sharing must not rely on separately opened descendant files."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_sync.exporters.emby import ExportConflictError
from media_sync.exporters.emby import exporter as module

ERROR_CODE = "published_tree_drifted"
_RENAME_CHILD = """
import json, os, sys
try:
    os.rename(sys.argv[1], sys.argv[2])
except OSError as error:
    print(json.dumps({"renamed": False, "winerror": getattr(error, "winerror", None)}))
else:
    print(json.dumps({"renamed": True, "winerror": None}))
"""


class _NativeCall:
    def __init__(self, result: int | None) -> None:
        self.result = result
        self.calls: list[tuple[object, ...]] = []
        self.argtypes: tuple[object, ...] | None = None
        self.restype: object = None

    def __call__(self, *args: object) -> int | None:
        self.calls.append(args)
        return self.result


def _fake_native(monkeypatch: pytest.MonkeyPatch, result: int | None) -> _NativeCall:
    create = _NativeCall(result)
    kernel = SimpleNamespace(CreateFileW=create)

    def load(name: str, *, use_last_error: bool) -> SimpleNamespace:
        assert name == "kernel32" and use_last_error is True
        return kernel

    # WinDLL/get_last_error do not exist on POSIX. The mocked API contract
    # deliberately runs there too; it must not be a Windows-only regression.
    monkeypatch.setattr(module.ctypes, "WinDLL", load, raising=False)
    monkeypatch.setattr(module.ctypes, "get_last_error", lambda: 5, raising=False)
    return create


def test_native_directory_open_requests_minimal_data_read_without_delete_share(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create = _fake_native(monkeypatch, 42)
    target = tmp_path / "directory"

    assert module._open_windows_directory_handle(target) == 42
    assert create.calls == [(str(target), 0x00000001, 0x00000003, None, 3, 0x02200000, None)]
    assert create.restype is ctypes.c_void_p
    assert create.argtypes == (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )


@pytest.mark.parametrize("result", [None, ctypes.c_void_p(-1).value])
def test_native_open_failure_never_retries_with_metadata_only_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, result: int | None
) -> None:
    create = _fake_native(monkeypatch, result)

    with pytest.raises(OSError, match="could not bind existing directory") as caught:
        module._open_windows_directory_handle(tmp_path / "denied")

    assert caught.value.errno == 5
    assert len(create.calls) == 1
    assert create.calls[0][1] == 0x00000001
    assert not (tmp_path / "denied").exists()


def _rename_in_another_process(source: Path, destination: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-c", _RENAME_CHILD, str(source), str(destination)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    return dict(json.loads(result.stdout))


@pytest.mark.skipif(os.name != "nt", reason="Windows native directory sharing exclusion")
@pytest.mark.parametrize("target_kind", ["bound_directory", "parent", "grandparent"])
def test_windows_directory_and_ancestors_cannot_rename_until_pin_closes(tmp_path: Path, target_kind: str) -> None:
    outer = tmp_path / "outer"
    parent = outer / "parent"
    leaf = parent / "leaf"
    leaf.mkdir(parents=True)
    target = {"bound_directory": leaf, "parent": parent, "grandparent": outer}[target_kind]
    destination = tmp_path / "renamed-after-close"

    # No file is opened inside leaf. In particular, a manifest/lock file must
    # not accidentally provide the protection attributed to this directory.
    with module._bind_existing_directory(leaf, error_code=ERROR_CODE) as bound:
        assert bound.windows_handle is not None and bound.descriptor is None
        observed = _rename_in_another_process(target, destination)
        assert observed["renamed"] is False
        assert observed["winerror"] in {5, 32}
        if target_kind == "bound_directory":
            assert observed["winerror"] == 32
        assert target.is_dir() and not destination.exists()

    assert _rename_in_another_process(target, destination) == {"renamed": True, "winerror": None}
    assert destination.is_dir() and not target.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows handle lifetime on exceptional inspection exit")
def test_windows_pin_is_released_after_inspection_exception(tmp_path: Path) -> None:
    target = tmp_path / "bound"
    target.mkdir()
    destination = tmp_path / "released"

    with (
        pytest.raises(ValueError, match="synthetic inspection stop"),
        module._bind_existing_directory(target, error_code=ERROR_CODE),
    ):
        assert _rename_in_another_process(target, destination)["renamed"] is False
        raise ValueError("synthetic inspection stop")

    assert _rename_in_another_process(target, destination)["renamed"] is True


@pytest.mark.skipif(os.name != "nt", reason="Windows minimal pin must preserve ordinary inspection IO")
def test_windows_pin_preserves_directory_listing_reads_and_child_writes(tmp_path: Path) -> None:
    target = tmp_path / "bound"
    target.mkdir()
    original = target / "original.txt"
    original.write_bytes(b"original")

    with module._bind_existing_directory(target, error_code=ERROR_CODE):
        assert sorted(path.name for path in target.iterdir()) == ["original.txt"]
        assert original.read_bytes() == b"original"
        child = target / "new.txt"
        child.write_bytes(b"new")
        assert child.read_bytes() == b"new"


def test_missing_bound_directory_is_never_created(tmp_path: Path) -> None:
    target = tmp_path / "missing"
    with (
        pytest.raises(ExportConflictError, match=ERROR_CODE),
        module._bind_existing_directory(target, error_code=ERROR_CODE),
    ):
        pytest.fail("missing inspection root must not be entered")
    assert not target.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX open directories may rename; identity checks must reject drift")
def test_posix_keeps_descriptor_identity_fence_instead_of_assuming_windows_rename_exclusion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "bound"
    target.mkdir()
    moved = tmp_path / "moved"

    def forbid_windows(_path: Path) -> int:
        pytest.fail("POSIX directory inspection must not call the Windows helper")

    monkeypatch.setattr(module, "_open_windows_directory_handle", forbid_windows)
    descriptor: int | None = None
    with (
        pytest.raises(ExportConflictError, match=ERROR_CODE),
        module._bind_existing_directory(target, error_code=ERROR_CODE) as bound,
    ):
        assert bound.windows_handle is None and bound.descriptor is not None
        descriptor = bound.descriptor
        os.rename(target, moved)
        assert moved.is_dir() and not target.exists()
    assert descriptor is not None
    with pytest.raises(OSError):
        os.fstat(descriptor)
    assert moved.is_dir() and not target.exists()
