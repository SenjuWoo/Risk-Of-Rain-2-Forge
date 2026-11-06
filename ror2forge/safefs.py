"""Bounded, race-resistant reads of files that belong to one project.

`project_input()` proves a pathname is inside its project. That check alone is insufficient: between validation and
read a parent directory can be renamed and replaced with a junction, and a hardlink elsewhere has no visible link at
all. This module therefore opens the file once through a platform primitive that cannot follow a link, then proves
from the resulting handle — not from the path string — that the object is the intended project file, and reads a
bounded number of bytes from that same handle.

Windows: CreateFileW with FILE_FLAG_OPEN_REPARSE_POINT, then GetFinalPathNameByHandleW. The kernel resolves the opened
object's true path, so a junction anywhere above it shows up in the answer and the read is refused. The name is never
re-resolved afterwards.
POSIX: a directory-descriptor walk with O_NOFOLLOW and O_DIRECTORY on every component, finishing on the file itself.
Renaming or replacing a parent after a descriptor is open cannot redirect it.

Refusing is the safe outcome: when identity cannot be proven, packaging stops instead of shipping foreign bytes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_FILES = 10_000

_GENERIC_READ = 0x80000000
_SHARE_ALL = 0x00000007
_OPEN_EXISTING = 3
_BACKUP_SEMANTICS = 0x02000000
_OPEN_REPARSE_POINT = 0x00200000
_ATTRIBUTE_REPARSE_POINT = 0x00000400


class Budget:
    """Cumulative quota for one packaging operation, charged before any content is read."""

    def __init__(self, files: int = MAX_FILES, total: int = MAX_TOTAL_BYTES, per_file: int = MAX_FILE_BYTES):
        self.files, self.total, self.per_file = files, total, per_file
        self.seen_files, self.seen_bytes = 0, 0

    def charge(self, size: int, name: str) -> None:
        self.seen_files += 1
        self.seen_bytes += size
        if self.seen_files > self.files:
            raise ValueError(f"Package exceeds {self.files} files; reduce content/ before packaging")
        if size > self.per_file:
            raise ValueError(f"{name} is larger than the {self.per_file // (1024 * 1024)} MiB per-file limit")
        if self.seen_bytes > self.total:
            raise ValueError(f"Package exceeds the {self.total // (1024 * 1024)} MiB total limit")


def _normalised(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))


def _within(root: str, candidate: str) -> bool:
    root, candidate = _normalised(root), _normalised(candidate)
    return candidate == root or candidate.startswith(root.rstrip(os.sep) + os.sep)


def _open_windows(path: Path, root: Path, name: str) -> tuple[int, int]:
    """Open without following a reparse point, then confirm the handle's real path is inside the project."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel32.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]

    class _Info(ctypes.Structure):
        # BY_HANDLE_FILE_INFORMATION: 4-byte attribute field, three FILETIMEs, then seven DWORDs. No padding.
        _fields_ = [("attributes", wintypes.DWORD),
                    ("created", wintypes.DWORD * 2), ("accessed", wintypes.DWORD * 2), ("written", wintypes.DWORD * 2),
                    ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD), ("size_low", wintypes.DWORD),
                    ("links", wintypes.DWORD), ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]

    handle = kernel32.CreateFileW(str(path), _GENERIC_READ, _SHARE_ALL, None, _OPEN_EXISTING,
                                  _BACKUP_SEMANTICS | _OPEN_REPARSE_POINT, None)
    if handle == wintypes.HANDLE(-1).value or handle == -1:
        raise ValueError(f"Cannot open {name} safely: error {ctypes.get_last_error()}")
    try:
        info = _Info()
        if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(info)):
            raise ValueError(f"Cannot inspect {name} safely: error {ctypes.get_last_error()}")
        if info.attributes & _ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"{name} is a link or reparse point; package the real file instead")
        if info.links > 1:
            raise ValueError(f"{name} has multiple hard links; copy the asset into this project instead")
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel32.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise ValueError(f"Cannot resolve {name} safely")
        resolved = buffer.value[4:] if buffer.value.startswith("\\\\?\\") else buffer.value
        if not _within(str(root), resolved):
            raise ValueError(f"{name} resolves outside its project; a directory may have been replaced by a link")
        import msvcrt
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except BaseException:
        kernel32.CloseHandle(handle)
        raise
    return fd, (info.size_high << 32) | info.size_low


def _open_posix(path: Path, root: Path, name: str) -> tuple[int, int]:
    """Walk down from the project root with directory descriptors; no component may be a link."""
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{name} is outside its project") from exc
    if not relative.parts:
        raise ValueError(f"{name} is not a file")
    flags_dir = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory = os.open(root, flags_dir)
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(part, flags_dir, dir_fd=directory)
            os.close(directory)
            directory = next_fd
        fd = os.open(relative.parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
    finally:
        os.close(directory)
    info = os.fstat(fd)
    if getattr(info, "st_nlink", 1) > 1:
        os.close(fd)
        raise ValueError(f"{name} has multiple hard links; copy the asset into this project instead")
    return fd, info.st_size


def read_bounded(path: Path, budget: Budget, name: str, root: Path) -> bytes:
    """Read one project file from a verified handle; `root` is the project boundary it must belong to."""
    path, root = Path(path).resolve(), Path(root).resolve()
    if not _within(str(root), str(path)):
        raise ValueError(f"{name} is outside its project")
    opener = _open_windows if sys.platform == "win32" else _open_posix
    fd, size = opener(path, root, name)
    try:
        if size > budget.per_file:
            raise ValueError(f"{name} is larger than the {budget.per_file // (1024 * 1024)} MiB per-file limit")
        budget.charge(size, name)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(size + 1)
    finally:
        os.close(fd)
    if len(data) != size:
        raise ValueError(f"{name} changed size while it was read; package again")
    return data
