"""Every run row can reach its own report.

Decision `docs/design/2026-08-09-trace-ia-and-streaming-overhaul-decision.md` D8:
"运行列表每一行带报告链接。这需要后端把 `report_path` 从 `RunDetail` 扩展到列表项
`RunMetadata` ... 实施时须实测 20+ 条 run 时列表接口的耗时;若逐条 `is_file()` 探测
成为瓶颈,改为 seal 时把路径写进 run 元数据。"

The same decision keeps `report.md` a pure projection, so the path is DERIVED at
read time from the file's existence and never written into `run_metadata.json` —
a stored path outlives the file it describes and starts lying the moment the run
directory is cleaned.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.models.runs import RunMetadata
from app.services.run_manager import run_manager
from app.services.run_report import REPORT_FILENAME
from app.services.skills import runs_dir_for

RUN_WITH_REPORT = "2026-08-09T14-00-00_aaaaaaaa"
RUN_WITHOUT_REPORT = "2026-08-09T14-01-00_bbbbbbbb"


def _seed_run(root: Path, run_id: str, *, with_report: bool) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "kind": "run",
                "status": "success",
                "started_at": "2026-08-09T14:00:00",
                "metrics": None,
                "input_summary": None,
            }
        ),
        encoding="utf-8",
    )
    if with_report:
        (run_dir / REPORT_FILENAME).write_text("# Run report\n", encoding="utf-8")
    return run_dir


def test_a_run_row_carries_the_path_to_its_own_report(
    studio_roots: tuple[Path, Path],
) -> None:
    skills_dir, _ = studio_roots
    runs_root = runs_dir_for(skills_dir / "text-segmentation")
    run_dir = _seed_run(runs_root, RUN_WITH_REPORT, with_report=True)

    listed = run_manager.list_runs("text-segmentation")

    row = next(entry for entry in listed.runs if entry.run_id == RUN_WITH_REPORT)
    assert row.report_path == str(run_dir / REPORT_FILENAME)


def test_a_run_with_no_report_offers_no_link(studio_roots: tuple[Path, Path]) -> None:
    """A row must not advertise a report that is not there."""
    skills_dir, _ = studio_roots
    runs_root = runs_dir_for(skills_dir / "text-segmentation")
    _seed_run(runs_root, RUN_WITHOUT_REPORT, with_report=False)

    listed = run_manager.list_runs("text-segmentation")

    row = next(entry for entry in listed.runs if entry.run_id == RUN_WITHOUT_REPORT)
    assert row.report_path is None


def test_the_report_path_never_reaches_the_stored_document() -> None:
    """`report.md` stays a projection: the stored record must not name it.

    A path written into `run_metadata.json` survives the file being deleted and
    the skill directory being moved, at which point the record asserts something
    false. Persistence therefore serializes the stored subset explicitly.
    """
    metadata = RunMetadata(
        run_id=RUN_WITH_REPORT,
        status="success",
        started_at="2026-08-09T14:00:00",  # type: ignore[arg-type]
        report_path="/somewhere/report.md",
    )

    assert "report_path" not in json.loads(metadata.persisted_json())
    assert "report_path" in json.loads(metadata.model_dump_json())


def test_probing_twenty_five_runs_stays_within_one_listing_budget(
    studio_roots: tuple[Path, Path],
) -> None:
    """D8's measurement, kept as a regression bound rather than a stopwatch.

    One `is_file()` per row is a stat syscall; the bound below is ~2 orders of
    magnitude above the measured cost, so it stays quiet on a slow CI box while
    still failing loudly if listing ever becomes quadratic or starts reading the
    report bodies.
    """
    skills_dir, _ = studio_roots
    runs_root = runs_dir_for(skills_dir / "text-segmentation")
    for index in range(25):
        _seed_run(runs_root, f"2026-08-09T15-00-{index:02d}_cccccccc", with_report=True)

    started = time.perf_counter()
    listed = run_manager.list_runs("text-segmentation")
    elapsed = time.perf_counter() - started

    assert len(listed.runs) == 25
    assert all(entry.report_path is not None for entry in listed.runs)
    # Measured 23ms on the dev box (2026-08-09); the bound is ~40x that so a
    # slow CI runner stays quiet while a quadratic regression still trips it.
    assert elapsed < 1.0, f"listing 25 runs took {elapsed:.3f}s"
