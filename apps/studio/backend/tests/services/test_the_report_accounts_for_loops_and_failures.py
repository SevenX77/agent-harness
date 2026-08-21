"""What the report owes a reader about repetition and about going wrong.

Problem ledger R1, three of the five gaps found when the report was checked
line by line against the 2026-08-08 spec (PM's own words, quoted in
`run-execution/mvp1-alignment.md` F6):

  "…batch/loop 详细情况;… 每个节点报错详情"

* **Repetition was invisible.** A node that ran once and a node that ran forty
  times over forty items rendered as the same single row of summed numbers, so
  "which item was slow" and "which item failed" had no answer. The engine's own
  `parallel_map_group_started/ended` events were never read at all.
* **The `loop iterations` column was not loop iterations.** It counted
  `agent_loop_iteration` — turns of the ReAct loop INSIDE one execution — under
  a name that reads as "how many times this node ran".
* **Going wrong was under-reported.** Only a protocol violation and a rejected
  submission were collected. A run cut short for looping, or one that quietly
  fell back off its builtin subagent, left no trace in the report at all — and a
  single collected message could run to thousands of characters, burying the
  rest of the section.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.run_report import build_run_report


def _write_run(run_dir: Path, events: list[dict[str, object]], *, status: str = "success") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"status": status, "kind": "run"}), encoding="utf-8"
    )


def _phase(
    name: str,
    execution: str,
    at: str,
    *,
    end: bool = False,
    outcome: str = "completed",
) -> dict[str, object]:
    """One frame of a phase execution.

    ``phase_end`` always carries an ``outcome``: `PhaseEndEvent.status` is a
    required field precisely so that "a phase ended without saying how" is not
    representable (ledger E17), so a fixture omitting it would be describing an
    event the engine cannot emit.
    """
    if not end:
        return {
            "event_type": "phase_start",
            "timestamp": at,
            "phase_name": name,
            "phase_execution_id": execution,
        }
    return {
        "event_type": "phase_end",
        "timestamp": at,
        "phase_name": name,
        "phase_execution_id": execution,
        "status": outcome,
    }


def _llm(name: str, at: str, tokens: tuple[int, int]) -> dict[str, object]:
    return {
        "event_type": "llm_call",
        "timestamp": at,
        "phase_name": name,
        "input_tokens": tokens[0],
        "output_tokens": tokens[1],
        "resolved_model": "claude-sonnet-5",
    }


def _iterated_run(run_dir: Path) -> None:
    """One node, three executions — an `iterate` over three items."""
    _write_run(
        run_dir,
        [
            {"event_type": "run_started", "timestamp": "2026-08-20T10:00:00+00:00"},
            _phase("summarize", "exec-1", "2026-08-20T10:00:00+00:00"),
            _llm("summarize", "2026-08-20T10:00:01+00:00", (100, 20)),
            _phase("summarize", "exec-1", "2026-08-20T10:00:02+00:00", end=True),
            _phase("summarize", "exec-2", "2026-08-20T10:00:02+00:00"),
            _llm("summarize", "2026-08-20T10:00:03+00:00", (7, 3)),
            _phase("summarize", "exec-2", "2026-08-20T10:00:30+00:00", end=True),
            _phase("summarize", "exec-3", "2026-08-20T10:00:30+00:00"),
            {
                "event_type": "protocol_violation",
                "timestamp": "2026-08-20T10:00:31+00:00",
                "phase_name": "summarize",
                "violations": ["finish_task was never called"],
            },
            _phase("summarize", "exec-3", "2026-08-20T10:00:32+00:00", end=True, outcome="failed"),
            {"event_type": "run_ended", "timestamp": "2026-08-20T10:00:32+00:00"},
        ],
    )


def test_a_node_that_ran_three_times_says_so(tmp_path: Path) -> None:
    _iterated_run(tmp_path / "run")

    report = build_run_report(tmp_path / "run")

    assert "## Repeats" in report, "a node that ran more than once needs its own accounting"
    # The summed row is still there, and now says how many executions it sums.
    assert "| `summarize` |" in report


def test_each_execution_is_costed_and_judged_on_its_own(tmp_path: Path) -> None:
    """"item 数/耗时/token/成败" — the four things a per-item row has to answer."""
    _iterated_run(tmp_path / "run")

    report = build_run_report(tmp_path / "run")
    repeats = report.split("## Repeats", 1)[1]

    assert "3 executions" in repeats
    # The slow one is findable: execution 2 took 28s while its siblings took 2s.
    assert "28.00s" in repeats
    # Cost is per execution, not just per node.
    assert "100/20" in repeats and "7/3" in repeats
    # And the one that broke is marked, rather than being averaged away.
    assert "failed" in repeats


def test_the_agent_turn_count_is_not_called_a_loop_count(tmp_path: Path) -> None:
    """`agent_loop_iteration` counts turns WITHIN one execution of a node.

    Calling that column "loop iterations" told the reader a node had looped
    three times when it had run once and thought three times.
    """
    _write_run(
        tmp_path / "run",
        [
            _phase("draft", "exec-1", "2026-08-20T10:00:00+00:00"),
            {
                "event_type": "agent_loop_iteration",
                "timestamp": "2026-08-20T10:00:01+00:00",
                "phase_name": "draft",
                "iteration": 3,
            },
            _phase("draft", "exec-1", "2026-08-20T10:00:04+00:00", end=True),
        ],
    )

    report = build_run_report(tmp_path / "run")

    assert "agent turns" in report
    assert "loop iterations" not in report


def test_a_parallel_map_fan_out_is_reported_as_the_group_it_was(tmp_path: Path) -> None:
    """The engine already announces the fan-out; the report simply never read it."""
    _write_run(
        tmp_path / "run",
        [
            {
                "event_type": "parallel_map_group_started",
                "timestamp": "2026-08-20T10:00:00+00:00",
                "group_key": "grp-1",
                "skill_path": "skills/summarize-one",
                "item_count": 12,
                "max_concurrent": 4,
                "item_as": "chapter",
            },
            {
                "event_type": "parallel_map_group_ended",
                "timestamp": "2026-08-20T10:01:00+00:00",
                "group_key": "grp-1",
                "succeeded": 10,
                "failed": 2,
                "wall_time_seconds": 58.5,
            },
        ],
    )

    report = build_run_report(tmp_path / "run")
    repeats = report.split("## Repeats", 1)[1]

    assert "skills/summarize-one" in repeats
    assert "12" in repeats and "10" in repeats and "2" in repeats
    assert "58.50s" in repeats
    assert "4" in repeats, "concurrency is what makes a fan-out's wall time readable"


def test_a_run_cut_for_looping_says_it_was(tmp_path: Path) -> None:
    _write_run(
        tmp_path / "run",
        [
            _phase("draft", "exec-1", "2026-08-20T10:00:00+00:00"),
            {
                "event_type": "loop_detected",
                "timestamp": "2026-08-20T10:00:05+00:00",
                "phase_name": "draft",
                "message": "same tool call repeated 5 times",
            },
        ],
        status="failed",
    )

    report = build_run_report(tmp_path / "run")

    assert "loop_detected" in report
    assert "same tool call repeated 5 times" in report


def test_a_builtin_subagent_that_fell_back_is_reported(tmp_path: Path) -> None:
    """A fallback is not a crash, which is exactly why it needs saying.

    The run completed — on a lesser path than the one it was configured for.
    Nothing else in the report would have shown that.
    """
    _write_run(
        tmp_path / "run",
        [
            _phase("draft", "exec-1", "2026-08-20T10:00:00+00:00"),
            {
                "event_type": "builtin_subagent_fallback",
                "timestamp": "2026-08-20T10:00:03+00:00",
                "phase_name": "draft",
                "message": "claude_code unavailable; ran inline",
            },
            _phase("draft", "exec-1", "2026-08-20T10:00:09+00:00", end=True),
        ],
    )

    report = build_run_report(tmp_path / "run")

    assert "claude_code unavailable" in report


def test_one_enormous_message_cannot_bury_the_section(tmp_path: Path) -> None:
    """Measured: a real protocol_violation message ran to several thousand chars.

    The full text is in `trace.jsonl`, which the report links to. What the
    report owes is enough to recognise the failure, not a transcript of it.
    """
    _write_run(
        tmp_path / "run",
        [
            _phase("draft", "exec-1", "2026-08-20T10:00:00+00:00"),
            {
                "event_type": "protocol_violation",
                "timestamp": "2026-08-20T10:00:01+00:00",
                "phase_name": "draft",
                "message": "schema mismatch: " + "x" * 4000,
            },
        ],
        status="failed",
    )

    report = build_run_report(tmp_path / "run")
    failure = report.split("## Failure", 1)[1].split("\n##", 1)[0]

    assert "schema mismatch" in failure, "the recognisable head of the message survives"
    assert len(failure) < 800, f"section is still {len(failure)} chars long"
    assert "…" in failure, "a truncated message has to look truncated"


def test_every_node_row_says_how_it_ended(tmp_path: Path) -> None:
    """R1 gap ⑤: the Nodes table costed each node without ever saying its outcome."""
    _write_run(
        tmp_path / "run",
        [
            _phase("ok_node", "exec-1", "2026-08-20T10:00:00+00:00"),
            _phase("ok_node", "exec-1", "2026-08-20T10:00:01+00:00", end=True),
            _phase("broke", "exec-2", "2026-08-20T10:00:01+00:00"),
            {
                "event_type": "protocol_violation",
                "timestamp": "2026-08-20T10:00:02+00:00",
                "phase_name": "broke",
                "message": "no finish_task",
            },
            _phase("broke", "exec-2", "2026-08-20T10:00:02+00:00", end=True, outcome="failed"),
            _phase("never_closed", "exec-3", "2026-08-20T10:00:02+00:00"),
        ],
        status="failed",
    )

    nodes = build_run_report(tmp_path / "run").split("## Nodes", 1)[1].split("\n##", 1)[0]
    rows = {
        line.split("|")[1].strip(): line for line in nodes.splitlines() if line.startswith("| `")
    }

    assert "ok" in rows["`ok_node`"]
    assert "failed" in rows["`broke`"]
    # A node that opened and never closed did not succeed and did not fail — the
    # run ended while it was still open, and saying so is the whole point.
    assert "unfinished" in rows["`never_closed`"]


def test_a_correction_is_counted_but_is_not_a_failure(tmp_path: Path) -> None:
    """Nudges and handled tool errors changed the run without breaking it.

    They belong in the accounting — a node that needed six nudges is worth
    looking at — but not in Failure, which is the list of things that went
    wrong. Same reasoning the engine already applies to `tool_error_handled`:
    it became feedback the model read, and the run carried on.
    """
    _write_run(
        tmp_path / "run",
        [
            _phase("draft", "exec-1", "2026-08-20T10:00:00+00:00"),
            {
                "event_type": "nudge",
                "timestamp": "2026-08-20T10:00:01+00:00",
                "phase_name": "draft",
                "message": "keep going",
            },
            {
                "event_type": "tool_error_handled",
                "timestamp": "2026-08-20T10:00:02+00:00",
                "phase_name": "draft",
                "message": "read_file: no such file",
            },
            _phase("draft", "exec-1", "2026-08-20T10:00:03+00:00", end=True),
        ],
    )

    report = build_run_report(tmp_path / "run")
    nodes = report.split("## Nodes", 1)[1].split("\n##", 1)[0]

    assert "corrections" in nodes
    assert "| 2 |" in nodes, "one nudge plus one handled tool error"
    assert "## Failure" not in report, "nothing here went wrong"
