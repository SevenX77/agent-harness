"""Publishing a document must not depend on nobody currently reading it.

Swapping a complete file in with a rename is what keeps a reader from ever
seeing half a document. On Windows that rename is refused while any handle is
open on the destination — unless the handle was opened sharing delete, which
``open()`` never does. So a publisher and a reader that both used the obvious
API would block each other, and one of them would report a permission error on
a file that is entirely healthy. The listing loops in this codebase read these
files constantly, so "currently being read" is the normal case, not the rare one.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest
from app.core.adapters.atomic_file import (
    open_published,
    read_published_text,
    write_text_atomically,
)


def test_a_publish_goes_through_while_a_reader_holds_the_file_open(tmp_path: Path) -> None:
    path = tmp_path / "run_metadata.json"
    write_text_atomically(path, "first")

    with open_published(path) as reader:
        write_text_atomically(path, "second")
        # The open handle keeps showing the version it opened — a whole
        # document, just not the newest one. That is the guarantee: old or new,
        # never a mixture and never a failure.
        assert reader.read() == "first"

    assert read_published_text(path) == "second"


def test_reading_a_file_that_is_not_there_says_so(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_published_text(tmp_path / "never-written.json")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits are not what Windows enforces")
def test_a_published_file_is_readable_only_by_its_owner(tmp_path: Path) -> None:
    """Some of these documents hold API keys, so the mode is part of publishing.

    Asserted here rather than at each call site: a caller that has to remember
    to chmod afterwards is a caller that can forget, and the window between the
    rename and the chmod would be real either way.
    """
    path = tmp_path / "llm_credentials.json"

    write_text_atomically(path, '{"api_key": "secret"}')

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
