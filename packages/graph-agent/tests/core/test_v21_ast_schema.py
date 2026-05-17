from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from graph_agent.core.manifest import LogicNodeAST, PhaseAST, SkillNodeAST, SubgraphNodeAST
from pydantic import TypeAdapter

_GOLDEN_DIR = Path(__file__).parents[1] / "golden" / "schema"
_UPDATE_HINT = (
    "AST schema golden mismatch. If this is an intentional V2.1 schema "
    "contract change, run `python -m scripts.update_ast_golden` and review "
    "the snapshot diff."
)


def _load_golden(name: str) -> dict[str, Any]:
    return json.loads((_GOLDEN_DIR / name).read_text(encoding="utf-8"))


def test_logic_node_ast_schema_matches_golden() -> None:
    assert LogicNodeAST.model_json_schema() == _load_golden(
        "logic_node_ast.schema.json"
    ), _UPDATE_HINT


def test_subgraph_node_ast_schema_matches_golden() -> None:
    assert SubgraphNodeAST.model_json_schema() == _load_golden(
        "subgraph_node_ast.schema.json"
    ), _UPDATE_HINT


def test_skill_node_ast_schema_matches_golden() -> None:
    assert SkillNodeAST.model_json_schema() == _load_golden(
        "skill_node_ast.schema.json"
    ), _UPDATE_HINT


def test_phase_ast_union_schema_matches_golden() -> None:
    assert TypeAdapter(PhaseAST).json_schema() == _load_golden(
        "phase_ast_union.schema.json"
    ), _UPDATE_HINT
