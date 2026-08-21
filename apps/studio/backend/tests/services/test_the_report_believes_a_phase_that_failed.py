"""A node whose phase reported failure is not reported as ok.

Field evidence (2026-08-20, run ``2026-08-20T15-44-03_98726d7c``): the run died
on ``[F-v3-agent-validator-failed]`` in phase ``impossible``, and the Nodes table
gave that node ``ok`` — the only failure signal anywhere in the report was the
run-level Failure section. Nothing was wrong with the reader: the node's own
frames said nothing about the outcome, so ``ok`` was the honest reading of what
it had (ledger E17).

The engine now states the outcome on ``phase_end`` (``status``). This pins the
report reading it, and pins the two things a status must NOT do: a phase that
completed stays ok, and a rejected submission the model then fixed is still not
a failed phase — the phase says how IT ended, which is the whole point of asking
the phase instead of inferring from the events inside it.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.run_report import build_run_report

NODE_ROW_PREFIX = "| `impossible` |"


def _event(event_type: str, at: str, **fields: object) -> dict[str, object]:
    return {"event_type": event_type, "timestamp": at, "phase_name": "impossible", **fields}


def _write_run(run_dir: Path, events: list[dict[str, object]], *, status: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"status": status, "kind": "run"}), encoding="utf-8"
    )


def _node_row(report: str) -> str:
    rows = [line for line in report.splitlines() if line.startswith(NODE_ROW_PREFIX)]
    assert len(rows) == 1, f"expected exactly one row for the node, got:\n{report}"
    return rows[0]


def test_a_phase_that_says_it_failed_is_a_failed_node(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-validator-died"
    _write_run(
        run_dir,
        [
            _event("phase_start", "2026-08-20T10:00:00+00:00", phase_execution_id="exec-1"),
            # The submission passed the finish gate — the validator that rejected
            # it runs after, so every event INSIDE the phase reads like success.
            _event(
                "finish_task_verdict",
                "2026-08-20T10:00:03+00:00",
                phase_execution_id="exec-1",
                verdict="accepted",
            ),
            _event(
                "phase_end",
                "2026-08-20T10:00:04+00:00",
                phase_execution_id="exec-1",
                status="failed",
            ),
        ],
        status="crashed",
    )

    row = _node_row(build_run_report(run_dir))

    assert " failed " in row, f"the phase said it failed, so the node did too; got: {row}"


def test_a_phase_that_completed_is_still_ok(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-clean"
    _write_run(
        run_dir,
        [
            _event("phase_start", "2026-08-20T10:00:00+00:00", phase_execution_id="exec-1"),
            _event(
                "phase_end",
                "2026-08-20T10:00:04+00:00",
                phase_execution_id="exec-1",
                status="completed",
            ),
        ],
        status="success",
    )

    row = _node_row(build_run_report(run_dir))

    assert " ok " in row, f"nothing went wrong in this phase; got: {row}"


def test_a_rejected_submission_the_model_then_fixed_is_not_a_failed_phase(
    tmp_path: Path,
) -> None:
    """The third rule this file's docstring states, which nothing checked.

    Field evidence (2026-08-20, run ``2026-08-20T19-55-51_722f59b0``): phase
    ``first`` had one submission rejected by the finish gate, was sent back,
    corrected it, and ended ``completed`` — ``trace.jsonl`` says so and the
    canvas drew it as Success. The Nodes table printed it ``failed``, in a row
    whose own ``corrections`` column said ``1``.

    Two answers to one question, and the report was giving the wrong one: being
    sent back to fix a submission is what the correction loop is FOR. If that
    counted as failure, every phase that ever used the loop would be a failed
    phase, and the word would stop distinguishing anything.
    """
    run_dir = tmp_path / "run-corrected"
    _write_run(
        run_dir,
        [
            _event("phase_start", "2026-08-20T10:00:00+00:00", phase_execution_id="exec-1"),
            _event(
                "finish_task_verdict",
                "2026-08-20T10:00:02+00:00",
                phase_execution_id="exec-1",
                verdict="rejected",
                message="Rejected a finish_task submission in phase 'first': 1 problem(s) found",
                errors=["business_data_md is empty"],
            ),
            _event(
                "finish_task_verdict",
                "2026-08-20T10:00:05+00:00",
                phase_execution_id="exec-1",
                verdict="accepted",
            ),
            _event(
                "phase_end",
                "2026-08-20T10:00:06+00:00",
                phase_execution_id="exec-1",
                status="completed",
            ),
        ],
        status="success",
    )

    report = build_run_report(run_dir)
    row = _node_row(report)

    assert " ok " in row, (
        f"the phase was sent back once and then finished; it did not fail. Got: {row}"
    )
    assert "business_data_md is empty" in report, (
        "the rejection still belongs in the report — it is a real thing that "
        "happened inside the phase. What it must not do is decide how the "
        "phase ENDED"
    )
