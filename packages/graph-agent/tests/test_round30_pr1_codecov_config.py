"""PR-1 Codecov 接入 config characterization tests.

锁 design.md §2.1 (ci.yml codecov upload step) + §2.2 (codecov.yml) +
§2.3 (pyproject [tool.coverage]).
PR-1 必须 report-only — fail_ci_if_error: false + target: auto.
M-2/M-3 防 false positive 关键.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
CODECOV_CONFIG = REPO_ROOT / "codecov.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
ROOT_PYPROJECT = REPO_ROOT / "pyproject.toml"


def test_codecov_yml_declares_report_only_status_and_flags() -> None:
    assert CODECOV_CONFIG.exists(), "codecov.yml must exist at the repository root"

    config = yaml.safe_load(CODECOV_CONFIG.read_text(encoding="utf-8")) or {}
    assert config["codecov"]["require_ci_to_pass"] is True

    project_default = config["coverage"]["status"]["project"]["default"]
    assert isinstance(project_default, dict)
    assert project_default["target"] == "auto"
    assert project_default["threshold"] == "1%"

    patch_default = config["coverage"]["status"]["patch"]["default"]
    assert patch_default["target"] == "auto"
    assert patch_default["threshold"] == "1%"

    flags = config["flags"]
    assert "apps/studio/backend/app/" in flags["backend"]["paths"]
    assert "packages/graph-agent/src/graph_agent/" in flags["graph-agent"]["paths"]

    comment = config["comment"]
    assert "layout" in comment
    assert "behavior" in comment


def test_ci_uploads_backend_and_graph_agent_coverage_to_codecov() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "codecov/codecov-action@v7" in workflow
    assert "token: ${{ secrets.CODECOV_TOKEN }}" in workflow
    assert "files: coverage-backend.xml" in workflow
    assert "files: coverage-graph-agent.xml" in workflow
    assert "flags: backend" in workflow
    assert "flags: graph-agent" in workflow
    assert workflow.count("fail_ci_if_error: false") >= 2


def test_root_pyproject_enables_coverage_runtime_options() -> None:
    pyproject = tomllib.loads(ROOT_PYPROJECT.read_text(encoding="utf-8"))

    coverage_run = pyproject["tool"]["coverage"]["run"]
    assert coverage_run["relative_files"] is True
    assert coverage_run["parallel"] is True
    assert "tests/*" in str(coverage_run.get("omit", []))

    coverage_report = pyproject["tool"]["coverage"]["report"]
    assert "pragma: no cover" in str(coverage_report.get("exclude_lines", []))
