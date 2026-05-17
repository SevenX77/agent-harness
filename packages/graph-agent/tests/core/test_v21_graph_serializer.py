from __future__ import annotations

import difflib
import shutil
from pathlib import Path

import pytest
from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_serializer import serialize_graph
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import GraphManifest, GraphPhaseRef

REPO_ROOT = Path(__file__).resolve().parents[4]
CANVAS_SERIALIZER_FIXTURES = (
    REPO_ROOT / "packages" / "graph-agent" / "tests" / "fixtures" / "canvas_serializer"
)
FAKE_CANVAS_FANOUT_ROOT = (
    REPO_ROOT / "packages" / "graph-agent" / "tests" / "fixtures" / "fake_canvas_fanout"
)
REAL_V21_SKILL_ROOTS = tuple(
    path.parent
    for path in sorted((REPO_ROOT / "skills").glob("*/GRAPH.md"))
    if 'schema_version: "2.1"' in path.read_text(encoding="utf-8")
)
CANVAS_DOD_MATRIX_ROOTS = (
    *REAL_V21_SKILL_ROOTS,
    FAKE_CANVAS_FANOUT_ROOT,
)


def _skill_graph(skill: str) -> tuple[GraphManifest, str]:
    root = REPO_ROOT / "skills" / skill
    return compile_skill(root, cache=False).manifest, (root / "GRAPH.md").read_text(
        encoding="utf-8"
    )


def _fixture_graph(name: str) -> tuple[GraphManifest, str]:
    root = CANVAS_SERIALIZER_FIXTURES / name
    return compile_skill(root, cache=False).manifest, (root / "GRAPH.md").read_text(
        encoding="utf-8"
    )


def _copy_skill_with_graph(root: Path, graph_text: str, tmp_path: Path) -> Path:
    copied = tmp_path / root.name
    shutil.copytree(root, copied)
    (copied / "GRAPH.md").write_text(graph_text, encoding="utf-8")
    return copied


def _compile_graph_for_serializer(root: Path) -> GraphManifest:
    return SkillLoader(validate_context_writes=False).compile_skill(root).manifest


def _line_diff_count(before: str, after: str) -> int:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    return sum(1 for old, new in zip(before_lines, after_lines, strict=False) if old != new) + abs(
        len(after_lines) - len(before_lines)
    )


def _diff_changed_lines(before: str, after: str) -> tuple[int, int]:
    diff = difflib.unified_diff(
        before.splitlines(),
        after.splitlines(),
        lineterm="",
    )
    removed = 0
    added = 0
    for line in diff:
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("-"):
            removed += 1
        elif line.startswith("+"):
            added += 1
    return removed, added


def _build_manifest_with_phases(phases: list[tuple[str, list[str]]]) -> GraphManifest:
    return GraphManifest(
        name="footer-ordering",
        phases=[
            GraphPhaseRef(id=phase_id, src=f"phases/{phase_id}", depends_on=depends_on)
            for phase_id, depends_on in phases
        ],
    )


@pytest.mark.parametrize(
    "root",
    CANVAS_DOD_MATRIX_ROOTS,
    ids=lambda root: (
        "skill:" + root.name if root.parent.name == "skills" else "fixture:" + root.name
    ),
)
class TestCanvasV2SerializerDoDMatrix:
    def test_parse_serialize_parse_equivalence(self, root: Path, tmp_path: Path) -> None:
        manifest = _compile_graph_for_serializer(root)
        original = (root / "GRAPH.md").read_text(encoding="utf-8")
        serialized = serialize_graph(manifest, original)

        reparsed = _compile_graph_for_serializer(_copy_skill_with_graph(root, serialized, tmp_path))

        assert reparsed.model_dump() == manifest.model_dump()

    def test_serialize_is_byte_idempotent(self, root: Path, tmp_path: Path) -> None:
        manifest = _compile_graph_for_serializer(root)
        original = (root / "GRAPH.md").read_text(encoding="utf-8")
        first = serialize_graph(manifest, original)
        reparsed = _compile_graph_for_serializer(_copy_skill_with_graph(root, first, tmp_path))

        assert serialize_graph(reparsed, first) == first


def test_single_phase_graph_round_trips_byte_exact() -> None:
    manifest, original = _skill_graph("hello-world")

    assert serialize_graph(manifest, original) == original


def test_serial_graph_round_trips_byte_exact() -> None:
    manifest, original = _skill_graph("global-synthesis")

    assert serialize_graph(manifest, original) == original


def test_fanout_graph_round_trips_byte_exact() -> None:
    root = REPO_ROOT / "packages" / "graph-agent" / "tests" / "fixtures" / "fake_canvas_fanout"
    manifest = compile_skill(root, cache=False).manifest
    original = (root / "GRAPH.md").read_text(encoding="utf-8")

    assert serialize_graph(manifest, original) == original


def test_depends_on_change_only_rewrites_target_phase_line() -> None:
    root = FAKE_CANVAS_FANOUT_ROOT
    manifest = compile_skill(root, cache=False).manifest
    original = (root / "GRAPH.md").read_text(encoding="utf-8")
    mutated = manifest.model_copy(
        update={
            "phases": [
                phase.model_copy(update={"depends_on": ["prepare", "branch_a"]})
                if phase.id == "branch_b"
                else phase
                for phase in manifest.phases
            ]
        }
    )

    serialized = serialize_graph(mutated, original)

    assert _line_diff_count(original, serialized) == 1
    assert _diff_changed_lines(original, serialized) == (1, 1)
    assert (
        '<phase id="branch_b" src="phases/branch_b" depends_on="prepare,branch_a" />' in serialized
    )
    assert 'schema_version: "2.1"' in serialized
    assert '<input src="io/inputs.json" />' in serialized
    assert '<output src="io/outputs.json" />' in serialized


def test_new_phase_appends_one_phase_line() -> None:
    manifest, original = _skill_graph("hello-world")
    new_phase = GraphPhaseRef(id="review", src="phases/review", depends_on=["greet"])
    mutated = manifest.model_copy(update={"phases": [*manifest.phases, new_phase]})

    serialized = serialize_graph(mutated, original)

    assert serialized.startswith(original)
    assert serialized.count("\n") == original.count("\n") + 1
    assert _diff_changed_lines(original, serialized) == (0, 1)
    assert serialized.endswith('<phase id="review" src="phases/review" depends_on="greet" />\n')


def test_serialize_new_phase_inserts_before_footer_comment() -> None:
    original = """---
schema_version: "2.1"
---
<input src="io/inputs.py:Req" />
<output src="io/outputs.py:Res" />
<phase id="setup" src="phases/setup" depends_on="" mode="logic" />

<!-- footer: maintained by Canvas -->
"""
    manifest = _build_manifest_with_phases([("setup", []), ("new_phase", ["setup"])])

    result = serialize_graph(manifest, original)

    assert result.index('id="new_phase"') < result.index("<!-- footer")


def test_serialize_new_phase_no_footer_appends_at_end() -> None:
    original = """---
schema_version: "2.1"
---
<input src="io/inputs.py:Req" />
<output src="io/outputs.py:Res" />
<phase id="setup" src="phases/setup" depends_on="" mode="logic" />
"""
    manifest = _build_manifest_with_phases([("setup", []), ("new_phase", ["setup"])])

    result = serialize_graph(manifest, original)

    assert 'id="new_phase"' in result
    assert result.endswith('<phase id="new_phase" src="phases/new_phase" depends_on="setup" />\n')


def test_serialize_no_additions_preserves_footer() -> None:
    original = """---
schema_version: "2.1"
---
<input src="io/inputs.py:Req" />
<output src="io/outputs.py:Res" />
<phase id="setup" src="phases/setup" depends_on="" mode="logic" />

<!-- footer comment -->
"""
    manifest = _build_manifest_with_phases([("setup", [])])

    result = serialize_graph(manifest, original)

    assert result == original
    assert "<!-- footer comment -->" in result


def test_deleted_phase_removes_only_that_phase_line() -> None:
    root = FAKE_CANVAS_FANOUT_ROOT
    manifest = compile_skill(root, cache=False).manifest
    original = (root / "GRAPH.md").read_text(encoding="utf-8")
    mutated = manifest.model_copy(
        update={"phases": [phase for phase in manifest.phases if phase.id != "branch_b"]}
    )

    serialized = serialize_graph(mutated, original)

    assert serialized.count("\n") == original.count("\n") - 1
    assert '<phase id="branch_b" src="phases/branch_b" depends_on="prepare" />' not in serialized
    assert '<phase id="branch_a" src="phases/branch_a" depends_on="prepare" />' in serialized
    assert (
        '<phase id="assemble" src="phases/assemble" depends_on="branch_a branch_b" />' in serialized
    )


def test_fanout_deleted_phase_removes_inserted_downward_attachment() -> None:
    root = FAKE_CANVAS_FANOUT_ROOT
    manifest = compile_skill(root, cache=False).manifest
    original = (root / "GRAPH.md").read_text(encoding="utf-8")
    branch_a_line = '<phase id="branch_a" src="phases/branch_a" depends_on="prepare" />'
    original_with_attachment = original.replace(
        branch_a_line,
        "<!-- branch_a canvas note -->\nBranch A operator note.\n" + branch_a_line,
    )
    mutated = manifest.model_copy(
        update={"phases": [phase for phase in manifest.phases if phase.id != "branch_a"]}
    )

    serialized = serialize_graph(mutated, original_with_attachment)

    assert "<!-- branch_a canvas note -->" not in serialized
    assert "Branch A operator note." not in serialized
    assert '<phase id="branch_b" src="phases/branch_b" depends_on="prepare" />' in serialized
    assert (
        '<phase id="assemble" src="phases/assemble" depends_on="branch_a branch_b" />' in serialized
    )


def test_deleted_phase_removes_its_downward_attachment_only() -> None:
    manifest, original = _fixture_graph("with_comments_v21")
    mutated = manifest.model_copy(
        update={"phases": [phase for phase in manifest.phases if phase.id != "branch"]}
    )

    serialized = serialize_graph(mutated, original)

    assert "<!-- branch attachment -->" not in serialized
    assert "Branch prose belongs to branch." not in serialized
    assert "<!-- prepare attachment -->" in serialized
    assert "Prepare prose belongs to prepare." in serialized
    assert '<phase id="prepare" src="phases/prepare" depends_on="" />' in serialized
    assert '<phase id="assemble" src="phases/assemble" depends_on="branch" />' in serialized


def test_deleted_last_phase_preserves_footer() -> None:
    manifest, original = _fixture_graph("with_comments_v21")
    mutated = manifest.model_copy(
        update={"phases": [phase for phase in manifest.phases if phase.id != "assemble"]}
    )

    serialized = serialize_graph(mutated, original)

    assert "<!-- assemble attachment -->" not in serialized
    assert "Assemble prose belongs to assemble." not in serialized
    assert "<!-- global footer -->" in serialized
    assert "Footer prose remains." in serialized


def test_frontmatter_comments_are_not_phase_attachment() -> None:
    manifest, original = _fixture_graph("with_comments_v21")
    mutated = manifest.model_copy(
        update={"phases": [phase for phase in manifest.phases if phase.id != "prepare"]}
    )

    serialized = serialize_graph(mutated, original)

    assert "# frontmatter comment stays with YAML" in serialized
    assert '<input src="io/inputs.json" />' in serialized
    assert '<output src="io/outputs.json" />' in serialized
    assert "<!-- prepare attachment -->" not in serialized
    assert "Prepare prose belongs to prepare." not in serialized


def test_between_phase_comment_attaches_downward_not_upward() -> None:
    manifest, original = _fixture_graph("with_comments_v21")
    without_prepare = manifest.model_copy(
        update={"phases": [phase for phase in manifest.phases if phase.id != "prepare"]}
    )
    without_branch = manifest.model_copy(
        update={"phases": [phase for phase in manifest.phases if phase.id != "branch"]}
    )

    prepare_deleted = serialize_graph(without_prepare, original)
    branch_deleted = serialize_graph(without_branch, original)

    assert "<!-- branch attachment -->" in prepare_deleted
    assert "Branch prose belongs to branch." in prepare_deleted
    assert "<!-- branch attachment -->" not in branch_deleted
    assert "Branch prose belongs to branch." not in branch_deleted


def test_fresh_render_without_original_markdown_uses_canonical_graph() -> None:
    manifest = GraphManifest(
        name="fresh",
        phases=[
            GraphPhaseRef(id="start", src="phases/start", depends_on=[]),
            GraphPhaseRef(id="end", src="phases/end", depends_on=["start"]),
        ],
    )

    assert serialize_graph(manifest) == (
        "---\n"
        'schema_version: "2.1"\n'
        "name: fresh\n"
        "---\n"
        '<input src="io/inputs.json" />\n'
        '<output src="io/outputs.json" />\n'
        '<phase id="start" src="phases/start" depends_on="" />\n'
        '<phase id="end" src="phases/end" depends_on="start" />\n'
    )
