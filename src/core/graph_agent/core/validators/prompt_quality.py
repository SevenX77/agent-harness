"""Prompt-quality validators.

Includes:
- W-PROMPT-DUPLICATION
- W-FINISH-TASK-VISIBILITY
- W-SETUP-PHASE-ANTI-PATTERN
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from ..compiler import CompileIssue

if TYPE_CHECKING:
    from ..manifest import GraphSkillDef, LLMPhase


_DUPLICATION_MARKERS = (
    "执行步骤",
    "A类",
    "B类",
    "C类",
    "A/B",
    "A/B/C",
    "判断三问",
    "C类边界",
    "A/B混合",
    "B类时空连续性",
    "基础分类",
    "进入标志",
    "退出标志",
    "行号范围",
    "连续覆盖",
    "不能跳过",
    "同一时空",
    "设定",
    "事件",
    "次元空间",
    "系统空间",
    "意识空间",
    "分段列表",
    "修正",
    "优先级",
    "confidence",
    "log_ambiguous_segments",
    "parse_segmentation_output",
    "store_segments",
)


def check_prompt_quality(manifest: GraphSkillDef) -> list[CompileIssue]:
    """Run prompt-quality warning checks on the manifest."""
    from ..manifest import LLMPhase

    issues: list[CompileIssue] = []

    for phase_idx, phase in enumerate(manifest.phases):
        if not isinstance(phase, LLMPhase):
            continue

        prompt = (phase.prompt or "").strip()
        user_prompt = (phase.user_prompt_template or "").strip()

        if prompt and user_prompt:
            issues.extend(
                _check_prompt_duplication(prompt, user_prompt, phase, phase_idx)
            )

        if prompt:
            issues.extend(_check_finish_task_visibility(prompt, phase, phase_idx))

    issues.extend(_check_setup_anti_pattern(manifest))
    return issues


def _check_prompt_duplication(
    sys_prompt: str,
    user_prompt: str,
    phase: LLMPhase,
    phase_idx: int,
) -> list[CompileIssue]:
    """W-PROMPT-DUPLICATION: longest common substring exceeds 100 chars."""
    del phase_idx
    sys_norm = "".join(sys_prompt.split())
    usr_norm = "".join(user_prompt.split())
    if not sys_norm or not usr_norm:
        return []

    matcher = SequenceMatcher(None, sys_norm, usr_norm, autojunk=False)
    match = matcher.find_longest_match(0, len(sys_norm), 0, len(usr_norm))

    if match.size >= 100:
        overlap = sys_norm[match.a : match.a + min(match.size, 80)]
        detail = (
            f"Detected {match.size} consecutive overlapping characters between "
            f"system prompt and user_prompt_template (sample: {overlap!r}...). "
        )
    else:
        shared_markers = [
            marker
            for marker in _DUPLICATION_MARKERS
            if marker in sys_prompt and marker in user_prompt
        ]
        if len(user_prompt) < 400 or len(shared_markers) < 6:
            return []
        detail = (
            "Detected duplicated instruction blocks between system prompt and "
            "user_prompt_template via shared rule markers "
            f"{shared_markers[:8]!r}. "
        )

    return [
        CompileIssue(
            rule_id="W-PROMPT-DUPLICATION",
            severity="WARNING",
            location=f"SKILL.md:phases.{phase.name}.user_prompt_template",
            message=(
                detail +
                "Repeating instructions in both layers dilutes attention; keep the "
                "directive in system prompt and reference it from user prompt."
            ),
        )
    ]


def _check_finish_task_visibility(
    sys_prompt: str,
    phase: LLMPhase,
    phase_idx: int,
) -> list[CompileIssue]:
    """W-FINISH-TASK-VISIBILITY: finish_task buried at end of long step list."""
    del phase_idx
    if "finish_task" not in sys_prompt:
        return []

    head_quarter = sys_prompt[: max(len(sys_prompt) // 5, 200)]
    if "finish_task" in head_quarter:
        return []

    step_lines = re.findall(r"^\s*(\d+)\.\s+(.+)$", sys_prompt, flags=re.MULTILINE)
    if len(step_lines) <= 4:
        return []

    finish_step_indices = [int(num) for num, body in step_lines if "finish_task" in body]
    if not finish_step_indices:
        return []

    last_step_num = int(step_lines[-1][0])
    if all(idx >= last_step_num - 1 for idx in finish_step_indices):
        return [
            CompileIssue(
                rule_id="W-FINISH-TASK-VISIBILITY",
                severity="WARNING",
                location=f"SKILL.md:phases.{phase.name}.prompt",
                message=(
                    f"finish_task appears only at step {finish_step_indices[0]} of "
                    f"{last_step_num}. In long prompts the LLM may loop before "
                    "reaching the final step. Move finish_task into a dedicated "
                    "highlighted block (e.g. '## ⚠️ 退出契约') near the prompt head, "
                    "or to step 1-3 of the execute list."
                ),
            )
        ]
    return []


def _check_setup_anti_pattern(manifest: GraphSkillDef) -> list[CompileIssue]:
    """W-SETUP-PHASE-ANTI-PATTERN: logic setup/prepare/init as first phase."""
    if not manifest.phases:
        return []

    first = manifest.phases[0]
    name_lower = (getattr(first, "name", "") or "").lower()
    mode = getattr(first, "mode", None)

    if name_lower in ("setup", "prepare", "init", "preprocess") and mode == "logic":
        return [
            CompileIssue(
                rule_id="W-SETUP-PHASE-ANTI-PATTERN",
                severity="WARNING",
                location="SKILL.md:phases[0]",
                message=(
                    f"First phase '{first.name}' is a logic-mode preprocessing "
                    "step. This is a code smell — most setup tasks (line numbering, "
                    "format conversion, key extraction) can be expressed declaratively "
                    "via io.inputs + context_mapping filters, eliminating an entire "
                    "node and its tracing overhead. Consider whether this phase can "
                    "be inlined into upstream context preparation."
                ),
            )
        ]
    return []
