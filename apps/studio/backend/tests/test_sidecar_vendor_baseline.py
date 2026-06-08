from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPO_ROOT / "apps" / "studio" / "backend"
TAURI_CONF = REPO_ROOT / "apps" / "studio" / "tauri" / "tauri.conf.json"
BUILD_VENDOR = BACKEND_DIR / "scripts" / "build_vendor.py"

# Dynamically import build_vendor
spec = importlib.util.spec_from_file_location("build_vendor", str(BUILD_VENDOR))
build_vendor = importlib.util.module_from_spec(spec)
sys.modules["build_vendor"] = build_vendor
spec.loader.exec_module(build_vendor)


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


def test_sidecar_vendor_builder_uses_locked_export_by_default() -> None:
    # 1. Assert that the old requirements.txt does not exist
    requirements_txt = BACKEND_DIR / "requirements.txt"
    assert not requirements_txt.exists(), "manual requirements.txt should be deleted"

    # 2. Assert that build_vendor.py has a way to get locked export
    assert hasattr(build_vendor, "get_locked_requirements"), "build_vendor should have a function to get locked export"


def test_locked_export_selected_pins_are_the_sidecar_source_of_truth() -> None:
    # Run uv export directly to get the current locked requirements
    cmd = ["uv", "export", "--package", "studio-backend", "--no-dev", "--no-hashes", "--no-editable", "--frozen"]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, check=True)
    locked_content = res.stdout

    # Verify key packages are present in uv export output
    key_packages = ["claude-agent-sdk", "fastapi", "pydantic", "uvicorn", "anthropic", "openai"]
    for pkg in key_packages:
        assert f"{pkg}==" in locked_content, f"Locked export should pin {pkg}"

    # Verify build_vendor's default requirements content matches this locked export content
    default_reqs = build_vendor.get_locked_requirements()
    assert default_reqs == locked_content, "build_vendor's locked requirements must match uv export output exactly"


def test_no_cwd_relative_requirements_path_dependency() -> None:
    # Assert that build_vendor resolves local packages relative to repo root, not cwd.
    assert hasattr(build_vendor, "get_repo_root"), "build_vendor should define get_repo_root"
    assert build_vendor.get_repo_root() == REPO_ROOT

    # The paths like ./packages/graph-agent should be resolved against repo_root
    assert hasattr(build_vendor, "resolve_local_paths"), "build_vendor should define resolve_local_paths"


def test_vendor_remains_bundle_safe() -> None:
    # Run the verify_sidecar_vendor.py script to ensure everything builds and runs correctly
    verify_script = REPO_ROOT / "apps" / "studio" / "tauri" / "scripts" / "verify_sidecar_vendor.py"
    cmd = [sys.executable, str(verify_script)]
    res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)

    assert res.returncode == 0, f"verify_sidecar_vendor failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "IMPORT_OK" in res.stdout
    assert "HEALTH_STATUS=200" in res.stdout
    assert "VENDOR_OK" in res.stdout
