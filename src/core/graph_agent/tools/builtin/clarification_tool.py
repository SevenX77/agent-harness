from __future__ import annotations

from typing import Literal

from langchain.tools import tool


@tool("ask_clarification", parse_docstring=True, return_direct=True)
def ask_clarification_tool(
    question: str,
    clarification_type: Literal[
        "missing_info",
        "ambiguous_requirement",
        "approach_choice",
        "risk_confirmation",
        "suggestion",
    ],
    context: str | None = None,
    options: list[str] | None = None,
) -> str:
    """Ask the user for clarification when more information is required.

    Args:
        question: The clarification question to ask the user.
        clarification_type: The type of clarification needed.
        context: Optional context explaining why clarification is needed.
        options: Optional choices for approach or suggestion clarification.
    """
    return "Clarification request processed by middleware"
