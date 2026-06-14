"""Phase 3.3 e2e: view a past run's full trace from the timeline (trace F2).

The timeline run cards looked clickable but did nothing. Now clicking a past run
fetches its RunDetail.events and shows that run's trace in place (with a back
button). Verified on the running app: run e2e-fast, go Home, reopen, open the
Trace Timeline panel, click the recorded run -> its trace renders.

No LLM credentials needed (logic-only skill produces a real trace).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from playwright.sync_api import Page, expect

logger = logging.getLogger("e2e.timeline_history")


def _action_button(page: Page, name: str):
    return page.get_by_role("button", name=name, exact=True)


def _open_skill(page: Page, skill_id: str) -> None:
    page.get_by_text(skill_id, exact=True).first.click()
    expect(_action_button(page, "Compile")).to_be_visible(timeout=10_000)


def _drive_compile_predict_run(page: Page) -> None:
    _action_button(page, "Compile").click()
    expect(_action_button(page, "Predict")).to_be_enabled(timeout=20_000)
    _action_button(page, "Predict").click()
    expect(_action_button(page, "Run")).to_be_enabled(timeout=20_000)
    _action_button(page, "Run").click()


def _wait_for_completed_run(runs_root: Path, timeout_s: float = 30.0) -> None:
    deadline = time.time() + timeout_s
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T")
    while time.time() < deadline:
        if runs_root.exists():
            for run_dir in runs_root.glob("*"):
                if pattern.match(run_dir.name) and (run_dir / "final_state.json").exists():
                    return
        time.sleep(0.25)
    raise AssertionError(f"no completed run under {runs_root}")


def test_timeline_run_card_opens_historical_trace(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    page = studio_page
    page.set_default_timeout(15_000)

    _open_skill(page, "e2e-fast")
    runs_root = (
        studio_workspace["workspaces_dir"]
        / "default" / "skills" / "e2e-fast" / ".workspace" / "runs"
    )
    _drive_compile_predict_run(page)
    _wait_for_completed_run(runs_root)
    logger.info("run completed + recorded")

    # Go Home and reopen so the timeline (history) shows instead of the live trace.
    page.get_by_role("button", name="Back to Home").click()
    _open_skill(page, "e2e-fast")
    _action_button(page, "Trace Timeline").click()  # left toolbar -> timeline panel
    logger.info("reopened skill + opened Trace Timeline panel")

    # The recorded run appears in the list; click it to load its trace.
    run_card = page.get_by_role("button", name=re.compile("View trace for run"))
    expect(run_card.first).to_be_visible(timeout=15_000)
    run_card.first.click()
    logger.info("clicked historical run card")

    # The historical trace for THAT run renders in place: a back button + the
    # TracePanel log region (present whether or not the run has events). This
    # proves the historical-load path (getRunDetail -> TracePanel); the live
    # run-flow e2e separately proves trace events render.
    expect(page.get_by_role("button", name="Back to timeline")).to_be_visible(timeout=10_000)
    expect(page.get_by_role("log", name="Trace Timeline")).to_be_visible(timeout=10_000)
    logger.info("historical trace view rendered for the clicked run")

    # Back returns to the run list.
    page.get_by_role("button", name="Back to timeline").click()
    expect(page.get_by_role("button", name=re.compile("View trace for run")).first).to_be_visible(
        timeout=10_000
    )
