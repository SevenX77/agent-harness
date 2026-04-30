"""Phase 3.3 e2e: Run + Trace WebSocket event flow.

Validates:
- Clicking Run produces ≥ 5 CallbackEvents on the trace timeline.
- The terminal RunEndedEvent (status=success) closes the WebSocket.
- final_state.json + tracing.jsonl + metrics.json land in the run dir on disk.
- No internal_error event is emitted, no Run timeout.

We use the synthesized `e2e-fast` logic-only skill so the run completes in
sub-second time without needing API keys.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

logger = logging.getLogger("e2e.run_flow")

RUN_TIMEOUT_S = 30.0


def _select_skill(page: Page, skill_id: str) -> None:
    page.get_by_role("button", name=re.compile(rf"^{re.escape(skill_id)}$")).click()
    expect(page.get_by_role("button", name=re.compile(r"^Run$"))).to_be_enabled(timeout=10_000)


def _open_artifacts_panel(page: Page) -> None:
    page.get_by_role("button", name=re.compile(r"^Artifacts$")).click()
    expect(page.get_by_text("Run Input", exact=False)).to_be_visible()


def _paste_run_json(page: Page, payload: dict) -> None:
    textarea = page.locator("textarea")
    textarea.first.fill(json.dumps(payload))


def test_run_emits_trace_events_and_writes_artifacts(
    studio_page: Page,
    studio_workspace: dict[str, Path],
) -> None:
    page = studio_page
    page.set_default_timeout(15_000)

    _select_skill(page, "e2e-fast")
    logger.info("selected e2e-fast skill")

    _open_artifacts_panel(page)
    _paste_run_json(page, {"payload": "hello"})
    logger.info("pasted run input")

    runs_root = (
        studio_workspace["workspaces_dir"]
        / "default"
        / "skills"
        / "e2e-fast"
        / "runs"
    )
    pre_existing = set(runs_root.glob("*")) if runs_root.exists() else set()

    page.get_by_role("button", name=re.compile(r"^Run$")).click()
    logger.info("triggered Run")

    timeline_heading = page.get_by_text("Trace Timeline", exact=False)
    expect(timeline_heading).to_be_visible(timeout=15_000)

    deadline = time.time() + RUN_TIMEOUT_S
    new_run_dirs: set[Path] = set()
    while time.time() < deadline:
        if runs_root.exists():
            new_run_dirs = set(runs_root.glob("*")) - pre_existing
            if new_run_dirs:
                break
        time.sleep(0.25)
    assert new_run_dirs, f"no run directory created under {runs_root} within {RUN_TIMEOUT_S}s"
    run_dir = new_run_dirs.pop()
    logger.info("detected run_dir=%s", run_dir)

    final_state_path = run_dir / "final_state.json"
    tracing_path = run_dir / "tracing.jsonl"
    metrics_path = run_dir / "metrics.json"

    while time.time() < deadline:
        if final_state_path.exists() and metrics_path.exists():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            if metrics.get("status") in {"success", "failed"}:
                break
        time.sleep(0.25)
    assert final_state_path.exists(), f"final_state.json missing at {final_state_path}"
    assert tracing_path.exists(), f"tracing.jsonl missing at {tracing_path}"
    assert metrics_path.exists(), f"metrics.json missing at {metrics_path}"

    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics_payload.get("status") == "success", (
        f"e2e-fast run did not finish successfully; metrics={metrics_payload}"
    )

    tracing_lines = [line for line in tracing_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(tracing_lines) >= 5, (
        f"expected >= 5 CallbackEvents on disk, saw {len(tracing_lines)}: {tracing_lines}"
    )
    event_types = []
    for line in tracing_lines:
        try:
            event_types.append(json.loads(line).get("event_type"))
        except json.JSONDecodeError:
            continue
    logger.info("event_types=%s", event_types)
    assert "run_ended" in event_types, f"run_ended must terminate the stream; got {event_types}"
    assert "internal_error" not in event_types, f"saw internal_error: {event_types}"

    timeline_count = page.locator(".relative.pl-6").count()
    logger.info("trace timeline cards on page: %s", timeline_count)
    assert timeline_count >= 5, (
        f"expected >= 5 trace timeline entries on page, saw {timeline_count}"
    )

    run_button = page.get_by_role("button", name=re.compile(r"^(Run|Running\.\.\.)$"))
    expect(run_button).to_have_text(re.compile(r"^Run$"), timeout=10_000)
