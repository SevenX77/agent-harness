from __future__ import annotations

from graph_agent.cognitive.prompt import apply_v030_cognitive_template


def test_v030_exit_contract_is_hardcoded_at_prompt_tail() -> None:
    prompt = apply_v030_cognitive_template(
        phase_name="main",
        role="Researcher",
        goal="Answer.",
        steps=[],
        protocols=[],
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
    )

    assert prompt.count("\n<exit_contract>\n") == 1
    assert prompt.rstrip().endswith("</exit_contract>")
    exit_contract = prompt[prompt.index("<exit_contract>") :]
    assert "finish_task" in exit_contract
    assert "output_schema" in exit_contract
    assert "answer" in exit_contract
