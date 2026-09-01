"""Reading a file inside a skill workspace, which a person may have authored elsewhere.

A skill lives in a directory the user owns and edits with whatever they like, so
some of its files arrive with a UTF-8 byte-order mark (bytes ``EF BB BF``) in
front. The mark is part of the ENCODING, not of the content, and decoding it as
content is what produced ledger K7 — a ``GRAPH.md`` beginning ``\\ufeff---``
read as having no frontmatter at all, so Studio drew a skill with zero phases
and reported nothing wrong.

That ledger entry is the evidence this exists for: it is a thing that happened
here, not a thing we expect. Signed files are not the Windows DEFAULT any more
and this module must not be read as claiming they are — current Notepad saves
UTF-8 without one, and Windows PowerShell 5.1's ``>`` writes UTF-16LE, which
``utf-8-sig`` cannot read either and which this module does not attempt to
handle. What still produces the mark is deliberate or incidental rather than
default: Notepad's explicit "UTF-8 with BOM" save option, Windows PowerShell
5.1's ``Out-File``/``Set-Content -Encoding utf8`` (PowerShell 6+ changed that
default to no BOM), editors configured to add one, and spreadsheet "CSV UTF-8"
exports. One user with one of those is enough, and the failure they get names
neither the cause nor the fix.

Two consequences make this sharper than a cosmetic stray character:

- ``json.loads`` does not mis-read a signed file, it refuses it outright
  (``Expecting value: line 1 column 1``), so a signed test input or golden case
  fails in a way that names neither the cause nor the fix.
- The Rust native-fs layer is the sole writer of skill files and drops the mark
  where it decodes (``native_fs.rs::read_workspace_text``). If this side keeps
  it, the two compute different values for :func:`workspace_text_hash` over the
  same file, and every optimistic-lock write on a signed file reports a
  conflict that did not happen.

*Borrowed*: Python's own ``utf-8-sig`` codec, which exists for exactly this and
strips only a LEADING mark. A ``\\ufeff`` anywhere else in the text is left
alone, because there it really is content — a zero-width no-break space.

*Rejected*: ``lstrip("\\ufeff")`` at each parser that trips over it. That is a
call-site fix, so every reader has to remember, and the readers that forget
disagree with the ones that don't — which is how ``runtime_config`` came to
answer both ways twelve lines apart. It also strips a RUN of marks rather than
the single one a signature consists of.

This is the read-side half of ``docs/development/CROSS_PLATFORM.md``: that rule
governs what we WRITE (UTF-8, no signature, LF) and cannot govern what an
outside editor hands us. Twin of ``graph_agent.core.authored_text`` (engine) and
``native_fs.rs::read_workspace_text`` (Rust); each module names the rule once
for itself.
"""

from __future__ import annotations

from pathlib import Path


def read_authored_text(path: Path | str) -> str:
    """Decode a file from a user's skill workspace, without its signature.

    Use for anything that lives in a skill directory: phase markdown, golden
    cases, declared test inputs, ``.workspace`` config. NOT for files Studio
    keeps for itself under the app config directory (settings, indexes, leases,
    run records) — those have no signature to strip, and reading them with plain
    ``utf-8`` is how the code says which kind of file it is holding.
    """
    return Path(path).read_text(encoding="utf-8-sig")
