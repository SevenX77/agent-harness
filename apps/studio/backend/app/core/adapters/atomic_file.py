"""Publishing a file so no reader ever sees it half-written.

Opening a file in ``"w"`` mode truncates it immediately, so between that moment
and the last byte of the new content the path holds a document nobody wrote. A
reader that arrives in between gets it — and every reader of these files
(listings, watchers, reports) reads them straight off disk with no lock to wait
on. The window is small, which is exactly why the bug it causes shows up as an
occasional missing row rather than an obvious failure.

Writing the content into a sibling temporary file and renaming it over the
destination closes the window: the rename replaces one complete document with
another in a single step, so a reader sees the old one or the new one and never
anything in between.

That story is only true if the rename can happen WHILE someone is reading —
which is the whole point, because in this codebase "someone is reading" is the
normal state, not the rare one. POSIX gives it for free. Windows gives it only
if both sides ask, and neither of the obvious APIs asks:

* a handle from ``open()`` does not share delete, so it blocks any rename over
  the file it holds;
* ``os.replace`` calls ``MoveFileExW``, which refuses with ``ACCESS_DENIED``
  when the destination has any handle open at all — sharing delete is not
  enough for it.

So on Windows this module opens readers with ``FILE_SHARE_DELETE`` and renames
with ``FileRenameInfoEx`` + ``FILE_RENAME_FLAG_POSIX_SEMANTICS``, which is the
one Win32 call that means what ``rename(2)`` means. Readers holding the file
keep reading the version they opened; the publisher never waits for them.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


def write_text_atomically(path: Path, text: str) -> None:
    """Replace ``path``'s contents with ``text`` in one observable step.

    The temporary file is created in the destination's own directory because a
    rename is only atomic within a filesystem, and a system temp dir is often a
    different one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as temp_file:
            temp_file.write(text)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        _rename_over(temp_path, path)
    finally:
        # Only reachable when the write or the rename failed: a successful
        # rename leaves nothing behind. The destination keeps its previous
        # contents, which is the point.
        if temp_path.exists():
            temp_path.unlink()


def read_published_text(path: Path) -> str:
    """Read one whole document published by :func:`write_text_atomically`."""
    with open_published(path) as file:
        return file.read()


if sys.platform == "win32":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _GENERIC_READ = 0x8000_0000
    _DELETE = 0x0001_0000
    _FILE_SHARE_READ = 0x0000_0001
    _FILE_SHARE_WRITE = 0x0000_0002
    _FILE_SHARE_DELETE = 0x0000_0004
    _SHARE_EVERYTHING = _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x0000_0080
    _INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
    _FILE_RENAME_INFO_EX = 22
    _RENAME_REPLACE_IF_EXISTS = 0x0000_0001
    _RENAME_POSIX_SEMANTICS = 0x0000_0002

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    _kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL

    def _open_handle(path: Path, access: int) -> int:
        handle: int = _kernel32.CreateFileW(
            str(path),
            access,
            _SHARE_EVERYTHING,
            None,
            _OPEN_EXISTING,
            _FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if handle == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def _rename_over(source: Path, destination: Path) -> None:
        """Rename ``source`` onto ``destination`` the way ``rename(2)`` does.

        Renaming requires DELETE access on the file being renamed, which is why
        the source is opened at all; the rename itself is one call and either
        happens or does not.
        """
        name = os.path.abspath(destination)
        # FileName is a variable-length array, so the struct is shaped per call.
        # FileNameLength counts BYTES and excludes the terminator.
        class _RenameInfo(ctypes.Structure):
            _fields_ = (
                ("Flags", wintypes.DWORD),
                ("RootDirectory", wintypes.HANDLE),
                ("FileNameLength", wintypes.DWORD),
                ("FileName", ctypes.c_wchar * (len(name) + 1)),
            )

        info = _RenameInfo(
            _RENAME_REPLACE_IF_EXISTS | _RENAME_POSIX_SEMANTICS,
            None,
            len(name) * ctypes.sizeof(ctypes.c_wchar),
            name,
        )
        handle = _open_handle(source, _DELETE)
        try:
            renamed = _kernel32.SetFileInformationByHandle(
                handle,
                _FILE_RENAME_INFO_EX,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not renamed:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            _kernel32.CloseHandle(handle)

    @contextmanager
    def open_published(path: Path) -> Iterator[IO[str]]:
        """Open ``path`` for reading without standing in a publisher's way.

        Sharing delete is what lets the publisher's rename go through while this
        handle is open. The handle keeps showing the version it opened, so the
        reader still gets one whole document — just not the newest one.
        """
        handle = _open_handle(path, _GENERIC_READ)
        try:
            descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY)
        except OSError:
            _kernel32.CloseHandle(handle)
            raise
        # From here the descriptor owns the handle: closing the file closes it.
        with os.fdopen(descriptor, encoding="utf-8") as file:
            yield file

else:

    def _rename_over(source: Path, destination: Path) -> None:
        os.replace(source, destination)

    @contextmanager
    def open_published(path: Path) -> Iterator[IO[str]]:
        """Open ``path`` for reading; POSIX renames never disturb an open file."""
        with path.open(encoding="utf-8") as file:
            yield file


__all__ = ["open_published", "read_published_text", "write_text_atomically"]
