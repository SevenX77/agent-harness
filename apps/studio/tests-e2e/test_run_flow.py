"""Phase 3.3 e2e: Run + Trace event flow against the current Studio UI.

Validates the real user lifecycle on the running app:
- Open the e2e-fast skill from the welcome page (workspace card).
- Drive the center action bar Compile -> Predict -> Run.
- The live Trace Timeline (TracePanel) mounts and shows run events.
- final_state.json + trace.jsonl + metrics.json land in the run dir on disk,
  the run finishes success, and a terminal run_ended event closes the stream.

`e2e-fast` is a logic-only skill so the run completes in sub-second time
without API keys.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from playwright.sync_api import Page, expect

logger = logging.getLogger("e2e.run_flow")

RUN_TIMEOUT_S = 30.0


def _action_button(page: Page, name: str):
    return page.get_by_role("button", name=name, exact=True)


def _select_skill(page: Page, skill_id: str) -> None:
    # The welcome page renders each skill as a workspace card whose title is the
    # exact skill id; clicking the title opens the workspace + center action bar.
    page.get_by_text(skill_id, exact=True).first.click()
    expect(_action_button(page, "Compile")).to_be_visible(timeout=10_000)


def _drive_compile_predict_run(page: Page) -> None:
    # Compile -> Predict -> Run; each button only enables once the prior stage
    # passes (center-action-bar deriveButtons gating).
    _action_button(page, "Compile").click()
    logger.info("clicked Compile")
    expect(_action_button(page, "Predict")).to_be_enabled(timeout=20_000)

    _action_button(page, "Predict").click()
    logger.info("clicked Predict")
    expect(_action_button(page, "Run")).to_be_enabled(timeout=20_000)

    _action_button(page, "Run").click()
    logger.info("clicked Run")


def test_run_emits_trace_events_and_writes_artifacts(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "e2e-fast")
    logger.info("selected e2e-fast skill")

    # Execution artifacts land under the workspace .workspace/runs; the run dir is
    # timestamp-named (the predict dir is run-<id>-idem-... and is excluded).
    runs_root = (
        studio_workspace["workspaces_dir"] / "default" / "skills" / "e2e-fast" / ".workspace" / "runs"
    )
    run_dir_re = re.compile(r"^\d{4}-\d{2}-\d{2}T")
    pre_existing = {d for d in runs_root.glob("*") if run_dir_re.match(d.name)} if runs_root.exists() else set()

    _drive_compile_predict_run(page)

    # Starting a run opens the timeline region with the live TracePanel mounted.
    timeline_heading = page.get_by_text("Trace Timeline", exact=False)
    expect(timeline_heading).to_be_visible(timeout=15_000)
    logger.info("Trace Timeline panel mounted")

    deadline = time.time() + RUN_TIMEOUT_S
    new_run_dirs: set[Path] = set()
    while time.time() < deadline:
        if runs_root.exists():
            new_run_dirs = {d for d in runs_root.glob("*") if run_dir_re.match(d.name)} - pre_existing
            if new_run_dirs:
                break
        time.sleep(0.25)
    assert new_run_dirs, f"no run directory created under {runs_root} within {RUN_TIMEOUT_S}s"
    run_dir = sorted(new_run_dirs)[-1]
    logger.info("detected run_dir=%s", run_dir)

    final_state_path = run_dir / "final_state.json"
    trace_path = run_dir / "trace.jsonl"
    metrics_path = run_dir / "metrics.json"

    while time.time() < deadline:
        if final_state_path.exists() and metrics_path.exists():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            if metrics.get("status") in {"success", "failed"}:
                break
        time.sleep(0.25)
    assert final_state_path.exists(), f"final_state.json missing at {final_state_path}"
    assert trace_path.exists(), f"trace.jsonl missing at {trace_path}"
    assert metrics_path.exists(), f"metrics.json missing at {metrics_path}"

    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics_payload.get("status") == "success", (
        f"e2e-fast run did not finish successfully; metrics={metrics_payload}"
    )

    trace_lines = [
        line for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(trace_lines) >= 5, (
        f"expected >= 5 CallbackEvents on disk, saw {len(trace_lines)}: {trace_lines}"
    )
    event_types = []
    for line in trace_lines:
        try:
            event_types.append(json.loads(line).get("event_type"))
        except json.JSONDecodeError:
            continue
    logger.info("event_types=%s", event_types)
    assert "run_ended" in event_types, f"run_ended must terminate the stream; got {event_types}"
    assert "internal_error" not in event_types, f"saw internal_error: {event_types}"


def _wait_for_completed_run(runs_root: Path, pre_existing: set[Path], pattern: re.Pattern[str]) -> Path:
    deadline = time.time() + RUN_TIMEOUT_S
    while time.time() < deadline:
        if runs_root.exists():
            fresh = {d for d in runs_root.glob("*") if pattern.match(d.name)} - pre_existing
            done = [
                d for d in fresh
                if (d / "final_state.json").exists() and (d / "metrics.json").exists()
            ]
            if done:
                return sorted(done)[-1]
        time.sleep(0.25)
    raise AssertionError(f"no completed run under {runs_root} within {RUN_TIMEOUT_S}s")


def test_promote_then_compare_golden_renders_per_node_diff(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "e2e-fast")
    runs_root = (
        studio_workspace["workspaces_dir"] / "default" / "skills" / "e2e-fast" / ".workspace" / "runs"
    )
    run_dir_re = re.compile(r"^\d{4}-\d{2}-\d{2}T")
    pre_existing = (
        {d for d in runs_root.glob("*") if run_dir_re.match(d.name)} if runs_root.exists() else set()
    )

    _drive_compile_predict_run(page)
    expect(page.get_by_text("Trace Timeline", exact=False)).to_be_visible(timeout=15_000)
    _wait_for_completed_run(runs_root, pre_existing, run_dir_re)
    logger.info("run completed; promoting to golden")

    # Promote the run to a golden baseline (TracePanel header button I wired).
    page.get_by_role("button", name="Promote run to golden baseline").click()
    expect(page.get_by_text(re.compile("Promoted run to golden", re.IGNORECASE))).to_be_visible(
        timeout=10_000
    )

    # Compare the run to the golden baseline -> golden diff overlay with a verdict.
    page.get_by_role("button", name="Compare trace to golden baseline").click()
    expect(page.get_by_text("Golden Diff").first).to_be_visible(timeout=10_000)
    # Run vs its own freshly-promoted golden is identical -> a passing verdict
    # with no differences (proves compare resolved + rendered, not a silent fail).
    expect(page.get_by_text("No differences", exact=False).first).to_be_visible(timeout=10_000)
    logger.info("golden diff overlay rendered with a verdict")


def test_release_without_registry_reports_clear_typed_error(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    # Publish design F2: "Release to Artifact Registry" requires registry
    # settings; missing settings must give a CLEAR error (not a silent fail or a
    # mutated draft). The e2e env has no registry configured, so this validates
    # that designed behavior end-to-end.
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "e2e-fast")
    _action_button(page, "Compile").click()
    expect(_action_button(page, "Predict")).to_be_enabled(timeout=20_000)

    # Release via the Team dropdown.
    page.get_by_role("button", name="Team").click()
    with page.expect_response(re.compile(r"/publish")) as resp_info:
        page.get_by_role("menuitem", name="Release").click()
    response = resp_info.value

    # Backend returns a typed, clear error.
    assert response.status == 400, f"expected a clear 400, got {response.status}"
    body = response.json()
    assert body["error_code"] == "REGISTRY_NOT_CONFIGURED", body

    # And the frontend surfaces that clear reason (not a generic toast) so the
    # user knows to configure the registry.
    expect(
        page.get_by_text(re.compile("Artifact Registry Host", re.IGNORECASE)).first
    ).to_be_visible(timeout=10_000)
