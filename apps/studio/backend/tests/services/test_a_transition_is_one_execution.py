"""An edge event names the transition it happened in, not the phase after it.

Field evidence (2026-08-20, run ``2026-08-20T15-44-03_98726d7c``): a run with a
single phase and therefore a single transition reported ``input -> impossible``
as **2 executions** — one "unfinished", one "ok".

The cause is that two identifiers now ride on the same event. The engine stamps
``phase_execution_id`` on everything emitted inside ``wrap_edge_transition``
(ledger E15), and that scope covers the transition's own events too, where it
names the execution the transition leads INTO. The report charges those events
to the transition row (``_event_node``: an event carrying
``edge_transition_id`` happened between two node executions, decision
2026-08-15 D8) but then looked up the execution by the phase field, found an id
the transition row had never opened, and opened a second one for it.

So the rule this pins is that the two decisions use the same evidence: whichever
identifier says which ROW an event belongs to also says which EXECUTION of that
row it belongs to. Reading one from the transition and the other from the phase
is how one transition became two.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.run_report import build_run_report

TRANSITION = "transition-1"
EXECUTION = "execution-1"


def _write_run(run_dir: Path, events: list[dict[str, object]]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"status": "success", "kind": "run"}), encoding="utf-8"
    )


def test_one_transition_is_reported_as_one_execution(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-one-transition"
    _write_run(
        run_dir,
        [
            # Every event inside the transition scope carries BOTH ids: the
            # transition it is part of, and the phase execution it leads into.
            {
                "event_type": "edge_start",
                "timestamp": "2026-08-20T10:00:00+00:00",
                "edge_transition_id": TRANSITION,
                "phase_execution_id": EXECUTION,
                "to_phase": "worker",
            },
            {
                "event_type": "input_dispatch",
                "timestamp": "2026-08-20T10:00:01+00:00",
                "edge_transition_id": TRANSITION,
                "phase_execution_id": EXECUTION,
                "to_phase": "worker",
            },
            {
                "event_type": "edge_end",
                "timestamp": "2026-08-20T10:00:02+00:00",
                "edge_transition_id": TRANSITION,
                "phase_execution_id": EXECUTION,
                "to_phase": "worker",
            },
            {
                "event_type": "phase_start",
                "timestamp": "2026-08-20T10:00:03+00:00",
                "phase_name": "worker",
                "phase_execution_id": EXECUTION,
            },
            {
                "event_type": "phase_end",
                "timestamp": "2026-08-20T10:00:04+00:00",
                "phase_name": "worker",
                "phase_execution_id": EXECUTION,
            },
        ],
    )

    report = build_run_report(run_dir)

    assert "2 executions" not in report, report
    transition_rows = [
        line for line in report.splitlines() if line.startswith("| `input -> worker`")
    ]
    assert len(transition_rows) == 1, f"expected one transition row, got:\n{report}"
    assert "1×" in transition_rows[0], (
        f"the transition ran once and should say so; got {transition_rows[0]!r}"
    )
