from __future__ import annotations

from graph_agent.cognitive.prompt import apply_v030_cognitive_template


def _prompt() -> str:
    return apply_v030_cognitive_template(
        phase_name="main",
        role="Researcher",
        goal="Answer with evidence from @reference:R1 and @example:E2.",
        steps=[{"id": "S1", "name": "Read", "content": "Read the registered reference."}],
        protocols=[{"id": "P1", "content": "Cite every claim."}],
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        knowledge_base="Aligned concepts and critical corrections.\n- R1: Primary guide",
        inline_examples=["Inline example body."],
        document_examples=[{"id": "E2", "summary": "Document example summary"}],
    )


def test_v030_template_renders_the_eight_ground_truth_slots() -> None:
    prompt = _prompt()

    slots = [
        "role",
        "goal",
        "thinking_style",
        "knowledge_base",
        "examples",
        "ambiguity_feedback",
        "protocol_citation",
        "critical_reminders",
    ]

    for slot in slots:
        assert f"<{slot}>" in prompt
        assert f"</{slot}>" in prompt


def test_v030_template_has_no_deprecated_steps_or_document_examples_shell() -> None:
    prompt = _prompt()

    assert "<steps>" not in prompt
    assert "</steps>" not in prompt
    assert "<document_examples>" not in prompt
    assert "</document_examples>" not in prompt


def test_v030_template_places_step_body_under_thinking_style() -> None:
    prompt = _prompt()
    thinking = prompt[prompt.index("<thinking_style>") : prompt.index("</thinking_style>")]

    assert "建议步骤:" in thinking
    assert "[S1]" in thinking
    assert "Read the registered reference." in thinking


def test_v030_template_knowledge_base_contains_reader_output_and_reference_listing() -> None:
    prompt = _prompt()
    knowledge_base = prompt[prompt.index("<knowledge_base>") : prompt.index("</knowledge_base>")]

    assert "Aligned concepts and critical corrections." in knowledge_base
    assert "R1: Primary guide" in knowledge_base
    assert "read_reference" in knowledge_base
    assert "当前可用 Reference 注册清单" in knowledge_base


def test_v030_template_examples_contains_inline_and_document_registry_listing() -> None:
    prompt = _prompt()
    examples = prompt[prompt.index("<examples>") : prompt.index("</examples>")]

    assert "Inline example body." in examples
    assert "E2: Document example summary" in examples


def test_v030_template_exit_contract_is_trailing_and_contains_output_schema() -> None:
    prompt = _prompt()

    assert "<exit_contract>" in prompt
    assert "output_schema" in prompt[prompt.index("<exit_contract>") :]
    assert "answer" in prompt[prompt.index("<exit_contract>") :]
    assert prompt.rstrip().endswith("</exit_contract>")
    assert prompt.rfind("<exit_contract>") > prompt.rfind("</critical_reminders>")
