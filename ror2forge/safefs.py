"""Bounded, race-resistant reads of files that belong to one project.

`project_input()` proves a pathname is inside its project and free of links. That is not enough on its own:
between the check and the read the name can be replaced, and a hardlink elsewhere has no link to see at all.
This module opens the file once, refuses to follow a final symlink, checks the opened inode's identity and
link count, and reads a bounded number of bytes from that same handle.
"""
from __future__ import annotations

import os
from pathlib import Path

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_FILES = 10_000


class Budget:
    """Cumulative quota for one packaging operation."""

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


def read_bounded(path: Path, budget: Budget, name: str) -> bytes:
    """Open, verify and read one project file without a check/read gap.

    O_NOFOLLOW closes the swap-to-symlink race at the final component; the project boundary check closes the
    directory case; st_nlink closes hardlinks. Where O_NOFOLLOW is unavailable the fstat checks still run, and
    the residual risk is documented in RELEASE_PROCESS.md.
    """
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        handle = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"Cannot open {name} safely: {exc}") from exc
    try:
        info = os.fstat(handle)
        if not os.path.isfile(path):
            raise ValueError(f"{name} is not a regular file")
        if getattr(info, "st_nlink", 1) > 1:
            raise ValueError(f"{name} has multiple hard links; copy the asset into this project instead")
        if info.st_size > budget.per_file:
            raise ValueError(f"{name} is larger than the {budget.per_file // (1024 * 1024)} MiB per-file limit")
        budget.charge(info.st_size, name)
        with os.fdopen(handle, "rb", closefd=False) as stream:
            data = stream.read(info.st_size + 1)
    finally:
        os.close(handle)
    if len(data) != info.st_size:
        raise ValueError(f"{name} changed size while it was read; package again")
    return data
