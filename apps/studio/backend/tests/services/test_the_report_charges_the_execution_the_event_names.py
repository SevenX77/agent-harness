"""A call is charged to the execution it names, not to whichever one is open.

Field evidence (2026-08-20, run ``2026-08-20T13-14-59_14582c6b``): ``aggregate``,
``extrac`` and ``settings`` each had two executions of the same node open at the
same time, and 4 of the run's 63 calls arrived during those windows. The report
kept one open execution per node id and charged every call to it, so those four
landed on whichever execution had opened last — a coin flip, not an attribution.

The engine now stamps ``phase_execution_id`` on every event emitted inside a
phase (ledger E15), so the owner is stated by the producer. What is left here is
to read it. The fallback for an event that names nothing is unchanged: charge it
to the open execution, because charging it somewhere still beats dropping it.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.run_report import build_run_report

FIRST, SECOND = "exec-first", "exec-second"


def _event(event_type: str, at: str, **fields: object) -> dict[str, object]:
    return {"event_type": event_type, "timestamp": at, "phase_name": "worker", **fields}


def _write_run(run_dir: Path, events: list[dict[str, object]]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"status": "success", "kind": "run"}), encoding="utf-8"
    )


def test_overlapping_executions_each_keep_their_own_calls(tmp_path: Path) -> None:
    """Two runs of one node, open at once, each with a call of its own size."""
    run_dir = tmp_path / "run-overlap"
    _write_run(
        run_dir,
        [
            _event("phase_start", "2026-08-20T10:00:00+00:00", phase_execution_id=FIRST),
            _event("phase_start", "2026-08-20T10:00:01+00:00", phase_execution_id=SECOND),
            # Both are open now. The first one's call arrives second, so a
            # reader that charges "whichever opened last" gets both wrong.
            _event(
                "llm_call",
                "2026-08-20T10:00:02+00:00",
                phase_execution_id=SECOND,
                input_tokens=200,
                output_tokens=20,
                resolved_model="claude-sonnet-5",
            ),
            _event(
                "llm_call",
                "2026-08-20T10:00:03+00:00",
                phase_execution_id=FIRST,
                input_tokens=100,
                output_tokens=10,
                resolved_model="claude-sonnet-5",
            ),
            _event("phase_end", "2026-08-20T10:00:04+00:00", phase_execution_id=SECOND),
            _event("phase_end", "2026-08-20T10:00:05+00:00", phase_execution_id=FIRST),
        ],
    )

    report = build_run_report(run_dir)

    repeats = [
        line
        for line in report.splitlines()
        if line.startswith("| 1 |") or line.startswith("| 2 |")
    ]
    assert len(repeats) == 2, f"expected two executions, got:\n{report}"
    charged = sorted(
        cell.strip()
        for line in repeats
        for cell in line.split("|")
        if "/" in cell and cell.strip()[:1].isdigit()
    )
    assert charged == ["100/10", "200/20"], (
        "each execution should carry exactly the call that named it, one 100/10 "
        f"and one 200/20; got {charged} in:\n{report}"
    )
    # The node row still sums both, which is a different question.
    assert any("300/30" in line for line in report.splitlines()), report
