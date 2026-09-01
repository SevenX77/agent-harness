"""Proving a path a CALLER chose stays inside a directory Studio owns.

Several requests let the caller say which file or directory they mean: a batch
run names test inputs inside the skill's ``.workspace/import_files/``, a canvas
save and a relint name the workspace root whose ``GRAPH.md`` they are editing.
Each of those values arrives from outside and ends up in a filesystem call, so
each needs the same proof — and before this module each spelled its own partial
version of it, or none.

Two questions, because the two shapes of caller-supplied path are answered
differently and neither answer covers the other:

- **A NAME joined onto a known directory.** ``WorkspaceEntryName`` is the
  constrained type a request model declares, so a name that could never address
  one entry is refused by the schema before any code runs (FastAPI answers 422
  naming the field). It starts alphanumeric and then allows word characters,
  dots and dashes, which excludes ``/``, ``\\``, ``.`` and ``..`` — the four
  spellings that make a name address something other than a child.
  :func:`resolve_inside` then proves the join actually LANDS inside, because the
  name rule cannot see symlinks: ``escape.json`` is a well-formed name, and if
  it is a link it resolves outside with no ``..`` in the spelling anywhere.
- **An ABSOLUTE path the caller supplies whole.** There is no spelling rule that
  helps — every absolute path is well-formed. The only question is whether it
  lands inside one of the roots Studio actually manages, which is what
  :func:`resolve_within_roots` answers.

*Borrowed*: the two-layer shape of Python's own ``zipfile`` extraction fix
(CVE-2007-4559: ``_sanitize_windows_name`` for the spelling, plus a containment
check on the joined path) and Git's ``verify_path`` — both refuse the dangerous
spellings up front AND check where the result landed, because each layer catches
what the other cannot. *Rejected*: string-prefix comparison
(``str(candidate).startswith(str(root))``), which calls ``/skills-evil`` a child
of ``/skills``; ``Path.is_relative_to`` compares path components instead.

This is the STUDIO side of the rule. The engine states its own inside
``graph_agent.core.topology_projection`` (``resolve_subgraph_child_root``), and
that is not duplication to remove: the engine's rule answers a different
question — whether a path is a legal subgraph child, GRAPH.md and all — and the
module boundary forbids either side importing the other's internals. What the
two share is a three-line predicate, not a decision.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

from pydantic import StringConstraints

#: Start alphanumeric, then word characters, dots and dashes. Anchored so it can
#: be handed to a request model's ``pattern`` (pydantic anchors nothing itself)
#: and to :func:`re.fullmatch` alike.
WORKSPACE_ENTRY_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"

#: Long enough for a descriptive case name, short enough that the name plus its
#: directory prefix stays under the path limits of every host filesystem.
WORKSPACE_ENTRY_NAME_MAX_LENGTH = 100

_WORKSPACE_ENTRY_NAME_RE = re.compile(WORKSPACE_ENTRY_NAME_PATTERN)

#: The type a request model declares for a field that names one workspace entry.
WorkspaceEntryName = Annotated[
    str,
    StringConstraints(
        pattern=WORKSPACE_ENTRY_NAME_PATTERN,
        max_length=WORKSPACE_ENTRY_NAME_MAX_LENGTH,
    ),
]


def is_workspace_entry_name(value: str) -> bool:
    """Whether ``value`` can name one entry, asked without raising.

    For the callers that check a name arriving somewhere a request model cannot
    declare its type — a URL path segment, a field inside a free-form payload —
    and that answer "no" with their own error.
    """
    return bool(
        value
        and len(value) <= WORKSPACE_ENTRY_NAME_MAX_LENGTH
        and _WORKSPACE_ENTRY_NAME_RE.fullmatch(value)
    )


class PathEscapesDirectory(Exception):
    """A resolved path landed outside the directory it was supposed to stay in.

    Raised rather than returned so no caller can reach the file by forgetting to
    check: the only way past these functions is with a path they have vouched
    for.
    """

    def __init__(self, resolved: Path, roots: tuple[Path, ...]) -> None:
        super().__init__(f"path escapes {[str(root) for root in roots]}: {resolved}")
        self.resolved = resolved
        self.roots = roots


def resolve_inside(directory: Path, *segments: str) -> Path:
    """The path ``segments`` name under ``directory``, proven to stay under it.

    ``strict=False`` because the answer must not depend on whether the file
    exists yet — a caller asking "may I read this" and one asking "may I create
    this" are entitled to the same verdict, and a check that only works on
    existing paths silently stops checking the moment it is used for a write.
    Symlinks that DO exist are still followed, which is the case the name rule
    cannot see.
    """
    resolved_directory = directory.resolve(strict=False)
    resolved = resolved_directory.joinpath(*segments).resolve(strict=False)
    if not resolved.is_relative_to(resolved_directory):
        raise PathEscapesDirectory(resolved, (resolved_directory,))
    return resolved


def resolve_within_roots(raw_path: str, roots: Iterable[Path]) -> Path:
    """An absolute path a caller supplied, proven to land inside one of ``roots``.

    Refuses a relative path outright rather than resolving it against the
    process working directory. The caller is naming a place on the user's disk,
    and a relative name would mean "wherever this server happens to be running
    from" — an answer that depends on how the app was launched is not an answer.
    """
    candidate = Path(raw_path.strip()).expanduser()
    if not candidate.is_absolute():
        raise PathEscapesDirectory(candidate, tuple(roots))
    # Resolving IS the check: containment is a fact about the resolved path, so
    # there is no way to establish it without resolving first. A taint scanner
    # sees an untrusted value reaching a path expression and is right about the
    # value and wrong about the expression — nothing is opened here, and the
    # function's only exits are "inside one of `roots`" or a raise.
    # codeql[py/path-injection] this call is the containment check itself; the verdict is below.
    resolved = candidate.resolve(strict=False)
    resolved_roots = tuple(root.resolve(strict=False) for root in roots)
    if not any(resolved.is_relative_to(root) for root in resolved_roots):
        raise PathEscapesDirectory(resolved, resolved_roots)
    return resolved
