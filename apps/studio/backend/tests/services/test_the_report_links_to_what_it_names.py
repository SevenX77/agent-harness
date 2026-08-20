"""The report names files and runs; it has to let the reader open them.

Problem ledger R1, gaps ① and ③ — the two the 2026-08-08 spec asks for by name
("input files链接;… llm vs 结果链接") and the report answered with plain text:

* **Input files were code spans, not links.** ``import_files/x.json`` is
  the path the run pinned, relative to the skill's `.workspace`. The run
  directory sits under that same `.workspace`, so the file is two levels up —
  computable, and the report simply never computed it.
* **Only the run's DECLARED bindings were read**, from
  `runtime_config.snapshot.json`. A file the engine injected mid-run
  (`input_file_injected`, carried on an edge transition into one node) appeared
  nowhere, so "which files did this run read" had an answer that was true at
  launch and stale by the end.
* **A compare candidate's report named its group and candidate id and stopped
  there** — no way to reach the run it is being compared against. That was not
  only a rendering gap: a side-run never recorded WHICH run it was a candidate
  against, so the link had nothing to be made of.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.run_report import build_run_report

BINDING = {
    "path": "import_files/sample/chapters.json",
    "sha256": "sha256:abc123",
    "value_type": "json",
}


def _write_run(
    run_dir: Path,
    *,
    events: list[dict[str, object]] | None = None,
    metadata: dict[str, object] | None = None,
    runtime_config: dict[str, object] | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "trace.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events or []), encoding="utf-8"
    )
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"status": "success", "kind": "run", **(metadata or {})}), encoding="utf-8"
    )
    if runtime_config is not None:
        (run_dir / "runtime_config.snapshot.json").write_text(
            json.dumps(runtime_config), encoding="utf-8"
        )


def _run_in_a_workspace(tmp_path: Path, run_id: str = "2026-08-20T10-00-00_abcd") -> Path:
    """A run directory where it really lives: `<skill>/.workspace/runs/<run id>`."""
    run_dir = tmp_path / "skill" / ".workspace" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def test_a_pinned_input_file_is_a_link_the_reader_can_follow(tmp_path: Path) -> None:
    run_dir = _run_in_a_workspace(tmp_path)
    _write_run(run_dir, runtime_config={"inputs": {"active": {"root": {"chapters": BINDING}}}})

    inputs = build_run_report(run_dir).split("## Inputs", 1)[1].split("\n##", 1)[0]

    # Two levels up from `<workspace>/runs/<run id>` is the workspace the
    # binding path is relative to.
    assert "(../../import_files/sample/chapters.json)" in inputs
    assert "`chapters`" in inputs, "the fields it supplied still have to be named"


def test_a_run_outside_a_workspace_still_names_the_file(tmp_path: Path) -> None:
    """No workspace above it, so no link can be computed — and none is faked.

    A link that resolves to nothing is worse than the path in plain text: it
    invites a click that fails.
    """
    run_dir = tmp_path / "loose-run"
    _write_run(run_dir, runtime_config={"inputs": {"active": {"root": {"chapters": BINDING}}}})

    inputs = build_run_report(run_dir).split("## Inputs", 1)[1].split("\n##", 1)[0]

    assert "import_files/sample/chapters.json" in inputs
    assert "](" not in inputs.split("input_data.json")[0]


def test_a_file_the_engine_injected_mid_run_is_reported(tmp_path: Path) -> None:
    """The snapshot says what was declared; the events say what actually arrived."""
    run_dir = _run_in_a_workspace(tmp_path)
    _write_run(
        run_dir,
        runtime_config={"inputs": {"active": {"root": {"chapters": BINDING}}}},
        events=[
            {
                "event_type": "input_file_injected",
                "timestamp": "2026-08-20T10:00:01+00:00",
                "edge_transition_id": "t-1",
                "from_phases": ["setup"],
                "to_phase": "summarize",
                "changed_keys": [],
                "blackboard_snapshot": {},
                "file_ref": "import_files/late/notes.md",
                "target_field": "notes",
            }
        ],
    )

    inputs = build_run_report(run_dir).split("## Inputs", 1)[1].split("\n##", 1)[0]

    assert "import_files/late/notes.md" in inputs
    assert "summarize" in inputs, "an injected file belongs to the node it was handed to"
    assert "`notes`" in inputs


def test_a_compare_candidate_links_back_to_the_run_it_is_measured_against(
    tmp_path: Path,
) -> None:
    run_dir = _run_in_a_workspace(tmp_path, "2026-08-20T10-05-00_cand")
    _write_run(
        run_dir,
        metadata={
            "compare_group_id": "cmp-1",
            "compare_node_id": "summarize",
            "candidate_id": "cand-a",
            "candidate_label": "claude-opus-5",
            "compare_base_run_id": "2026-08-20T10-00-00_abcd",
        },
    )

    compare = build_run_report(run_dir).split("## Model compare", 1)[1].split("\n##", 1)[0]

    assert "(../2026-08-20T10-00-00_abcd/report.md)" in compare
    assert "claude-opus-5" in compare
    assert "summarize" in compare


def test_a_candidate_with_no_base_recorded_says_so_rather_than_guessing(
    tmp_path: Path,
) -> None:
    run_dir = _run_in_a_workspace(tmp_path, "2026-08-20T10-05-00_cand")
    _write_run(
        run_dir,
        metadata={
            "compare_group_id": "cmp-1",
            "compare_node_id": "summarize",
            "candidate_id": "cand-a",
            "candidate_label": "claude-opus-5",
        },
    )

    compare = build_run_report(run_dir).split("## Model compare", 1)[1].split("\n##", 1)[0]

    assert "report.md)" not in compare
    assert "claude-opus-5" in compare
