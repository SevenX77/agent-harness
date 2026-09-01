"""Where an execution keeps its artifacts inside a workspace.

A workspace holds two kinds of execution, and they do not share a directory.
A **run** is the real thing: it spends tokens, its outputs are what the skill
produced, and it is what gets promoted, compared and resumed. A **predict** is
a rehearsal: it exists to answer "would this graph work", and its artifacts are
worth exactly one look.

Filing them together makes every reader pay for the difference — listing runs
means filtering rehearsals out, clearing rehearsals means being careful not to
delete a run, and the newest directory is whichever kind ran last. Two roots
cost one extra name and remove all of that.

Which root an execution belongs to is decided by the caller that knows the
kind, and carried from there as a plain path. Nothing infers it from the run
id: an id's shape is a naming convention of whoever minted it, and a library
that reads storage layout out of a string is a library that files somebody
else's run in the wrong place the day that convention changes.
"""

from __future__ import annotations

from pathlib import Path

RUNS_DIRNAME = "runs"
PREDICTS_DIRNAME = "predicts"

# The event stream an execution writes inside its own directory. Named here
# because "where does an execution keep its artifacts" is this module's whole
# subject: the sink that opens the file and the runner that has to report the
# file's path after the sink is gone must agree on it, and a second spelling of
# the name is a second answer to the same question.
TRACE_FILENAME = "trace.jsonl"

__all__ = [
    "PREDICTS_DIRNAME",
    "RUNS_DIRNAME",
    "TRACE_FILENAME",
    "predicts_root",
    "run_dir",
    "runs_root",
]


def runs_root(workspace_dir: Path) -> Path:
    """The directory that holds one subdirectory per run."""
    return workspace_dir / RUNS_DIRNAME


def predicts_root(workspace_dir: Path) -> Path:
    """The directory that holds one subdirectory per predict."""
    return workspace_dir / PREDICTS_DIRNAME


#: Names Windows resolves to a DEVICE rather than to a filesystem entry.
#:
#: Lifted from CPython 3.13's ``ntpath._isreservedname`` (the ``CONIN$`` /
#: ``CONOUT$`` entries and the superscript ``COM¹²³`` forms included — Windows
#: treats ``COM¹`` as ``COM1``). Spelled out here rather than imported because
#: this package supports Python 3.11, where ``ntpath.isreserved`` does not exist;
#: when the floor rises to 3.13 this constant and its helper are what to delete.
_WINDOWS_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    | {f"COM{suffix}" for suffix in "123456789\xb9\xb2\xb3"}
    | {f"LPT{suffix}" for suffix in "123456789\xb9\xb2\xb3"}
)

#: Characters Windows refuses in a filename outright (``ntpath._reserved_chars``
#: minus the separators, which are checked separately because their failure is a
#: different one — they make the id a PATH rather than an unstorable name).
_UNSTORABLE_CHARACTERS = frozenset('"*:<>?|')


def run_dir(root: Path, run_id: str) -> Path:
    """The one subdirectory of ``root`` that holds this execution's artifacts.

    "One subdirectory per run" is the invariant this module is FOR, stated in
    its first paragraph — and an id is not obliged to satisfy it. The id is
    minted by whoever called the SDK: ``run_skill(thread_id=...)`` and
    ``resume_skill(run_id=...)`` take it verbatim, and a host that passes one
    through from a request has handed the library a string, not a directory
    name. ``root / "../.."`` is still a valid ``Path``; it is just not a
    subdirectory of anything, and everything downstream — the trace the sink
    opens, the artifacts written beside it, the spend ledger re-read on a
    resume — then lands somewhere that is not this run's directory.

    So the join happens HERE, once. What it refuses is the set of ids for which
    "this names one subdirectory of ``root``" is FALSE, and there are four ways
    for that to happen — worth separating, because only the first is obvious:

    - **It names a path, not a name.** Empty, ``.``, ``..``, or containing either
      separator. Both separators on every platform: ``\\`` is a legal filename
      character on Linux, so a platform-native check would accept ``..\\x``
      there and refuse it on Windows — and a workspace is a directory tree that
      gets copied between machines, so a verdict that changes with the host is a
      verdict that holds only until someone moves the workspace.
    - **No host will store the name.** U+0000..U+001F, and the seven characters
      Windows refuses (``" * : < > ? |``). There is then no subdirectory at all.
    - **Two ids become ONE directory.** A trailing dot or space is silently
      stripped by Windows when it creates the entry, so ``run.`` and ``run`` are
      the same place and the second run overwrites the first's artifacts. This is
      the failure that reports nothing.
    - **The name is a device.** ``runs/NUL`` on Windows is the null device, not a
      directory: writes succeed and the bytes are gone. ``NUL.json`` is the same
      device, which is why the check looks at the part before the first dot.

    That set is a completeness argument, NOT a character vocabulary. Everything a
    filesystem will store stays legal — every non-ASCII character, spaces and
    dots inside the name, mixed case, ``CONSOLE``, ``COM10``. Which characters an
    id may contain is a naming convention of whoever minted it, the same
    reasoning this module already gives for refusing to read the storage root out
    of an id's shape.

    **Not checked, and cannot be:** two ids differing only in case are one
    directory on Windows and on macOS's default filesystem. ``run-A`` is a good
    name and so is ``run-a``; only the PAIR is a problem, and this function is
    never shown the pair. Minting ids that stay distinct under case folding is
    therefore the minter's responsibility — the same rule
    ``docs/development/CROSS_PLATFORM.md`` states for paths in the repo.

    ``ValueError`` because this is a caller-contract violation, not a runtime
    condition the SDK can recover from or report as a run failure — the same
    answer ``_validate_workspace_dir`` gives a relative workspace path.
    """
    if not _names_one_directory(run_id):
        raise ValueError(
            f"run_id must name one directory under {root}, not a path: {run_id!r}",
        )
    return root / run_id


def _names_one_directory(run_id: str) -> bool:
    """Whether ``run_id`` can be one subdirectory on every host we support.

    Split out so :func:`run_dir` reads as "join it or refuse it" and the four
    reasons an id fails sit together, each next to the clause that catches it.
    """
    if not run_id or run_id in {".", ".."}:
        return False
    if "/" in run_id or "\\" in run_id:
        return False
    if Path(run_id).name != run_id:
        # The platform-native form of the same question, kept as well as the
        # explicit separator check because on Windows it also catches the
        # drive-relative spellings (`C:x`) that are neither a path nor a name.
        return False
    if any(character in _UNSTORABLE_CHARACTERS or ord(character) < 32 for character in run_id):
        return False
    if run_id != run_id.rstrip(". "):
        return False
    return run_id.partition(".")[0].rstrip(" ").upper() not in _WINDOWS_DEVICE_NAMES
