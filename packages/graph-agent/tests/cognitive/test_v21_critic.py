from __future__ import annotations

import pytest
from graph_agent.cognitive.critic import (
    CriticMetrics,
    CriticVerdict,
    FakeCriticClient,
    LLMCriticClient,
    build_critic_tool,
)


def test_critic_pass_verdict() -> None:
    client = FakeCriticClient(CriticVerdict(passed=True, reasons=["ok"]))
    tool, metrics = build_critic_tool("reviewer", "Review for quality", client)

    result = tool.invoke({"target_text": "draft", "criteria": "quality"})

    assert result["passed"] is True
    assert result["reasons"] == ["ok"]
    assert metrics.invocations == 1
    assert metrics.passed == 1
    assert metrics.rejected == 0


def test_critic_reject_verdict() -> None:
    client = FakeCriticClient(
        CriticVerdict(passed=False, reasons=["bad"], suggestions=["fix X"])
    )
    tool, metrics = build_critic_tool("auditor", "Audit for defects", client)

    result = tool.invoke({"target_text": "draft", "criteria": "correctness"})

    assert result["passed"] is False
    assert result["reasons"] == ["bad"]
    assert result["suggestions"] == ["fix X"]
    assert metrics.invocations == 1
    assert metrics.passed == 0
    assert metrics.rejected == 1


def test_critic_multiple_invocations() -> None:
    client = FakeCriticClient(CriticVerdict(passed=True, reasons=["ok"]))
    tool, metrics = build_critic_tool("critic_quality", "Review for quality", client)

    for _ in range(3):
        tool.invoke({"target_text": "draft", "criteria": "quality"})

    assert metrics.invocations == 3
    assert metrics.passed == 3
    assert metrics.rejected == 0


def test_critic_metrics_shared() -> None:
    shared = CriticMetrics()
    client = FakeCriticClient(CriticVerdict(passed=True))

    _, metrics = build_critic_tool("reviewer", "Review", client, metrics=shared)

    assert metrics is shared


def test_llm_critic_client_stub_raises() -> None:
    with pytest.raises(NotImplementedError, match="T1.5 LangGraph"):
        LLMCriticClient().review("draft", "quality")


def test_critic_tool_name_and_description() -> None:
    client = FakeCriticClient(CriticVerdict(passed=True))
    tool, _ = build_critic_tool("reviewer", "Review for quality", client)

    assert tool.name == "reviewer"
    assert "Review for quality" in tool.description


def test_critic_tool_pydantic_args_schema() -> None:
    client = FakeCriticClient(CriticVerdict(passed=True))
    tool, _ = build_critic_tool("reviewer", "Review", client)

    parsed = tool.args_schema(target_text="draft", criteria="quality")

    assert parsed.target_text == "draft"
    assert parsed.criteria == "quality"
    with pytest.raises(ValueError):
        tool.args_schema(target_text="draft")


def test_critic_attempt_increments() -> None:
    client = FakeCriticClient(CriticVerdict(passed=True))
    tool, _ = build_critic_tool("reviewer", "Review", client)

    for _ in range(3):
        tool.invoke({"target_text": "draft", "criteria": "quality"})

    assert [call["attempt"] for call in client.calls] == [1, 2, 3]


def test_critic_phase_isolation() -> None:
    client_a = FakeCriticClient(CriticVerdict(passed=True))
    client_b = FakeCriticClient(CriticVerdict(passed=False))
    tool_a, metrics_a = build_critic_tool("reviewer_a", "Review A", client_a)
    tool_b, metrics_b = build_critic_tool("reviewer_b", "Review B", client_b)

    tool_a.invoke({"target_text": "draft", "criteria": "quality"})
    tool_b.invoke({"target_text": "draft", "criteria": "risk"})

    assert metrics_a.invocations == 1
    assert metrics_a.passed == 1
    assert metrics_a.rejected == 0
    assert metrics_b.invocations == 1
    assert metrics_b.passed == 0
    assert metrics_b.rejected == 1
