from __future__ import annotations

from pathlib import Path

from graph_agent.cognitive.prompt import apply_v030_cognitive_template
from graph_agent.core.loader import SkillLoader
from graph_agent.core.manifest import AgentNodeAST

FIXTURE = Path(__file__).parent / "v030_agent_demo"


class InMemorySkillResolver:
    def __init__(self, mapping: dict[str, Path]) -> None:
        self.mapping = mapping

    def resolve_skill(self, skill_id: str) -> Path:
        return self.mapping[skill_id]


def test_v030_agent_demo_fixture_compiles_and_renders_template() -> None:
    resolver = InMemorySkillResolver({"demo.echo_agent": FIXTURE / "registry" / "echo_agent"})

    compiled = SkillLoader().compile_skill(FIXTURE, skill_resolver=resolver)
    ast = compiled.nodes[0].ast

    assert compiled.manifest.schema_version == "0.3.0"
    assert isinstance(ast, AgentNodeAST)
    assert ast.role == "You are a narrative segmentation editor."
    assert ast.goal.startswith("Segment chapter_content")
    assert [step.id for step in ast.steps] == ["S1", "S2", "S3"]
    assert ast.protocols[0].id == "P1"
    assert ast.references[0].id == "R1"
    assert {example.id for example in ast.examples} == {"E1", "E2"}
    assert compiled.subagents_by_phase["segment"][0].target_skill == "demo.echo_agent"

    prompt = apply_v030_cognitive_template(
        phase_name="segment",
        role=ast.role,
        goal=ast.goal,
        steps=[step.model_dump() for step in ast.steps],
        protocols=[protocol.model_dump() for protocol in ast.protocols],
        exit_contract=ast.exit_contract,
        output_schema=ast.io.outputs if ast.io is not None else None,
        inline_examples=[
            example.content for example in ast.examples if example.type == "inline" and example.content
        ],
        document_examples=[
            {"id": example.id, "summary": example.summary or ""}
            for example in ast.examples
            if example.type == "document"
        ],
    )

    for slot in [
        "<role>",
        "<goal>",
        "<thinking_style>",
        "<knowledge_base>",
        "<examples>",
        "<ambiguity_feedback>",
        "<protocol_citation>",
        "<critical_reminders>",
        "<exit_contract>",
    ]:
        assert slot in prompt
    assert "Long mixed timeline segmentation example." in prompt
    assert "<output_schema>" in prompt
