"""Tests for cognitive prompt composition helpers."""

from __future__ import annotations

import logging

import pytest

from graph_agent.cognitive.prompt import (
    apply_cognitive_template,
    apply_v030_cognitive_template,
    resolve_role_prefix_from_llm_role,
)


def _compose_with_role_prefix(role_prefix: str) -> str:
    return apply_cognitive_template(
        phase_name="phaseA",
        skill_system_prompt="Do the work.",
        data_architecture=None,
        role_prefix=role_prefix,
    )


def test_engine_no_longer_reads_role_prefix_from_llm_role() -> None:
    prefix = resolve_role_prefix_from_llm_role("architect")

    prompt = _compose_with_role_prefix(prefix)

    assert prefix == ""
    assert "<role_prefix>" not in prompt


def test_role_prefix_empty_when_llm_role_none() -> None:
    prefix = resolve_role_prefix_from_llm_role(None)

    prompt = _compose_with_role_prefix(prefix)

    assert prefix == ""
    assert "<role_prefix>" not in prompt


def test_unknown_llm_role_does_not_read_role_config(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)

    prefix = resolve_role_prefix_from_llm_role("does_not_exist")
    prompt = _compose_with_role_prefix(prefix)

    assert prefix == ""
    assert "<role_prefix>" not in prompt
    assert caplog.text == ""


def test_critical_reminders_use_finish_task_v2_contract() -> None:
    prompt = _compose_with_role_prefix("")

    assert "diagnostics_md" in prompt
    assert "business_data_md" in prompt
    assert "execution_summary" not in prompt
    assert "plan_checklist" not in prompt
    assert "unresolved_issues" not in prompt


def test_v030_cognitive_template_places_exit_contract_with_output_schema() -> None:
    prompt = apply_v030_cognitive_template(
        phase_name="main",
        role="Researcher",
        goal="Answer the question.",
        steps=[{"id": "S1", "name": "Read", "content": "Read references."}],
        protocols=[{"id": "P1", "content": "Cite evidence."}],
        output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        inline_examples=["Example A"],
        document_examples=[{"id": "E2", "summary": "Long example"}],
    )

    assert "<knowledge_base>" in prompt
    assert "<ambiguity_feedback>" in prompt
    assert "<protocol_citation>" in prompt
    assert "[protocol:P1]" in prompt
    assert "Example A" in prompt
    assert "E2: Long example" in prompt
    assert "<output_schema>" in prompt
    assert prompt.rfind("<output_schema>") > prompt.rfind("Call finish_task")
