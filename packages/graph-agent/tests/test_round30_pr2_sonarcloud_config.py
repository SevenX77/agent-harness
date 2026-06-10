"""SonarCloud analysis-scope config characterization tests.

历史: round-30 PR-2 接入 SonarCloud 时走 CI sonar-scan + sonar-project.properties;
round-30 后置 cleanup 改 Automatic Analysis 模式后, Automatic Analysis 不读
sonar-project.properties, 只读默认分支根目录的 .sonarcloud.properties。
本测试锁当前权威配置: .sonarcloud.properties 存在且声明测试归类/排除规则,
失效的 sonar-project.properties 不得回归(避免再次误导扫描范围认知)。
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SONARCLOUD_PROPERTIES = REPO_ROOT / ".sonarcloud.properties"
LEGACY_SONAR_PROPERTIES = REPO_ROOT / "sonar-project.properties"


def _read_sonarcloud_properties() -> dict[str, str]:
    assert SONARCLOUD_PROPERTIES.exists(), (
        ".sonarcloud.properties must exist at the repository root "
        "(it is the only config file SonarCloud Automatic Analysis reads)"
    )

    properties: dict[str, str] = {}
    for raw_line in SONARCLOUD_PROPERTIES.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        properties[key.strip()] = value.strip()
    return properties


def test_legacy_sonar_project_properties_must_not_return() -> None:
    assert not LEGACY_SONAR_PROPERTIES.exists(), (
        "sonar-project.properties is ignored by Automatic Analysis and was removed; "
        "configure analysis scope in .sonarcloud.properties instead"
    )


def test_sonarcloud_properties_classifies_tests_and_excludes_non_product_code() -> None:
    properties = _read_sonarcloud_properties()

    test_inclusions = properties["sonar.test.inclusions"].split(",")
    assert "**/tests/**" in test_inclusions
    assert "**/conftest.py" in test_inclusions
    assert "**/*.test.ts" in test_inclusions
    assert "**/*.test.tsx" in test_inclusions

    exclusions = properties["sonar.exclusions"].split(",")
    assert "code-diagnostics/**" in exclusions
    assert "**/__pycache__/**" in exclusions

    cpd_exclusions = properties["sonar.cpd.exclusions"].split(",")
    assert "skills/**" in cpd_exclusions
    assert "**/tests/**" in cpd_exclusions
