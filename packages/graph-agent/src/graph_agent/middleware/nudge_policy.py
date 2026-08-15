"""NudgePolicy — the single strategy source for exit-control nudges.

Migration decision 2026-08-15 §3.5: the explainable nudge policy that
lived in the dead family (``core/nudge_injector.py`` gates +
``cognitive/finish.py`` texts) moves here verbatim as the ONE place
that decides when to nudge and with which words; the live
``ExitControlMiddleware`` stays a middleware-side adapter over it
(WS-E8 constraint: adapter over the existing policy, never a second
unexplainable policy). The dead-side modules are untouched and fall
with the family in the follow-up removal PR.

Two deliberate divergences from the dead side, both mandated by §3.5:

* Budget is check-before-increment for ALL three gates. The dead side
  carried an increment-before-check FIXME quirk on planning/standard —
  a condition hit with no budget left still bumped the counters, which
  could starve a later cross-type nudge out of the global cap. Fixed
  at the source (§3.5 目标设计 5); the regression test pins the exact
  divergent sequence.
* The policy is pure decision logic: no callbacks, no message objects,
  no state reads. The adapter owns HumanMessage construction, typed
  NudgeEvent emission, and state extraction (§3.5 目标设计 1/4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

NudgeKind = Literal["planning", "selfcheck", "standard"]

#: Per-kind nudge budget. User ruling (plan.md 悬决表 #1, Task 6.5):
#: "保留但降权:默认 max_nudges=1"; the global cap stays max_nudges * 2.
DEFAULT_MAX_NUDGES = 1

#: A finish_task submission counts as self-checked when its diagnostics
#: or reasoning reach this many characters (dead-side bar, kept as-is).
MIN_FINISH_REASONING_LEN = 30

PLANNING_NUDGE = (
    "[系统提示] 在执行任何业务工具之前，你必须先调用 update_working_memory "
    "记录你的执行计划。计划应包含：\n"
    "1. 本阶段的目标是什么\n"
    "2. 你打算按什么顺序执行哪些步骤\n"
    "3. 每步需要什么数据（如果需要从上下文或工具获取，写明）\n"
    "4. 预期产出是什么\n"
    "请现在调用 update_working_memory。"
)

SELFCHECK_NUDGE = (
    "[系统提示] 你调用了 finish_task，但缺少必要字段。"
    "请重新调用 finish_task，并提供："
    "diagnostics_md（自检诊断 Markdown，逐条对照计划说明质量结论）"
    "+ business_data_md（业务输出 Markdown，遵循 phase 的 output_schema）。"
)


def build_standard_nudge_text(nudge_count: int, latest_content: str) -> str:
    """Build escalating nudge text for plain-text model outputs."""
    if nudge_count == 1:
        return (
            "[系统提示] 你输出了文本但未调用 finish_task。"
            "如果任务已完成，请调用 finish_task 并在 reasoning 中逐条自检计划完成度；"
            "如果未完成，请继续使用工具。"
        )
    if nudge_count == 2:
        return (
            "[系统警告] 这是第二次提醒。你必须调用工具（如 finish_task）来推进状态，"
            "纯文本输出是无效的。请立即修正。"
            f"\n你的无效输出: {latest_content[:600]}"
        )
    return (
        "[严重警告] 你的行为已偏离规范！必须立即调用 finish_task 结束本阶段，否则任务将被强制终止。"
    )


@dataclass(frozen=True)
class NudgeDecision:
    """Outcome of one gate consultation.

    Attributes
    ----------
    text:
        The nudge text to inject, or ``None`` when nothing should be
        injected.
    kind:
        Which gate produced the decision; ``None`` on a silent decline.
    count:
        Per-kind counter after this decision (0 when nothing has been
        counted for that kind yet).
    counted:
        ``True`` only when this decision consumed one budget unit. The
        selfcheck validation-error echo returns text WITHOUT counting.
    budget_exhausted:
        ``True`` only when the triggering condition was met but a budget
        gate blocked the injection.
    """

    text: str | None
    kind: NudgeKind | None = None
    count: int = 0
    counted: bool = False
    budget_exhausted: bool = False


_NO_NUDGE = NudgeDecision(text=None)


class NudgePolicy:
    """Three-gate nudge state machine for one phase execution.

    Counters are scoped to a single graph invoke — the adapter keeps one
    instance per thread key, mirroring its iteration budget.
    """

    def __init__(self, max_nudges: int = DEFAULT_MAX_NUDGES) -> None:
        self._max_nudges = max_nudges
        self._counters: dict[str, int] = {"planning": 0, "selfcheck": 0, "standard": 0}
        self._total = 0

    # ----- gates --------------------------------------------------------

    def try_selfcheck(self, finish_payload: dict[str, Any]) -> NudgeDecision:
        """Judge a finish_task payload that reached the gate unqualified.

        A schema-validation failure echoes the validation error text and
        never consumes budget (the model is being corrected, not nudged);
        a payload that clears the structured-selfcheck bar needs nothing;
        anything else earns SELFCHECK_NUDGE within budget.
        """
        if finish_payload.get("schema_validation") == "failed":
            error_text = finish_payload.get(
                "validation_error_text",
                "Schema validation failed.",
            )
            return NudgeDecision(
                text=str(error_text),
                kind="selfcheck",
                count=self._counters["selfcheck"],
            )
        if self._has_structured_selfcheck(finish_payload):
            return _NO_NUDGE
        if self._consume("selfcheck"):
            return NudgeDecision(
                text=SELFCHECK_NUDGE,
                kind="selfcheck",
                count=self._counters["selfcheck"],
                counted=True,
            )
        return NudgeDecision(text=None, kind="selfcheck", budget_exhausted=True)

    def try_planning(
        self,
        latest_content: str,
        *,
        has_tool_calls: bool,
        has_plan: bool,
    ) -> NudgeDecision:
        """Nudge the model to record a plan first (§3.5 目标设计 3).

        Trigger: the model produced text, called no tools, and
        ``flow.working_memory`` carries no plan yet.
        """
        if not latest_content or has_tool_calls or has_plan:
            return _NO_NUDGE
        if self._consume("planning"):
            return NudgeDecision(
                text=PLANNING_NUDGE,
                kind="planning",
                count=self._counters["planning"],
                counted=True,
            )
        return NudgeDecision(text=None, kind="planning", budget_exhausted=True)

    def try_standard(self, latest_content: str, *, has_tool_calls: bool) -> NudgeDecision:
        """Generic "don't just talk — use tools or finish" fallback gate."""
        if not latest_content or has_tool_calls:
            return _NO_NUDGE
        if self._consume("standard"):
            count = self._counters["standard"]
            return NudgeDecision(
                text=build_standard_nudge_text(count, latest_content),
                kind="standard",
                count=count,
                counted=True,
            )
        return NudgeDecision(text=None, kind="standard", budget_exhausted=True)

    # ----- observation ---------------------------------------------------

    def counts(self) -> dict[str, int]:
        """Counter snapshot for tests / diagnostics / failure messages."""
        snapshot: dict[str, int] = dict(self._counters)
        snapshot["total"] = self._total
        return snapshot

    # ----- private helpers ------------------------------------------------

    def _consume(self, kind: NudgeKind) -> bool:
        """Check both budget gates, and count only when the nudge fires."""
        per_kind = self._counters[kind]
        if per_kind < self._max_nudges and self._total < self._max_nudges * 2:
            self._counters[kind] = per_kind + 1
            self._total += 1
            return True
        return False

    @staticmethod
    def _has_structured_selfcheck(payload: dict[str, Any]) -> bool:
        """True iff the finish_task payload meets the structured-selfcheck bar.

        Accepted when either structured business output has passed schema
        validation, diagnostics are substantive, or the minimal no-schema
        completion text is substantive. Validation failures are intercepted
        earlier in ``try_selfcheck``.
        """
        schema_status = payload.get("schema_validation")
        business_data_md = str(payload.get("business_data_md", "")).strip()
        if business_data_md and schema_status == "passed":
            return True

        diagnostics_md = str(payload.get("diagnostics_md", "")).strip()
        if len(diagnostics_md) >= MIN_FINISH_REASONING_LEN:
            return True

        reasoning_text = str(payload.get("reasoning", "")).strip()
        return len(reasoning_text) >= MIN_FINISH_REASONING_LEN


__all__ = [
    "DEFAULT_MAX_NUDGES",
    "MIN_FINISH_REASONING_LEN",
    "PLANNING_NUDGE",
    "SELFCHECK_NUDGE",
    "NudgeDecision",
    "NudgeKind",
    "NudgePolicy",
    "build_standard_nudge_text",
]
