"""Tests for template variable lifecycle validation."""

from __future__ import annotations

import pytest
from graph_agent.core.manifest import GraphSkillDef
from graph_agent.core.template import MissingContextError, _render_user_prompt
from graph_agent.core.validators.template_variables import (
    check_template_variables,
    find_template_variables,
)


def _manifest(phases: list[dict], context_mapping: dict[str, str] | None = None) -> GraphSkillDef:
    return GraphSkillDef.model_validate(
        {
            "schema_version": "2.0",
            "type": "graph",
            "name": "template-test",
            "description": "template-test",
            "context_mapping": context_mapping or {},
            "io": {
                "inputs": [
                    {"name": "chapter_content", "source": "runtime"},
                    {"name": "chapter_number", "source": "runtime"},
                ],
                "outputs": [],
            },
            "phases": phases,
        }
    )


def _llm_phase(
    name: str,
    template: str,
    *,
    hoist_to: str | None = None,
) -> dict:
    phase = {
        "name": name,
        "mode": "llm",
        "user_prompt_template": template,
        "prompt": "Do the work.",
    }
    if hoist_to:
        phase["hoist_to"] = hoist_to
    return phase


def test_find_template_variables_ignores_escaped_braces() -> None:
    assert find_template_variables("{chapter_content} {{escaped}} {{{ignored}}}") == {
        "chapter_content"
    }


def test_template_vars_accept_inputs_context_mapping_and_prior_hoist() -> None:
    manifest = _manifest(
        [
            _llm_phase("segment", "Chapter {chapter_content} / {prepared}", hoist_to="segments"),
            _llm_phase("review", "Review {segments} for chapter {chapter_number}"),
        ],
        context_mapping={"prepared": ""},
    )

    assert check_template_variables(manifest) == []


def test_template_vars_reject_missing_producer() -> None:
    manifest = _manifest(
        [
            _llm_phase("segment", "Missing {raw_segmentation}"),
        ]
    )

    issues = check_template_variables(manifest)

    assert len(issues) == 1
    assert issues[0].rule_id == "F-TEMPLATE-VAR-UNDECLARED"
    assert issues[0].severity == "FATAL"
    assert "{raw_segmentation}" in issues[0].message
    assert "Available variables at this phase" in issues[0].message


def test_template_vars_reject_forward_reference() -> None:
    manifest = _manifest(
        [
            _llm_phase("review", "Review {segments}"),
            _llm_phase("segment", "Chapter {chapter_content}", hoist_to="segments"),
        ]
    )

    issues = check_template_variables(manifest)

    assert [issue.rule_id for issue in issues] == ["F-TEMPLATE-VAR-UNDECLARED"]
    assert "phase 'review'" in issues[0].message


def test_render_user_prompt_raises_friendly_missing_context() -> None:
    manifest = _manifest(
        [
            _llm_phase("segment", "Need {chapter_content} and {segments}"),
        ]
    )
    phase = manifest.phases[0]

    with pytest.raises(MissingContextError) as exc_info:
        _render_user_prompt(phase, {"chapter_content": "text"})

    message = str(exc_info.value)
    assert "Phase 'segment'" in message
    assert "segments" in message
    assert "hoist_to" in message
    assert "当前可用变量" in message
