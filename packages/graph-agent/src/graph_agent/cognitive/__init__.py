"""Cognitive control tools and middlewares."""

from __future__ import annotations

from graph_agent.cognitive.ambiguity import log_ambiguity
from graph_agent.cognitive.context_facade import Context
from graph_agent.cognitive.finish import (
    MIN_FINISH_REASONING_LEN,
    PLANNING_NUDGE,
    SELFCHECK_NUDGE,
    build_standard_nudge_text,
    finish_task,
)
from graph_agent.cognitive.memory import update_working_memory
from graph_agent.cognitive.middlewares import create_custom_middlewares
from graph_agent.cognitive.prompt import apply_cognitive_template

__all__ = [
    "PLANNING_NUDGE",
    "SELFCHECK_NUDGE",
    "MIN_FINISH_REASONING_LEN",
    "Context",
    "build_standard_nudge_text",
    "finish_task",
    "update_working_memory",
    "log_ambiguity",
    "apply_cognitive_template",
    "create_custom_middlewares",
]
