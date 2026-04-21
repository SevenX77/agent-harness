"""Cognitive control tools and middlewares."""
from __future__ import annotations

from .finish import (
    PLANNING_NUDGE,
    SELFCHECK_NUDGE,
    MIN_FINISH_REASONING_LEN,
    build_standard_nudge_text,
    finish_task,
)
from .memory import update_working_memory
from .ambiguity import log_ambiguity
from .prompt import apply_cognitive_template
from .middlewares import create_custom_middlewares

__all__ = [
    "PLANNING_NUDGE",
    "SELFCHECK_NUDGE",
    "MIN_FINISH_REASONING_LEN",
    "build_standard_nudge_text",
    "finish_task",
    "update_working_memory",
    "log_ambiguity",
    "apply_cognitive_template",
    "create_custom_middlewares",
]
