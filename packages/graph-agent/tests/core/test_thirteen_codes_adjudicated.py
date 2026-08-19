"""The registry holds no code without an emitter; wired seams actually fire.

Adjudication 2026-08-19 (decision doc
`.kiro/specs/decision-2026-08-19-an-error-code-either-fires-or-leaves.md`):
13 registry codes had no production emitter. Eleven leave the registry — nine
describe conditions covered by live codes, unrepresentable in MVP1, or
contradicting pinned behavior, and the two subgraph-io 1:1 codes pin a gate
the MVP1 design explicitly removed (skill-syntax mvp1-alignment §3.4 「父图和
子图 IO 不需要字段全集一一相等」, gate deleted by commit cad7dbc0; they had
only been retained to keep the old 99-code count, which this adjudication
abandons). Two describe real unchecked compile gates — they get emitters,
pinned here by building the violating skill and compiling it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.error_registry import ERROR_REGISTRY
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.skill_resolver_protocol import SkillResolutionError

from ..ws_e4_runtime_skills import _write_graph, write_logic_phase

_DELETED = [
    "[F-v3-graph-phase-dir-missing]",
    "[F-v3-agent-name-invalid]",
    "[F-v3-logic-name-invalid]",
    "[F-v3-mention-type-unknown]",
    "[F-v3-mention-unused-registry-entry]",
    "[F-v3-reference-reader-input-invalid]",
    "[F-v3-reference-reader-output-invalid]",
    "[F-v3-cognitive-slot-render-failed]",
    "[F-v3-cognitive-output-schema-render-failed]",
    "[F-v3-subgraph-io-mismatch]",
    "[F-v3-subgraph-io-schema-incompatible]",
]


def test_no_adjudicated_dead_code_remains_registered() -> None:
    remaining = [code for code in _DELETED if code in ERROR_REGISTRY]
    assert remaining == [], (
        "these codes were adjudicated OUT (no emitter, condition covered "
        f"elsewhere or unrepresentable): {remaining}"
    )


def _child(root: Path, in_field: str, out_field: str) -> None:
    _write_graph(
        root,
        name="seam-child",
        inputs={in_field: {"type": "string"}},
        outputs={out_field: {"type": "string"}},
        phases=["inner"],
        phase_edges='<phase depends_on="input" output>inner</phase>',
        required_inputs=[in_field],
    )
    write_logic_phase(
        root,
        "inner",
        inputs={in_field: {"type": "string"}},
        outputs={out_field: {"type": "string"}},
        required=[in_field],
        action_body=f"""
            def inner(inputs):
                return {{"{out_field}": inputs["{in_field}"]}}
        """,
    )


def _subgraph_md(phase_dir: Path, *, path: str, io_yaml: str, name: str = "work") -> None:
    phase_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"name: {name}", f"path: {path}", *io_yaml.strip().split(chr(10)), "---"]
    (phase_dir / "SUBGRAPH.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")


def _parent(root: Path) -> None:
    _write_graph(
        root,
        name="seam-parent",
        inputs={"text": {"type": "string"}},
        outputs={"result": {"type": "string"}},
        phases=["work"],
        phase_edges='<phase depends_on="input" output>work</phase>',
        required_inputs=["text"],
    )


def _codes_of(exc: SkillLoadError) -> set[str]:
    issues = getattr(getattr(exc, "compile_result", None), "issues", None) or []
    codes = {issue.rule_id for issue in issues}
    payload = getattr(exc, "payload", None)
    if payload is not None and getattr(payload, "code", None):
        codes.add(payload.code)
    return codes


IO_OK = """io:
  inputs:
    type: object
    required: [text]
    properties:
      text: {type: string}
  outputs:
    type: object
    required: [result]
    properties:
      result: {type: string}"""


class TestSubgraphSeamGates:
    def test_a_non_one_to_one_seam_compiles_by_design(
        self, tmp_path: Path, mock_skill_resolver: object
    ) -> None:
        """Parent SUBGRAPH declares an output the child does not produce AND a
        same-name input with a different type — and that COMPILES, on purpose.

        skill-syntax mvp1-alignment §3.4: 父图和子图 IO 不需要字段全集一一相等;
        the compile gate was removed by cad7dbc0 (StateMapper guards the seam at
        runtime via [F-v3-runtime-state-mapping-failed]). This pin keeps the
        adjudication from re-wiring the two deleted 1:1 codes by accident.
        """
        _parent(tmp_path)
        _child(tmp_path / "child", "text", "result")
        io = """io:
  inputs:
    type: object
    required: [text]
    properties:
      text: {type: number}
  outputs:
    type: object
    required: [result, phantom]
    properties:
      result: {type: string}
      phantom: {type: string}"""
        _subgraph_md(tmp_path / "phases" / "work", path="child", io_yaml=io)

        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    def test_a_matching_seam_still_compiles(
        self, tmp_path: Path, mock_skill_resolver: object
    ) -> None:
        _parent(tmp_path)
        _child(tmp_path / "child", "text", "result")
        _subgraph_md(tmp_path / "phases" / "work", path="child", io_yaml=IO_OK)

        compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

    def test_an_invalid_subgraph_name_is_fatal(
        self, tmp_path: Path, mock_skill_resolver: object
    ) -> None:
        """`name` must be an identifier, the same rule agent-embedded subgraph
        declarations already enforce (manifest.SubgraphAST pattern). Compiled
        CLEAN before wiring (probe 2026-08-19)."""
        _parent(tmp_path)
        _child(tmp_path / "child", "text", "result")
        _subgraph_md(
            tmp_path / "phases" / "work", path="child", io_yaml=IO_OK, name="bad name!"
        )

        with pytest.raises(SkillLoadError) as exc_info:
            compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)

        assert "[F-v3-subgraph-name-invalid]" in _codes_of(exc_info.value)


class TestResolverInterfaceGate:
    def test_a_resolver_without_resolve_skill_fails_at_the_boundary(
        self, tmp_path: Path
    ) -> None:
        """Fail fast at the compile entry instead of an AttributeError somewhere
        deep once a subgraph finally needs the resolver.

        Resolver-domain errors are caller misconfiguration, not skill content:
        they surface as SkillResolutionError, the same seam
        [F-v3-resolver-missing] already uses, not as aggregated SkillLoadError
        diagnostics.
        """
        _parent(tmp_path)
        _child(tmp_path / "child", "text", "result")
        _subgraph_md(tmp_path / "phases" / "work", path="child", io_yaml=IO_OK)

        class NotAResolver:
            pass

        with pytest.raises(SkillResolutionError) as exc_info:
            compile_skill(tmp_path, cache=False, skill_resolver=NotAResolver())

        assert exc_info.value.code == "[F-v3-resolver-interface-invalid]"
