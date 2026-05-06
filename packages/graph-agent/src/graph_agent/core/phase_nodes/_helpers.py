"""Module-level helpers extracted from the legacy ``phase_executor.py``.

PHASE3_DESIGN.md §2 M6: keep the small private utilities together so
the PhaseNode subclasses (and any future helpers) can share them
without drifting copies. These functions are deliberately
side-effect-free pure helpers — anything that touches lifecycle state
lives on the corresponding :class:`PhaseNode` subclass instead.
"""

from __future__ import annotations

from collections.abc import Sequence

from graph_agent.core.state import StateManager, StateMessage, WorkflowState

_AMBIGUITY_REPORTS_KEY = "_ambiguity_reports"
_FINISH_TASK_RESULT_KEY = "_finish_task_result"
_RETRY_FEEDBACK_KEY = "_retry_feedback"
_SKILL_BASE_DIR_KEY = "_skill_base_dir"
_VALIDATION_WARNINGS_KEY = "_validation_warnings"
_WORKING_MEMORY_KEY = "_working_memory"


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _tool_text(tool_state: dict[str, object], key: str) -> str | None:
    return _as_text(tool_state.get(key))


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)] if value else []


def _tool_reports(tool_state: dict[str, object]) -> list[dict[str, object]]:
    raw = tool_state.get(_AMBIGUITY_REPORTS_KEY, [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _append_tool_warning(tool_state: dict[str, object], warning: str) -> None:
    existing = tool_state.get(_VALIDATION_WARNINGS_KEY)
    if isinstance(existing, list):
        existing.append(warning)
        return
    if existing is None:
        tool_state[_VALIDATION_WARNINGS_KEY] = [warning]
        return
    tool_state[_VALIDATION_WARNINGS_KEY] = [str(existing), warning]


def _finish_result_from_tool_state(
    tool_state: dict[str, object],
) -> dict[str, object] | None:
    value = tool_state.get(_FINISH_TASK_RESULT_KEY)
    return value if isinstance(value, dict) else None


def _sync_tool_state(
    state: WorkflowState,
    tool_state: dict[str, object],
    *,
    messages: Sequence[StateMessage] | None = None,
) -> WorkflowState:
    business_fields = {k: v for k, v in tool_state.items() if not k.startswith("_")}
    next_state = state
    if business_fields:
        next_state = StateManager.update_business(next_state, **business_fields)

    flow_updates: dict[str, object] = {}
    if _VALIDATION_WARNINGS_KEY in tool_state:
        flow_updates["validation_warnings"] = _normalize_string_list(
            tool_state.get(_VALIDATION_WARNINGS_KEY)
        )
    if _RETRY_FEEDBACK_KEY in tool_state:
        flow_updates["retry_feedback"] = _normalize_string_list(tool_state.get(_RETRY_FEEDBACK_KEY))
    if _WORKING_MEMORY_KEY in tool_state:
        flow_updates["working_memory"] = tool_state.get(_WORKING_MEMORY_KEY)
    if _AMBIGUITY_REPORTS_KEY in tool_state:
        flow_updates["ambiguity_reports"] = _tool_reports(tool_state)

    if flow_updates:
        next_state = StateManager.update_framework(next_state, **flow_updates)

    return WorkflowState(
        data=next_state["data"],
        flow=next_state["flow"],
        messages=list(messages) if messages is not None else next_state["messages"],
    )


__all__ = [
    "_AMBIGUITY_REPORTS_KEY",
    "_FINISH_TASK_RESULT_KEY",
    "_RETRY_FEEDBACK_KEY",
    "_SKILL_BASE_DIR_KEY",
    "_VALIDATION_WARNINGS_KEY",
    "_WORKING_MEMORY_KEY",
    "_append_tool_warning",
    "_as_text",
    "_finish_result_from_tool_state",
    "_normalize_string_list",
    "_sync_tool_state",
    "_tool_reports",
    "_tool_text",
]
