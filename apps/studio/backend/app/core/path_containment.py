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
- **An ABSOLUTE path the caller supplies whole.** No spelling rule can decide
  this one — every absolute path is well-formed — so the question is whether it
  lands inside one of the roots Studio actually manages, which is what
  :func:`resolve_within_roots` answers. What CAN be decided lexically there, and
  must be, is whether the path is a local one at all: resolving a UNC name makes
  network requests, so "refuse it" has to be reached before the resolve rather
  than after it. See that function's docstring for the ordering and why.

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
    """A caller-supplied path is not one this code may touch.

    Raised rather than returned so no caller can reach the file by forgetting to
    check: the only way past these functions is with a path they have vouched
    for.

    ``reason`` exists because there are several distinct ways to fail the check
    — empty, not absolute, a UNC or device name, on a volume we do not manage, or
    simply outside every root — and one message covering all of them makes the
    log entry say less than the code knew.
    """

    def __init__(
        self,
        resolved: Path,
        roots: tuple[Path, ...],
        *,
        reason: str = "path is outside every root",
    ) -> None:
        super().__init__(f"{reason}: {resolved} (roots: {[str(root) for root in roots]})")
        self.resolved = resolved
        self.roots = roots
        self.reason = reason


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
        raise PathEscapesDirectory(
            resolved,
            (resolved_directory,),
            reason="name resolves outside the directory it belongs to",
        )
    return resolved


def resolve_within_roots(raw_path: str, roots: Iterable[Path]) -> Path:
    """An absolute path a caller supplied, proven to land inside one of ``roots``.

    Three gates, in this order, and the order is the point: **resolving a path
    is not a free operation**, so everything that can be decided by reading the
    string is decided before anything touches the filesystem.

    1. *Lexically*, before any filesystem call at all: a UNC or device-namespace
       path is refused. ``ntpath.realpath`` walks ``\\\\attacker\\share\\x``
       component by component, and each component is an SMB request that can
       carry an NTLM handshake — so a "refusal" placed after the resolve has
       already reached out to the attacker's host and leaked a credential
       exchange. The verdict for these has to be reached without moving.
    2. The path must be *absolute*. A relative name would mean "wherever this
       server happens to be running from", and an answer that depends on how the
       app was launched is not an answer.
    3. The path's *anchor* must match one of the roots'. On Windows that is the
       drive letter, so a path on some other (possibly mapped-network) drive is
       out before the link-following resolve, not after. On POSIX every absolute
       path anchors at ``/`` and the gate is a no-op — which is correct, not
       vestigial: it is the same question, and there it has one answer.

    Only then is the candidate resolved and its landing place compared against
    the roots. The roots are ours, so resolving THEM is not attacker-reachable.

    *Borrowed*: the "decide what you can lexically, before you touch the
    network" ordering from Go's ``filepath.IsLocal`` and from Windows' own
    guidance on ``\\\\?\\``-prefixed paths (both treat the UNC/device forms as a
    separate kind of name rather than as a path with unusual characters).
    """
    stripped = raw_path.strip()
    if not stripped:
        raise PathEscapesDirectory(Path(), tuple(roots), reason="path is empty")
    _reject_unc_or_device_namespace(stripped, roots)
    # Building the path is not opening it; `expanduser` reads the user's own
    # HOME, never the caller's string. The lexical gate is re-applied to the
    # expanded form for the same reason it ran on the raw one: whichever string
    # we are about to resolve is the one that has to have passed it.
    candidate = Path(stripped).expanduser()  # codeql[py/path-injection]
    _reject_unc_or_device_namespace(str(candidate), roots)
    if not candidate.is_absolute():
        raise PathEscapesDirectory(candidate, tuple(roots), reason="path is not absolute")

    resolved_roots = tuple(root.resolve(strict=False) for root in roots)
    if not any(candidate.anchor == root.anchor for root in resolved_roots):
        raise PathEscapesDirectory(
            candidate,
            resolved_roots,
            reason=f"path is not on a volume we manage (anchor {candidate.anchor!r})",
        )

    # Resolving IS the containment check: containment is a fact about the
    # RESOLVED path, so there is no establishing it without first producing one.
    # By this line the path is local and on one of our own volumes, so following
    # its links reaches this machine's filesystem and nothing else.
    resolved = candidate.resolve(strict=False)  # codeql[py/path-injection]
    if not any(resolved.is_relative_to(root) for root in resolved_roots):
        raise PathEscapesDirectory(resolved, resolved_roots, reason="path is outside every root")
    return resolved


def _reject_unc_or_device_namespace(value: str, roots: Iterable[Path]) -> None:
    """Refuse the two-leading-separator forms, on every platform.

    ``\\\\server\\share`` (UNC), ``\\\\?\\`` (extended-length) and ``\\\\.\\``
    (device namespace) all begin with two separators, and Windows accepts the
    forward-slash spelling of each. Refused on POSIX too, where ``//x`` is a
    legal absolute path: no workspace of ours is ever spelled that way, and a
    rule that answers differently per platform is a rule that cannot be tested
    on one runner and trusted on another.
    """
    normalized = value.replace("\\", "/")
    if normalized.startswith("//"):
        raise PathEscapesDirectory(
            Path(value),
            tuple(roots),
            reason="UNC and device-namespace paths are refused before any filesystem access",
        )
