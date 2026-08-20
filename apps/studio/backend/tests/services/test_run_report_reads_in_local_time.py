"""The report's clock is the clock of the person reading it.

A run puts two readings of its own start on one screen: the run id, which is a
local wall clock by decision D13 (`run-execution/mvp1-alignment.md` F1b — "UTC
戳对着文件树的人读起来就是错的时间"), and the report's `Started` row, which
printed the stored instant verbatim. Measured 2026-08-20 on a real report
(`story-deconstruction-v3-lab/.workspace/runs/2026-08-19T06-58-15_179d1440`):

    | Run     | `2026-08-19T06-58-15_179d1440` |
    | Started | 2026-08-19T13:58:15.556101Z    |

Two lines apart, one instant, seven hours between the readings. Neither value is
wrong; the presentation was, and D13's reason applies to whichever surface a
person reads it on.

The offset comes along because a bare local stamp cannot say which zone it is —
`git log` prints local time with its offset for exactly that reason, and the
run id cannot carry one (it is a filename).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def _sealed(run_dir: Path, started_at: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "trace.jsonl").write_text(
        json.dumps({"event_type": "run_started", "timestamp": started_at}) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": run_dir.name, "status": "success", "started_at": started_at}),
        encoding="utf-8",
    )


def _started_row(report: str) -> str:
    rows = [line for line in report.splitlines() if line.startswith("| Started |")]
    assert len(rows) == 1, f"expected exactly one Started row, got {rows}"
    return rows[0]


def test_started_is_the_reader_s_wall_clock(tmp_path: Path) -> None:
    from app.services.run_report import build_run_report

    instant = datetime(2026, 8, 19, 13, 58, 15, tzinfo=UTC)
    run_dir = tmp_path / "runs" / "2026-08-19T06-58-15_179d1440"
    _sealed(run_dir, instant.isoformat().replace("+00:00", "Z"))

    row = _started_row(build_run_report(run_dir))

    local = instant.astimezone()
    assert local.strftime("%Y-%m-%d %H:%M:%S") in row, (
        f"the row should read the local wall clock of {instant}; got {row}"
    )
    assert local.strftime("%z")[:3] + ":" + local.strftime("%z")[3:] in row, (
        f"a local stamp with no offset cannot say which zone it is; got {row}"
    )
    assert "Z" not in row.replace("Started", ""), f"a UTC stamp leaked into the report: {row}"


def test_a_naive_stamp_is_read_as_local_not_reinterpreted(tmp_path: Path) -> None:
    """A stamp with no zone is already the local wall clock — do not shift it.

    The engine writes aware UTC everywhere, so this is the defensive half: if a
    naive value ever reaches the report, adding an offset to it would move the
    reading by the size of the local zone and the report would name a moment the
    run never had.
    """
    from app.services.run_report import build_run_report

    run_dir = tmp_path / "runs" / "2026-08-19T06-58-15_naive"
    _sealed(run_dir, "2026-08-19T06:58:15")

    row = _started_row(build_run_report(run_dir))

    assert "2026-08-19 06:58:15" in row, f"a naive stamp must not be shifted; got {row}"
