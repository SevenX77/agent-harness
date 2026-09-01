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
        r"nested\child",
        r"..\escape",
    ],
)
def test_an_id_that_is_a_path_is_refused(tmp_path: Path, run_id: str) -> None:
    """Both separators, on every platform.

    ``\\`` is a legal filename character on Linux, so a platform-native check
    accepts ``..\\escape`` there and refuses it on Windows. A workspace is a
    directory tree that gets copied between machines, so the verdict has to be
    the same on all of them or the invariant holds only until someone moves the
    workspace.
    """
    with pytest.raises(ValueError, match="run_id must name one directory"):
        run_dir(runs_root(tmp_path), run_id)


@pytest.mark.parametrize(
    "run_id",
    ["run\x00id", "run\nid", "run\tid", "\x1brun", "run\x1f"],
)
def test_an_id_containing_a_control_character_is_refused(tmp_path: Path, run_id: str) -> None:
    """A name no host will store is not the name of a subdirectory.

    Windows refuses U+0000..U+001F in a filename outright, and a NUL byte does
    not even reach the syscall — Python raises on the embedded null. Either way
    the run has no directory, which is the invariant broken rather than a
    stylistic complaint about the id.
    """
    with pytest.raises(ValueError, match="run_id must name one directory"):
        run_dir(runs_root(tmp_path), run_id)


@pytest.mark.parametrize("run_id", ["run.", "run ", "run...", "run  ", " "])
def test_an_id_with_a_trailing_dot_or_space_is_refused(tmp_path: Path, run_id: str) -> None:
    """The collision case: TWO ids, ONE directory.

    Windows silently strips trailing dots and spaces when it creates the entry,
    so ``run.`` and ``run`` become the same directory. That is the sharpest form
    of the invariant failing — nothing errors, two runs simply overwrite each
    other's artifacts.
    """
    with pytest.raises(ValueError, match="run_id must name one directory"):
        run_dir(runs_root(tmp_path), run_id)


@pytest.mark.parametrize(
    "run_id",
    [
        "NUL",
        "nul",
        "CON",
        "PRN",
        "AUX",
        "COM1",
        "COM9",
        "LPT1",
        "CONIN$",
        "CONOUT$",
        "NUL.json",
        "com1.trace.jsonl",
        "COM\xb9",
        "nul ",
    ],
)
def test_a_windows_reserved_device_name_is_refused(tmp_path: Path, run_id: str) -> None:
    """The quietest failure of all: the name resolves to a DEVICE.

    ``runs/NUL`` on Windows is not a directory that failed to be created, it is
    the null device — every write succeeds and every byte disappears. The check
    matches the part before the first dot with trailing spaces stripped, because
    ``NUL.json`` is the same device; that rule, and the name list including the
    ``CONIN$``/``CONOUT$`` and superscript ``COM¹`` forms, is CPython 3.13's
    ``ntpath._isreservedname``, which this repo (3.11) cannot import yet.
    """
    with pytest.raises(ValueError, match="run_id must name one directory"):
        run_dir(runs_root(tmp_path), run_id)


@pytest.mark.parametrize(
    "run_id",
    ["a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b"],
)
def test_an_id_containing_a_character_no_host_can_store_is_refused(
    tmp_path: Path,
    run_id: str,
) -> None:
    """Same reason as the control characters, same verdict.

    These seven are legal on Linux and rejected by Windows, so accepting them
    would make a run directory that exists on one host and cannot be opened on
    another — the portability half of "one subdirectory per run".
    """
    with pytest.raises(ValueError, match="run_id must name one directory"):
        run_dir(runs_root(tmp_path), run_id)


@pytest.mark.parametrize(
    "run_id",
    [
        "CONSOLE",
        "NULL",
        "COM0",
        "COM10",
        "LPT0",
        "conference-run",
        "run.name.with.dots",
        "leading space is fine",
        " leading",
    ],
)
def test_a_name_that_merely_looks_reserved_is_allowed(tmp_path: Path, run_id: str) -> None:
    """The refusals are exact, not fuzzy.

    ``CONSOLE`` is not ``CON`` and ``COM10`` is not a device; a rule that
    rejected them would be legislating a vocabulary, which is what this module
    declines to do. A LEADING space is preserved by every host, so it stays
    legal — only trailing ones collide.
    """
    root = runs_root(tmp_path)

    assert run_dir(root, run_id) == root / run_id


def test_the_refusal_names_the_id_it_refused(tmp_path: Path) -> None:
    """A rejected id has to be visible, or the caller cannot see what it sent."""
    with pytest.raises(ValueError) as excinfo:
        run_dir(runs_root(tmp_path), "../../etc")

    assert "../../etc" in str(excinfo.value)


@pytest.mark.parametrize(
    "run_id",
    [
        "batch-run 3 (retry)",
        "运行-2026-09-01",
        "run—em-dash",
        "run·mid·dot",
        "🏃",
        "MiXeD-CaSe",
        "run+plus=equals,comma;semi",
        "run'quote",
        "run#hash%percent&amp",
        "run[bracket]{brace}",
        "run@at!bang~tilde^caret",
    ],
)
def test_a_character_vocabulary_is_not_imposed(tmp_path: Path, run_id: str) -> None:
    """Which characters an id may contain belongs to whoever minted it.

    The same reasoning ``run_layout`` already gives for refusing to read the
    storage root out of an id's shape: an id's spelling is a naming convention of
    its minter. So the refusals above are not a vocabulary — they are the names
    that cannot be one subdirectory on a host this workspace may be opened on.
    Everything a filesystem will store, including every non-ASCII character,
    stays legal.
    """
    root = runs_root(tmp_path)

    assert run_dir(root, run_id) == root / run_id


def test_the_docstring_owns_the_case_folding_caveat(tmp_path: Path) -> None:
    """Two ids differing only in case are ONE directory on Windows and macOS.

    That cannot be judged one id at a time — ``run-A`` is a perfectly good name
    and so is ``run-a``; only the pair is a problem, and this function is never
    shown the pair. So both are accepted here and the caveat is stated in the
    docstring as the minter's responsibility, which is where a rule this
    function structurally cannot enforce has to live.
    """
    root = runs_root(tmp_path)

    assert run_dir(root, "run-A") == root / "run-A"
    assert run_dir(root, "run-a") == root / "run-a"
    assert "case" in (run_dir.__doc__ or "")
