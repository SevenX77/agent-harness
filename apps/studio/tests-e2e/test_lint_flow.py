"""Phase 3.2 e2e: Monaco edit + Lint flow.

Validates:
- Successful Save -> "Saved and linted" toast (lint passed).
- Corrupting SKILL.md -> 422 returns lint failed errors -> red error drawer with clickable line numbers.
- ReactFlow canvas still renders after a lint failure (no white screen).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from playwright.sync_api import Page, expect

logger = logging.getLogger("e2e.lint_flow")


SAVE_TOAST = re.compile(r"Saved and linted", re.IGNORECASE)
LINT_FAIL_PANEL = re.compile(r"Manifest validation failed", re.IGNORECASE)


def _select_skill(page: Page, skill_id: str) -> None:
    """Click the skill in the left sidebar and wait for SKILL.md tab to populate."""
    button = page.get_by_role("button", name=re.compile(rf"^{re.escape(skill_id)}$"))
    button.click()
    expect(page.get_by_role("button", name=re.compile(r"^Save$"))).to_be_enabled(timeout=10_000)
    page.wait_for_function(
        "() => document.querySelectorAll('.monaco-editor').length > 0",
        timeout=10_000,
    )


def _replace_monaco_content(page: Page, new_content: str) -> None:
    """Replace the Monaco editor model via the global monaco runtime.

    Direct keyboard / paste injection on the hidden textarea is fragile
    (rendered glyphs intercept clicks; Monaco's clipboard pipeline may not
    fire React `onChange`). The robust alternative is to call Monaco's own
    model API and synthesize an input event afterwards so React's
    controlled-component state catches up.
    """
    page.locator(".monaco-editor").first.click()
    page.wait_for_function("() => !!window.monaco?.editor?.getModels?.().length", timeout=10_000)
    page.evaluate(
        """(value) => {
            const monaco = window.monaco;
            const model = monaco.editor.getModels()[0];
            model.setValue(value);
            const editor = monaco.editor.getEditors()[0];
            if (editor) {
                editor.trigger('e2e', 'editor.action.formatDocument', null);
            }
        }""",
        new_content,
    )


def test_save_passes_then_failed_lint_renders_canvas(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "text-segmentation")
    logger.info("selected text-segmentation; ready to edit Monaco buffer")

    workspace_skill = (
        studio_workspace["workspaces_dir"] / "default" / "skills" / "text-segmentation" / "SKILL.md"
    )
    public_skill = studio_workspace["skills_dir"] / "text-segmentation" / "SKILL.md"
    initial_text = public_skill.read_text(encoding="utf-8")

    minor_change = initial_text.replace(
        "ABC paragraph segmentation",
        "ABC paragraph segmentation (e2e-touched)",
        1,
    )
    assert minor_change != initial_text, "test fixture must contain the source string"
    _replace_monaco_content(page, minor_change)

    save_button = page.get_by_role("button", name=re.compile(r"^Save$"))
    save_button.click()

    success_toast = page.get_by_text(SAVE_TOAST, exact=False)
    expect(success_toast).to_be_visible(timeout=10_000)
    logger.info("save+lint passed toast visible")

    assert workspace_skill.exists(), "save must materialize a workspace copy"
    saved = workspace_skill.read_text(encoding="utf-8")
    assert "ABC paragraph segmentation (e2e-touched)" in saved

    canvas_first = page.locator(".react-flow__node").first
    expect(canvas_first).to_be_visible()
    logger.info("ReactFlow canvas survived first save")

    broken_text = saved.replace("mode: logic", "mode: bogus", 1)
    assert broken_text != saved, "must contain mode: logic to corrupt"
    _replace_monaco_content(page, broken_text)
    save_button.click()

    error_panel = page.get_by_text(LINT_FAIL_PANEL, exact=False).first
    expect(error_panel).to_be_visible(timeout=10_000)
    logger.info("lint failed panel visible after corrupt save")

    error_button = page.locator("button", has_text=re.compile(r"Line \d+", re.IGNORECASE)).first
    expect(error_button).to_be_visible()
    error_button.click()

    canvas_after_failure = page.locator(".react-flow__node").first
    expect(canvas_after_failure).to_be_visible()
    logger.info("ReactFlow canvas still renders after failed lint")
