"""Reading a file a person wrote in some other editor.

A skill is authored outside this engine — in Studio, in VS Code, in Notepad —
and what arrives is bytes plus whatever the editor decided to put in front of
them. On Windows that is routinely a UTF-8 byte-order mark (``EF BB BF``):
Notepad writes one by default, and so does PowerShell redirection.

The mark is part of the ENCODING, not of the content. Decoding it as content is
what produced ledger K7: ``GRAPH.md`` began with ``\\ufeff---``, the anchored
frontmatter matcher (``^---``) missed, and Studio drew a skill with zero
phases — no error, no diagnostic, just an empty canvas.

So the mark is removed where bytes become text, once, rather than at each place
that later trips over it. ``graph_assembler`` used to do the latter — a
call-site ``.lstrip("\\ufeff")`` on runtime input files — which is exactly the
shape of the defect: one reader tolerated the mark, its neighbour did not, and
the same file therefore had two readings.

*Borrowed*: Python's own ``utf-8-sig`` codec, which is the standard library's
answer to this and was added for it. It strips only a LEADING mark and only when
one is present, so a file without one decodes identically — and a ``\\ufeff``
occurring anywhere else in the text is left alone, because there it really is
content (a zero-width no-break space).

*Rejected*: ``lstrip("\\ufeff")``, the shape being replaced. It strips a RUN of
marks rather than the single one a signature consists of, so it silently eats
authored content in the one case where the two differ; and being a call-site
fix, it has to be remembered at every reader, which is how the two readings came
about.

This is the read-side half of the repo's encoding rule (``docs/development/
CROSS_PLATFORM.md``): that rule governs what we WRITE (UTF-8, no signature, LF),
and it cannot govern what an outside editor hands us.
"""

from __future__ import annotations

from pathlib import Path


def read_authored_text(path: Path | str) -> str:
    """Decode a file a person may have authored elsewhere, without its signature.

    Use for anything hand-written that the engine reads back: skill markdown,
    validator sources, declared runtime input files. NOT for files the engine
    itself wrote (caches, traces, metrics) — those have no signature to strip and
    reading them says so plainly by using ``utf-8``.
    """
    return Path(path).read_text(encoding="utf-8-sig")
