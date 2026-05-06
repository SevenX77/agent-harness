"""Tests for cognitive prompt composition helpers."""

from __future__ import annotations

import logging

from graph_agent.cognitive.prompt import (
    apply_cognitive_template,
    resolve_role_prefix_from_llm_role,
)


def _compose_with_role_prefix(role_prefix: str) -> str:
    return apply_cognitive_template(
        phase_name="phaseA",
        skill_system_prompt="Do the work.",
        data_architecture=None,
        role_prefix=role_prefix,
    )


def test_role_prefix_injected_when_llm_role_set() -> None:
    prefix = resolve_role_prefix_from_llm_role("architect")

    prompt = _compose_with_role_prefix(prefix)

    assert prefix
    assert "<role_prefix>" in prompt
    assert "严谨的故事结构与逻辑一致性专家" in prompt


def test_role_prefix_empty_when_llm_role_none() -> None:
    prefix = resolve_role_prefix_from_llm_role(None)

    prompt = _compose_with_role_prefix(prefix)

    assert prefix == ""
    assert "<role_prefix>" not in prompt


def test_unknown_llm_role_fallback(caplog) -> None:
    caplog.set_level(logging.WARNING)

    prefix = resolve_role_prefix_from_llm_role("does_not_exist")
    prompt = _compose_with_role_prefix(prefix)

    assert prefix == ""
    assert "<role_prefix>" not in prompt
    assert "does_not_exist" in caplog.text


def test_critical_reminders_use_finish_task_v2_contract() -> None:
    prompt = _compose_with_role_prefix("")

    assert "diagnostics_md" in prompt
    assert "business_data_md" in prompt
    assert "execution_summary" not in prompt
    assert "plan_checklist" not in prompt
    assert "unresolved_issues" not in prompt
