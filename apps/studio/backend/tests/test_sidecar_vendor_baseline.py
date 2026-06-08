from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPO_ROOT / "apps" / "studio" / "backend"
TAURI_CONF = REPO_ROOT / "apps" / "studio" / "tauri" / "tauri.conf.json"
BUILD_VENDOR = BACKEND_DIR / "scripts" / "build_vendor.py"


def _requirements_lines() -> list[str]:
    return [
        line.strip()
        for line in (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_studio_sidecar_requirements_include_runtime_imports() -> None:
    requirements = _requirements_lines()

    assert "../../../packages/graph-agent-gateway" in requirements
    assert "../../../packages/graph-agent" in requirements
    assert "watchfiles>=1.1.1" in requirements
    assert "claude-agent-sdk>=0.1.80" in requirements
    assert "uvicorn[standard]>=0.30" in requirements


def test_studio_backend_pyproject_declares_gateway_runtime_dependency() -> None:
    pyproject = (BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8")

    assert '"graph-agent-gateway"' in pyproject


def test_tauri_before_build_uses_uv_python_for_vendor_builder() -> None:
    config = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    steps = [step.strip() for step in config["build"]["beforeBuildCommand"].split("&&")]

    assert "uv run python backend/scripts/build_vendor.py" in steps
    assert "python backend/scripts/build_vendor.py" not in steps


def test_vendor_builder_uses_uv_pip_instead_of_embedded_pip() -> None:
    script = BUILD_VENDOR.read_text(encoding="utf-8")

    assert '"uv",\n            "pip",\n            "install",' in script
    assert '"-m",\n            "pip",' not in script


def test_vendor_builder_converts_local_path_dependencies_to_wheels() -> None:
    script = BUILD_VENDOR.read_text(encoding="utf-8")

    assert "def _build_local_requirement_wheel" in script
    assert '"uv",\n        "build",\n        "--wheel",' in script
