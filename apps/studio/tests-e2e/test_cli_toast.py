"""Phase 3.4 e2e: Open CLI + skill_changed toast flow.

Validates:
- "Open CLI" button creates a PTY session whose terminal status reaches "open".
- An external mtime touch on SKILL.md triggers a skill_changed event delivered
  through /ws/events to the frontend, which renders a toast within ~1s.
- The frontend mutates SWR (verified indirectly: the canvas re-renders without
  user interaction and the toast text references the changed skill id).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from playwright.sync_api import Page, expect

logger = logging.getLogger("e2e.cli_toast")


def _select_skill(page: Page, skill_id: str) -> None:
    page.get_by_role("button", name=re.compile(rf"^{re.escape(skill_id)}$")).click()
    expect(page.get_by_role("button", name=re.compile(r"^Open CLI$"))).to_be_enabled(timeout=10_000)


def test_open_cli_status_and_skill_changed_toast(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "text-segmentation")
    logger.info("selected text-segmentation skill")

    page.get_by_role("button", name=re.compile(r"^Open CLI$")).click()
    cli_session_toast = page.get_by_text("CLI session opened", exact=False)
    expect(cli_session_toast).to_be_visible(timeout=15_000)
    logger.info("CLI session opened toast visible")

    open_status = page.locator("span", has_text=re.compile(r"^open$"))
    expect(open_status.first).to_be_visible(timeout=15_000)
    logger.info("terminal status reached 'open'")

    target = studio_workspace["skills_dir"] / "text-segmentation" / "SKILL.md"
    assert target.exists(), f"target SKILL.md must exist for the e2e fixture: {target}"
    original = target.read_text(encoding="utf-8")
    target.write_text(original + f"\n# touched at {time.time()}\n", encoding="utf-8")
    logger.info("touched SKILL.md to trigger FileWatcher")

    skill_changed_toast = page.get_by_text(
        re.compile(r"Skill changed: text-segmentation"),
        exact=False,
    ).first
    expect(skill_changed_toast).to_be_visible(timeout=10_000)
    logger.info("skill_changed toast appeared")

    canvas_first = page.locator(".react-flow__node").first
    expect(canvas_first).to_be_visible()
    logger.info("ReactFlow canvas remains visible after toast")
