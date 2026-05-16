from __future__ import annotations

from pathlib import Path

from graph_agent.core.compiler import compile_skill
from graph_agent.core.graph_serializer import serialize_graph
from graph_agent.core.manifest import GraphManifest, GraphPhaseRef


REPO_ROOT = Path(__file__).resolve().parents[4]


def _skill_graph(skill: str) -> tuple[GraphManifest, str]:
    root = REPO_ROOT / "skills" / skill
    return compile_skill(root, cache=False).manifest, (root / "GRAPH.md").read_text(encoding="utf-8")


def _line_diff_count(before: str, after: str) -> int:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    return sum(1 for old, new in zip(before_lines, after_lines) if old != new) + abs(
        len(after_lines) - len(before_lines)
    )


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
    root = REPO_ROOT / "packages" / "graph-agent" / "tests" / "fixtures" / "fake_canvas_fanout"
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
    assert '<phase id="branch_b" src="phases/branch_b" depends_on="prepare,branch_a" />' in serialized
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
    assert serialized.endswith('<phase id="review" src="phases/review" depends_on="greet" />\n')


def test_deleted_phase_removes_only_that_phase_line() -> None:
    root = REPO_ROOT / "packages" / "graph-agent" / "tests" / "fixtures" / "fake_canvas_fanout"
    manifest = compile_skill(root, cache=False).manifest
    original = (root / "GRAPH.md").read_text(encoding="utf-8")
    mutated = manifest.model_copy(
        update={"phases": [phase for phase in manifest.phases if phase.id != "branch_b"]}
    )

    serialized = serialize_graph(mutated, original)

    assert serialized.count("\n") == original.count("\n") - 1
    assert '<phase id="branch_b" src="phases/branch_b" depends_on="prepare" />' not in serialized
    assert '<phase id="branch_a" src="phases/branch_a" depends_on="prepare" />' in serialized
    assert '<phase id="assemble" src="phases/assemble" depends_on="branch_a branch_b" />' in serialized


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
