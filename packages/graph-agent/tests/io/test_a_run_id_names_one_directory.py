"""An execution's directory is a CHILD of its root, whatever id the caller minted.

``run_layout``'s first paragraph states the invariant — "one subdirectory per
run" — and the id that names that subdirectory comes from outside the SDK:
``run_skill(thread_id=...)`` and ``resume_skill(run_id=...)`` take it verbatim,
and a host that passes one through from a request has handed the library a
string, not a directory name. ``root / "../.."`` is a perfectly valid ``Path``;
it is just not a subdirectory of anything, and the trace sink, the result
artifacts and the resumed spend ledger all then land somewhere that is not this
run's directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.io.run_layout import run_dir, runs_root


def test_a_plain_id_names_a_child_of_the_root(tmp_path: Path) -> None:
    root = runs_root(tmp_path)

    assert run_dir(root, "9f1c8e2a") == root / "9f1c8e2a"


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        ".",
        "..",
        "../escape",
        "nested/child",
        "/absolute",
    ],
)
def test_an_id_that_is_a_path_is_refused(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError, match="run_id must name one directory"):
        run_dir(runs_root(tmp_path), run_id)


def test_the_refusal_names_the_id_it_refused(tmp_path: Path) -> None:
    """A rejected id has to be visible, or the caller cannot see what it sent."""
    with pytest.raises(ValueError) as excinfo:
        run_dir(runs_root(tmp_path), "../../etc")

    assert "../../etc" in str(excinfo.value)


def test_a_character_vocabulary_is_not_imposed(tmp_path: Path) -> None:
    """Which characters an id may contain belongs to whoever minted it.

    The same reasoning ``run_layout`` already gives for refusing to read the
    storage root out of an id's shape: an id's spelling is a naming convention
    of its minter, so this function checks the ONE thing that is the module's
    own invariant — that the id names a single child — and nothing else.
    """
    root = runs_root(tmp_path)

    assert run_dir(root, "batch-run 3 (retry)") == root / "batch-run 3 (retry)"
