"""A report can be regenerated, so opening one shows today's rendering.

`report.md` is written exactly once, at the moment the run is sealed. The design
calls it a pure projection that "随时可以被重新生成,删掉不丢信息" — regenerable at
any time, losing nothing when deleted (RUN_EXECUTION-5, run-execution
mvp1-alignment.md:137). Nothing in the product could regenerate one, so a report
stayed frozen on whatever the renderer did the day the run finished: every
improvement to the renderer reached new runs only, and the run history read as a
museum of past versions.

Opening the report is the moment that matters, and it is the moment the
projection is cheap: one run, one write, only when a person asks to read it.

A run that has not concluded is refused rather than projected half-way. It is
not squeamishness about a partial render: `report_path` is derived from the
file's existence (`_run_report_path`), so writing one for a live run would make
the run list advertise a report for a run that is still going, and its contents
would contradict themselves minutes later.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.core.exceptions import StudioHTTPException
from app.services.run_manager import run_manager
from app.services.run_report import REPORT_FILENAME, build_run_report
from app.services.skills import runs_dir_for
from fastapi.testclient import TestClient

SKILL = "text-segmentation"
STALE = "# written by last year's renderer\n"


def _seal_run(root: Path, run_id: str, *, status: str = "success", report: str | None) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "kind": "run",
                "status": status,
                "started_at": "2026-08-20T14:00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "trace.jsonl").write_text("", encoding="utf-8")
    if report is not None:
        (run_dir / REPORT_FILENAME).write_text(report, encoding="utf-8")
    return run_dir


def test_opening_a_report_re_renders_it_with_todays_renderer(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    run_dir = _seal_run(
        runs_dir_for(skills_dir / SKILL), "2026-08-20T14-00-00_aaaaaaaa", report=STALE
    )

    run_manager.rebuild_run_report(SKILL, run_dir.name)

    rendered = (run_dir / REPORT_FILENAME).read_text(encoding="utf-8")
    assert STALE not in rendered
    assert rendered == build_run_report(run_dir)


def test_a_run_whose_report_was_deleted_gets_one_back(
    studio_roots: tuple[Path, Path],
) -> None:
    """"Deleting it loses no information" is only true if it can come back."""
    skills_dir, _ = studio_roots
    run_dir = _seal_run(
        runs_dir_for(skills_dir / SKILL), "2026-08-20T14-01-00_bbbbbbbb", report=None
    )

    metadata = run_manager.rebuild_run_report(SKILL, run_dir.name)

    assert (run_dir / REPORT_FILENAME).is_file()
    assert metadata.report_path == f".workspace/runs/{run_dir.name}/{REPORT_FILENAME}"


def test_a_run_still_going_is_refused_rather_than_projected_half_way(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    run_dir = _seal_run(
        runs_dir_for(skills_dir / SKILL),
        "2026-08-20T14-02-00_cccccccc",
        status="running",
        report=None,
    )

    with pytest.raises(StudioHTTPException) as raised:
        run_manager.rebuild_run_report(SKILL, run_dir.name)

    assert raised.value.status_code == 409
    assert raised.value.detail["error_code"] == "RUN_NOT_CONCLUDED"
    assert not (run_dir / REPORT_FILENAME).exists(), "a live run must not advertise a report"


def test_a_run_that_was_never_there_is_not_found(studio_roots: tuple[Path, Path]) -> None:
    with pytest.raises(StudioHTTPException) as raised:
        run_manager.rebuild_run_report(SKILL, "2026-08-20T14-03-00_dddddddd")

    assert raised.value.status_code == 404


def test_the_endpoint_answers_with_the_run_the_editor_should_open(
    client: TestClient,
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    run_dir = _seal_run(
        runs_dir_for(skills_dir / SKILL), "2026-08-20T14-04-00_eeeeeeee", report=STALE
    )

    response = client.post(f"/api/skills/{SKILL}/runs/{run_dir.name}/report")

    assert response.status_code == 200
    assert response.json()["report_path"] == (
        f".workspace/runs/{run_dir.name}/{REPORT_FILENAME}"
    )
    assert STALE not in (run_dir / REPORT_FILENAME).read_text(encoding="utf-8")
