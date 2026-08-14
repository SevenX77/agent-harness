"""RED tests for engine-compile-diagnostics-v2 (four under-reporting root causes).

Frozen spec: ``.kiro/specs/engine-compile-diagnostics-v2/`` (design.md §6 test
matrix + requirements.md R1-R4 + tasks.md A1-A5). Written by g1 (gatekeeper)
BEFORE any production change; g1-m1 implements against these without editing the
assertions.

Every diagnostic assertion anchors on the ONE aggregation seam the spec fixes:
``exc.compile_result.issues`` (a list of ``CompileIssue`` carrying
``rule_id`` / ``source_path`` / ``line`` / ``field_path``). No test reaches into
compiler internals.

Status legend (see the companion ``.g1-red-report-2026-07-12.md``):
  * RED    — reproduces an unfixed root cause; fails today because the
             production code has not changed yet.
  * LOCK   — a regression guard that is GREEN today and must STAY green
             (contract non-regression: 97-code freeze, predecessor collect-all,
             already-fixed PM symptom, reference/example asymmetry). The spec
             (design §6.5 red-line) requires these to ship inside the RED batch.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path
from typing import Any

import pytest

from graph_agent.core.compiler import compile_skill
from graph_agent.core.error_registry import ERROR_REGISTRY, export_error_catalog
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.skill_resolver_protocol import SkillResolverProtocol

# --------------------------------------------------------------------------- #
# Fixture builders (skill directory on disk, per design §6 "造样输入").          #
# --------------------------------------------------------------------------- #

_EMPTY_IO = """io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _graph_md(
    root: Path,
    *,
    phases: list[str],
    body: str,
    name: str = "diag-v2",
    io_block: str = _EMPTY_IO,
) -> None:
    roster = "\n".join(f"  - {phase}" for phase in phases)
    _write(
        root / "GRAPH.md",
        f'---\nschema_version: "v0.3.0"\nname: {name}\n{io_block}\nphases:\n{roster}\n---\n{body}\n',
    )


def _agent_md(
    *,
    extra_fm: str = "",
    include_io: bool = True,
    io_block: str = _EMPTY_IO,
    llm_role: str | None = "analyst",
    body: str = "<role>R</role>\n<goal>G</goal>\n",
) -> str:
    lines = ["---"]
    if llm_role is not None:
        lines.append(f"llm_role: {llm_role}")
    if extra_fm:
        lines.append(extra_fm.strip("\n"))
    if include_io:
        lines.append(io_block)
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def _solo_agent_skill(
    root: Path,
    *,
    phase: str = "main",
    graph_io: str = _EMPTY_IO,
    graph_name: str = "diag-v2",
    **agent_kwargs: object,
) -> None:
    _graph_md(
        root,
        phases=[phase],
        body=f'<phase depends_on="input" output>{phase}</phase>',
        name=graph_name,
        io_block=graph_io,
    )
    _write(root / "phases" / phase / "SKILL.md", _agent_md(**agent_kwargs))  # type: ignore[arg-type]


def _logic_md(*, validator_line: str = "") -> str:
    validator_block = f"{validator_line}\n" if validator_line else ""
    return f"---\n{validator_block}{_EMPTY_IO}\n---\n<action>run</action>\n"


def _solo_logic_skill(root: Path, *, phase: str = "main", validator: bool = False) -> Path:
    _graph_md(root, phases=[phase], body=f'<phase depends_on="input" output>{phase}</phase>')
    phase_dir = root / "phases" / phase
    _write(phase_dir / "LOGIC.md", _logic_md(validator_line="validator: true" if validator else ""))
    _write(phase_dir / "actions" / "run.py", "def run(inputs):\n    return {}\n")
    return phase_dir


# --------------------------------------------------------------------------- #
# Diagnostic-seam readers (mirror test_compiler_line_locations.py helpers).     #
# --------------------------------------------------------------------------- #


def _raises(root: Path, resolver: SkillResolverProtocol) -> SkillLoadError:
    with pytest.raises(SkillLoadError) as excinfo:
        SkillLoader().compile_skill(root, skill_resolver=resolver)
    return excinfo.value


def _issues(exc: SkillLoadError) -> list[object]:
    compile_result = getattr(exc, "compile_result", None)
    issues = getattr(compile_result, "issues", None)
    if isinstance(issues, list) and issues:
        return list(issues)
    return [exc.payload] if exc.payload is not None else []


def _codes(exc: SkillLoadError) -> set[str]:
    return {str(getattr(issue, "rule_id", getattr(issue, "code", ""))) for issue in _issues(exc)}


def _messages(exc: SkillLoadError) -> str:
    parts = [str(getattr(issue, "message", "")) for issue in _issues(exc)]
    return " | ".join([*parts, str(exc)])


def _source_paths(exc: SkillLoadError) -> set[str]:
    return {str(getattr(issue, "source_path", "")) for issue in _issues(exc)}


def _compile_with_allowed_roles(
    root: Path, resolver: SkillResolverProtocol, roles: set[str] | None
) -> object:
    # Splat through an untyped kwargs dict so the call is mypy-clean both before
    # (``allowed_roles`` absent -> RED) and after g1-m1 adds the B3a/C6 param.
    kwargs: dict[str, Any] = {"cache": False, "skill_resolver": resolver, "allowed_roles": roles}
    return compile_skill(root, **kwargs)


# =========================================================================== #
# §6.1 病根一 — frontmatter aggregation + not masking phase files (R1)          #
# =========================================================================== #


def test_graph_frontmatter_multiple_field_errors_all_reported(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: two independent GRAPH.md field violations (empty name + non-object io)
    # must BOTH surface. Today _build_graph_manifest takes _first_validation_loc
    # and folds to one generic [F-v3-graph-schema-unknown-field].
    _graph_md(
        tmp_path,
        phases=["main"],
        body='<phase depends_on="input" output>main</phase>',
        name='""',
        io_block="io: 123",
    )
    _write(tmp_path / "phases" / "main" / "SKILL.md", _agent_md())

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-graph-name-invalid]" in codes, codes
    assert "[F-v3-graph-io-not-object]" in codes, codes


def test_graph_frontmatter_error_does_not_mask_phase_node_errors(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: a GRAPH.md frontmatter defect must not stop the phase files from
    # compiling. Today _build_graph_manifest raises before the per-node loop, so
    # the phase's own [F-v3-agent-role-missing] never appears.
    _graph_md(
        tmp_path,
        phases=["main"],
        body='<phase depends_on="input" output>main</phase>',
        name='""',
    )
    _write(tmp_path / "phases" / "main" / "SKILL.md", _agent_md(body="<goal>G</goal>\n"))

    exc = _raises(tmp_path, mock_skill_resolver)
    codes = _codes(exc)
    assert "[F-v3-agent-role-missing]" in codes, codes
    assert "GRAPH.md" in _source_paths(exc)


def test_graph_structural_prereq_still_fail_fast(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # LOCK (R1.4): the structural pre-check (no frontmatter `phases` roster) must
    # STAY fail-fast — collect-all must never "hard-run" a missing roster into
    # phantom errors. The phases/ dir exists so the physical-layout guard passes
    # and we reach the frontmatter-roster check inside _build_graph_manifest.
    _write(
        tmp_path / "GRAPH.md",
        f'---\nschema_version: "v0.3.0"\nname: no-roster\n{_EMPTY_IO}\n---\n',
    )
    _write(tmp_path / "phases" / "main" / "SKILL.md", _agent_md())

    exc = _raises(tmp_path, mock_skill_resolver)
    assert "[F-v3-graph-phases-missing]" in _codes(exc), _codes(exc)


def test_poisoned_manifest_does_not_emit_phantom_phase_errors(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: a poisoned frontmatter (non-object io) must still let the real phase
    # defect surface, WITHOUT topology emitting "phase not declared" phantoms.
    # Today the manifest builder aborts before any phase compiles.
    _graph_md(
        tmp_path,
        phases=["main"],
        body='<phase depends_on="input" output>main</phase>',
        io_block="io: 123",
    )
    _write(tmp_path / "phases" / "main" / "SKILL.md", _agent_md(body="<goal>G</goal>\n"))

    exc = _raises(tmp_path, mock_skill_resolver)
    codes = _codes(exc)
    assert "[F-v3-agent-role-missing]" in codes, codes
    assert "[F-v3-graph-phase-name-mismatch]" not in codes, codes
    assert "[F-v3-graph-phase-node-missing]" not in codes, codes


# =========================================================================== #
# §6.2 病根二 — 9 post-barrier validators do not mask each other (R2)           #
# =========================================================================== #


def _resource_and_tool_skill(root: Path, *, phase: str = "main") -> None:
    fm = (
        "tools:\n"
        "  - ghost_tool\n"
        "references:\n"
        "  - id: R1\n"
        "    path: refs/missing.md\n"
        "    summary: ok"
    )
    _graph_md(root, phases=[phase], body=f'<phase depends_on="input" output>{phase}</phase>')
    _write(root / "phases" / phase / "SKILL.md", _agent_md(extra_fm=fm))


def test_independent_validators_all_report_in_one_pass(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: resource-path check (runs first) must not swallow the unknown-tool
    # check (runs later). Today the first raising validator aborts the rest.
    _resource_and_tool_skill(tmp_path)

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-resource-reference-path-invalid]" in codes, codes
    assert "[F-v3-agent-tool-unknown]" in codes, codes


def test_static_dataflow_error_not_masked_by_earlier_validator(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: a resource-path defect must not hide a static-dataflow defect. Today
    # _validate_agent_resource_paths raises before _validate_static_dataflow runs.
    phase_io = """io:
  inputs:
    type: object
    properties:
      orphan:
        type: string
    required: [orphan]
  outputs:
    type: object
    properties:
      answer:
        type: string"""
    fm = "references:\n  - id: R1\n    path: refs/missing.md\n    summary: ok"
    _graph_md(tmp_path, phases=["main"], body='<phase depends_on="input" output>main</phase>')
    _write(tmp_path / "phases" / "main" / "SKILL.md", _agent_md(extra_fm=fm, io_block=phase_io))

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-resource-reference-path-invalid]" in codes, codes
    assert "[F-v3-graph-dataflow-source-missing]" in codes, codes


def test_discover_phase_error_preserves_already_collected_dataflow_diag(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED (REVIEW-line1 F1): B4 discovery validators run after static dataflow
    # has already appended diagnostics. A discovery SkillLoadError must be added
    # to the same bag instead of escaping and discarding earlier diagnostics.
    _graph_md(
        tmp_path,
        phases=["needs_input", "bad_discovery"],
        body='<phase depends_on="input">needs_input</phase>\n'
        '<phase depends_on="needs_input" output>bad_discovery</phase>',
    )
    dataflow_io = """io:
  inputs:
    type: object
    properties:
      orphan:
        type: string
    required: [orphan]
  outputs:
    type: object
    properties: {}"""
    _write(tmp_path / "phases" / "needs_input" / "SKILL.md", _agent_md(io_block=dataflow_io))
    _write(tmp_path / "phases" / "bad_discovery" / "LOGIC.md", _logic_md())
    _write(tmp_path / "phases" / "bad_discovery" / "tools" / "ghost.py", "def ghost():\n    return None\n")

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-graph-dataflow-source-missing]" in codes, codes
    assert "[F-v3-agent-tool-unknown]" in codes, codes


def _poisoned_subgraph_skill(root: Path) -> None:
    # `broken`  : subgraph delegating to a child whose GRAPH.md omits `io`
    #             (child compile fails => `broken` is poisoned).
    # `consumer`: depends on `broken`; its dataflow cascade must be SKIPPED
    #             (not crash on the poisoned upstream).
    # `solo`    : unrelated; its own dataflow gap must surface normally.
    _write(
        root / "GRAPH.md",
        f"""---
schema_version: "v0.3.0"
name: poison-cascade
{_EMPTY_IO}
phases:
  - broken
  - consumer
  - solo
---
<phase depends_on="input">broken</phase>
<phase depends_on="broken">consumer</phase>
<phase depends_on="input" output>solo</phase>
""",
    )
    _write(root / "phases" / "broken" / "SUBGRAPH.md", f"---\npath: subskills/child\n{_EMPTY_IO}\n---\n")
    # child GRAPH.md deliberately omits `io` -> manifest validation fails.
    _write(
        root / "subskills" / "child" / "GRAPH.md",
        '---\nschema_version: "v0.3.0"\nname: child\nphases:\n  - done\n---\n'
        '<phase depends_on="input" output>done</phase>\n',
    )
    _write(root / "subskills" / "child" / "phases" / "done" / "LOGIC.md", _logic_md())
    _write(
        root / "subskills" / "child" / "phases" / "done" / "actions" / "run.py",
        "def run(inputs):\n    return {}\n",
    )
    consumer_io = """io:
  inputs:
    type: object
    properties:
      from_broken:
        type: string
    required: [from_broken]
  outputs:
    type: object
    properties: {}"""
    _write(root / "phases" / "consumer" / "SKILL.md", _agent_md(io_block=consumer_io))
    solo_io = """io:
  inputs:
    type: object
    properties:
      orphan:
        type: string
    required: [orphan]
  outputs:
    type: object
    properties: {}"""
    _write(root / "phases" / "solo" / "SKILL.md", _agent_md(io_block=solo_io))


def test_poisoned_subgraph_skips_cascade_but_keeps_other_nodes(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: a totally-failed subgraph child must not mask the unrelated `solo`
    # node's dataflow defect, and the skipped cascade must be announced
    # (R2.4 no-silent-caps). Today the subgraph validator raises and aborts.
    _poisoned_subgraph_skill(tmp_path)

    exc = _raises(tmp_path, mock_skill_resolver)
    codes = _codes(exc)
    # The unrelated node's independent defect survives (today: masked).
    assert "[F-v3-graph-dataflow-source-missing]" in codes, codes
    assert any("solo" in str(getattr(i, "field_path", "")) for i in _issues(exc)), _issues(exc)
    # R2.4: the skipped cascade is announced, not silently dropped.
    lowered = _messages(exc).lower()
    assert any(kw in lowered for kw in ("skip", "poison", "跳过", "毒化", "上游", "upstream")), lowered


# =========================================================================== #
# §6.3 病根三 — design-mandated compile-time FATALs moved back to compile (R3)  #
# =========================================================================== #


def test_llm_role_unknown_is_compile_fatal_when_roles_injected(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: with a role set injected, an unknown node-level llm_role is a
    # compile-time FATAL. Today compile_skill has no allowed_roles param.
    _solo_agent_skill(tmp_path, llm_role="c")

    with pytest.raises(SkillLoadError) as excinfo:
        _compile_with_allowed_roles(tmp_path, mock_skill_resolver, {"a", "b"})
    assert "[F-v3-agent-llm-role-unknown]" in _codes(excinfo.value), _codes(excinfo.value)


def test_llm_role_check_skipped_when_roles_not_injected(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: with allowed_roles=None (CLI standalone compile), the engine has no
    # basis to judge llm_role -> it must skip (no code, no warning), i.e. compile
    # succeeds. Today the param does not exist.
    _solo_agent_skill(tmp_path, llm_role="c")

    compiled = _compile_with_allowed_roles(tmp_path, mock_skill_resolver, None)
    assert compiled is not None


def test_llm_role_empty_set_treats_all_roles_unknown(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: allowed_roles=set() means "injected but zero valid roles" -> any
    # llm_role is unknown -> FATAL (fail-closed; design §8.2 precision note).
    _solo_agent_skill(tmp_path, llm_role="x")

    with pytest.raises(SkillLoadError) as excinfo:
        _compile_with_allowed_roles(tmp_path, mock_skill_resolver, set())
    assert "[F-v3-agent-llm-role-unknown]" in _codes(excinfo.value), _codes(excinfo.value)


def test_allowed_roles_param_is_pure_set_no_gateway_import() -> None:
    # RED on the signature (param not added yet) + LOCK on NFR1: the engine
    # package must never import gateway/studio.
    sig = inspect.signature(compile_skill)
    assert "allowed_roles" in sig.parameters, "compile_skill must accept allowed_roles (B3a/C6)"
    annotation = str(sig.parameters["allowed_roles"].annotation)
    assert "set" in annotation and "str" in annotation, annotation

    engine_pkg = Path(__file__).resolve().parents[2] / "src" / "graph_agent"
    offenders = [
        str(py)
        for py in engine_pkg.rglob("*.py")
        if re.search(
            r"^\s*(from|import)\s+graph_agent_gateway\b",
            py.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    ]
    assert not offenders, f"engine must not import gateway (NFR1): {offenders}"


def test_missing_validator_py_is_compile_fatal(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: `validator: true` without a sibling validator.py is a COMPILE-time
    # FATAL. Today the check lives at assemble time, so compile passes.
    _solo_logic_skill(tmp_path, validator=True)

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-logic-validator-missing]" in codes, codes


def test_validator_py_without_validate_fn_is_compile_fatal(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED: a validator.py with no top-level `def validate` is a COMPILE-time
    # FATAL. Today the entrypoint check lives at assemble time.
    phase_dir = _solo_logic_skill(tmp_path, validator=True)
    _write(phase_dir / "validator.py", "def not_validate(value):\n    return True\n")

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-logic-validator-entrypoint-missing]" in codes, codes


def test_validator_static_check_does_not_import_user_code(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED + guard: the compile-time validator check must be static (ast.parse),
    # never importlib. A validator.py whose top level writes a file AND imports a
    # missing dependency must (a) still yield the clean entrypoint-missing code
    # (not ModuleNotFoundError) and (b) leave the side-effect file uncreated.
    phase_dir = _solo_logic_skill(tmp_path, validator=True)
    _write(
        phase_dir / "validator.py",
        "from pathlib import Path as _P\n"
        '_P(__file__).with_name("SIDE_EFFECT.txt").write_text("boom", encoding="utf-8")\n'
        "import definitely_missing_pkg_zzz  # noqa: F401\n",
    )

    exc = _raises(tmp_path, mock_skill_resolver)
    assert "[F-v3-logic-validator-entrypoint-missing]" in _codes(exc), _codes(exc)
    assert not (phase_dir / "SIDE_EFFECT.txt").exists(), "compile executed user validator code"


def test_agent_node_missing_io_is_compile_error(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED (§8.1 Path A): a SKILL.md with no `io` block is a compile-time
    # [F-v3-agent-io-schema-invalid], not a runtime agent-output-schema-missing.
    # Today AgentNodeAST.io is Optional, so compile passes.
    _solo_agent_skill(tmp_path, include_io=False)

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-agent-io-schema-invalid]" in codes, codes


def test_iterate_batch_missing_item_var_is_compile_error(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED (R3.4): a batch-mode phase whose io.inputs omits batch.item_var is a
    # compile-time [F-v3-iterate-accumulate-fields-missing]. Today the batch
    # branch is not validated at all.
    fm = "batch:\n  iterator: things\n  item_var: piece"
    _graph_md(tmp_path, phases=["main"], body='<phase depends_on="input" output>main</phase>')
    _write(tmp_path / "phases" / "main" / "SKILL.md", _agent_md(extra_fm=fm))

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-iterate-accumulate-fields-missing]" in codes, codes


# =========================================================================== #
# §6.4 病根四 — specific codes carried, not folded; full extraction (R4)         #
# =========================================================================== #


def test_agent_role_and_goal_both_missing_reported_together(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # LOCK: the PM symptom "supply role, THEN goal error appears" was fixed by the
    # predecessor (#231, _parse_agent_body collect-all). One compile must surface
    # BOTH; this spec must not regress it.
    _solo_agent_skill(tmp_path, body="Just prose, no tags.\n")

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-agent-role-missing]" in codes, codes
    assert "[F-v3-agent-goal-missing]" in codes, codes


def test_pydantic_field_error_carries_specific_code_not_generic(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # RED (R4.1): a field with a dedicated code (max_iterations out of 1..50)
    # must carry [F-v3-agent-max-iterations-invalid], not the folded generic.
    _solo_agent_skill(tmp_path, extra_fm="max_iterations: 999")

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-agent-max-iterations-invalid]" in codes, codes
    assert "[F-v3-agent-schema-unknown-field]" not in codes, codes


def test_field_validator_code_shelling_falls_back_when_no_code(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # LOCK: a truly unknown extra field has no specific code and must keep
    # falling back to [F-v3-agent-schema-unknown-field] (the shelling has a
    # backstop and does not mis-map).
    _solo_agent_skill(tmp_path, extra_fm="totally_unknown_field: 1")

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert "[F-v3-agent-schema-unknown-field]" in codes, codes


_REVIVAL_CASES: list[tuple[str, str, str]] = [
    ("graph-name", "graph", "[F-v3-graph-name-invalid]"),
    ("agent-max-iterations", "max_iterations: 999", "[F-v3-agent-max-iterations-invalid]"),
    (
        "agent-subgraph",
        "subgraphs:\n  - name: worker\n    path: subskills/worker",
        "[F-v3-agent-subgraph-invalid]",
    ),
]


@pytest.mark.parametrize("case_id,trigger,expected_code", _REVIVAL_CASES, ids=[c[0] for c in _REVIVAL_CASES])
def test_dead_code_now_emitted_matches_registry_remediation(
    tmp_path: Path,
    mock_skill_resolver: SkillResolverProtocol,
    case_id: str,
    trigger: str,
    expected_code: str,
) -> None:
    # RED (§5.1): each "definitely revived" dead code must actually emit its
    # SPECIFIC code (today folded to *-schema-unknown-field) and be a registered
    # code whose remediation is retrievable.
    if trigger == "graph":
        _graph_md(
            tmp_path,
            phases=["main"],
            body='<phase depends_on="input" output>main</phase>',
            name='""',
        )
        _write(tmp_path / "phases" / "main" / "SKILL.md", _agent_md())
    else:
        _solo_agent_skill(tmp_path, extra_fm=trigger)

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert expected_code in codes, (case_id, codes)
    assert expected_code in ERROR_REGISTRY
    assert ERROR_REGISTRY[expected_code].remediation, expected_code


_RESOURCE_CASES: list[tuple[str, str, str, str]] = [
    ("ref-id", "references", "  - id: badid\n    path: refs/r.md\n    summary: ok", "[F-v3-resource-reference-id-invalid]"),
    ("ref-summary", "references", '  - id: R1\n    path: refs/r.md\n    summary: ""', "[F-v3-resource-reference-summary-missing]"),
    ("ref-path-empty", "references", '  - id: R1\n    path: ""\n    summary: ok', "[F-v3-resource-reference-invalid]"),
    ("ex-id", "examples", "  - id: badid\n    path: ex/e.md\n    summary: ok", "[F-v3-resource-example-id-invalid]"),
    ("ex-summary", "examples", '  - id: E1\n    path: ex/e.md\n    summary: ""', "[F-v3-resource-example-summary-missing]"),
    ("ex-path-empty", "examples", '  - id: E1\n    path: ""\n    summary: ok', "[F-v3-resource-example-path-missing]"),
    ("ex-extra", "examples", "  - id: E1\n    path: ex/e.md\n    summary: ok\n    bogus: 1", "[F-v3-resource-example-invalid]"),
]


@pytest.mark.parametrize(
    "case_id,kind,entry,expected_code", _RESOURCE_CASES, ids=[c[0] for c in _RESOURCE_CASES]
)
def test_resource_reference_and_example_invalid_codes_emitted(
    tmp_path: Path,
    mock_skill_resolver: SkillResolverProtocol,
    case_id: str,
    kind: str,
    entry: str,
    expected_code: str,
) -> None:
    # RED (R4.5): each malformed reference/example must emit its SPECIFIC
    # resource-* code instead of the folded agent-schema-unknown-field, honoring
    # the reference/example path asymmetry (reference path empty ->
    # resource-reference-invalid; example path empty -> resource-example-path-missing).
    _graph_md(tmp_path, phases=["main"], body='<phase depends_on="input" output>main</phase>')
    _write(tmp_path / "phases" / "main" / "SKILL.md", _agent_md(extra_fm=f"{kind}:\n{entry}"))

    codes = _codes(_raises(tmp_path, mock_skill_resolver))
    assert expected_code in codes, (case_id, codes)
    assert "[F-v3-agent-schema-unknown-field]" not in codes, (case_id, codes)


def test_reference_has_no_path_missing_code_example_does() -> None:
    # LOCK (R4.5 asymmetry): the registry must NOT grow a
    # resource-reference-path-missing code, while resource-example-path-missing
    # stays present — guards g1-m1 against inventing the symmetric code.
    assert "[F-v3-resource-reference-path-missing]" not in ERROR_REGISTRY
    assert "[F-v3-resource-example-path-missing]" in ERROR_REGISTRY


def test_error_registry_len_unchanged_97() -> None:
    # LOCK (R4.3 / design §6.5): the 98-code freeze and the round28 catalog
    # bijection must not move — this spec revives dead codes, never adds/removes.
    assert len(ERROR_REGISTRY) == 98
    catalog = export_error_catalog()
    assert len(catalog["items"]) == 98
    assert all(item["remediation"] for item in catalog["items"])


# =========================================================================== #
# §6.5 契约不回归 — regression guards (LOCK)                                     #
# =========================================================================== #

# Frozen (level, stage) semantics for every live code, captured from the current
# registry. This spec reuses existing codes and lets dead codes fire; it must not
# re-stage or re-level any of the 71 frontend-visible live codes (design §6.5).
_REGISTRY_STAGE_SNAPSHOT: dict[str, tuple[str, tuple[str, ...]]] = {
    '[F-v3-graph-schema-unknown-field]': ('FATAL', ('编译期',)),
    '[F-v3-graph-name-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-graph-schema-version-mismatch]': ('FATAL', ('编译期',)),
    '[F-v3-graph-llm-role-unknown]': ('FATAL', ('编译期',)),
    '[F-v3-graph-root-missing]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phases-dir-missing]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phases-missing]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phase-id-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phase-name-mismatch]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phase-id-duplicate]': ('FATAL', ('编译期',)),
    '[F-v3-graph-depends-unknown]': ('FATAL', ('编译期',)),
    '[F-v3-graph-output-phase-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phase-cycle]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phase-island]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phase-dir-missing]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phase-mode-ambiguous]': ('FATAL', ('编译期',)),
    '[F-v3-graph-phase-node-missing]': ('FATAL', ('编译期',)),
    '[F-v3-graph-io-not-object]': ('FATAL', ('编译期',)),
    '[F-v3-graph-io-schema-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-graph-io-physical-file-deprecated]': ('FATAL', ('编译期',)),
    '[F-v3-graph-dataflow-source-missing]': ('FATAL', ('编译期',)),
    '[F-v3-compile-recursion-cycle]': ('FATAL', ('编译期',)),
    '[F-v3-compile-depth-exceeded]': ('FATAL', ('编译期',)),
    '[F-v3-logic-schema-unknown-field]': ('FATAL', ('编译期',)),
    '[F-v3-logic-name-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-logic-io-schema-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-logic-actions-empty]': ('FATAL', ('编译期',)),
    '[F-v3-logic-action-name-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-logic-action-dir-missing]': ('FATAL', ('编译期',)),
    '[F-v3-logic-action-not-found]': ('FATAL', ('编译期',)),
    '[F-v3-logic-action-entrypoint-missing]': ('FATAL', ('编译期',)),
    '[F-v3-logic-action-purity-violation]': ('FATAL', ('编译期',)),
    '[F-v3-logic-action-return-invalid]': ('FATAL', ('运行期',)),
    '[F-v3-logic-output-field-undeclared]': ('FATAL', ('运行期',)),
    '[F-v3-logic-validator-type-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-logic-validator-missing]': ('FATAL', ('编译期',)),
    '[F-v3-logic-validator-entrypoint-missing]': ('FATAL', ('编译期',)),
    '[F-v3-logic-validator-failed]': ('FATAL', ('运行期',)),
    '[F-v3-iterate-accumulate-fields-missing]': ('FATAL', ('编译期',)),
    '[F-v3-iterate-over-not-list]': ('FATAL', ('编译期', '运行期')),
    '[F-v3-agent-validator-failed]': ('FATAL', ('运行期',)),
    '[F-v3-subgraph-validator-failed]': ('FATAL', ('运行期',)),
    '[F-v3-subgraph-schema-unknown-field]': ('FATAL', ('编译期',)),
    '[F-v3-subgraph-name-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-subgraph-target-skill-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-subgraph-io-schema-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-subgraph-io-mismatch]': ('FATAL', ('编译期',)),
    '[F-v3-subgraph-io-schema-incompatible]': ('FATAL', ('编译期',)),
    '[F-v3-golden-stale-fields]': ('FATAL', ('eval 期',)),
    '[F-v3-agent-schema-unknown-field]': ('FATAL', ('编译期',)),
    '[F-v3-agent-name-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-agent-llm-role-unknown]': ('FATAL', ('编译期',)),
    '[F-v3-agent-io-schema-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-agent-output-schema-invalid]': ('FATAL', ('运行期',)),
    '[F-v3-agent-output-schema-missing]': ('FATAL', ('运行期',)),
    '[F-v3-agent-tool-unknown]': ('FATAL', ('编译期',)),
    '[F-v3-agent-tool-reserved]': ('FATAL', ('编译期',)),
    '[F-v3-agent-subagent-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-agent-subgraph-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-agent-max-iterations-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-agent-body-tag-unknown]': ('FATAL', ('编译期',)),
    '[F-v3-agent-role-missing]': ('FATAL', ('编译期',)),
    '[F-v3-agent-goal-missing]': ('FATAL', ('编译期',)),
    '[F-v3-agent-step-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-agent-protocol-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-agent-example-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-mention-type-unknown]': ('FATAL', ('编译期',)),
    '[F-v3-mention-syntax-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-mention-target-not-found]': ('FATAL', ('编译期',)),
    '[F-v3-mention-unused-registry-entry]': ('WARN', ('编译期',)),
    '[F-v3-resource-reference-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-resource-reference-id-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-resource-reference-path-invalid]': ('FATAL', ('编译期', '运行期')),
    '[F-v3-resource-reference-summary-missing]': ('FATAL', ('编译期',)),
    '[F-v3-resource-reference-not-found]': ('FATAL', ('运行期',)),
    '[F-v3-resource-example-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-resource-example-id-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-resource-example-path-missing]': ('FATAL', ('编译期',)),
    '[F-v3-resource-example-path-invalid]': ('FATAL', ('编译期', '运行期')),
    '[F-v3-resource-example-summary-missing]': ('FATAL', ('编译期',)),
    '[F-v3-resource-example-not-found]': ('FATAL', ('运行期',)),
    '[F-v3-reference-reader-failed]': ('WARN', ('装配期',)),
    '[F-v3-resolver-skill-id-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-skill-id-ambiguous]': ('FATAL', ('编译期', '装配期')),
    '[F-v3-skill-not-registered]': ('FATAL', ('编译期', '装配期')),
    '[F-v3-resolver-path-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-resolver-interface-invalid]': ('FATAL', ('编译期',)),
    '[F-v3-resolver-missing]': ('FATAL', ('运行期',)),
    '[F-v3-cognitive-slot-render-failed]': ('FATAL', ('装配期',)),
    '[F-v3-cognitive-output-schema-render-failed]': ('FATAL', ('装配期',)),
    '[F-v3-cognitive-output-schema-invalid]': ('FATAL', ('装配期', '装配前')),
    '[F-v3-reference-reader-input-invalid]': ('FATAL', ('装配期',)),
    '[F-v3-reference-reader-output-invalid]': ('FATAL', ('装配期',)),
    '[F-v3-tool-argument-invalid]': ('FATAL', ('运行期',)),
    '[F-v3-runtime-state-mapping-failed]': ('FATAL', ('运行期',)),
    '[F-v3-runtime-phase-failed]': ('FATAL', ('运行期',)),
    '[F-v3-sequential-overwrite-unauthorized]': ('FATAL', ('编译期',)),
    '[F-v3-agent-exit-control-failed]': ('FATAL', ('运行期',)),
}


def test_no_frontend_visible_code_semantics_changed_without_signoff() -> None:
    # LOCK (design §6.5): reviving dead codes must not drift the rule_id/stage of
    # any live code. In particular agent-output-schema-missing stays 运行期 (this
    # spec reuses agent-io-schema-invalid at compile, not a re-staged runtime code).
    actual = {code: (meta.level, tuple(meta.stage)) for code, meta in ERROR_REGISTRY.items()}
    assert actual == _REGISTRY_STAGE_SNAPSHOT


def test_collect_all_predecessor_regressions_still_green(
    tmp_path: Path, mock_skill_resolver: SkillResolverProtocol
) -> None:
    # LOCK: the predecessor collect-all seam (test_compiler_line_locations.py)
    # must not regress. Re-exercise its load-bearing guarantees directly: one
    # compile surfaces role+goal together, and separate nodes do not hide each
    # other. (CI also runs the predecessor file in full.)
    _graph_md(
        tmp_path,
        phases=["first", "second"],
        body='<phase depends_on="input">first</phase>\n'
        '<phase depends_on="first" output>second</phase>',
    )
    for phase in ("first", "second"):
        _write(tmp_path / "phases" / phase / "SKILL.md", _agent_md(body="Just prose, no tags.\n"))

    exc = _raises(tmp_path, mock_skill_resolver)
    codes = _codes(exc)
    assert "[F-v3-agent-role-missing]" in codes, codes
    assert "[F-v3-agent-goal-missing]" in codes, codes
    located = _source_paths(exc)
    assert any("first" in loc for loc in located), located
    assert any("second" in loc for loc in located), located
