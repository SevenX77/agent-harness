"""Finish task and nudge utilities for cognitive control."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

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
    "[系统提示] 你调用了 finish_task，但自检结构不完整。"
    "请重新调用 finish_task，并补全以下字段："
    "execution_summary、plan_checklist（数组，每项含 step/completed/quality_check）、"
    "unresolved_issues。"
    "请逐条对照计划说明质量结论后再 finish。"
)

MIN_FINISH_REASONING_LEN = 30


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
        "[严重警告] 你的行为已偏离规范！必须立即调用 finish_task 结束本阶段，"
        "否则任务将被强制终止。"
    )


def finish_task(
    ctx: dict[str, Any],
    reasoning: str = "",
    evidence: str = "[]",
    execution_summary: str = "",
    plan_checklist: str = "[]",
    unresolved_issues: str = "",
    diagnostics_md: str = "",
    business_data_md: str = "",
) -> str:
    """Mark current cognitive phase as complete with structured self-review."""
    if business_data_md:
        output_schema_path = ctx.get("output_schema_path") or ctx.get("_md_schema_path")
        if not output_schema_path:
            ctx["_finish_task_result"] = {
                "diagnostics_md": diagnostics_md.strip(),
                "business_data_md": business_data_md.strip(),
                "business_data_parsed": None,
                "schema_validation": "skipped: no output_schema declared",
            }
            return "PHASE_COMPLETE"

        try:
            from ..tools.md_to_json import (
                SemanticValidationError,
                _resolve_schema_from_path,
                md_to_json,
            )

            schema = _resolve_schema_from_path(str(output_schema_path))
            validated_items = md_to_json(business_data_md, schema)
        except SemanticValidationError as exc:
            ctx["_finish_task_result"] = {
                "schema_validation": "failed",
                "validation_error_text": (
                    "[finish_task] business_data_md schema validation failed:\n"
                    f"{exc}\n"
                    "请按上面的错误说明修正你的 business_data_md 后重新调用 finish_task。"
                ),
            }
            logger.warning(
                "finish_task v2: schema validation failed "
                "(delegating to NudgeInjector retry loop)"
            )
            return "PHASE_COMPLETE"
        except Exception as exc:
            ctx["_finish_task_result"] = {
                "schema_validation": "failed",
                "validation_error_text": (
                    "[finish_task] failed to parse business_data_md or load schema "
                    f"{output_schema_path}: {exc}\n"
                    "请确认 markdown 格式（## 分隔条目、字段用 - key: value）和 schema 路径正确。"
                ),
            }
            logger.warning(
                "finish_task v2: parse/import failed "
                "(delegating to NudgeInjector retry loop): %s",
                exc,
            )
            return "PHASE_COMPLETE"

        ctx["_finish_task_result"] = {
            "diagnostics_md": diagnostics_md.strip(),
            "business_data_md": business_data_md.strip(),
            "business_data_parsed": [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in validated_items
            ],
            "schema_validation": "passed",
        }
        logger.info(
            "finish_task v2: diagnostics_len=%d business_data_len=%d items=%d schema=%s",
            len(diagnostics_md),
            len(business_data_md),
            len(validated_items),
            output_schema_path,
        )
        return "PHASE_COMPLETE"

    parsed_evidence: list[str] = []
    raw_evidence = (evidence or "").strip()
    if raw_evidence:
        try:
            parsed = json.loads(raw_evidence)
            if isinstance(parsed, list):
                parsed_evidence = [str(item) for item in parsed]
            else:
                parsed_evidence = [str(parsed)]
        except (json.JSONDecodeError, ValueError, TypeError):
            parsed_evidence = [raw_evidence]

    parsed_checklist: list[dict[str, Any]] = []
    raw_checklist = (plan_checklist or "").strip()
    if raw_checklist:
        try:
            parsed = json.loads(raw_checklist)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        parsed_checklist.append({
                            "step": str(item.get("step", "")),
                            "completed": bool(item.get("completed", False)),
                            "quality_check": str(item.get("quality_check", "")),
                        })
                    else:
                        parsed_checklist.append(
                            {"step": str(item), "completed": False, "quality_check": ""}
                        )
        except (json.JSONDecodeError, ValueError, TypeError):
            parsed_checklist = [{"step": raw_checklist, "completed": False, "quality_check": ""}]

    final_summary = (execution_summary or "").strip() or (reasoning or "").strip()
    if not final_summary:
        final_summary = "任务已结束。"

    if not parsed_evidence and parsed_checklist:
        parsed_evidence = [
            f"{item.get('step', '')}: completed={item.get('completed', False)}"
            for item in parsed_checklist
        ]

    ctx["_finish_task_result"] = {
        "execution_summary": final_summary,
        "plan_checklist": parsed_checklist,
        "unresolved_issues": (unresolved_issues or "").strip(),
        "reasoning": (reasoning or "").strip(),
        "evidence": parsed_evidence,
    }
    logger.info(
        "finish_task: summary_len=%d, checklist_items=%d, evidence_items=%d",
        len(final_summary),
        len(parsed_checklist),
        len(parsed_evidence),
    )
    return "PHASE_COMPLETE"


__all__ = [
    "PLANNING_NUDGE",
    "SELFCHECK_NUDGE",
    "MIN_FINISH_REASONING_LEN",
    "build_standard_nudge_text",
    "finish_task",
]
