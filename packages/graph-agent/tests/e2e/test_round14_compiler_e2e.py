"""Round-14 skill-compilation compiler end-to-end tests.

These tests drive the real public compile entry (``SkillLoader.compile_skill``)
against real on-disk skill directories — no mocking of the compile core. They
cover both contract directions of the V0.3.0 compiler:

* happy path: a structurally complete multi-phase skill (agent + logic +
  subgraph nodes, subagent/subgraph registries, references, examples, body
  ``@mention`` resolution, child-skill IO alignment) compiles into a
  ``CompiledSkill`` whose products are asserted field by field.
* precise-error path: an otherwise-valid skill is corrupted one defect at a
  time, and each corruption must raise its own dedicated ``[F-v3-*]`` code
  (no defect code reused across two different defects, and no other defect's
  code leaking into the message) plus, where the failure originates inside a
  source file, a ``file:line`` location. Round-14 is a *hard cutover* that
  rejects the old V2.1 shape, so the error path also covers legacy-metadata
  rejection and three-way phase-name consistency.

The happy-path fixture lives at ``tests/fixtures/v030_e2e_pipeline`` so the
artifact can be inspected directly. Every test copies that fixture into a
``tmp_path`` before compiling, so the committed fixture stays pristine (the
LOGIC action ``.py`` files are never imported from their committed location,
so no ``__pycache__`` is written into the fixture). Error variants then mutate
exactly one file, proving the compiler pinpoints the specific defect.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.loader import CompiledSkill, SkillLoader
from graph_agent.core.manifest import AgentNodeAST, LogicNodeAST, SubgraphNodeAST

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "v030_e2e_pipeline"


class DictSkillResolver:
    """Minimal resolver mapping skill ids to on-disk child roots."""

    def __init__(self, mapping: dict[str, Path]) -> None:
        self.mapping = mapping

    def resolve_skill(self, skill_id: str) -> Path:
        return self.mapping[skill_id]


def _resolver_for(root: Path) -> DictSkillResolver:
    return DictSkillResolver(
        {
            "e2e.echo": root / "registry" / "echo",
            "e2e.expander": root / "registry" / "expander",
        }
    )


def _copy_pipeline(tmp_path: Path) -> Path:
    root = tmp_path / "skill"
    shutil.copytree(FIXTURE, root)
    return root


@pytest.fixture
def pipeline_root(tmp_path: Path) -> Path:
    """A pristine on-disk copy of the full pipeline skill."""

    return _copy_pipeline(tmp_path)


@pytest.fixture
def corrupt_root(tmp_path: Path) -> Path:
    """A pipeline copy whose pristine form is proven to compile.

    Any failure raised after a mutation below is therefore attributable to that
    single mutation, not to a pre-existing defect.
    """

    root = _copy_pipeline(tmp_path)
    SkillLoader().compile_skill(root, skill_resolver=_resolver_for(root))
    return root


# --------------------------------------------------------------------------- #
# Happy path                                                                   #
# --------------------------------------------------------------------------- #


def test_full_pipeline_skill_compiles_into_expected_products(pipeline_root: Path) -> None:
    compiled: CompiledSkill = SkillLoader().compile_skill(
        pipeline_root, skill_resolver=_resolver_for(pipeline_root)
    )

    # Root manifest: schema pin, name, phase registry, inline IO.
    assert compiled.manifest.schema_version == "v0.3.0"
    assert compiled.manifest.name == "round14-e2e-pipeline"
    assert compiled.manifest.phases == ["segment", "score", "expand"]
    assert sorted(compiled.manifest.io.inputs["properties"]) == ["chapter_content"]
    assert sorted(compiled.manifest.io.outputs["properties"]) == ["report"]

    # DAG topology: body <phase> drives dependency order; expand is terminal.
    topology = compiled.raw["graph_topology"]
    assert topology["order"] == ["segment", "score", "expand"]
    by_name = {entry["name"]: entry for entry in topology["phases"]}
    assert by_name["segment"]["depends_on"] == ["input"]
    assert by_name["score"]["depends_on"] == ["segment"]
    assert by_name["expand"]["depends_on"] == ["score"]
    assert by_name["expand"]["output"] is True
    assert by_name["segment"]["output"] is False

    # Each phase resolves to the AST type its file name implies.
    modes = {node.phase_name: node.mode for node in compiled.nodes}
    assert modes == {"segment": "agent", "score": "logic", "expand": "subgraph"}
    node_types = {node.phase_name: type(node.ast).__name__ for node in compiled.nodes}
    assert node_types == {
        "segment": "AgentNodeAST",
        "score": "LogicNodeAST",
        "expand": "SubgraphNodeAST",
    }

    # Agent phase products: role/goal, ordered steps, protocols, references,
    # document + inline examples, declared tools, subagent + subgraph registry.
    segment = next(node.ast for node in compiled.nodes if node.phase_name == "segment")
    assert isinstance(segment, AgentNodeAST)
    assert segment.role == "You are a narrative segmentation editor."
    assert segment.goal.startswith("Segment chapter_content")
    assert [step.id for step in segment.steps] == ["S1", "S2", "S3"]
    assert [step.name for step in segment.steps] == [
        "read_reference",
        "review_with_subagent",
        "finish",
    ]
    assert [protocol.id for protocol in segment.protocols] == ["P1"]
    assert [reference.id for reference in segment.references] == ["R1"]
    assert [example.id for example in segment.examples] == ["E2"]
    assert [example.id for example in segment.examples_inline] == ["E1"]
    assert segment.tools == ["finish_task"]
    assert [(s.name, s.target_skill) for s in segment.subagents] == [("echo_helper", "e2e.echo")]
    assert [(s.name, s.target_skill) for s in segment.subgraphs] == [("deep_dive", "e2e.expander")]
    assert segment.max_iterations == 8

    # Logic phase products: phase-level IO + discovered action registry.
    score = next(node.ast for node in compiled.nodes if node.phase_name == "score")
    assert isinstance(score, LogicNodeAST)
    assert score.actions == ["score"]
    assert score.validator is False
    assert sorted(score.io.inputs["properties"]) == ["segments"]
    assert sorted(score.io.outputs["properties"]) == ["report"]
    assert "score" in compiled.actions.for_phase("score")

    # Subgraph phase products: target_skill + phase IO (which the compiler has
    # already proven aligns 1:1 with the e2e.expander child GRAPH IO).
    expand = next(node.ast for node in compiled.nodes if node.phase_name == "expand")
    assert isinstance(expand, SubgraphNodeAST)
    assert expand.target_skill == "e2e.expander"
    assert sorted(expand.io.inputs["properties"]) == ["brief"]
    assert sorted(expand.io.outputs["properties"]) == ["report"]

    # Subagent metadata resolved + compiled from the e2e.echo child skill.
    echo = compiled.subagents_by_phase["segment"][0]
    assert echo.name == "echo_helper"
    assert echo.target_skill == "e2e.echo"
    assert echo.root == pipeline_root / "registry" / "echo"
    assert sorted(echo.input_schema["properties"]) == ["note"]


# --------------------------------------------------------------------------- #
# Precise-error path                                                           #
# --------------------------------------------------------------------------- #


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prepend_frontmatter_line(path: Path, line: str) -> None:
    """Insert ``line`` as the first key inside the file's YAML frontmatter."""

    text = _read(path)
    assert text.startswith("---\n"), path
    _write(path, "---\n" + line + "\n" + text[len("---\n") :])


# -- Legacy / hard-cutover rejection (round-14 core) ------------------------- #


def _legacy_mode_on_agent(root: Path) -> None:
    _prepend_frontmatter_line(root / "phases" / "segment" / "SKILL.md", "mode: agent")


def _legacy_schema_version_on_logic(root: Path) -> None:
    _prepend_frontmatter_line(root / "phases" / "score" / "LOGIC.md", 'schema_version: "v0.3.0"')


def _legacy_graph_skill_id_on_subgraph(root: Path) -> None:
    _prepend_frontmatter_line(root / "phases" / "expand" / "SUBGRAPH.md", "graph_skill_id: polluted")


def _legacy_phase_id_on_agent(root: Path) -> None:
    _prepend_frontmatter_line(root / "phases" / "segment" / "SKILL.md", "phase_id: polluted")


# -- Three-way phase-name / topology consistency ----------------------------- #


def _rename_body_phase(root: Path) -> None:
    # body <phase> name diverges from frontmatter `phases` + physical dir.
    graph = root / "GRAPH.md"
    _write(
        graph,
        _read(graph).replace(
            '<phase depends_on="input">segment</phase>',
            '<phase depends_on="input">segmentx</phase>',
        ),
    )


def _mark_nonterminal_as_output(root: Path) -> None:
    # segment has downstream edges, so marking it `output` is invalid.
    graph = root / "GRAPH.md"
    _write(
        graph,
        _read(graph).replace(
            '<phase depends_on="input">segment</phase>',
            '<phase depends_on="input" output>segment</phase>',
        ),
    )


def _duplicate_phase_registration(root: Path) -> None:
    graph = root / "GRAPH.md"
    _write(graph, _read(graph).replace("  - segment\n  - score", "  - segment\n  - segment\n  - score"))


# -- Per-domain structural / semantic defects -------------------------------- #


def _set_schema_version_21(root: Path) -> None:
    graph = root / "GRAPH.md"
    _write(graph, _read(graph).replace('"v0.3.0"', '"2.1"', 1))


def _introduce_cycle(root: Path) -> None:
    graph = root / "GRAPH.md"
    _write(
        graph,
        _read(graph).replace(
            '<phase depends_on="segment">score</phase>',
            '<phase depends_on="expand">score</phase>',
        ),
    )


def _introduce_island(root: Path) -> None:
    graph = root / "GRAPH.md"
    _write(
        graph,
        _read(graph).replace(
            '<phase depends_on="segment">score</phase>',
            '<phase depends_on="nowhere">score</phase>',
        ),
    )


def _add_second_node_file(root: Path) -> None:
    _write(
        root / "phases" / "score" / "SKILL.md",
        "---\n---\n<role>x</role>\n<goal>y</goal>\n",
    )


def _drop_agent_role(root: Path) -> None:
    skill = root / "phases" / "segment" / "SKILL.md"
    _write(
        skill,
        _read(skill).replace(
            "<role>\nYou are a narrative segmentation editor.\n</role>\n\n",
            "",
        ),
    )


def _add_exit_contract_tag(root: Path) -> None:
    skill = root / "phases" / "segment" / "SKILL.md"
    _write(skill, _read(skill) + "\n<exit_contract>forbidden</exit_contract>\n")


def _break_mention_target(root: Path) -> None:
    skill = root / "phases" / "segment" / "SKILL.md"
    _write(skill, _read(skill).replace("@reference:R1", "@reference:DOES_NOT_EXIST"))


def _break_mention_syntax(root: Path) -> None:
    skill = root / "phases" / "segment" / "SKILL.md"
    _write(skill, _read(skill).replace("follow @protocol:P1.", "see @reference here."))


def _bad_logic_validator_type(root: Path) -> None:
    logic = root / "phases" / "score" / "LOGIC.md"
    _write(logic, _read(logic).replace("validator: false", 'validator: "yes"'))


def _empty_logic_actions(root: Path) -> None:
    logic = root / "phases" / "score" / "LOGIC.md"
    _write(logic, _read(logic).replace("<action>score</action>", ""))


def _mismatch_subgraph_io(root: Path) -> None:
    subgraph = root / "phases" / "expand" / "SUBGRAPH.md"
    text = _read(subgraph).replace("required: [brief]", "required: [outline]")
    text = text.replace("brief:", "outline:")
    _write(subgraph, text)


def _add_deprecated_physical_io(root: Path) -> None:
    (root / "io").mkdir()
    _write(root / "io" / "inputs.json", "{}\n")


# Mutations whose failure surfaces from inside a source file (path:line carried).
_LOCATED_ERROR_CASES: list[tuple[str, Callable[[Path], None], str]] = [
    # legacy-metadata rejection: per-domain unknown-field code (hard cutover)
    ("legacy-mode-on-agent", _legacy_mode_on_agent, "[F-v3-agent-schema-unknown-field]"),
    (
        "legacy-schema-version-on-logic",
        _legacy_schema_version_on_logic,
        "[F-v3-logic-schema-unknown-field]",
    ),
    (
        "legacy-graph-skill-id-on-subgraph",
        _legacy_graph_skill_id_on_subgraph,
        "[F-v3-subgraph-schema-unknown-field]",
    ),
    ("legacy-phase-id-on-agent", _legacy_phase_id_on_agent, "[F-v3-agent-schema-unknown-field]"),
    # three-way phase-name / topology consistency
    ("phase-name-mismatch", _rename_body_phase, "[F-v3-graph-phase-name-mismatch]"),
    ("output-phase-non-terminal", _mark_nonterminal_as_output, "[F-v3-graph-output-phase-invalid]"),
    ("phase-id-duplicate", _duplicate_phase_registration, "[F-v3-graph-phase-id-duplicate]"),
    # per-domain structural / semantic defects
    ("schema-version-mismatch", _set_schema_version_21, "[F-v3-graph-schema-version-mismatch]"),
    ("phase-cycle", _introduce_cycle, "[F-v3-graph-phase-cycle]"),
    ("phase-island", _introduce_island, "[F-v3-graph-phase-island]"),
    ("phase-mode-ambiguous", _add_second_node_file, "[F-v3-graph-phase-mode-ambiguous]"),
    ("agent-role-missing", _drop_agent_role, "[F-v3-agent-role-missing]"),
    ("agent-body-tag-unknown", _add_exit_contract_tag, "[F-v3-agent-body-tag-unknown]"),
    ("mention-target-not-found", _break_mention_target, "[F-v3-mention-target-not-found]"),
    ("mention-syntax-invalid", _break_mention_syntax, "[F-v3-mention-syntax-invalid]"),
    ("logic-validator-type-invalid", _bad_logic_validator_type, "[F-v3-logic-validator-type-invalid]"),
    ("logic-actions-empty", _empty_logic_actions, "[F-v3-logic-actions-empty]"),
    ("subgraph-io-mismatch", _mismatch_subgraph_io, "[F-v3-subgraph-io-mismatch]"),
    (
        "graph-io-physical-file-deprecated",
        _add_deprecated_physical_io,
        "[F-v3-graph-io-physical-file-deprecated]",
    ),
]

_SOURCE_FILE_MARKERS = ("GRAPH.md", "SKILL.md", "LOGIC.md", "SUBGRAPH.md", ".json")

# Every ``[F-v3-*]`` token a SkillLoadError message can carry.
_CODE_RE = re.compile(r"\[F-v3-[a-z0-9-]+\]")
_GENERIC_WRAPPER_CODES = frozenset()


def _assert_unique_defect_code(exc: BaseException, expected: str) -> None:
    """Assert ``exc`` carries ``expected`` and no *other* defect code.

    This is the permanent form of the one-off discrimination check: the only
    dedicated ``[F-v3-*]`` code in the message (after stripping generic routing
    wrappers) must be the one defect under test, so no two distinct defects can
    masquerade behind a shared or leaked error code.
    """

    payload = getattr(exc, "payload", None)
    if payload is not None:
        assert payload.code == expected
        return
    message = str(exc)
    found = set(_CODE_RE.findall(message))
    defect_codes = found - _GENERIC_WRAPPER_CODES
    assert expected in message, f"missing expected {expected} in: {message}"
    assert defect_codes == {expected}, (
        f"expected only defect code {expected}, found {sorted(defect_codes)} in: {message}"
    )


@pytest.mark.parametrize(
    ("label", "mutate", "code"),
    _LOCATED_ERROR_CASES,
    ids=[case[0] for case in _LOCATED_ERROR_CASES],
)
def test_corrupted_skill_raises_dedicated_located_code(
    corrupt_root: Path,
    label: str,
    mutate: Callable[[Path], None],
    code: str,
) -> None:
    del label
    mutate(corrupt_root)

    with pytest.raises((SkillLoadError, GraphAgentFatalError)) as exc:
        SkillLoader().compile_skill(corrupt_root, skill_resolver=_resolver_for(corrupt_root))

    message = str(exc.value)
    _assert_unique_defect_code(exc.value, code)
    assert any(marker in message for marker in _SOURCE_FILE_MARKERS), message


def test_unresolvable_subgraph_target_raises_skill_not_registered(corrupt_root: Path) -> None:
    # Resolver knows the echo subagent but not the expander subgraph target.
    resolver = DictSkillResolver({"e2e.echo": corrupt_root / "registry" / "echo"})

    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(corrupt_root, skill_resolver=resolver)

    _assert_unique_defect_code(exc.value, "[F-v3-skill-not-registered]")


def test_missing_resolver_raises_resolver_missing(corrupt_root: Path) -> None:
    # The skill declares a subgraph + subagent, so a resolver is mandatory.
    with pytest.raises(SkillLoadError) as exc:
        SkillLoader().compile_skill(corrupt_root, skill_resolver=None)

    _assert_unique_defect_code(exc.value, "[F-v3-resolver-missing]")
