"""HITL tool-name detection set stays aligned with tools that actually exist.

Migration decision 2026-08-15 §3.1 item 3: ``request_human_input`` had no
definition anywhere in src — a pure reserved dead entry — so the detection
set names exactly the one HITL tool the engine mounts.
"""

from __future__ import annotations

from graph_agent.core.runner import _HITL_TOOL_NAMES


def test_hitl_tool_names_contains_only_tools_defined_in_src() -> None:
    assert _HITL_TOOL_NAMES == {"ask_clarification"}
