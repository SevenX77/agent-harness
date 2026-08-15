"""NudgePolicy — 三闸触发条件、预算与文案的纯策略单测。

迁移决议 2026-08-15 §3.5:死侧 ``core/nudge_injector.py`` 的 nudge 策略语义
(三闸 + 文案 + 预算 + 结构化自检判定)迁到活侧中间件层,成为唯一策略源。
两处刻意差异(同为决议目标设计条款):

* 预算统一为 check-before-increment(修掉死侧 planning/standard 的
  increment-before-check FIXME quirk,§3.5 目标设计 5)。
* 策略纯化:不发回调、不构造 message 对象——事件与注入归
  ``ExitControlMiddleware`` 适配器(§3.5 目标设计 1/4)。
"""

from __future__ import annotations

from graph_agent.middleware.nudge_policy import (
    MIN_FINISH_REASONING_LEN,
    PLANNING_NUDGE,
    SELFCHECK_NUDGE,
    NudgePolicy,
    build_standard_nudge_text,
)


class TestPlanningGate:
    def test_fires_on_text_only_turn_without_plan(self) -> None:
        policy = NudgePolicy(max_nudges=1)

        decision = policy.try_planning("just talking", has_tool_calls=False, has_plan=False)

        assert decision.text == PLANNING_NUDGE
        assert decision.kind == "planning"
        assert decision.count == 1
        assert decision.counted is True
        assert decision.budget_exhausted is False

    def test_declines_when_tool_calls_present(self) -> None:
        policy = NudgePolicy(max_nudges=1)

        decision = policy.try_planning("text", has_tool_calls=True, has_plan=False)

        assert decision.text is None
        assert decision.budget_exhausted is False
        assert policy.counts()["total"] == 0

    def test_declines_when_no_text_content(self) -> None:
        policy = NudgePolicy(max_nudges=1)

        decision = policy.try_planning("", has_tool_calls=False, has_plan=False)

        assert decision.text is None
        assert decision.budget_exhausted is False

    def test_declines_when_plan_already_recorded(self) -> None:
        policy = NudgePolicy(max_nudges=1)

        decision = policy.try_planning("text", has_tool_calls=False, has_plan=True)

        assert decision.text is None
        assert decision.budget_exhausted is False
        assert policy.counts()["planning"] == 0


class TestSelfcheckGate:
    def test_schema_failed_returns_error_text_without_counting(self) -> None:
        policy = NudgePolicy(max_nudges=1)
        payload = {
            "schema_validation": "failed",
            "validation_error_text": "item 1: answer: field required",
        }

        decision = policy.try_selfcheck(payload)

        assert decision.text == "item 1: answer: field required"
        assert decision.counted is False
        assert decision.budget_exhausted is False
        assert policy.counts() == {"planning": 0, "selfcheck": 0, "standard": 0, "total": 0}

    def test_schema_failed_never_consumes_budget_even_repeated(self) -> None:
        policy = NudgePolicy(max_nudges=1)
        payload = {"schema_validation": "failed"}

        first = policy.try_selfcheck(payload)
        second = policy.try_selfcheck(payload)

        assert first.text == "Schema validation failed."
        assert second.text == "Schema validation failed."
        assert policy.counts()["total"] == 0

    def test_structured_business_output_passes_without_nudge(self) -> None:
        policy = NudgePolicy(max_nudges=1)
        payload = {"schema_validation": "passed", "business_data_md": "## item\n- a: b"}

        decision = policy.try_selfcheck(payload)

        assert decision.text is None
        assert decision.budget_exhausted is False

    def test_substantive_diagnostics_pass_without_nudge(self) -> None:
        policy = NudgePolicy(max_nudges=1)
        payload = {"diagnostics_md": "x" * MIN_FINISH_REASONING_LEN}

        assert policy.try_selfcheck(payload).text is None

    def test_substantive_reasoning_passes_without_nudge(self) -> None:
        policy = NudgePolicy(max_nudges=1)
        payload = {"reasoning": "r" * MIN_FINISH_REASONING_LEN}

        assert policy.try_selfcheck(payload).text is None

    def test_reasoning_below_threshold_gets_selfcheck_nudge(self) -> None:
        policy = NudgePolicy(max_nudges=1)
        payload = {"reasoning": "r" * (MIN_FINISH_REASONING_LEN - 1)}

        decision = policy.try_selfcheck(payload)

        assert decision.text == SELFCHECK_NUDGE
        assert decision.kind == "selfcheck"
        assert decision.count == 1
        assert decision.counted is True

    def test_thin_payload_gets_selfcheck_nudge_until_budget(self) -> None:
        policy = NudgePolicy(max_nudges=1)

        first = policy.try_selfcheck({})
        second = policy.try_selfcheck({})

        assert first.text == SELFCHECK_NUDGE
        assert second.text is None
        assert second.budget_exhausted is True
        assert policy.counts()["selfcheck"] == 1


class TestStandardGate:
    def test_first_nudge_is_gentle_and_mentions_finish_task(self) -> None:
        policy = NudgePolicy(max_nudges=1)

        decision = policy.try_standard("chatty output", has_tool_calls=False)

        assert decision.text is not None
        assert "finish_task" in decision.text
        assert decision.kind == "standard"
        assert decision.count == 1

    def test_second_nudge_escalates_and_echoes_truncated_output(self) -> None:
        policy = NudgePolicy(max_nudges=2)
        long_output = "长" * 700

        policy.try_standard("first", has_tool_calls=False)
        decision = policy.try_standard(long_output, has_tool_calls=False)

        assert decision.text is not None
        assert "[系统警告] 这是第二次提醒" in decision.text
        assert "长" * 600 in decision.text
        assert "长" * 601 not in decision.text

    def test_declines_when_tool_calls_or_no_text(self) -> None:
        policy = NudgePolicy(max_nudges=1)

        assert policy.try_standard("text", has_tool_calls=True).text is None
        assert policy.try_standard("", has_tool_calls=False).text is None
        assert policy.counts()["total"] == 0


class TestBuildStandardNudgeText:
    def test_escalation_ladder(self) -> None:
        assert "finish_task" in build_standard_nudge_text(1, "out")
        assert "[系统警告] 这是第二次提醒" in build_standard_nudge_text(2, "out")
        assert "[严重警告]" in build_standard_nudge_text(3, "out")

    def test_second_reminder_truncates_echo_at_600_chars(self) -> None:
        text = build_standard_nudge_text(2, "a" * 601)
        assert "a" * 600 in text
        assert "a" * 601 not in text


class TestBudget:
    def test_check_before_increment_fixes_dead_side_quirk(self) -> None:
        """条件命中但预算不足时不得计数——死侧 quirk 的反例钉死。

        死侧序列(max_nudges=1):planning 命中并注入(t=1)→ planning 再次
        命中但超额,quirk 仍把 total 抬到 2 → 后续 standard 被全局上限挡死。
        修复后:超额尝试不计数,standard 仍可注入。
        """
        policy = NudgePolicy(max_nudges=1)

        first = policy.try_planning("text", has_tool_calls=False, has_plan=False)
        assert first.text == PLANNING_NUDGE

        blocked = policy.try_planning("text", has_tool_calls=False, has_plan=False)
        assert blocked.text is None
        assert blocked.budget_exhausted is True
        assert policy.counts() == {"planning": 1, "selfcheck": 0, "standard": 0, "total": 1}

        follow_up = policy.try_standard("text", has_tool_calls=False)
        assert follow_up.text is not None, "修复后 standard 不再被 quirk 抬高的 total 挡死"
        assert policy.counts()["total"] == 2

    def test_global_cap_is_twice_max_nudges(self) -> None:
        policy = NudgePolicy(max_nudges=1)
        policy.try_planning("text", has_tool_calls=False, has_plan=False)
        policy.try_standard("text", has_tool_calls=False)

        decision = policy.try_selfcheck({})

        assert decision.text is None
        assert decision.budget_exhausted is True
        assert policy.counts()["total"] == 2

    def test_per_kind_cap_applies_before_global_cap(self) -> None:
        policy = NudgePolicy(max_nudges=2)
        policy.try_standard("text", has_tool_calls=False)
        policy.try_standard("text", has_tool_calls=False)

        decision = policy.try_standard("text", has_tool_calls=False)

        assert decision.text is None
        assert decision.budget_exhausted is True
        assert policy.counts() == {"planning": 0, "selfcheck": 0, "standard": 2, "total": 2}

    def test_default_max_nudges_is_one(self) -> None:
        policy = NudgePolicy()

        assert policy.try_planning("t", has_tool_calls=False, has_plan=False).text is not None
        assert policy.try_planning("t", has_tool_calls=False, has_plan=False).text is None
