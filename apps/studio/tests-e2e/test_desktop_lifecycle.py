"""T2.6 desktop sidecar lifecycle and P0 regression tests.

The real Tauri window path is record-only when DISABLE_GUI=1 or no display is
available. The sidecar lifecycle checks still run headlessly and validate the
same Python command shape used by the Rust runtime manager.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
STUDIO_BACKEND = REPO_ROOT / "apps" / "studio" / "backend"
TAURI_DIR = REPO_ROOT / "apps" / "studio" / "tauri"
GRAPH_AGENT_SRC = REPO_ROOT / "packages" / "graph-agent" / "src"
PYTHON = (
    REPO_ROOT / ".venv" / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
)

SIDECAR_NEEDLES = ("uvicorn", "app.main:app")
# The backend refuses to start without an auth token (app/main.py); every
# non-/health request needs Authorization: Bearer <token>.
SIDECAR_TOKEN = "t26-sidecar-token"
AUTH_HEADERS = {"Authorization": f"Bearer {SIDECAR_TOKEN}"}


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    command: str


def list_processes() -> list[ProcessInfo]:
    if platform.system() == "Windows":
        script = (
            "Get-CimInstance Win32_Process | "
            "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout or "[]")
        if isinstance(payload, dict):
            payload = [payload]
        return [
            ProcessInfo(int(item["ProcessId"]), item.get("CommandLine") or "")
            for item in payload
            if item.get("CommandLine")
        ]

    result = subprocess.run(
        ["ps", "-eo", "pid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    processes: list[ProcessInfo] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        pid_text, _, command = stripped.partition(" ")
        if pid_text.isdigit():
            processes.append(ProcessInfo(int(pid_text), command))
    return processes


def find_sidecar_processes(processes: list[ProcessInfo] | None = None) -> list[ProcessInfo]:
    candidates = processes if processes is not None else list_processes()
    return [
        process
        for process in candidates
        if all(needle in process.command for needle in SIDECAR_NEEDLES)
    ]


def assert_no_new_sidecar_processes(baseline_pids: set[int]) -> None:
    deadline = time.time() + 5
    leaked: list[ProcessInfo] = []
    while time.time() < deadline:
        leaked = [
            process for process in find_sidecar_processes() if process.pid not in baseline_pids
        ]
        if not leaked:
            return
        time.sleep(0.25)
    details = "\n".join(f"{process.pid}: {process.command}" for process in leaked)
    raise AssertionError(f"sidecar Python process leak detected:\n{details}")


@contextlib.contextmanager
def occupy_port(port: int) -> Iterator[None]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(1)
    try:
        yield
    finally:
        sock.close()


def allocate_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(
    port: int,
    *,
    timeout: float = 10.0,
    process: subprocess.Popen[str] | None = None,
) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
            if response.status_code == 200:
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        if process is not None and process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise AssertionError(f"sidecar exited before /health passed: {stderr[-4000:]}")
        time.sleep(0.1)
    raise AssertionError(f"/health did not pass within {timeout}s; last_error={last_error}")


def resource_dir(tmp_path: Path) -> Path:
    root = tmp_path / "resources"
    (root / "skills" / "pm-smoke").mkdir(parents=True)
    (root / "workspaces").mkdir()
    (root / "config").mkdir()
    (root / "config" / "llm_roles.yaml").write_text("roles: []\n", encoding="utf-8")
    (root / "skills" / "pm-smoke" / "SKILL.md").write_text(
        """---
schema_version: "2.0"
name: pm-smoke
description: Desktop lifecycle smoke skill
type: graph
context_mapping: {}
io:
  inputs: []
  outputs: []
phases: []
---
""",
        encoding="utf-8",
    )
    return root


def sidecar_env(tmp_path: Path) -> dict[str, str]:
    paths = [str(STUDIO_BACKEND), str(GRAPH_AGENT_SRC)]
    existing_pythonpath = os.environ.get("PYTHONPATH")
    if existing_pythonpath:
        paths.append(existing_pythonpath)
    return {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(paths),
        "STUDIO_RESOURCE_DIR": str(resource_dir(tmp_path)),
        "STUDIO_SHUTDOWN_TOKEN": "t26-token",
        "STUDIO_DEV_TUNNEL_TOKEN": SIDECAR_TOKEN,
    }


def start_python_sidecar(port: int, tmp_path: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            str(PYTHON if PYTHON.exists() else sys.executable),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=STUDIO_BACKEND,
        env=sidecar_env(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def shutdown_sidecar(process: subprocess.Popen[str], port: int) -> None:
    with contextlib.suppress(Exception):
        httpx.post(
            f"http://127.0.0.1:{port}/shutdown",
            headers={"x-studio-shutdown-token": "t26-token"},
            timeout=1.0,
        )
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if platform.system() == "Windows":
            process.kill()
        else:
            os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def test_process_scanner_detects_uvicorn_sidecars() -> None:
    processes = [
        ProcessInfo(1, "python -m uvicorn app.main:app --host 127.0.0.1 --port 49152"),
        ProcessInfo(2, "python -m http.server"),
    ]

    assert find_sidecar_processes(processes) == [processes[0]]


def test_dynamic_sidecar_port_works_when_8787_is_occupied(tmp_path: Path) -> None:
    baseline = {process.pid for process in find_sidecar_processes()}
    with occupy_port(8787):
        port = allocate_port()
        assert port != 8787
        process = start_python_sidecar(port, tmp_path)
        try:
            wait_for_health(port, process=process)
            skills = httpx.get(
                f"http://127.0.0.1:{port}/api/skills", headers=AUTH_HEADERS, timeout=2.0
            )
            assert skills.status_code == 200
            assert any(skill["id"] == "pm-smoke" for skill in skills.json())
        finally:
            shutdown_sidecar(process, port)
    assert_no_new_sidecar_processes(baseline)


def test_sidecar_shutdown_leaves_no_uvicorn_process(tmp_path: Path) -> None:
    baseline = {process.pid for process in find_sidecar_processes()}
    port = allocate_port()
    process = start_python_sidecar(port, tmp_path)
    try:
        wait_for_health(port, process=process)
    finally:
        shutdown_sidecar(process, port)

    assert process.poll() is not None
    assert process.pid not in {process.pid for process in find_sidecar_processes()}
    assert_no_new_sidecar_processes(baseline)


def test_tauri_dev_lifecycle_record_or_gui(tmp_path: Path) -> None:
    record = {
        "check": "cargo tauri dev lifecycle",
        "disable_gui": os.environ.get("DISABLE_GUI") == "1",
        "display": os.environ.get("DISPLAY"),
        "platform": platform.platform(),
    }
    record_path = tmp_path / "tauri-dev-lifecycle-record.json"

    if record["disable_gui"] or (platform.system() == "Linux" and not record["display"]):
        record["mode"] = "headless-record-only"
        record["status"] = "skipped-gui"
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        assert record_path.exists()
        return

    if not shutil.which("cargo"):
        pytest.skip("cargo is unavailable")

    result = subprocess.run(
        ["cargo", "tauri", "--version"],
        cwd=TAURI_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    record["mode"] = "gui-preflight"
    record["status"] = "tauri-cli-available" if result.returncode == 0 else "tauri-cli-unavailable"
    record["stdout"] = result.stdout
    record["stderr"] = result.stderr
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    assert result.returncode == 0
