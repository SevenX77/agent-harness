"""Event extraction validators for story deconstruction.

This module provides validation functions for event extraction quality assurance.

Phase 2 A1 contract (2026-04-29): every validator mounted on an LLMPhase
must accept ``payload: list[dict[str, Any]]`` — the structured items
parsed from the phase's declared ``output_schema``. The validator must
not reach into the global ctx (that broken pattern is what the v1.1+
``schema is None`` purge eliminated). See PHASE2_DESIGN.md §2.4.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# Setting IDs are expected to follow ``SET_<digits>`` per the SKILL.md
# prompt and the Pydantic Setting class description ("如 SET_001").
_SETTING_ID_PATTERN = re.compile(r"^SET_\d+$")

# Empirical band for ``core_knowledge`` from the SKILL prompt:
# "核心知识点（50-100 字精炼）". We allow a wider window to absorb
# normal LLM variance but still flag obvious starvation / overrun.
_CORE_KNOWLEDGE_MIN = 30
_CORE_KNOWLEDGE_MAX = 200


def validate_event_extraction(
    payload: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Validate the ``settings`` LLMPhase output (a list of Setting dicts).

    The settings phase is configured in ``skills/event-extraction/SKILL.md``
    with ``output_schema: script.models.Setting``. After Phase 2 A1, the
    framework's CognitiveFlow / Validation middleware parses the LLM
    markdown into ``list[dict]`` of Setting fields and hands that list to
    this validator. We therefore check semantic invariants over the
    parsed list — Pydantic itself already enforces the field shape.

    Checks:
      - Non-empty list (a Settings phase must extract at least one setting;
        the LLM is explicitly prompted for these).
      - ``setting_id`` matches ``SET_<digits>`` and is unique across items.
      - ``paragraph_indices`` is non-empty for every item.
      - ``related_event_id`` is a non-empty string.
      - ``core_knowledge`` length lands in a plausible band (30..200 chars);
        too short or too long flags a quality regression.

    Args:
        payload: Parsed Setting items as ``list[dict[str, Any]]``. Each
            dict carries ``setting_id``, ``paragraph_indices``,
            ``related_event_id`` and ``core_knowledge``.

    Returns:
        ``(is_valid, issues)``: pass / fail flag plus a list of
        human-readable issue strings (empty when ``is_valid``).
    """
    issues: list[str] = []

    logger.info(
        "phase=settings action=validate_event_extraction settings_count=%d",
        len(payload),
    )

    if not payload:
        issues.append("settings 为空，settings phase 必须至少抽出 1 条世界观条目")
        logger.error(
            "phase=settings action=validate_event_extraction decision=reject reason=empty_payload"
        )
        return False, issues

    seen_ids: set[str] = set()
    for index, item in enumerate(payload):
        # ``index`` is the positional fallback when an LLM emits a malformed
        # setting_id. Diagnostic strings always surface both for traceability.
        setting_id = str(item.get("setting_id") or "").strip()
        ref = setting_id or f"index={index}"

        if not setting_id:
            issues.append(f"item {ref}: 缺少 setting_id")
        elif not _SETTING_ID_PATTERN.match(setting_id):
            issues.append(f"item {ref}: setting_id={setting_id!r} 不符合 SET_数字 格式")
        elif setting_id in seen_ids:
            issues.append(f"item {ref}: setting_id={setting_id!r} 重复")
        else:
            seen_ids.add(setting_id)

        paragraph_indices = item.get("paragraph_indices")
        if not isinstance(paragraph_indices, list) or not paragraph_indices:
            issues.append(
                f"item {ref}: paragraph_indices 必须是非空 list[int]，got {paragraph_indices!r}"
            )

        related_event_id = str(item.get("related_event_id") or "").strip()
        if not related_event_id:
            issues.append(f"item {ref}: related_event_id 缺失或为空")

        core_knowledge = str(item.get("core_knowledge") or "")
        ck_len = len(core_knowledge)
        if ck_len < _CORE_KNOWLEDGE_MIN:
            issues.append(
                f"item {ref}: core_knowledge 长度 {ck_len} 字 < "
                f"{_CORE_KNOWLEDGE_MIN} 字下限，判为信息密度不足"
            )
        elif ck_len > _CORE_KNOWLEDGE_MAX:
            issues.append(
                f"item {ref}: core_knowledge 长度 {ck_len} 字 > "
                f"{_CORE_KNOWLEDGE_MAX} 字上限，判为冗长应精炼"
            )

    is_valid = not issues
    if is_valid:
        logger.info(
            "phase=settings action=validate_event_extraction decision=pass "
            "settings_count=%d unique_ids=%d",
            len(payload),
            len(seen_ids),
        )
    else:
        logger.warning(
            "phase=settings action=validate_event_extraction decision=fail "
            "settings_count=%d issue_count=%d",
            len(payload),
            len(issues),
        )
    return is_valid, issues
