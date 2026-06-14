"""Phase 3.3 e2e: copilot analysis bar after a run (F7).

Drives the real lifecycle: open e2e-fast, Compile -> Predict -> Run; once the
run finishes, the copilot panel shows a transient "auto-write golden" bar.
Confirming writes a golden baseline (none existed) and the bar disappears.

This needs no LLM credentials — the bar is driven by run completion + the golden
endpoints, not the copilot chat model.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from playwright.sync_api import Page, expect

logger = logging.getLogger("e2e.analysis_bar")


def _action_button(page: Page, name: str):
    return page.get_by_role("button", name=name, exact=True)


def _select_skill(page: Page, skill_id: str) -> None:
    page.get_by_text(skill_id, exact=True).first.click()
    expect(_action_button(page, "Compile")).to_be_visible(timeout=10_000)


def _drive_compile_predict_run(page: Page) -> None:
    _action_button(page, "Compile").click()
    expect(_action_button(page, "Predict")).to_be_enabled(timeout=20_000)
    _action_button(page, "Predict").click()
    expect(_action_button(page, "Run")).to_be_enabled(timeout=20_000)
    _action_button(page, "Run").click()


def test_analysis_bar_writes_golden_after_run(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "e2e-fast")
    golden_dir = (
        studio_workspace["workspaces_dir"]
        / "default" / "skills" / "e2e-fast" / ".workspace" / "golden"
    )
    pre_existing = {p.name for p in golden_dir.glob("*")} if golden_dir.exists() else set()

    _drive_compile_predict_run(page)
    logger.info("drove compile->predict->run")

    # F7: once the run finishes, the copilot panel shows the analysis bar.
    confirm = page.get_by_role("button", name="确认", exact=True)
    expect(page.get_by_text("运行完成", exact=False)).to_be_visible(timeout=20_000)
    expect(confirm).to_be_visible(timeout=10_000)
    logger.info("analysis bar appeared")

    confirm.click()
    # Confirm -> a golden baseline is written (none existed) + a success toast.
    expect(page.get_by_text(re.compile("Wrote golden baseline", re.IGNORECASE))).to_be_visible(
        timeout=10_000
    )
    # ...and the bar disappears.
    expect(confirm).to_have_count(0, timeout=10_000)
    logger.info("confirmed -> golden written + bar dismissed")

    deadline = time.time() + 10.0
    new_golden: set[str] = set()
    while time.time() < deadline:
        if golden_dir.exists():
            new_golden = {p.name for p in golden_dir.glob("*")} - pre_existing
            if new_golden:
                break
        time.sleep(0.25)
    assert new_golden, f"no golden baseline written under {golden_dir}"

    # F5 (input region): the written golden now appears in the I/O panel's Golden
    # section (golden 摘要入口归 I/O).
    page.get_by_role("button", name="Input", exact=True).click()
    expect(page.get_by_text("No golden baselines yet.")).to_have_count(0, timeout=10_000)
    logger.info("golden baseline visible in the I/O panel Golden section")
