"""The design-doc standard existed and nobody followed it.

``docs/development/design-doc-standards/`` has defined how a design document is
supposed to look — its file-level status machine, its carrier roles — since
before this test existed. But no project rule entry point (``AGENTS.md`` /
``CLAUDE.md``) ever pointed at it, so nothing ever enforced it, and a quarter
of the ``status:`` values actually written across ``docs/`` drifted outside the
old four-state machine (``drafted`` / ``FROZEN`` / ``superseded`` /
``deprecated``): ``audited-ready``, ``Living``/``active``, ``retired`` were
already real, established usage — the standard just hadn't caught up to them.
Meanwhile the standard's own three files never carried the frontmatter they
prescribe for everyone else.

This module is the machine gate for the updated standard
(``docs/development/design-doc-standards/01-writing-standard.md`` §1.1/§1.2):

* Gate 1 — every ``status:`` value actually written anywhere under ``docs/``
  must resolve (after stripping its parenthetical annotation) to the closed
  state set. A rogue value here is exactly the drift that made the standard
  look optional.
* Gate 2 — every document under the two directories that are authoritative by
  construction (the standard itself, and the Studio MVP1 design body) must
  declare which of the standard's carrier roles it plays. Without this, a
  reader has no way to tell "this is the authority" from "this is a
  navigational summary of it" without reading the whole document.
* Gate 3 — a document that declares itself a ``summary`` must name the file
  that is actually authoritative, and that file must exist. This is the fix
  for the exact failure mode that happened on 2026-08-23:
  ``01_workflows/00_settings.md`` names its own authority
  (``00_settings-ux-spec.md``) in prose, in the middle of the document, where a
  reader who stops at the summary has already missed it — and did.
* Gate 4 — a document's frontmatter must not still contain one of the literal
  placeholder tokens copied out of the standard's own templates (``<commit>``,
  ``<milestone>``, …). That is what an abandoned copy-paste of the template
  looks like; ``docs/development/design-doc-standards/example/`` is exempt
  because showing the placeholder *is* its job.

Each gate is written against the real repository tree (not a fixture), because
the defect these gates were built to catch is a specific, already-diagnosed
state of that real tree — a fixture would validate the checker in the
abstract, not whether the actual corpus was fixed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
DOCS_ROOT = REPO_ROOT / "docs"

#: A YAML frontmatter scalar assignment: ``key: value`` at the start of a
#: line, inside the frontmatter block. Good enough for the fields this module
#: reads (``status`` / ``role`` / ``authority``) — none of them span lines.
_STATUS_LINE = re.compile(r"^status:\s*(.+)$")
_ROLE_LINE = re.compile(r"^role:\s*(.+)$")
_AUTHORITY_LINE = re.compile(r"^authority:\s*(.+)$")

#: Splits a status value from its parenthetical annotation. Both ASCII ``(``
#: and fullwidth ``（`` show up across the corpus (the fullwidth form is the
#: convention in Chinese prose), so both are recognized.
_PAREN_SPLIT = re.compile(r"[（(]")

#: The file-level status machine, per ``01-writing-standard.md`` §1.1.
#: ``FROZEN`` stays uppercase by design — it is the one state with a machine
#: lock (a SHA-256 hash table) behind it, and the shouting case is the visual
#: flag for that. Every other state is free-text lowercase-kebab.
CLOSED_STATUS_SET = frozenset(
    {
        "drafted",
        "audited-ready",
        "FROZEN",
        "superseded",
        "retired",
        "living",
    }
)

#: The carrier roles a document can declare itself as, per
#: ``01-writing-standard.md`` §0. ``index`` is deliberately narrow: it means
#: the axis-③ design-unit hub specifically (``DESIGN_UNITS_INDEX.md``), not
#: "any document with a table of contents" — a plain navigational TOC (a
#: directory README, a workflow-node listing) is ``guide``.
CLOSED_ROLE_SET = frozenset(
    {
        "workflow-record",
        "baseline",
        "alignment",
        "index",
        "summary",
        "guide",
    }
)

#: Directories where the standard is authoritative by construction — the
#: standard's own text, and the Studio MVP1 design body — so every document in
#: them must declare its role. Other directories (engine/gateway mvp1, the
#: rest of docs/development/) are not covered by this gate yet; backfilling
#: them is future work, not something this PR does in bulk (405 documents).
ROLE_REQUIRED_ROOTS: tuple[Path, ...] = (
    DOCS_ROOT / "development" / "design-doc-standards",
    DOCS_ROOT / "studio" / "mvp1",
)

#: The example/ directory's entire purpose is to show what the templates in
#: 01-writing-standard.md look like, placeholder tokens included — so those
#: placeholders are not a defect there the way they would be anywhere else.
EXAMPLE_ROOT = DOCS_ROOT / "development" / "design-doc-standards" / "example"

#: Placeholder tokens copied verbatim out of the templates in
#: ``01-writing-standard.md`` §3 (workflow), §4 (baseline), §5 (alignment). A
#: real document that still contains one of these copy-pasted the template and
#: never filled it in. This is a denylist of the standard's own literal
#: placeholder strings rather than a generic ``<...>`` regex on purpose: a
#: generic regex also matches legitimate prose that happens to use angle
#: brackets for a code/path variable, e.g. ``runs/<run_id>`` in
#: ``docs/engine/mvp1/01-contract/01-physical-layout/baseline.md`` — that is
#: real content, not an abandoned placeholder, and must not be flagged.
TEMPLATE_PLACEHOLDERS: tuple[str, ...] = (
    "<Node N>",
    "<设计决策旅程步骤>",
    "<链接>",
    "<模块路径>",
    "<commit>",
    "<一句话状态>",
    "<milestone>",
    "<文件:符号名 为主、行号辅,如 core/x.py:fn>",
    "<unit-a>",
    "<状态>",
    "<模块>",
    "<架构总览§x>",
    "<示例>",
)


def _frontmatter_lines(path: Path) -> list[str] | None:
    """The lines strictly between the opening and closing ``---`` fence.

    Returns ``None`` when the file has no real top-of-file frontmatter block.
    This deliberately does not look inside fenced code examples elsewhere in a
    file — ``01-writing-standard.md`` §4/§5 embed ``---``-delimited template
    examples inside ` ```markdown ` fences partway through the document, and
    those are illustrations of what other files should contain, not this
    file's own frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index]
    return None


def _first_match(lines: list[str], pattern: re.Pattern[str]) -> str | None:
    for line in lines:
        matched = pattern.match(line.strip())
        if matched:
            return matched.group(1).strip()
    return None


def _normalize_status(raw: str) -> str:
    """Strip the parenthetical annotation, keeping only the state word."""
    return _PAREN_SPLIT.split(raw.strip(), maxsplit=1)[0].strip()


def _all_docs() -> list[Path]:
    return sorted(DOCS_ROOT.rglob("*.md"))


def _relpath(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _placeholder_matches(block: str) -> list[str]:
    """Which known template placeholder tokens (if any) appear in ``block``."""
    return [token for token in TEMPLATE_PLACEHOLDERS if token in block]


# ---------------------------------------------------------------------------
# Unit tests for the parsing helpers
# ---------------------------------------------------------------------------


def test_frontmatter_lines_returns_none_without_a_leading_fence(tmp_path: Path) -> None:
    doc = tmp_path / "no-frontmatter.md"
    doc.write_text("# Title\n\nstatus: drafted\n", encoding="utf-8")

    assert _frontmatter_lines(doc) is None


def test_frontmatter_lines_returns_none_when_the_fence_never_closes(tmp_path: Path) -> None:
    doc = tmp_path / "unterminated.md"
    doc.write_text("---\nstatus: drafted\n\n# Title\n", encoding="utf-8")

    assert _frontmatter_lines(doc) is None


def test_frontmatter_lines_does_not_reach_into_a_later_code_fence_example(tmp_path: Path) -> None:
    """The exact shape of 01-writing-standard.md §4: a template example is
    delimited by ``---`` too, but it is not this file's own frontmatter."""
    doc = tmp_path / "standard-with-embedded-template.md"
    doc.write_text(
        "# A standard\n\n## Template\n```markdown\n---\nstatus: drafted（<一句话状态>）\n---\n```\n",
        encoding="utf-8",
    )

    assert _frontmatter_lines(doc) is None


def test_normalize_status_strips_ascii_and_fullwidth_parens() -> None:
    assert _normalize_status("FROZEN（已锁）") == "FROZEN"
    assert _normalize_status("drafted (in progress)") == "drafted"
    assert _normalize_status("living") == "living"


# ---------------------------------------------------------------------------
# Gate 1 — every status: value resolves into the closed state set
# ---------------------------------------------------------------------------


def test_every_status_value_is_in_the_closed_state_set() -> None:
    violations: list[str] = []
    for doc in _all_docs():
        frontmatter = _frontmatter_lines(doc)
        if frontmatter is None:
            continue
        raw = _first_match(frontmatter, _STATUS_LINE)
        if raw is None:
            continue
        normalized = _normalize_status(raw)
        if normalized not in CLOSED_STATUS_SET:
            violations.append(
                f"{_relpath(doc)}: status: {raw!r} normalizes to {normalized!r}, "
                f"which is not in {sorted(CLOSED_STATUS_SET)}"
            )

    assert not violations, (
        "docs/development/design-doc-standards/01-writing-standard.md §1.1 defines the "
        "closed status set; fix these documents' status: values (keep the parenthetical "
        "annotation, only the state word must change):\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Gate 2 — role: is present and closed-set inside the two priority roots
# ---------------------------------------------------------------------------


def _priority_docs() -> list[Path]:
    return [doc for doc in _all_docs() if any(doc.is_relative_to(root) for root in ROLE_REQUIRED_ROOTS)]


def test_priority_roots_are_non_empty() -> None:
    """Guards against the gate silently passing because nothing matched."""
    assert len(_priority_docs()) > 50


def test_every_priority_document_declares_a_closed_set_role() -> None:
    violations: list[str] = []
    for doc in _priority_docs():
        frontmatter = _frontmatter_lines(doc)
        role = _first_match(frontmatter, _ROLE_LINE) if frontmatter is not None else None
        if role is None:
            violations.append(f"{_relpath(doc)}: missing role: frontmatter field")
        elif role not in CLOSED_ROLE_SET:
            violations.append(f"{_relpath(doc)}: role: {role!r} is not in {sorted(CLOSED_ROLE_SET)}")

    assert not violations, (
        "docs/development/design-doc-standards/ and docs/studio/mvp1/ are the authoritative "
        "roots; every document in them must declare which carrier role it plays "
        "(01-writing-standard.md §0):\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Gate 3 — role: summary must name an authority that actually exists
# ---------------------------------------------------------------------------


def test_summary_role_names_an_authority_file_that_exists() -> None:
    violations: list[str] = []
    for doc in _all_docs():
        frontmatter = _frontmatter_lines(doc)
        if frontmatter is None:
            continue
        role = _first_match(frontmatter, _ROLE_LINE)
        if role != "summary":
            continue

        authority = _first_match(frontmatter, _AUTHORITY_LINE)
        if not authority:
            violations.append(f"{_relpath(doc)}: role: summary but no authority: pointer")
            continue

        target = (doc.parent / authority).resolve()
        if not target.is_file():
            violations.append(
                f"{_relpath(doc)}: authority: {authority!r} does not resolve to an existing file (resolved to {target})"
            )

    assert not violations, (
        "a document that says it is only a summary must name the file a reader has to follow "
        "for the real answer, and that file must exist — this is the exact gap that let "
        "01_workflows/00_settings.md's authority pointer sit unenforced in prose:\n" + "\n".join(violations)
    )


def test_at_least_one_real_summary_role_exists() -> None:
    """Guards against gate 3 passing only because nothing ever uses role: summary."""
    summaries = []
    for doc in _all_docs():
        frontmatter = _frontmatter_lines(doc)
        if frontmatter is None:
            continue
        if _first_match(frontmatter, _ROLE_LINE) == "summary":
            summaries.append(doc)

    assert summaries, "expected at least one document (00_settings.md) to declare role: summary"


# ---------------------------------------------------------------------------
# Gate 4 — no leftover template placeholders in real frontmatter
# ---------------------------------------------------------------------------


def test_placeholder_detector_flags_a_known_template_token() -> None:
    """Proves the detector has real bite, independent of whether today's
    corpus happens to contain a live violation (it currently does not — see
    the module docstring's Gate 4 note)."""
    block = "module: <模块路径>\ndoc: baseline\nstatus: drafted（现状对齐 pinned 代码 <commit>；<一句话状态>）"

    assert _placeholder_matches(block) == ["<模块路径>", "<commit>", "<一句话状态>"]


def test_placeholder_detector_does_not_flag_incidental_angle_bracket_prose() -> None:
    """The false positive a generic ``<...>`` regex would produce: real prose
    using angle brackets for a code/path variable, not a leftover template
    fill-in. Exact shape of
    docs/engine/mvp1/01-contract/01-physical-layout/baseline.md's status line."""
    block = "status: audited-ready（现状对齐 WS-E7:skill 树按 loader 校验；run/predict 写 runs/<run_id>；）"

    assert _placeholder_matches(block) == []


def test_frontmatter_has_no_unfilled_template_placeholder() -> None:
    violations: list[str] = []
    for doc in _all_docs():
        if doc.is_relative_to(EXAMPLE_ROOT):
            continue
        frontmatter = _frontmatter_lines(doc)
        if frontmatter is None:
            continue
        block = "\n".join(frontmatter)
        for token in _placeholder_matches(block):
            violations.append(f"{_relpath(doc)}: frontmatter still contains template placeholder {token!r}")

    assert not violations, (
        "these documents still carry a literal placeholder token copied from a "
        "01-writing-standard.md template and never filled in:\n" + "\n".join(violations)
    )


def test_the_example_directory_is_exempt_from_the_placeholder_gate() -> None:
    """example/ exists specifically to show the templates with placeholders
    still in place; that is not the defect gate 4 exists to catch."""
    example_docs = [doc for doc in _all_docs() if doc.is_relative_to(EXAMPLE_ROOT)]
    assert example_docs, "expected docs/development/design-doc-standards/example/ to contain documents"

    for doc in example_docs:
        frontmatter = _frontmatter_lines(doc)
        assert frontmatter is not None, f"{_relpath(doc)}: expected the example to carry real frontmatter"
        block = "\n".join(frontmatter)
        assert any(token in block for token in TEMPLATE_PLACEHOLDERS), (
            f"{_relpath(doc)}: expected this example to still demonstrate a placeholder token"
        )
