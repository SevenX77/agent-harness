"""PR-3 CodeQL 接入 config characterization tests.

锁 design rev2 §4.1 codeql.yml workflow (Python 解释型, build-mode: none +
queries: security-extended).
PR-3 必须 report-only — design §4.2 'PR-3 初期只上报 Code Scanning'.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
CODEQL_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "codeql.yml"


def _load_codeql_workflow() -> tuple[str, dict[str, Any]]:
    assert CODEQL_WORKFLOW.exists(), "CodeQL workflow must exist at .github/workflows/codeql.yml"

    workflow_text = CODEQL_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    assert isinstance(workflow, dict)
    return workflow_text, workflow


def test_codeql_workflow_exists_and_top_level_config() -> None:
    workflow_text, workflow = _load_codeql_workflow()

    assert workflow["name"] == "CodeQL"

    triggers = workflow["on"]
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert "schedule" in triggers
    assert any("cron" in item for item in triggers["schedule"])
    assert "cron:" in workflow_text
    # SF-1 (a3 audit): cron 具体值锁住 design §4.1 调度协议。
    assert "0 6 * * 1" in workflow_text, (
        "schedule cron must lock to '0 6 * * 1' per design §4.1 "
        "(Mon 06:00, offset from Scorecard 07:00 to avoid runner contention)"
    )

    permissions = workflow["permissions"]
    assert permissions["security-events"] == "write"
    assert permissions["contents"] == "read"
    assert permissions["actions"] == "read"


def test_codeql_analyze_job_uses_init_and_analyze_v4() -> None:
    workflow_text, workflow = _load_codeql_workflow()

    analyze_job = workflow["jobs"]["analyze"]
    assert analyze_job["runs-on"] == "ubuntu-latest"

    steps = analyze_job["steps"]
    assert any(step.get("uses") == "actions/checkout@v4" for step in steps)

    init_steps = [step for step in steps if step.get("uses") == "github/codeql-action/init@v4"]
    assert len(init_steps) == 1

    init_with = init_steps[0]["with"]
    assert init_with["languages"] == "python"
    assert init_with["build-mode"] == "none"
    assert init_with["queries"] == "security-extended"

    assert any(step.get("uses") == "github/codeql-action/analyze@v4" for step in steps)
    assert "github/codeql-action/init@v4" in workflow_text
    assert "github/codeql-action/analyze@v4" in workflow_text
