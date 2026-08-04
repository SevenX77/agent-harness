"""Stopping a run must end it without destroying what it produced.

The only way to end a run early used to be DELETE, which terminates the worker
and then removes the whole run directory — so "stop and look at how far it got"
was not expressible. Cancelling is its own terminal outcome: the worker stops,
the run keeps its evidence, and every surface hears about it the same way it
hears about a run that finished on its own.
"""

from __future__ import annotations

import queue
from pathlib import Path
from typing import Any

import pytest
from app.services.run_manager import run_manager
from fastapi.testclient import TestClient

from .test_api import _record_predict_pass, fake_run_worker


class HangingProcess:
    """A worker that starts and then never finishes on its own."""

    def __init__(self, *, target: Any, args: tuple[Any, ...]) -> None:
        self._target = target
        self._args = args
        self.exitcode: int | None = None
        self._alive = False
        self.terminated = False

    def start(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        del timeout

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False
        self.exitcode = -15


def _start_hanging_run(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(run_manager, "process_factory", HangingProcess)
    monkeypatch.setattr(run_manager, "queue_factory", queue.Queue)
    monkeypatch.setattr(run_manager, "worker", fake_run_worker)
    _record_predict_pass("text-segmentation")

    response = client.post(
        "/api/skills/text-segmentation/runs",
        json={"input_data": {"input_text": "hello"}},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running"
    return str(body["run_id"])


def test_cancelling_a_run_stops_the_worker_and_keeps_the_run(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del studio_roots
    run_id = _start_hanging_run(client, monkeypatch)

    response = client.post(f"/api/skills/text-segmentation/runs/{run_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # Stopping is not deleting: the directory and its account survive, which is
    # what DELETE takes away. (Reading a cancelled run's full detail additionally
    # needs its artifacts sealed — a worker killed mid-flight never sealed any.
    # Tracked separately; this test states only what cancel itself promises.)
    listed = client.get("/api/skills/text-segmentation/runs")
    assert listed.status_code == 200
    statuses = {run["run_id"]: run["status"] for run in listed.json()["runs"]}
    assert statuses[run_id] == "cancelled"


def test_cancelling_a_run_that_already_ended_is_rejected(
    client: TestClient,
    studio_roots: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del studio_roots
    run_id = _start_hanging_run(client, monkeypatch)
    assert client.post(f"/api/skills/text-segmentation/runs/{run_id}/cancel").status_code == 200

    # A second stop has nothing to stop; saying so beats silently reporting success.
    again = client.post(f"/api/skills/text-segmentation/runs/{run_id}/cancel")

    assert again.status_code == 409
    assert again.json()["error_code"] == "RUN_NOT_RUNNING"
