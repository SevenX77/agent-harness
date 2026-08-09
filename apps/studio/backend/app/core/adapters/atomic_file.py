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
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

#: Windows refuses to rename over a file another handle has open, and Python's
#: ``open()`` for reading does not grant delete-sharing. A reader therefore holds
#: the destination for as long as it takes to read a few hundred bytes, and a
#: publish that lands in that instant raises ``PermissionError`` instead of
#: replacing anything. Waiting out a reader is not the same as retrying a failed
#: write: the document is already complete in the temporary file, and nothing
#: has been shown to anyone yet. The budget is small on purpose — a wait this
#: long means something is holding the file open, which is worth failing over.
_REPLACE_RETRY_DELAYS = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05)


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
        _replace_waiting_out_readers(temp_path, path)
    finally:
        # Only reachable when the write or the rename failed: a successful
        # rename leaves nothing behind. The destination keeps its previous
        # contents, which is the point.
        if temp_path.exists():
            temp_path.unlink()


def read_published_text(path: Path) -> str:
    """Read a file that ``write_text_atomically`` may be republishing right now.

    The rename that publishes a new version briefly makes the destination
    un-openable on Windows, so a reader can meet a transient ``PermissionError``
    on a file that is perfectly fine. Waiting that out is the mirror of the
    writer waiting out a reader, and it is deliberately NOT a retry on bad
    content: text that arrives and does not parse is a corrupt record, and the
    caller must be free to treat it as one.
    """
    for delay in _REPLACE_RETRY_DELAYS:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            time.sleep(delay)
    return path.read_text(encoding="utf-8")


def _replace_waiting_out_readers(temp_path: Path, path: Path) -> None:
    for delay in _REPLACE_RETRY_DELAYS:
        try:
            os.replace(temp_path, path)
            return
        except PermissionError:
            time.sleep(delay)
    # Last attempt outside the loop so a still-blocked destination raises the
    # real error rather than being reported as some invented one.
    os.replace(temp_path, path)


__all__ = ["read_published_text", "write_text_atomically"]
