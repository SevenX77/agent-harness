"""Cognitive control tools and middlewares."""
from __future__ import annotations

from .ambiguity import log_ambiguity
from .finish import (
    MIN_FINISH_REASONING_LEN,
    PLANNING_NUDGE,
    SELFCHECK_NUDGE,
    build_standard_nudge_text,
    finish_task,
)
from .memory import update_working_memory
from .middlewares import create_custom_middlewares
from .prompt import apply_cognitive_template

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
