from __future__ import annotations

from pathlib import Path

import pytest
from graph_agent.core.exceptions import SkillLoadError
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentNodeAST, SubgraphNodeAST
from graph_agent.core.validator_contract import VALIDATOR_ERROR_CODES, VALIDATOR_SIGNATURE
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[4]
GAMMA0_SPEC_DIR = (
    REPO_ROOT / ".kiro/specs/engine-mvp0-rebuild-v030/round-10-PR-gamma0-contract-patch"
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_v030_graph(root: Path, *, mode: str = "agent") -> None:
    phase_file = "SKILL.md" if mode == "agent" else "SUBGRAPH.md"
    _write(
        root / "GRAPH.md",
        """---
schema_version: "0.3.0"
name: gamma0-contract
io:
  inputs:
    type: object
    properties: {}
  outputs:
    type: object
    properties: {}
phases:
  - id: main
    src: phases/main
    depends_on: []
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(root / "phases" / "main" / phase_file, "")


def _write_agent_phase(
    root: Path,
    *,
    validator: bool | None = None,
    include_exit_contract: bool = False,
) -> None:
    validator_line = "" if validator is None else f"validator: {str(validator).lower()}\n"
    exit_contract = (
        """
<exit_contract>
Return via finish_task.
</exit_contract>
"""
        if include_exit_contract
        else ""
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
mode: agent
name: main
{validator_line}phase_config:
  tools:
    - finish_task
---
<role>
Research assistant.
</role>
<goal>
Return a concise answer.
</goal>
<step id="S1" name="Do">
Do the task.
</step>
<protocol id="P1">
Follow the instructions.
</protocol>
{exit_contract}
""",
    )


def _write_subgraph_phase(root: Path, *, validator: bool | None = None) -> None:
    validator_line = "" if validator is None else f"validator: {str(validator).lower()}\n"
    _write(
        root / "phases" / "main" / "SUBGRAPH.md",
        f"""---
mode: subgraph
name: main
target_skill: child-skill
{validator_line}---
""",
    )


def test_γ0_1_agent_body_without_exit_contract_loads_successfully(tmp_path: Path) -> None:
    _write_v030_graph(tmp_path)
    _write_agent_phase(tmp_path, include_exit_contract=False)

    compiled = SkillLoader().compile_skill(tmp_path)

    ast = compiled.nodes[0].ast
    assert isinstance(ast, AgentNodeAST)
    assert not hasattr(ast, "exit_contract")


def test_γ0_1_legacy_exit_contract_tag_is_rejected_for_v030_agent(tmp_path: Path) -> None:
    _write_v030_graph(tmp_path)
    _write_agent_phase(tmp_path, include_exit_contract=True)

    with pytest.raises(SkillLoadError, match="exit_contract"):
        SkillLoader().compile_skill(tmp_path)


def test_γ0_2_agent_node_validator_defaults_false() -> None:
    ast = AgentNodeAST.model_validate(
        {
            "mode": "agent",
            "role": "Research assistant.",
            "goal": "Return a concise answer.",
        }
    )

    assert ast.validator is False


def test_γ0_2_agent_loader_accepts_validator_true(tmp_path: Path) -> None:
    _write_v030_graph(tmp_path)
    _write_agent_phase(tmp_path, validator=True, include_exit_contract=False)

    compiled = SkillLoader().compile_skill(tmp_path)

    ast = compiled.nodes[0].ast
    assert isinstance(ast, AgentNodeAST)
    assert ast.validator is True


def test_validator_non_bool_fatal() -> None:
    with pytest.raises(ValidationError):
        AgentNodeAST.model_validate(
            {
                "mode": "agent",
                "role": "Research assistant.",
                "goal": "Return a concise answer.",
                "validator": "maybe",
            }
        )


def test_γ0_2_subgraph_node_validator_defaults_false() -> None:
    ast = SubgraphNodeAST.model_validate(
        {
            "mode": "subgraph",
            "target_skill": "child-skill",
        }
    )

    assert ast.validator is False


def test_γ0_2_subgraph_loader_accepts_validator_true(tmp_path: Path) -> None:
    _write_v030_graph(tmp_path, mode="subgraph")
    _write_subgraph_phase(tmp_path, validator=True)

    compiled = SkillLoader().compile_skill(tmp_path)

    ast = compiled.nodes[0].ast
    assert isinstance(ast, SubgraphNodeAST)
    assert ast.validator is True


def test_γ0_3_middleware_order_contract_constant_exists() -> None:
    from graph_agent import middleware

    assert middleware.MVP0_MIDDLEWARE_ORDER_CONTRACT == (
        "ProtocolValidation",
        "CognitiveFlow",
        "ExecutionControl",
        "Tracing",
        "ToolError",
        "LoopDetection",
    )


def test_γ0_3_current_middleware_class_order_matches_contract_prefix() -> None:
    from graph_agent import middleware

    implemented_prefix = tuple(cls.__name__.replace("Middleware", "") for cls in middleware.DEFAULT_MIDDLEWARE_ORDER)

    assert implemented_prefix == middleware.MVP0_MIDDLEWARE_ORDER_CONTRACT[:3]


def test_γ0_4_validator_signature_and_error_placeholders_are_documented() -> None:
    docs = "\n".join(path.read_text(encoding="utf-8") for path in GAMMA0_SPEC_DIR.glob("*.md"))

    assert "def validate(output: dict, state_slice: dict, **kwargs) -> None | dict" in docs
    assert "[F-v3-agent-validator-failed]" in docs
    assert "[F-v3-subgraph-validator-failed]" in docs
    assert "[F-v3-logic-validator-failed]" in docs
    assert VALIDATOR_SIGNATURE == "def validate(output: dict, state_slice: dict, **kwargs) -> None | dict"
    assert VALIDATOR_ERROR_CODES == (
        "[F-v3-agent-validator-failed]",
        "[F-v3-subgraph-validator-failed]",
        "[F-v3-logic-validator-failed]",
    )


def test_γ0_5_docs_ship_gates_match_source_contract() -> None:
    tasks = (GAMMA0_SPEC_DIR / "tasks.md").read_text(encoding="utf-8")
    manifest = (REPO_ROOT / "packages/graph-agent/src/graph_agent/core/manifest.py").read_text(
        encoding="utf-8"
    )
    middleware_init = (
        REPO_ROOT / "packages/graph-agent/src/graph_agent/middleware/__init__.py"
    ).read_text(encoding="utf-8")

    assert "AgentNodeAST` 不再含 `exit_contract` 字段" in tasks
    assert "class AgentNodeAST" in manifest
    agent_block = manifest.split("class AgentNodeAST", 1)[1].split("class SkillNodeAST", 1)[0]
    assert "exit_contract" not in agent_block
    assert "validator: bool = False" in agent_block
    assert "MVP0_MIDDLEWARE_ORDER_CONTRACT" in middleware_init
