"""Run and predict ids are read by humans in a file tree, so their shape matters.

Decision 2026-08-09 D13: the timestamp is the wall clock of the machine that
produced the run (a UTC stamp reads as "wrong time" to the person looking at the
folder), and a predict id is the SAME shape as a run id with a `predict-` prefix
— not a bare uuid, which sorts by nothing and says nothing.
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest
from app.services import run_ids, run_manager

RUN_ID = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_[0-9a-f]{8}$")
PREDICT_ID = re.compile(r"^predict-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_[0-9a-f]{8}$")

FIXED_LOCAL = datetime(2026, 8, 9, 13, 40, 42)


@pytest.fixture()
def frozen_local_clock(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Pin the LOCAL wall clock the ids are built from.

    Patching this specific seam is what makes the test discriminating: a run id
    minted from `datetime.now(UTC)` would ignore the patch and fail the prefix
    assertion even on a CI box whose local time IS UTC.
    """
    monkeypatch.setattr(run_ids, "_local_now", lambda: FIXED_LOCAL)
    return FIXED_LOCAL


def test_run_id_carries_the_local_wall_clock(frozen_local_clock: datetime) -> None:
    run_id = run_ids.new_run_id()

    assert RUN_ID.fullmatch(run_id), run_id
    assert run_id.startswith("2026-08-09T13-40-42_")


def test_predict_id_is_a_run_id_with_a_prefix(frozen_local_clock: datetime) -> None:
    predict_id = run_ids.new_predict_run_id()

    assert PREDICT_ID.fullmatch(predict_id), predict_id
    assert predict_id.startswith("predict-2026-08-09T13-40-42_")


def test_predict_and_run_ids_share_one_format(frozen_local_clock: datetime) -> None:
    # One format means one producer: a second strftime call somewhere else is
    # how the two drifted apart in the first place.
    predict_id = run_ids.new_predict_run_id()

    assert RUN_ID.fullmatch(predict_id.removeprefix("predict-")), predict_id


def test_both_ids_pass_the_run_id_safety_check(frozen_local_clock: datetime) -> None:
    # Ids become path segments, so a shape the validator rejects is a run that
    # cannot be read back.
    run_manager._validate_run_id_segment(run_ids.new_run_id())
    run_manager._validate_run_id_segment(run_ids.new_predict_run_id())
