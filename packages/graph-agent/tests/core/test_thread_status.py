"""Tests for GraphAgentHarness.get_thread_status (I-1)."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from graph_agent.core.harness import GraphAgentHarness  # noqa: E402


def _make_harness_stub(checkpointer, graph) -> GraphAgentHarness:
    """Build a minimal GraphAgentHarness skeleton without running __init__."""
    h = GraphAgentHarness.__new__(GraphAgentHarness)
    h._checkpointer = checkpointer
    h._graph = graph
    return h


class _FakeGraph:
    """Minimal stand-in for CompiledStateGraph exposing only get_state."""

    def __init__(self, snapshot):
        self._snapshot = snapshot

    def get_state(self, config):
        return self._snapshot


class TestGetThreadStatusNoCheckpointer:
    def test_no_checkpointer_returns_not_found(self):
        h = _make_harness_stub(checkpointer=None, graph=_FakeGraph(None))
        assert h.get_thread_status("t1") == {"status": "NOT_FOUND", "reason": "no_checkpointer"}


class TestGetThreadStatusShapes:
    def test_no_snapshot_yields_not_found(self):
        h = _make_harness_stub(object(), _FakeGraph(None))
        assert h.get_thread_status("t1") == {"status": "NOT_FOUND"}

    def test_completed_run_has_no_next(self):
        snapshot = SimpleNamespace(next=(), tasks=())
        h = _make_harness_stub(object(), _FakeGraph(snapshot))
        assert h.get_thread_status("t1") == {"status": "COMPLETED"}

    def test_running_when_next_present_no_interrupts(self):
        task = SimpleNamespace(interrupts=())
        snapshot = SimpleNamespace(next=("phase_b",), tasks=(task,))
        h = _make_harness_stub(object(), _FakeGraph(snapshot))
        result = h.get_thread_status("t1")
        assert result["status"] == "RUNNING"
        assert result["next"] == ["phase_b"]

    def test_awaiting_input_returns_clarification(self):
        clarification_payload = {
            "question": "Which environment?",
            "clarification_type": "approach_choice",
            "options": ["dev", "prod"],
        }
        interrupt = SimpleNamespace(value=clarification_payload)
        task = SimpleNamespace(interrupts=(interrupt,))
        snapshot = SimpleNamespace(next=("phase_b",), tasks=(task,))
        h = _make_harness_stub(object(), _FakeGraph(snapshot))
        result = h.get_thread_status("t1")
        assert result == {
            "status": "AWAITING_INPUT",
            "clarification": clarification_payload,
        }

    def test_awaiting_input_falls_back_when_payload_is_bare_string(self):
        interrupt = SimpleNamespace(value="Confirm?")
        task = SimpleNamespace(interrupts=(interrupt,))
        snapshot = SimpleNamespace(next=("phase_b",), tasks=(task,))
        h = _make_harness_stub(object(), _FakeGraph(snapshot))
        result = h.get_thread_status("t1")
        assert result == {
            "status": "AWAITING_INPUT",
            "clarification": {
                "question": "Confirm?",
                "clarification_type": "missing_info",
                "options": [],
            },
        }


class TestGetThreadStatusExceptions:
    def test_exception_during_get_state_becomes_crashed(self):
        class _FailingGraph:
            def get_state(self, config):
                raise RuntimeError("boom")

        h = _make_harness_stub(object(), _FailingGraph())
        result = h.get_thread_status("t1")
        assert result["status"] == "CRASHED"
        assert "boom" in result.get("reason", "")
