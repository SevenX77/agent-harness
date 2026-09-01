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

    So the join happens HERE, once, and refuses an id that cannot name one
    child. What it checks is exactly the invariant and nothing more: the id
    must be a single path segment. It deliberately does NOT impose a character
    vocabulary — which characters an id may contain is a naming convention of
    whoever minted it, the same reasoning this module already gives for
    refusing to read the storage root out of an id's shape.

    ``ValueError`` because this is a caller-contract violation, not a runtime
    condition the SDK can recover from or report as a run failure — the same
    answer ``_validate_workspace_dir`` gives a relative workspace path.
    """
    if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError(
            f"run_id must name one directory under {root}, not a path: {run_id!r}",
        )
    return root / run_id
