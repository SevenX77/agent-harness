"""W3-A / T2: the dynamic probe-rule interpreter reproduces openai/gemini candidates
from config (app/data/probe_candidates_dynamic.json), not hardcoded if/else."""

from __future__ import annotations

from app.services.provider_probe_rules import dynamic_probe_candidate_specs


def _profiles(specs: list[dict[str, object]]) -> list[object]:
    return [spec["profile_id"] for spec in specs]


def test_unconfigured_backends_return_none() -> None:
    # claude/deepseek/ark are STATIC (handled by static_probe_candidate_specs).
    assert dynamic_probe_candidate_specs("claude", "claude-opus-4-1") is None
    assert dynamic_probe_candidate_specs("ark", "doubao-seed-1-6") is None
    assert dynamic_probe_candidate_specs("unknown", "whatever") is None


def test_openai_instruct_rule_uses_completions_only() -> None:
    specs = dynamic_probe_candidate_specs("openai", "gpt-3.5-turbo-instruct")
    assert specs is not None
    assert _profiles(specs) == ["text:openai_completions"]


def test_openai_default_expands_responses_chat_and_reasoning_ladders() -> None:
    specs = dynamic_probe_candidate_specs("openai", "gpt-4o")
    assert specs is not None
    assert _profiles(specs) == [
        "text:openai_responses",
        "text:openai_chat_completions",
        "reasoning:openai_responses:low",
        "reasoning:openai_responses:medium",
        "reasoning:openai_responses:high",
        "reasoning:openai_chat_completions:low",
        "reasoning:openai_chat_completions:medium",
        "reasoning:openai_chat_completions:high",
    ]
    low = next(s for s in specs if s["profile_id"] == "reasoning:openai_responses:low")
    assert low["default_rank"] == 5
    assert low["retry_group"] == "openai:reasoning:gpt-4o"
    assert low["runtime_settings"] == {
        "max_output_tokens": 16,
        "reasoning": {"enabled": True, "effort": "low"},
    }


def test_openai_pro_reasoning_is_responses_only_with_high_effort_and_64_tokens() -> None:
    specs = dynamic_probe_candidate_specs("openai", "gpt-5-pro")
    assert specs is not None
    assert _profiles(specs) == ["text:openai_responses", "reasoning:openai_responses:high"]
    assert specs[0]["runtime_settings"] == {
        "max_output_tokens": 64,
        "reasoning": {"enabled": True, "effort": "high"},
    }


def test_gemini_thinking_level_vs_default() -> None:
    thinking = dynamic_probe_candidate_specs("gemini", "gemini-3-pro")
    assert thinking is not None
    assert _profiles(thinking) == [
        "text:gemini_generate_content:minimal_thinking",
        "thinking:gemini_generate_content:level_low",
    ]
    default = dynamic_probe_candidate_specs("gemini", "gemini-2.0-flash")
    assert default is not None
    assert _profiles(default) == [
        "text:gemini_generate_content:no_thinking",
        "thinking:gemini_generate_content:budget_128",
        "thinking:gemini_generate_content:budget_512",
    ]
