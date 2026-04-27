"""Finish task and nudge utilities for cognitive control."""
from __future__ import annotations

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
    "[系统提示] 你调用了 finish_task，但缺少必要字段。"
    "请重新调用 finish_task，并提供："
    "diagnostics_md（自检诊断 Markdown，逐条对照计划说明质量结论）"
    "+ business_data_md（业务输出 Markdown，遵循 phase 的 output_schema）。"
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
    diagnostics_md: str = "",
    business_data_md: str = "",
) -> str:
    """完成当前 phase。

    参数：
    - diagnostics_md: 自检诊断 Markdown（推荐：逐条对照计划说明质量结论）
    - business_data_md: 业务输出 Markdown，会经 md_to_json 校验是否符合 phase 的 output_schema

    最简调用：finish_task(reasoning="任务已完成")
    （适用于无 output_schema 的 phase；不会触发 schema 验证）
    """
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

    ctx["_finish_task_result"] = {
        "reasoning": (reasoning or "").strip(),
        "diagnostics_md": diagnostics_md.strip(),
        "business_data_md": "",
        "schema_validation": "skipped",
    }
    logger.info(
        "finish_task: no business_data_md, schema validation skipped "
        "(reasoning_len=%d, diagnostics_len=%d)",
        len(reasoning or ""),
        len(diagnostics_md),
    )
    return "PHASE_COMPLETE"


__all__ = [
    "PLANNING_NUDGE",
    "SELFCHECK_NUDGE",
    "MIN_FINISH_REASONING_LEN",
    "build_standard_nudge_text",
    "finish_task",
]
