"""PR-2 SonarCloud 接入 config characterization tests.

锁 design.md §3.1 (前置) + §3.2 (ci.yml artifact + sonar-scan job) +
§3.3 (sonar-project.properties).
PR-2 必须 report-only — design §3.4 'PR-2 ship 时不在 CI 配置中阻断 PR merge'.
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
SONAR_PROPERTIES = REPO_ROOT / "sonar-project.properties"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
SONAR_SCAN_ACTION = "SonarSource/sonarqube-scan-action@v8"


def _read_sonar_properties() -> dict[str, str]:
    assert SONAR_PROPERTIES.exists(), "sonar-project.properties must exist at the repository root"

    properties: dict[str, str] = {}
    for raw_line in SONAR_PROPERTIES.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        properties[key.strip()] = value.strip()
    return properties


def test_sonar_project_properties_declares_project_sources_tests_and_coverage() -> None:
    properties = _read_sonar_properties()

    assert properties["sonar.organization"] == "sevenx77"
    assert properties["sonar.projectKey"] == "SevenX77_agent-harness"
    assert properties["sonar.host.url"] == "https://sonarcloud.io"
    assert properties["sonar.sources"] == "packages/graph-agent/src,apps/studio/backend/app"
    assert properties["sonar.tests"] == "packages/graph-agent/tests,apps/studio/backend/tests"
    assert properties["sonar.python.version"] == "3.11,3.12,3.13"
    assert (
        properties["sonar.python.coverage.reportPaths"]
        == "coverage-backend.xml,coverage-graph-agent.xml"
    )


def test_ci_uploads_coverage_artifacts_and_runs_sonar_scan_job() -> None:
    workflow_text = CI_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)

    assert "actions/upload-artifact@v4" in workflow_text
    assert "name: coverage-backend" in workflow_text
    assert "path: coverage-backend.xml" in workflow_text

    sonar_scan = workflow["jobs"]["sonar-scan"]
    assert sonar_scan["needs"] == ["quality-gates", "graph-agent-tests"]

    # SF-1 (a3 audit): graph-agent matrix 必须也有 upload-artifact step, total >= 2.
    assert workflow_text.count("actions/upload-artifact@v4") >= 2, (
        "expected upload-artifact in both quality-gates (backend) and graph-agent matrix jobs"
    )
    assert "name: coverage-graph-agent-py" in workflow_text, (
        "graph-agent matrix must upload coverage-graph-agent-py${{ matrix.python-version }} "
        "artifact"
    )

    # SF-2 (a3 audit): sonar-scan job 必须 download 全部 coverage artifact.
    assert "actions/download-artifact@v4" in workflow_text, (
        "sonar-scan job must download artifacts via download-artifact@v4"
    )
    assert "pattern: coverage-*" in workflow_text, (
        "download-artifact must use pattern: coverage-* to fetch all matrix outputs"
    )
    assert "merge-multiple: true" in workflow_text, (
        "download-artifact must use merge-multiple: true to flatten matrix artifacts"
    )

    # SF-3 (a3 audit): sonar-scan job 必须 fetch-depth: 0.
    assert "fetch-depth: 0" in workflow_text, (
        "sonar-scan job must use fetch-depth: 0 for SonarCloud incremental coverage"
    )

    assert SONAR_SCAN_ACTION in workflow_text
    assert "SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}" in workflow_text
    assert "SONAR_HOST_URL: https://sonarcloud.io" in workflow_text
