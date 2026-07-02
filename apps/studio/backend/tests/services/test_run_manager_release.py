"""RunManager._release_run_process must escalate to kill() for stubborn children.

A run child that survives terminate() + join(timeout) would be orphaned into
interpreter shutdown — the exit-139 class fixed in PR #259. terminate() sends
SIGTERM, which a busy/blocked child can ignore; release must escalate to kill()
and reap the child before dropping the reference.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.services.run_manager import RunManager


class _StubbornProcess:
    """Ignores terminate(); only dies after kill() followed by join()."""

    def __init__(self) -> None:
        self.terminate_calls = 0
        self.kill_calls = 0
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def terminate(self) -> None:
        self.terminate_calls += 1  # SIGTERM ignored

    def kill(self) -> None:
        self.kill_calls += 1

    def join(self, timeout: float | None = None) -> None:
        if self.kill_calls:
            self._alive = False


class _CooperativeProcess:
    """Dies on terminate(); kill() must never be needed."""

    def __init__(self) -> None:
        self.kill_calls = 0
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def terminate(self) -> None:
        self._alive = False

    def kill(self) -> None:
        self.kill_calls += 1

    def join(self, timeout: float | None = None) -> None:
        return None


def test_release_escalates_to_kill_when_terminate_is_ignored() -> None:
    process = _StubbornProcess()

    RunManager._release_run_process(process, SimpleNamespace())

    assert process.terminate_calls == 1
    assert process.kill_calls >= 1
    assert not process.is_alive()


def test_release_does_not_kill_a_child_that_died_on_terminate() -> None:
    process = _CooperativeProcess()

    RunManager._release_run_process(process, SimpleNamespace())

    assert process.kill_calls == 0
    assert not process.is_alive()


def test_release_is_a_noop_for_inline_test_doubles() -> None:
    # Mock factories used across the suite have neither terminate nor kill.
    RunManager._release_run_process(SimpleNamespace(), SimpleNamespace())
