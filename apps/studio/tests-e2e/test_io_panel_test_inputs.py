"""Phase 3.3 e2e: i/o panel test-input create/delete (INPUT-3).

Drives the real lifecycle on the running app:
- Open the e2e-fast skill, switch to the Input (i/o) panel.
- In the Test Inputs section, type a name + JSON and Save -> the row appears
  and a `<name>.json` lands under `.workspace/test_inputs/` on disk.
- Delete the row -> it disappears and the file is removed.

This is the browser-driven (mouse-sim) verification of the backend CRUD added
for INPUT-3; module/unit green alone does not count.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from playwright.sync_api import Page, expect

logger = logging.getLogger("e2e.io_panel_test_inputs")

INPUT_NAME = "happy-path"


def _action_button(page: Page, name: str):
    return page.get_by_role("button", name=name, exact=True)


def _select_skill(page: Page, skill_id: str) -> None:
    page.get_by_text(skill_id, exact=True).first.click()
    expect(page.get_by_role("button", name="Compile", exact=True)).to_be_visible(timeout=10_000)


def _wait_for_file(path: Path, *, exists: bool, timeout_s: float = 10.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if path.exists() == exists:
            return
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for exists={exists} at {path}")


def test_io_panel_create_and_delete_test_input(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "e2e-fast")
    logger.info("selected e2e-fast skill")

    input_file = (
        studio_workspace["workspaces_dir"]
        / "default"
        / "skills"
        / "e2e-fast"
        / ".workspace"
        / "test_inputs"
        / f"{INPUT_NAME}.json"
    )
    assert not input_file.exists(), f"unexpected pre-existing {input_file}"

    # Open the Input (i/o) panel from the left toolbar.
    page.get_by_role("button", name="I/O", exact=True).click()
    name_field = page.get_by_label("New test input name")
    expect(name_field).to_be_visible(timeout=10_000)
    logger.info("Input panel + Test Inputs section visible")

    # Save a new test input.
    name_field.fill(INPUT_NAME)
    page.get_by_label("New test input JSON").fill('{"input_text": "hello"}')
    page.get_by_role("button", name="Save test input").click()
    logger.info("clicked Save test input")

    delete_button = page.get_by_role("button", name=f"Delete test input {INPUT_NAME}")
    expect(delete_button).to_be_visible(timeout=10_000)
    _wait_for_file(input_file, exists=True)
    logger.info("test input saved + file on disk: %s", input_file)

    # Delete it.
    delete_button.click()
    logger.info("clicked delete")
    expect(delete_button).to_have_count(0, timeout=10_000)
    _wait_for_file(input_file, exists=False)
    logger.info("test input deleted + file removed")


def test_io_panel_duplicate_name_shows_clear_error(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    # Creating a second input with the same name must surface the backend's
    # typed reason "就近" (design: 错误就近显示), not a silent failure.
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "e2e-fast")
    page.get_by_role("button", name="I/O", exact=True).click()
    name_field = page.get_by_label("New test input name")
    expect(name_field).to_be_visible(timeout=10_000)

    name_field.fill("dup-case")
    page.get_by_label("New test input JSON").fill('{"input_text": "a"}')
    page.get_by_role("button", name="Save test input").click()
    expect(page.get_by_role("button", name="Delete test input dup-case")).to_be_visible(
        timeout=10_000
    )

    # Re-save the same name -> a clear in-panel error.
    name_field.fill("dup-case")
    page.get_by_label("New test input JSON").fill('{"input_text": "b"}')
    page.get_by_role("button", name="Save test input").click()
    expect(page.get_by_text("Test input already exists", exact=False)).to_be_visible(
        timeout=10_000
    )


def test_selected_test_input_feeds_predict_and_run(studio_page: Page) -> None:
    # F4: the input selected in the i/o panel must become the Predict/Run
    # payload (was hard-coded `{}`). Verified by capturing the actual request
    # bodies on the running app.
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "e2e-fast")
    page.get_by_role("button", name="I/O", exact=True).click()
    name_field = page.get_by_label("New test input name")
    expect(name_field).to_be_visible(timeout=10_000)

    marker = {"input_text": "selected-marker"}
    name_field.fill("marker-case")
    page.get_by_label("New test input JSON").fill('{"input_text": "selected-marker"}')
    page.get_by_role("button", name="Save test input").click()

    select_button = page.get_by_role("button", name="Select test input marker-case")
    expect(select_button).to_be_visible(timeout=10_000)
    select_button.click()
    expect(select_button).to_have_attribute("aria-pressed", "true", timeout=10_000)

    def is_predict(request) -> bool:  # type: ignore[no-untyped-def]
        return request.method == "POST" and request.url.rstrip("/").endswith("/runs/predict")

    def is_run(request) -> bool:  # type: ignore[no-untyped-def]
        return request.method == "POST" and request.url.rstrip("/").endswith("/runs")

    _action_button(page, "Compile").click()
    expect(_action_button(page, "Predict")).to_be_enabled(timeout=20_000)

    with page.expect_request(is_predict) as predict_info:
        _action_button(page, "Predict").click()
    assert predict_info.value.post_data_json["input_data"] == marker, (
        "Predict must use the selected test input"
    )
    expect(_action_button(page, "Run")).to_be_enabled(timeout=20_000)

    with page.expect_request(is_run) as run_info:
        _action_button(page, "Run").click()
    assert run_info.value.post_data_json["input_data"] == marker, (
        "Run must use the selected test input"
    )
