"""Cohesion plan 方针 4.3 (2026-04-26): a tool reference that
path-arithmetically escapes the SKILL.md's ``base_dir`` (e.g. one
that contains ``..`` segments and slips into ``/etc/passwd``) was
silently accepted by the compile-time tool_paths validator — the
load-time path-anchored resolver later rejected it, so the same
manifest was "valid" at compile and broken at run. Inconsistent
behaviour across the static / dynamic boundary is exactly the kind
of cohesion gap the 2026-04-26 plan exists to close.

Fixed contract: any local tool reference whose ``base_dir / parts``
form does not stay inside ``base_dir`` (after ``Path.resolve()``)
fatals as ``F-tool-path-escape``.
"""
from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill


def _write_host_with_tool_ref(tmp_path: Path, ref: str) -> Path:
    skill = tmp_path / "host" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        "---\n"
        'schema_version: "2.0"\n'
        "name: host\n"
        "description: x\n"
        "type: agent\n"
        "agent_profile:\n"
        "  role: r\n"
        "  goal: g\n"
        f"agent_tools: ['{ref}']\n"
        "---\n",
        encoding="utf-8",
    )
    return skill


def test_escaping_tool_reference_yields_escape_fatal(tmp_path: Path) -> None:
    """A reference whose resolved path falls outside ``base_dir`` must
    fatal with the dedicated ``F-tool-path-escape`` rule, not the
    generic not-found rule. The dedicated rule lets Studio's UI
    distinguish "you wrote something escaping the skill tree" from
    "you typo'd a module name"."""
    # Place a real file outside the host's base_dir so even a
    # path-walking check that ignores escape semantics could be
    # tricked into "found".
    outside = tmp_path / "outside" / "mod.py"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("def fn():\n    pass\n", encoding="utf-8")

    # Use a relative-segment reference that escapes the host's tree.
    # ``..outside.mod.fn`` → ``..outside/mod`` after dot-to-slash —
    # which is below base_dir but contains a leading double-dot
    # segment. We rely on Path.resolve() catching the escape.
    skill = _write_host_with_tool_ref(tmp_path, "..outside.mod.fn")
    result = compile_skill(skill)
    rule_ids = [f.rule_id for f in result.fatals]
    assert "F-tool-path-escape" in rule_ids, (
        "An escaping path must produce F-tool-path-escape; "
        f"got: {rule_ids}"
    )


def test_in_tree_tool_reference_still_validates(tmp_path: Path) -> None:
    """Regression guard: legitimate local refs continue to resolve."""
    skill_dir = tmp_path / "host"
    skill_dir.mkdir()
    (skill_dir / "tools.py").write_text("def fn():\n    pass\n", encoding="utf-8")

    skill = _write_host_with_tool_ref(tmp_path, "tools.fn")
    result = compile_skill(skill)
    fatal_rule_ids = [f.rule_id for f in result.fatals]
    assert "F-tool-path-escape" not in fatal_rule_ids, (
        f"In-tree tool reference must not trip the escape check; got {fatal_rule_ids}"
    )


# Codex review follow-up (2026-04-26): the original 4.3 fix resolved
# ``module_file`` (the no-extension form) to detect ``..`` arithmetic
# escapes, but a symlinked ``tools.py`` inside the skill tree pointing
# OUTSIDE base_dir was still accepted at compile time — only the
# load-time resolver caught the escape via importlib's path anchoring.
# That breaks compile/load consistency. Resolve ``py_file`` and
# ``init_file`` too so symlink escapes also fatal.


def test_symlinked_py_file_escaping_base_dir_fatals(tmp_path: Path) -> None:
    """A ``tools.py`` symlink inside the skill tree pointing outside
    base_dir must trip F-tool-path-escape."""
    # External target the symlink points at.
    external = tmp_path / "outside" / "real_tools.py"
    external.parent.mkdir(parents=True, exist_ok=True)
    external.write_text("def fn():\n    pass\n", encoding="utf-8")

    # Skill tree at <tmp>/host with a tools.py symlink → external.
    host_dir = tmp_path / "host"
    host_dir.mkdir(exist_ok=True)
    symlink = host_dir / "tools.py"
    symlink.symlink_to(external)

    skill = _write_host_with_tool_ref(tmp_path, "tools.fn")
    result = compile_skill(skill)
    rule_ids = [f.rule_id for f in result.fatals]
    assert "F-tool-path-escape" in rule_ids, (
        "A symlinked tools.py pointing outside base_dir must produce "
        f"F-tool-path-escape; got: {rule_ids}"
    )
