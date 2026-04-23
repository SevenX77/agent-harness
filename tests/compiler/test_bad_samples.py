"""Compiler regression: bad-samples must trigger expected FATAL rules (D-5.6).

Each sample under ``skills/examples/bad-samples/<pattern>/SKILL.md`` is
a hand-crafted anti-pattern that should produce exactly one expected
FATAL rule. If any of these stops firing, the compiler has regressed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "core"))

from graph_agent.core.compiler import compile_skill  # noqa: E402


_BAD_SAMPLES_ROOT = Path(__file__).resolve().parents[2] / "skills" / "examples" / "bad-samples"


@pytest.mark.parametrize("sample_dir,expected_rule", [
    ("subgraph-with-tools", "F-subgraph-exclusive-tools"),
    ("subgraph-with-prompt", "F-subgraph-exclusive-prompt"),
    ("subgraph-with-sub-skills", "F-subgraph-exclusive-sub-skills"),
])
def test_subgraph_exclusive_bad_samples_trigger_expected_fatal(
    sample_dir: str, expected_rule: str
) -> None:
    skill_path = _BAD_SAMPLES_ROOT / sample_dir / "SKILL.md"
    assert skill_path.exists(), f"bad-sample missing: {skill_path}"

    result = compile_skill(skill_path)

    fatal_ids = [i.rule_id for i in result.fatals]
    assert expected_rule in fatal_ids, (
        f"expected {expected_rule} in fatals for {sample_dir}; got {fatal_ids}"
    )
    # Anti-pattern samples must never pass compilation.
    assert not result.passed, f"bad-sample {sample_dir} should fail compile"


def test_step_expression_attribute_triggers_fatal() -> None:
    skill_path = _BAD_SAMPLES_ROOT / "step-no-expression" / "SKILL.md"
    assert skill_path.exists(), f"bad-sample missing: {skill_path}"

    result = compile_skill(skill_path)

    fatal_ids = [i.rule_id for i in result.fatals]
    assert "F-step-no-expression" in fatal_ids, (
        f"expected F-step-no-expression in fatals; got {fatal_ids}"
    )


def test_bad_samples_dir_has_at_least_four_samples() -> None:
    """Guard against accidentally removing samples — the parametrized
    tests above would silently go away if the directory were emptied.
    """
    samples = [
        p for p in _BAD_SAMPLES_ROOT.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    ]
    assert len(samples) >= 4, (
        f"expected at least 4 bad-sample skills under {_BAD_SAMPLES_ROOT}; "
        f"found {len(samples)}: {[p.name for p in samples]}"
    )
