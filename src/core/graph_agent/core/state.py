"""WorkflowState and small serialization helpers for LangGraph execution.

This module defines the reducer-friendly state object shared by all graph_agent
nodes. The state shape is intentionally small and stable so that loader,
harness, callbacks, and tests can reason about data flow consistently.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.messages import AnyMessage


class WorkflowState(TypedDict):
    """State passed between LangGraph nodes.

    Attributes:
        context: Business data blackboard — shared across phases, read/written by nodes.
        messages: Current phase's LLM conversation history — reset on new phase entry.
        current_phase: Name of the phase currently executing.
        retry_counts: Per-phase retry counters (key = phase name or retry_target).
        metrics: Accumulated token usage and timing across all phases.

    """

    context: dict[str, Any]  # Shared blackboard written by tools and validators.
    messages: list[AnyMessage]  # Current phase conversation window for the LLM.
    current_phase: str  # Phase name currently executing or being validated.
    retry_counts: dict[str, int]  # Retry counter bucketed by phase/retry_target.
    metrics: dict[str, Any]  # Aggregated runtime metrics across the whole graph.
