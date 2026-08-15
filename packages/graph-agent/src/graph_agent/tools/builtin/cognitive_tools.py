"""Cognitive framework tool shells resolved by CognitiveFlowMiddleware.

Like ``ask_clarification_tool``, these tools carry only the model-facing
schema: CognitiveFlowMiddleware intercepts the call by name and performs
the actual ``FrameworkState`` reads/writes, so the function bodies are
unreachable placeholders (migration decision 2026-08-15 §3.2-§3.4).
"""

from __future__ import annotations

from typing import Literal

from langchain.tools import tool


@tool("update_working_memory", parse_docstring=True)
def update_working_memory_tool(plan: str) -> str:
    """Replace the working-memory plan so progress stays explicit and auditable.

    Args:
        plan: The full replacement text of the current plan/status notes.
    """
    return "Working memory update processed by middleware"


@tool("log_ambiguity", parse_docstring=True)
def log_ambiguity_tool(
    question: str,
    ambiguity_type: Literal[
        "missing_info",
        "ambiguous_requirement",
        "approach_choice",
        "risk_confirmation",
        "suggestion",
    ],
    decision: str,
    reason: str = "",
) -> str:
    """Record an ambiguity and the decision taken, without interrupting the run.

    Unlike ask_clarification this never blocks: log the unclear point, state
    the most conservative decision you chose, and continue executing.

    Args:
        question: The unclear point encountered while executing.
        ambiguity_type: Category of ambiguity.
        decision: The decision chosen for this run.
        reason: Optional rationale for the decision.
    """
    return "Ambiguity report processed by middleware"


@tool("query_working_memory", parse_docstring=True)
def query_working_memory_tool() -> str:
    """Read the current working-memory plan text recorded by update_working_memory."""
    return "Working memory query processed by middleware"


@tool("read_artifact", parse_docstring=True)
def read_artifact_tool(name: str) -> str:
    """Read a named business artifact (an earlier phase's named output).

    Args:
        name: The business artifact name to read.
    """
    return "Artifact read processed by middleware"


__all__ = [
    "log_ambiguity_tool",
    "query_working_memory_tool",
    "read_artifact_tool",
    "update_working_memory_tool",
]
