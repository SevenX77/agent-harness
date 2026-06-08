#!/usr/bin/env python3
"""Verify a clean Studio sidecar vendor can import and serve the backend."""

from __future__ import annotations

import argparse
import os
import signal
import site
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

TAURI_DIR = Path(__file__).resolve().parents[1]
STUDIO_DIR = TAURI_DIR.parent
REPO_ROOT = STUDIO_DIR.parents[1]
BACKEND_DIR = STUDIO_DIR / "backend"
BUILD_VENDOR = BACKEND_DIR / "scripts" / "build_vendor.py"


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


def _assert_no_editable_paths(site_packages: Path) -> None:
    editable = sorted(site_packages.glob("_editable*.pth"))
    if editable:
        names = ", ".join(path.name for path in editable)
        raise SystemExit(f"editable vendor paths are not bundle-safe: {names}")


def _import_backend(site_packages: Path) -> None:
    code = """
import os
import site
import sys

site.addsitedir(os.environ["STUDIO_VENDOR_SITE_PACKAGES"])
sys.path.insert(0, os.environ["STUDIO_BACKEND_DIR"])

import graph_agent  # noqa: F401
import graph_agent_gateway  # noqa: F401
import claude_agent_sdk  # noqa: F401
import watchfiles  # noqa: F401
import app.main  # noqa: F401

print("IMPORT_OK")
"""
    env = {
        **os.environ,
        "PYTHONNOUSERSITE": "1",
        "STUDIO_API_TOKEN": "check",
        "STUDIO_BACKEND_DIR": str(BACKEND_DIR),
        "STUDIO_VENDOR_SITE_PACKAGES": str(site_packages),
    }
    _run([sys.executable, "-S", "-c", code], env=env)


def _allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _resource_dir() -> Path:
    root = Path(tempfile.mkdtemp(prefix="studio-sidecar-resources."))
    (root / "skills").mkdir(parents=True)
    (root / "config").mkdir(parents=True)
    (root / "workspaces").mkdir(parents=True)
    return root


def _check_health(site_packages: Path) -> None:
    port = _allocate_port()
    resource_dir = _resource_dir()
    config_dir = Path(tempfile.mkdtemp(prefix="studio-sidecar-config."))
    code = """
import os
import site
import sys

site.addsitedir(os.environ["STUDIO_VENDOR_SITE_PACKAGES"])
sys.path.insert(0, os.environ["STUDIO_BACKEND_DIR"])

import uvicorn

uvicorn.run(
    "app.main:app",
    host="127.0.0.1",
    port=int(os.environ["STUDIO_PORT"]),
    log_level="warning",
)
"""
    env = {
        **os.environ,
        "PYTHONNOUSERSITE": "1",
        "STUDIO_API_TOKEN": "check",
        "STUDIO_BACKEND_DIR": str(BACKEND_DIR),
        "STUDIO_VENDOR_SITE_PACKAGES": str(site_packages),
        "STUDIO_RESOURCE_DIR": str(resource_dir),
        "STUDIO_CONFIG_DIR": str(config_dir),
        "STUDIO_PORT": str(port),
    }
    process = subprocess.Popen(
        [sys.executable, "-S", "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.time() + 15
        last_error: Exception | None = None
        while time.time() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr else ""
                raise SystemExit(f"sidecar exited early: {stderr[-2000:]}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                    body = response.read().decode("utf-8")
                    print(f"HEALTH_STATUS={response.status}")
                    print(f"HEALTH_BODY={body}")
                    return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(0.2)
        raise SystemExit(f"health check timed out: {last_error}")
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    site_packages = args.target or Path(tempfile.mkdtemp(prefix="studio-clean-vendor.")) / "site-packages"
    if not args.skip_build:
        _run([sys.executable, str(BUILD_VENDOR), "--target", str(site_packages)])
    site.addsitedir(str(site_packages))
    _assert_no_editable_paths(site_packages)
    _import_backend(site_packages)
    _check_health(site_packages)
    print(f"VENDOR_OK={site_packages}")


if __name__ == "__main__":
    main()
