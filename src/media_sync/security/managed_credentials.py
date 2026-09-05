"""Immutable local credential versions with confined, private storage.

This boundary never deletes or replaces a version: a failed/uncertain database
commit may already reference it. POSIX uses owner-only modes; Windows uses an
explicit protected DACL at creation, not the ineffective POSIX chmod emulation.
"""

from __future__ import annotations

import ctypes
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Any
from uuid import uuid4

from .secrets import MAX_SECRET_BYTES, SecretReference, SecretResolutionError, SecretScheme, SecretValue


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("length", wintypes.DWORD), ("descriptor", ctypes.c_void_p), ("inherit", wintypes.BOOL)]


class _AclSize(ctypes.Structure):
    _fields_ = [("count", wintypes.DWORD), ("used", wintypes.DWORD), ("free", wintypes.DWORD)]


class _Ace(ctypes.Structure):
    _fields_ = [("kind", wintypes.BYTE), ("flags", wintypes.BYTE), ("size", wintypes.WORD), ("mask", wintypes.DWORD)]


class _WindowsPrivacy:
    """Small native ACL boundary; no shell, credentials in argv, or shared ACLs."""

    def __init__(self) -> None:
        loader = getattr(ctypes, "WinDLL", None)
        if not callable(loader):
            raise OSError("managed_security_unavailable")
        self.kernel: Any = loader("kernel32", use_last_error=True)
        self.security: Any = loader("advapi32", use_last_error=True)
        pointer = ctypes.c_void_p
        ppointer = ctypes.POINTER(pointer)
        self.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.LocalFree.argtypes = [pointer]
        self.kernel.LocalFree.restype = pointer
        self.kernel.CreateDirectoryW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(_SecurityAttributes)]
        self.kernel.CreateDirectoryW.restype = wintypes.BOOL
        self.kernel.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(_SecurityAttributes),
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        self.kernel.CreateFileW.restype = wintypes.HANDLE
        self.security.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        self.security.GetTokenInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            pointer,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.security.ConvertSidToStringSidW.argtypes = [pointer, ppointer]
        self.security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ppointer,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.security.GetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            ctypes.c_int,
            wintypes.DWORD,
            ppointer,
            ppointer,
            ppointer,
            ppointer,
            ppointer,
        ]
        self.security.GetNamedSecurityInfoW.restype = wintypes.DWORD
        self.security.GetSecurityDescriptorControl.argtypes = [
            pointer,
            ctypes.POINTER(wintypes.WORD),
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.security.GetAclInformation.argtypes = [pointer, pointer, wintypes.DWORD, ctypes.c_int]
        self.security.GetAce.argtypes = [pointer, wintypes.DWORD, ppointer]
        self.user_sid = self._current_sid()

    def _sid(self, address: object) -> str:
        converted = ctypes.c_void_p()
        if not self.security.ConvertSidToStringSidW(address, ctypes.byref(converted)):
            raise OSError("managed_security_unavailable")
        try:
            return ctypes.wstring_at(converted)
        finally:
            self.kernel.LocalFree(converted)

    def _current_sid(self) -> str:
        token = wintypes.HANDLE()
        if not self.security.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise OSError("managed_security_unavailable")
        try:
            size = wintypes.DWORD()
            self.security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if not 0 < size.value <= 65536:
                raise OSError("managed_security_unavailable")
            buffer = ctypes.create_string_buffer(size.value)
            if not self.security.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                raise OSError("managed_security_unavailable")
            return self._sid(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])
        finally:
            self.kernel.CloseHandle(token)

    def _attributes(self, *, directory: bool) -> tuple[_SecurityAttributes, ctypes.c_void_p]:
        inheritance = "OICI" if directory else ""
        sddl = f"D:P(A;{inheritance};FA;;;{self.user_sid})(A;{inheritance};FA;;;SY)"
        descriptor = ctypes.c_void_p()
        if not self.security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None
        ):
            raise OSError("managed_security_unavailable")
        return _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False), descriptor

    def mkdir(self, path: Path) -> None:
        attributes, descriptor = self._attributes(directory=True)
        try:
            if not self.kernel.CreateDirectoryW(str(path), ctypes.byref(attributes)):
                if getattr(ctypes, "get_last_error", lambda: -1)() == 183:
                    return
                raise OSError("managed_directory_unavailable")
        finally:
            self.kernel.LocalFree(descriptor)

    def create(self, path: Path) -> int:
        import msvcrt

        attributes, descriptor = self._attributes(directory=False)
        try:
            # CREATE_NEW is exclusive; OPEN_REPARSE_POINT prevents following a
            # substituted reparse object. Nothing ever opens a version to edit.
            handle = self.kernel.CreateFileW(str(path), 0x40000000, 0, ctypes.byref(attributes), 1, 0x00200080, None)
            if handle == ctypes.c_void_p(-1).value:
                raise OSError("managed_version_unavailable")
            try:
                open_handle = getattr(msvcrt, "open_osfhandle", None)
                if not callable(open_handle):
                    raise OSError("managed_file_primitives_unavailable")
                return int(open_handle(handle, os.O_WRONLY | getattr(os, "O_BINARY", 0)))
            except BaseException:
                self.kernel.CloseHandle(handle)
                raise
        finally:
            self.kernel.LocalFree(descriptor)

    def pin_directory(self, path: Path) -> int:
        # Excluding FILE_SHARE_DELETE pins the root against rename/replacement
        # for the entire write/read. No managed bytes exist before this lock.
        # GENERIC_READ matters: metadata-only handles do not participate in
        # the filesystem's sharing checks and would still permit a rename.
        handle = self.kernel.CreateFileW(str(path), 0x80020080, 3, None, 3, 0x02200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise OSError("managed_directory_unavailable")
        return int(handle)

    def require_private(self, path: Path) -> None:
        owner, acl, descriptor = (ctypes.c_void_p() for _ in range(3))
        result = self.security.GetNamedSecurityInfoW(
            str(path), 1, 5, ctypes.byref(owner), None, ctypes.byref(acl), None, ctypes.byref(descriptor)
        )
        if result != 0:
            raise OSError("managed_security_unavailable")
        try:
            control, revision = wintypes.WORD(), wintypes.DWORD()
            if (
                not acl.value
                or self._sid(owner) != self.user_sid
                or not self.security.GetSecurityDescriptorControl(
                    descriptor, ctypes.byref(control), ctypes.byref(revision)
                )
                or not control.value & 0x1000  # SE_DACL_PROTECTED: no inherited broad grants.
            ):
                raise OSError("managed_permissions_invalid")
            size = _AclSize()
            if not self.security.GetAclInformation(acl, ctypes.byref(size), ctypes.sizeof(size), 2):
                raise OSError("managed_permissions_invalid")
            user_full_control = False
            for index in range(size.count):
                ace_pointer = ctypes.c_void_p()
                if not self.security.GetAce(acl, index, ctypes.byref(ace_pointer)) or not ace_pointer.value:
                    raise OSError("managed_permissions_invalid")
                ace = ctypes.cast(ace_pointer, ctypes.POINTER(_Ace)).contents
                if ace.kind != 0 or ace.size < 12 or ace.flags & 0x08:  # allow ACE, not inherit-only.
                    raise OSError("managed_permissions_invalid")
                sid = self._sid(ace_pointer.value + 8)
                if sid not in {self.user_sid, "S-1-5-18"}:
                    raise OSError("managed_permissions_invalid")
                if sid == self.user_sid and ace.mask & 0x1F01FF == 0x1F01FF:
                    user_full_control = True
            if not user_full_control:
                raise OSError("managed_permissions_invalid")
        finally:
            self.kernel.LocalFree(descriptor)


def _real_path(path: Path, *, directory: bool) -> os.stat_result:
    opened = path.lstat()
    if (
        (not stat.S_ISDIR(opened.st_mode) if directory else not stat.S_ISREG(opened.st_mode))
        or path.is_symlink()
        or getattr(opened, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        or path.resolve() != path
        or (not directory and opened.st_nlink != 1)
    ):
        raise OSError("managed_path_invalid")
    return opened


def _posix_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        raise OSError("managed_file_primitives_unavailable")
    return value


class ManagedCredentialStore:
    """Resolve only an explicit root and freshly generated opaque version IDs."""

    scheme = SecretScheme.MANAGED

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("managed root must be a Path")
        # Do not resolve away a symlink before validation.
        self.root = Path(os.path.abspath(root.expanduser()))

    @staticmethod
    def _privacy() -> _WindowsPrivacy | None:
        return _WindowsPrivacy() if os.name == "nt" else None

    @staticmethod
    def _private(path: Path, *, directory: bool, privacy: _WindowsPrivacy | None) -> os.stat_result:
        opened = _real_path(path, directory=directory)
        if privacy is not None:
            privacy.require_private(path)
        else:
            get_euid = getattr(os, "geteuid", None)
            if (
                not callable(get_euid)
                or stat.S_IMODE(opened.st_mode) != (0o700 if directory else 0o600)
                or opened.st_uid != get_euid()
            ):
                raise OSError("managed_permissions_invalid")
        return opened

    def _root(self, privacy: _WindowsPrivacy | None, *, create: bool) -> os.stat_result:
        if create:
            pending: list[Path] = []
            ancestor = self.root.parent
            while not ancestor.exists() and not ancestor.is_symlink():
                pending.append(ancestor)
                if ancestor.parent == ancestor:
                    raise OSError("managed_parent_unavailable")
                ancestor = ancestor.parent
            _real_path(ancestor, directory=True)
            for directory in reversed(pending):
                directory.mkdir(mode=0o700, exist_ok=True)
                _real_path(directory, directory=True)
            if privacy is not None:
                privacy.mkdir(self.root)
            else:
                self.root.mkdir(mode=0o700, exist_ok=True)
        return self._private(self.root, directory=True, privacy=privacy)

    @contextmanager
    def _pinned_root(self, privacy: _WindowsPrivacy | None, *, create: bool) -> Iterator[int | None]:
        before = self._root(privacy, create=create)
        if privacy is not None:
            handle = privacy.pin_directory(self.root)
            try:
                after = self._root(privacy, create=False)
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise OSError("managed_root_changed")
                yield None
            finally:
                privacy.kernel.CloseHandle(handle)
        else:
            descriptor = os.open(self.root, os.O_RDONLY | _posix_flag("O_DIRECTORY") | _posix_flag("O_NOFOLLOW"))
            try:
                opened = os.fstat(descriptor)
                if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                    raise OSError("managed_root_changed")
                yield descriptor
            finally:
                os.close(descriptor)

    def write(self, value: SecretValue) -> SecretReference:
        """Durably create an unreferenced version; never overwrite or delete."""

        if not isinstance(value, SecretValue):
            raise SecretResolutionError("managed credential value is invalid")
        try:
            privacy = self._privacy()
            with self._pinned_root(privacy, create=True) as directory_fd:
                reference = SecretReference.parse(f"managed:{uuid4()}")
                name = f"{reference.locator}.secret"
                path = self.root / name
                descriptor = (
                    privacy.create(path)
                    if privacy is not None
                    else os.open(
                        name,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | _posix_flag("O_NOFOLLOW"),
                        0o600,
                        dir_fd=directory_fd,
                    )
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(value.reveal().encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                self._private(path, directory=False, privacy=privacy)
                if directory_fd is not None:
                    os.fsync(directory_fd)
            return reference
        except (OSError, ValueError, UnicodeError):
            raise SecretResolutionError("managed credential could not be saved privately") from None

    def resolve(self, reference: SecretReference) -> SecretValue:
        try:
            checked = SecretReference.parse(reference.serialize())
            if checked.scheme is not self.scheme:
                raise ValueError
            privacy = self._privacy()
            with self._pinned_root(privacy, create=False) as directory_fd:
                name = f"{checked.locator}.secret"
                path = self.root / name
                before = self._private(path, directory=False, privacy=privacy)
                if not 0 < before.st_size <= MAX_SECRET_BYTES:
                    raise ValueError
                descriptor = os.open(
                    path if directory_fd is None else name,
                    os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                with os.fdopen(descriptor, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or (opened.st_dev, opened.st_ino, opened.st_size)
                        != (before.st_dev, before.st_ino, before.st_size)
                        or opened.st_nlink != 1
                    ):
                        raise ValueError
                    raw = stream.read(MAX_SECRET_BYTES + 1)
                self._private(path, directory=False, privacy=privacy)
            if len(raw) != before.st_size:
                raise ValueError
            return SecretValue(raw.decode("utf-8"))
        except (OSError, ValueError, UnicodeError, AttributeError, TypeError):
            raise SecretResolutionError("managed credential is unavailable or not private") from None


__all__ = ["ManagedCredentialStore"]
