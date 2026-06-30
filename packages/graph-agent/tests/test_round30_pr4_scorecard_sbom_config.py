"""PR-4 Scorecard + SBOM + License + Dependabot config characterization tests.

锁 design rev2 §5.1-§5.4: Scorecard workflow, SBOM script, license script,
and existing Dependabot weekly ecosystem configuration.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
SCORECARD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "scorecard.yml"
SBOM_SCRIPT = REPO_ROOT / "scripts" / "generate_sbom.sh"
LICENSE_SCRIPT = REPO_ROOT / "scripts" / "check_licenses.sh"
DEPENDABOT_CONFIG = REPO_ROOT / ".github" / "dependabot.yml"


def _load_yaml(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    if not isinstance(parsed, dict):
        raise AssertionError(f"{path} must parse to a YAML mapping")
    return parsed


def _is_executable(path: Path) -> bool:
    if os.name == "nt" and path.suffix == ".sh":
        return path.read_text(encoding="utf-8").startswith("#!")
    return bool(os.stat(path).st_mode & 0o111)


def test_scorecard_workflow_matches_design_contract() -> None:
    assert SCORECARD_WORKFLOW.exists(), "Scorecard workflow must exist"

    workflow_text = SCORECARD_WORKFLOW.read_text(encoding="utf-8")
    workflow = _load_yaml(SCORECARD_WORKFLOW)

    assert workflow["name"] == "Scorecard"
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["schedule"][0]["cron"] == "0 7 * * 1"
    # Least-privilege top level (S8234); the analysis job re-declares the
    # write permissions Scorecard itself needs.
    assert workflow["permissions"] == {"contents": "read"}
    # MF-1 (a3 audit): Scorecard publish_results: true 要求 workflow 完整性, 不能设 workflow-level env / defaults
    assert "env" not in workflow, (
        "Scorecard publish_results forbids workflow-level env (design §5.1 L281)"
    )
    assert "defaults" not in workflow, (
        "Scorecard publish_results forbids workflow-level defaults (design §5.1 L281)"
    )

    analysis = workflow["jobs"]["analysis"]
    assert analysis["name"] == "Scorecard analysis"
    assert analysis["runs-on"] == "ubuntu-latest"
    assert analysis["permissions"] == {
        "security-events": "write",
        "id-token": "write",
        "contents": "read",
    }

    steps = analysis["steps"]
    checkout_steps = [step for step in steps if step.get("uses") == "actions/checkout@v7"]
    assert checkout_steps[0]["with"]["persist-credentials"] is False

    scorecard_steps = [
        step for step in steps if step.get("uses") == "ossf/scorecard-action@v2.4.3"
    ]
    assert len(scorecard_steps) == 1
    assert scorecard_steps[0]["with"] == {
        "results_file": "results.sarif",
        "results_format": "sarif",
        "publish_results": True,
    }

    upload_steps = [
        step for step in steps if step.get("uses") == "github/codeql-action/upload-sarif@v4"
    ]
    assert upload_steps[0]["with"]["sarif_file"] == "results.sarif"
    assert "0 7 * * 1" in workflow_text


def test_sbom_script_generates_cyclonedx_json_artifact() -> None:
    assert SBOM_SCRIPT.exists(), "SBOM generation script must exist"
    assert _is_executable(SBOM_SCRIPT), "SBOM generation script must be executable"

    script = SBOM_SCRIPT.read_text(encoding="utf-8")
    assert script.startswith("#!/usr/bin/env bash"), (
        "SBOM script must have #!/usr/bin/env bash shebang"
    )
    assert "set -euo pipefail" in script
    assert "cyclonedx-bom" in script
    assert "-o sbom.json" in script


def test_license_script_reports_markdown_urls_and_blocks_gpl_agpl() -> None:
    assert LICENSE_SCRIPT.exists(), "License check script must exist"
    assert _is_executable(LICENSE_SCRIPT), "License check script must be executable"

    script = LICENSE_SCRIPT.read_text(encoding="utf-8")
    assert script.startswith("#!/usr/bin/env bash"), (
        "license script must have #!/usr/bin/env bash shebang"
    )
    # SF-1 (a3 audit): license script 跟 SBOM 同模板, set -euo pipefail fail-fast
    assert "set -euo pipefail" in script, (
        "license script must use set -euo pipefail (design §5.3 L300)"
    )
    assert "pip-licenses" in script
    assert "--format=markdown" in script
    assert "--with-urls" in script
    assert "LICENSES.md" in script
    assert 'fail-on="GPL;AGPL"' in script


def test_dependabot_keeps_weekly_pip_and_github_actions_updates() -> None:
    assert DEPENDABOT_CONFIG.exists(), "Dependabot config must exist"

    config = _load_yaml(DEPENDABOT_CONFIG)
    updates = config["updates"]
    by_ecosystem = {update["package-ecosystem"]: update for update in updates}

    assert config["version"] == 2
    assert set(by_ecosystem) == {"pip", "github-actions"}
    assert by_ecosystem["pip"]["schedule"]["interval"] == "weekly"
    assert by_ecosystem["github-actions"]["schedule"]["interval"] == "weekly"
