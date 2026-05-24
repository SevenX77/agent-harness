"""Cognitive prompt composer for GraphAgentHarness.

This module turns framework-level methodology into the final system prompt seen
by a phase agent. It merges:

- the phase-local skill system prompt
- optional role-level methodology prefixes from ``llm_roles.yaml``
- optional ``data_architecture`` constraints
"""

from __future__ import annotations

import json
import logging
from typing import Any

from graph_agent.config.llm_config import get_role_config

logger = logging.getLogger(__name__)


def resolve_role_prefix_from_llm_role(llm_role: str | None) -> str:
    """Resolve ``llm_roles.yaml`` system_prompt_prefix for an LLM role."""
    if llm_role is None:
        return ""
    try:
        return get_role_config().resolve_role(llm_role).system_prompt_prefix
    except Exception as exc:
        logger.warning(
            "Failed to resolve llm_role=%s system_prompt_prefix: %s",
            llm_role,
            exc,
        )
        return ""


def _build_data_architecture_section(data_architecture: str | None) -> str:
    if not data_architecture:
        return ""
    return f"""<data_architecture>
{data_architecture}
</data_architecture>"""


def apply_cognitive_template(
    *,
    phase_name: str,
    skill_system_prompt: str,
    data_architecture: str | None,
    context: dict[str, Any] | None = None,
    role_prefix: str = "",
) -> str:
    """Compose final system prompt from cognitive template + skill prompt.

    Args:
        phase_name: Current phase name for contextual reminders.
        skill_system_prompt: Domain-specific instructions defined by the skill.
        data_architecture: Optional structural guidance about expected data
            shapes, field meanings, and producer/consumer boundaries.
        context: Reserved extension point for future context-aware prompt
            branching. Currently accepted for compatibility and ignored.
        role_prefix: Optional methodology prefix resolved from
            ``llm_roles.yaml.roles.<tier>.system_prompt_prefix``.

    Returns:
        One merged system prompt string consumed by ``create_agent()``.

    """
    _ = context
    data_architecture_section = _build_data_architecture_section(data_architecture)
    role_prefix_section = (
        f"<role_prefix>\n{role_prefix.strip()}\n</role_prefix>\n"
        if role_prefix and role_prefix.strip()
        else ""
    )

    return f"""
<role>
你是 GraphAgent 的执行节点，当前阶段：{phase_name}。
</role>

{role_prefix_section}

<thinking_style>
- 行动前先做简短策略思考：目标是什么、输入是否充分、输出标准是什么
- 区分“事实”与“推断”，不要把推断当作事实写入结果
- 对关键判断给出依据，不要无依据臆测
- 先规划后执行：明确步骤，再调用工具
- 思考用于规划；对外输出必须给出可执行结果，而不是只描述计划
</thinking_style>

<ambiguity_feedback>
当你发现规则不清晰、输入不足或存在多种合理解释时，不要静默跳过：
1. 优先调用 log_ambiguity 记录问题、类型、你的决策和理由
2. 然后继续按“最保守且可解释”的方案执行

这不是阻塞流程的澄清请求，而是用于改进技能定义的反馈回路。
</ambiguity_feedback>

<protocol_citation>
做判断时必须标注协议依据。推荐格式：
- [protocol:P1] ...
- [protocol:P6] ...
- [protocol:P9] ...

若无法对应到具体协议编号，必须在自检说明中写明“未找到明确协议条款”，并调用 log_ambiguity。
</protocol_citation>

{data_architecture_section}

<skill_section>
{skill_system_prompt}
</skill_section>

<critical_reminders>
- 调用 finish_task 前，先检查关键工具返回值是否与预期一致
- 如果发现不一致，先修复再 finish
- 对每个关键结论都给出规则依据或数据依据
- 当你不确定规则边界时，先 log_ambiguity，再继续执行
- finish_task 必须提供 diagnostics_md（自检诊断 Markdown）+ business_data_md（业务输出 Markdown，遵循 phase 的 output_schema）
- business_data_md 会经结构化输出校验。如果校验失败，你会收到错误反馈消息——按反馈修正后重新调用 finish_task
</critical_reminders>
""".strip()


def apply_v030_cognitive_template(
    *,
    phase_name: str,
    role: str,
    goal: str,
    steps: list[dict[str, str]],
    protocols: list[dict[str, str]],
    exit_contract: str,
    output_schema: dict[str, Any] | None = None,
    knowledge_base: str = "",
    inline_examples: list[str] | None = None,
    document_examples: list[dict[str, str]] | None = None,
    role_prefix: str = "",
) -> str:
    """Compose the V0.3.0 seven-slot cognitive template for Agent phases."""

    role_prefix_section = (
        f"<llm_role_prefix>\n{role_prefix.strip()}\n</llm_role_prefix>\n"
        if role_prefix and role_prefix.strip()
        else ""
    )
    steps_md = _render_steps(steps)
    protocols_md = _render_protocols(protocols)
    examples_md = _render_inline_examples(inline_examples or [])
    document_examples_md = (
        "\n".join(
            f"- {item.get('id')}: {item.get('summary', '')}" for item in document_examples or []
        )
        or "无扩展案例"
    )
    exit_contract_inline = exit_contract
    if output_schema is not None:
        try:
            schema_md = json.dumps(output_schema, ensure_ascii=False, indent=2, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("[F-v3-cognitive-output-schema-render-failed]") from exc
        exit_contract_inline = (
            exit_contract.rstrip()
            + "\n\noutput_schema:\n```json\n"
            + schema_md
            + "\n```"
        )

    return f"""
<role>
{role}
</role>

{role_prefix_section}

<goal>
{goal}
</goal>

<thinking_style>
- 行动前先做简短策略思考: 目标是什么, 输入是否充分, 输出标准是什么
- 区分"事实"与"推断", 不要把推断当作事实写入结果
- 对关键判断给出依据, 不要无依据臆测
- 先规划后执行: 明确步骤, 再调用工具
- 思考用于规划; 对外输出必须给出可执行结果, 而不是只描述计划
- 建议步骤:
{steps_md}
</thinking_style>

<knowledge_base>
【垂直领域知识修正报告】(系统已提前查阅相关资料并提取核心差异):
{knowledge_base or "无注册 Reference"}
</knowledge_base>

<examples>
以下是供你理解业务思路和处理风格的参考案例. 请注意: 这些案例仅用于辅助理解业务逻辑,
你的最终输出格式必须严格遵守 <exit_contract> 中的 Schema, 不要照搬案例的结构.

【内联示范】:
{examples_md}

【扩展案例库】:
系统还注册了以下更多复杂案例. 遇到棘手边界问题时, 你可以调用 `read_example` subagent 工具, 传入对应的 E-id 查阅:
{document_examples_md}
</examples>

<ambiguity_feedback>
当你发现规则不清晰, 输入不足或存在多种合理解释时, 不要静默跳过:
1. 优先调用 log_ambiguity 记录问题, 类型, 你的决策和理由
2. 然后继续按"最保守且可解释"的方案执行
</ambiguity_feedback>

<protocol_citation>
做判断时必须标注协议依据, 例如: [protocol:P1]. 若无明确协议, 需在自检说明中写明并调用 log_ambiguity.

必须遵守的协议:
{protocols_md}
</protocol_citation>

<critical_reminders>
- 调用 finish_task 前, 先检查关键工具返回值是否与预期一致
- 对每个关键结论都给出规则依据或数据依据
- 当你不确定规则边界时, 先 log_ambiguity, 再继续执行
- finish_task 必须提供 diagnostics_md (自检诊断 Markdown) + business_data_md (业务输出 Markdown)
- business_data_md 会经系统强校验. 如果校验失败, 你会收到错误反馈消息; 按反馈修正后重新调用 finish_task
</critical_reminders>

<exit_contract>
{exit_contract_inline}
</exit_contract>
""".strip()


def _render_steps(steps: list[dict[str, str]]) -> str:
    if not steps:
        return ""
    return "\n".join(
        f"    - [{item.get('id', '')}] {item.get('name', '')}: {item.get('content', '')}".rstrip()
        for item in steps
    )


def _render_protocols(protocols: list[dict[str, str]]) -> str:
    if not protocols:
        return "无显式协议"
    return "\n".join(
        f"[protocol:{item.get('id', '')}]\n{item.get('content', '')}".rstrip()
        for item in protocols
    )


def _render_inline_examples(inline_examples: list[str]) -> str:
    if not inline_examples:
        return "无内联示例"
    return "\n\n".join(inline_examples)
