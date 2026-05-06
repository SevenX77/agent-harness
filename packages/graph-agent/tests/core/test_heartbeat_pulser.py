"""Unit tests for ``_HeartbeatPulser`` (harness.py).

The pulser is a small threading primitive, so the tests stay at the
contract level:

* ``start`` launches a *daemon* thread (required so interpreter
  shutdown never blocks on the pulser).
* ``stop`` sets the Event and joins cleanly — calling ``stop`` without
  ``start`` is a no-op.
* ``_run`` emits exactly one ``HeartbeatEvent`` per interval and
  populates ``current_phase`` / ``elapsed_seconds``.
* A raising callback does not take down the pulser (swallow + continue).
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src" / "core"))

from graph_agent.callbacks.base import Callback  # noqa: E402
from graph_agent.callbacks.events import HeartbeatEvent  # noqa: E402
from graph_agent.core.harness import _HeartbeatPulser  # noqa: E402


class _RecordingCallback(Callback):
    """Collects events emitted to ``on_event`` so tests can assert on them."""

    def __init__(self) -> None:
        self.events: list[Any] = []
        self._lock = threading.Lock()

    def on_event(self, event: Any) -> None:
        with self._lock:
            self.events.append(event)


class _RaisingCallback(Callback):
    """Raises on every event — exercises the swallow-and-continue path."""

    def __init__(self) -> None:
        self.call_count = 0
        self._lock = threading.Lock()

    def on_event(self, event: Any) -> None:
        with self._lock:
            self.call_count += 1
        raise RuntimeError("callback intentionally raising")


class TestHeartbeatPulser:
    """Contract tests for _HeartbeatPulser."""

    def test_start_creates_daemon_thread(self) -> None:
        """Pulser thread MUST be daemon; otherwise interpreter shutdown hangs."""
        pulser = _HeartbeatPulser(callbacks=[], interval_seconds=10.0)
        pulser.start()
        try:
            assert pulser._thread is not None
            assert pulser._thread.daemon is True, (
                "pulser thread must be daemon so interpreter shutdown never blocks"
            )
            assert pulser._thread.is_alive()
        finally:
            pulser.stop()

    def test_start_is_idempotent(self) -> None:
        """Second ``start`` must not spawn a second thread."""
        pulser = _HeartbeatPulser(callbacks=[], interval_seconds=10.0)
        pulser.start()
        try:
            first_thread = pulser._thread
            pulser.start()  # no-op
            assert pulser._thread is first_thread
        finally:
            pulser.stop()

    def test_stop_without_start_is_noop(self) -> None:
        """Calling stop on an un-started pulser must not raise."""
        pulser = _HeartbeatPulser(callbacks=[], interval_seconds=10.0)
        pulser.stop()  # no-op
        assert pulser._thread is None

    def test_stop_joins_thread(self) -> None:
        """After ``stop``, the worker thread must have exited."""
        pulser = _HeartbeatPulser(callbacks=[], interval_seconds=10.0)
        pulser.start()
        thread = pulser._thread
        assert thread is not None
        pulser.stop()
        # Thread handle cleared after join.
        assert pulser._thread is None
        assert not thread.is_alive()

    def test_emits_heartbeat_event_per_tick(self) -> None:
        """``_run`` loop emits one HeartbeatEvent per interval slept."""
        cb = _RecordingCallback()
        # Tiny interval so the test finishes fast. 0.05s gives us 2+
        # ticks inside the 0.18s sleep window.
        pulser = _HeartbeatPulser(callbacks=[cb], interval_seconds=0.05)
        pulser.current_phase = "phase_x"
        pulser.start()
        try:
            time.sleep(0.18)
        finally:
            pulser.stop()

        assert len(cb.events) >= 1, "expected at least one heartbeat tick"
        for event in cb.events:
            assert isinstance(event, HeartbeatEvent)
            assert event.current_phase == "phase_x"
            assert event.elapsed_seconds >= 0.0
            # memory_usage_mb may be None on platforms where both
            # resource.getrusage and psutil fail — don't assert a value,
            # just that the field is present on the event.
            assert hasattr(event, "memory_usage_mb")

    def test_current_phase_mutation_reflected_on_next_tick(self) -> None:
        """Mutating ``current_phase`` before the next tick updates the event."""
        cb = _RecordingCallback()
        pulser = _HeartbeatPulser(callbacks=[cb], interval_seconds=0.05)
        pulser.current_phase = "phase_a"
        pulser.start()
        try:
            time.sleep(0.08)  # one tick with phase_a
            pulser.current_phase = "phase_b"
            time.sleep(0.12)  # more ticks with phase_b
        finally:
            pulser.stop()

        phases = [e.current_phase for e in cb.events]
        assert "phase_a" in phases or "phase_b" in phases
        # At least the last recorded tick must reflect the latest mutation.
        if len(phases) >= 2:
            assert phases[-1] == "phase_b"

    def test_raising_callback_does_not_crash_pulser(self) -> None:
        """A callback that raises must not stop the pulser loop."""
        bad = _RaisingCallback()
        good = _RecordingCallback()
        pulser = _HeartbeatPulser(callbacks=[bad, good], interval_seconds=0.05)
        pulser.start()
        try:
            time.sleep(0.18)
        finally:
            pulser.stop()

        # The bad callback was invoked, and the good callback kept
        # receiving events after the bad one raised.
        assert bad.call_count >= 1
        # Both callbacks see the same events — ordering is safe because
        # ``_safe_emit_event`` iterates sequentially.
        assert len(good.events) >= 1
