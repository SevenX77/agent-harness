"""Cognitive prompt composer for GraphAgentHarness.

This module turns framework-level methodology into the final system prompt seen
by a phase agent. It merges:

- the phase-local skill system prompt
- optional role-level methodology prefixes from ``llm_roles.yaml``
- optional ``data_architecture`` constraints
"""

from __future__ import annotations

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
- business_data_md 会经 md_to_json 校验。如果校验失败，你会收到错误反馈消息——按反馈修正后重新调用 finish_task
</critical_reminders>
""".strip()
