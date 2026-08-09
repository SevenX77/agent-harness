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

__all__ = ["PREDICTS_DIRNAME", "RUNS_DIRNAME", "predicts_root", "runs_root"]


def runs_root(workspace_dir: Path) -> Path:
    """The directory that holds one subdirectory per run."""
    return workspace_dir / RUNS_DIRNAME


def predicts_root(workspace_dir: Path) -> Path:
    """The directory that holds one subdirectory per predict."""
    return workspace_dir / PREDICTS_DIRNAME
