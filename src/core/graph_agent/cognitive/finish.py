"""Finish task and nudge utilities for cognitive control.

Architecture (post-MVP-2 T5)
----------------------------

``finish_task`` itself is intentionally a thin packager. The heavy
work — schema validation and io.outputs hoisting — lives in two
collaborators (post-Phase-3 M7 the legacy parallel pipeline is gone;
the modern owner is ``CognitiveFlowMiddleware``):

* :class:`graph_agent.middleware.cognitive_flow.CognitiveFlowMiddleware`
  intercepts the agent loop's ``finish_task`` tool call **before** the
  return-direct tool runs, validates ``business_data_md`` against the
  phase's ``output_schema`` (Pydantic ``type[BaseModel]`` or
  ``SchemaObject``), dispatches the per-phase business validator on
  the parsed items list, and re-routes invalid submissions back to
  the model in the same agent loop. It is the canonical schema gate.
* :class:`graph_agent.core.phase_executor.PhaseExecutor`'s LLM phase
  exit code (or, post-MVP-4, ``LLMPhaseNode.execute``) reads the
  validated payload from ``state['flow'].finish_task_result`` and runs
  :meth:`graph_agent.core.io_manager.IOManager.resolve_hoist` to move
  named outputs into ``state['data']``.

This function therefore does **not** call ``schema_engine`` or
``io_manager`` synchronously today — by the time it executes
CognitiveFlowMiddleware has already accepted the payload. The optional
``schema_engine`` / ``compiled_schema`` parameters exist as wiring
hooks so a defense-in-depth path can be turned on by callers (e.g. a
test harness running without the middleware, or a future MVP that
relocates validation back into the tool itself); when the kwargs are
omitted, behaviour is identical to the pre-MVP-2 packager.

``SCHEMA_VALIDATION_ERROR_TEMPLATE`` and ``PARSE_ERROR_TEMPLATE`` stay
as exported module constants because CognitiveFlowMiddleware formats
its rejection messages from them — single source of truth for LLM
retry feedback strings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid runtime import cycle
    from ..core.io_manager import IOManager
    from ..core.schema_engine import SchemaEngine, SchemaObject
    from ..tools.md_to_json import ParsedBlock

logger = logging.getLogger(__name__)


def _parse_business_md_to_blocks(
    business_data_md: str,
    schema_engine: SchemaEngine,
    compiled_schema: SchemaObject,
) -> tuple[list[ParsedBlock], type[Any]]:
    """Markdown → list[ParsedBlock] using the schema's projected Pydantic class.

    T5-hotfix: ``finish_task`` previously fed the raw markdown string
    directly into ``SchemaEngine.validate`` (line 148 in T5 commit
    5946638), which always failed because the engine's Pydantic model
    expected the schema's declared field names, not a single
    ``business_data_md`` key. The audit caught the test suite hiding
    this with a hand-empty schema (``fields=()``) so ``extra='forbid'``
    rejected the raw string and made the assertion pass for the wrong
    reason.

    The fix uses ``md_to_json.parse_md`` — the same canonical parser
    ``CognitiveFlowMiddleware`` runs upstream — to split the markdown into
    one ``ParsedBlock`` per ``##`` item. Each block's ``.data`` dict is
    what ``schema_engine.validate`` actually expects.
    """
    from ..tools.md_to_json import parse_md

    pydantic_cls = schema_engine.get_pydantic_model(compiled_schema)
    blocks = parse_md(business_data_md, pydantic_cls)
    return blocks, pydantic_cls

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

# Validation error templates emitted into ctx for LLM retry feedback.
# These are intentionally exposed as module-level constants so downstream
# applications can monkey-patch them at startup for English deployments
# or brand-specific phrasing. Templates use .format() with named fields.
SCHEMA_VALIDATION_ERROR_TEMPLATE = (
    "[finish_task] business_data_md schema validation failed:\n"
    "{exc}\n"
    "请按上面的错误"
    "说明修正你的 business_data_md 后重新调用 finish_task。"
)

PARSE_ERROR_TEMPLATE = (
    "[finish_task] failed to parse business_data_md or load schema "
    "{output_schema_path}: {exc}\n"
    "请确认 markdown "
    "格式（## 分隔条目、字段用 - key: value）和 schema 路径正确。"
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


def finish_task(
    ctx: dict[str, Any],
    reasoning: str = "",
    diagnostics_md: str = "",
    business_data_md: str = "",
    *,
    schema_engine: SchemaEngine | None = None,
    compiled_schema: SchemaObject | None = None,
    io_manager: IOManager | None = None,
) -> dict[str, Any]:
    """Mark the current phase complete.

    ``CognitiveFlowMiddleware`` has typically already accepted or
    rejected this submission inside the agent loop, so this function
    packages the accepted payload and lets the phase executor route it
    into framework state. The optional ``schema_engine`` /
    ``compiled_schema`` / ``io_manager`` kwargs (added in MVP-2 T5) are
    wiring hooks for the defense-in-depth path documented in the module
    header — when caller supplies all three the function performs a
    final validation + hoist pass; when omitted (the current production
    call site in ``phase_executor._finish_task_tool``) behaviour matches
    the pre-MVP-2 packager exactly.

    Returns a dict carrying the legacy ``value`` / ``duplicate`` keys
    (read by ``phase_executor._finish_task_tool``) plus the design.md
    §4.2 ``finish_task_result`` / ``diagnostics`` keys (introduced for
    MVP-3 phase_executor adopters and MVP-4 ``LLMPhaseNode``).
    """

    prior = ctx.get("finish_task_result")
    result = dict(prior) if isinstance(prior, dict) else {}
    result.update(
        {
            "reasoning": (reasoning or "").strip(),
            "diagnostics_md": diagnostics_md.strip(),
            "business_data_md": business_data_md.strip(),
        }
    )

    # Defense-in-depth schema validation. Active only when caller wires
    # both ``schema_engine`` and ``compiled_schema`` (today: tests and
    # future MVP-4 callers); CognitiveFlowMiddleware remains the canonical
    # gate when these kwargs are absent.
    if schema_engine is not None and compiled_schema is not None and business_data_md:
        # T5-hotfix: parse markdown → list[ParsedBlock.data] before
        # validating. The previous implementation skipped this step and
        # fed the raw markdown string into ``validate`` as a single
        # ``business_data_md`` key, which is not what any real schema
        # declares. See ``_parse_business_md_to_blocks`` for the audit
        # trail.
        try:
            blocks, _ = _parse_business_md_to_blocks(
                business_data_md, schema_engine, compiled_schema
            )
        except Exception as exc:  # noqa: BLE001 — md parse failures surface here
            blocks = []
            result["schema_validation"] = "failed"
            result["schema_validation_errors"] = [
                f"markdown parse failed: {type(exc).__name__}: {exc}"
            ]
        else:
            errors: list[str] = []
            parsed_dicts: list[dict[str, Any]] = []
            for block in blocks:
                validation = schema_engine.validate(block.data, compiled_schema)
                if validation.ok:
                    parsed_dicts.append(
                        validation.parsed if validation.parsed is not None else dict(block.data)
                    )
                else:
                    errors.extend(
                        f"item {block.meta.id}: {err}" for err in validation.errors
                    )
            if errors:
                result["schema_validation"] = "failed"
                result["schema_validation_errors"] = errors
            else:
                result["schema_validation"] = "passed"
                # T5-hotfix: ``business_data_parsed`` carries the
                # structured dict view downstream IOManager.resolve_hoist
                # needs. Without this, finish_task_result was opaque
                # markdown and ``source_field`` lookups returned None,
                # breaking the A7 hoist contract.
                result["business_data_parsed"] = parsed_dicts
    else:
        result.setdefault("schema_validation", "skipped")

    # IOManager wiring. The actual hoist runs in phase_executor at phase
    # exit (it knows the live BusinessData target); finish_task records
    # the io.outputs spec count so callers can sanity-check that the
    # phase declared any hoist mapping at all. The full IOManager.run
    # path remains the phase_executor's responsibility per design §4.3.
    if io_manager is not None:
        result.setdefault(
            "io_manifest", {"output_count": len(io_manager.io_specs)}
        )

    logger.info(
        "finish_task: accepted completion marker "
        "(reasoning_len=%d, diagnostics_len=%d, business_data_len=%d, "
        "schema_validation=%s)",
        len(reasoning or ""),
        len(diagnostics_md),
        len(business_data_md or ""),
        result.get("schema_validation"),
    )
    return {
        # Legacy keys consumed by ``phase_executor._finish_task_tool``.
        "value": result,
        "duplicate": prior is not None,
        # design.md §4.2 keys for MVP-3+ adopters.
        "finish_task_result": result,
        "diagnostics": diagnostics_md.strip(),
    }


__all__ = [
    "PLANNING_NUDGE",
    "SELFCHECK_NUDGE",
    "SCHEMA_VALIDATION_ERROR_TEMPLATE",
    "PARSE_ERROR_TEMPLATE",
    "MIN_FINISH_REASONING_LEN",
    "build_standard_nudge_text",
    "finish_task",
]
