"""PR-2 SonarCloud 接入 config characterization tests.

锁 design.md §3.1 (前置) + §3.3 (sonar-project.properties).
PR-2 必须 report-only — design §3.4 'PR-2 ship 时不在 CI 配置中阻断 PR merge'.
PR-2 ship 时 ci.yml 含 sonar-scan job; round-30 后置 cleanup 后改
SonarCloud Automatic Analysis 模式, 不再走 CI sonar-scan.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SONAR_PROPERTIES = REPO_ROOT / "sonar-project.properties"


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
    assert properties["sonar.sources"] == "packages/graph-agent/src,packages/graph-agent-gateway/src,apps/studio/backend/app,apps/studio/frontend/src"
    assert properties["sonar.tests"] == "packages/graph-agent/tests,packages/graph-agent-gateway/tests,apps/studio/backend/tests,apps/studio/frontend/src"
    assert properties["sonar.python.version"] == "3.11,3.12,3.13"
    assert (
        properties["sonar.python.coverage.reportPaths"]
        == "coverage-backend.xml,coverage-graph-agent.xml,coverage-gateway.xml"
    )
