"""End-to-end Playwright fixtures for Studio MVP1 Phase 3.

Spawns a real Studio backend (uvicorn pointed at temp skills/workspaces dirs)
and a real Vite dev server (frontend) so a Chromium browser can drive the
full UI stack end-to-end.

Port plan (matches design.md §4 defaults):
- backend  → http://127.0.0.1:8787
- frontend → http://127.0.0.1:5173
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import socket
import subprocess
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIO_BACKEND = REPO_ROOT / "studio-backend"
STUDIO_FRONTEND = REPO_ROOT / "studio-frontend"
SRC_CORE = REPO_ROOT / "src" / "core"

BACKEND_PORT = 8787
FRONTEND_PORT = 5173
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"
API_BASE_URL = f"{BACKEND_URL}/api"

logger = logging.getLogger("e2e.conftest")


def _is_port_free(port: int) -> bool:
    """Return True when 127.0.0.1:port refuses connections (i.e., free)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _wait_for_url(url: str, *, timeout: float, label: str) -> None:
    """Block until an HTTP GET on url returns < 500 or raise after timeout."""
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code < 500:
                logger.info("%s ready (status=%s) in %.1fs", label, response.status_code, timeout)
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"{label} did not become ready within {timeout}s; last_error={last_error}")


def _seed_skill_files(skills_dir: Path) -> None:
    """Copy a real text-segmentation manifest and synthesize a fast logic skill."""
    skills_dir.mkdir(parents=True, exist_ok=True)
    real_text_seg = REPO_ROOT / "skills" / "text-segmentation"
    if real_text_seg.exists():
        shutil.copytree(real_text_seg, skills_dir / "text-segmentation")
    else:
        _write_minimal_text_segmentation(skills_dir / "text-segmentation")
    _write_e2e_fast_skill(skills_dir / "e2e-fast")


def _write_minimal_text_segmentation(skill_dir: Path) -> None:
    """Fallback when the real text-segmentation skill is missing."""
    (skill_dir / "script").mkdir(parents=True)
    (skill_dir / "script" / "__init__.py").write_text("", encoding="utf-8")
    (skill_dir / "script" / "logic.py").write_text(
        "def prepare(context):\n"
        "    context['prepared'] = True\n"
        "    return 'ok'\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
            ---
            schema_version: "2.0"
            name: text-segmentation
            description: ABC paragraph segmentation (e2e fixture)
            type: graph
            context_mapping:
              chapter_content: "{input.chapter_content}"
              prepared: ""
            io:
              inputs:
                - name: chapter_content
                  type: str
                  source: runtime
              outputs:
                - name: prepared
                  type: dict
                  target: artifact
            phases:
              - name: setup
                mode: logic
                execute_steps:
                  - script.logic.prepare
            ---
            """),
        encoding="utf-8",
    )


def _write_e2e_fast_skill(skill_dir: Path) -> None:
    """Synthesize a multi-phase logic-only skill that completes in milliseconds."""
    (skill_dir / "script").mkdir(parents=True)
    (skill_dir / "script" / "__init__.py").write_text("", encoding="utf-8")
    (skill_dir / "script" / "fast.py").write_text(
        textwrap.dedent("""\
            from __future__ import annotations


            def step1(context):
                context['step1'] = (context.get('payload') or '') + '_s1'
                return 'step1 ok'


            def step2(context):
                context['step2'] = (context.get('step1') or '') + '_s2'
                return 'step2 ok'


            def step3(context):
                context['step3'] = (context.get('step2') or '') + '_s3'
                context['final_result'] = context['step3']
                return 'step3 ok'
            """),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        textwrap.dedent("""\
            ---
            schema_version: "2.0"
            name: e2e-fast
            description: Fast logic-only multi-phase skill used by the Studio e2e suite
            type: graph
            context_mapping:
              payload: "{input.payload}"
              step1: ""
              step2: ""
              step3: ""
              final_result: ""
            io:
              inputs:
                - name: payload
                  type: str
                  source: runtime
              outputs:
                - name: final_result
                  type: str
                  target: file
                  path: "output/e2e-fast/final.json"
            phases:
              - name: phase1
                mode: logic
                execute_steps:
                  - script.fast.step1
              - name: phase2
                mode: logic
                execute_steps:
                  - script.fast.step2
              - name: phase3
                mode: logic
                execute_steps:
                  - script.fast.step3
            ---
            """),
        encoding="utf-8",
    )


@pytest.fixture(scope="session")
def studio_workspace(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Path]]:
    """Create temp skills/workspaces dirs that are exclusively owned by the e2e suite."""
    base = tmp_path_factory.mktemp("studio_e2e")
    skills_dir = base / "skills"
    workspaces_dir = base / "workspaces"
    workspaces_dir.mkdir()
    _seed_skill_files(skills_dir)
    logger.info("seeded e2e workspace skills_dir=%s", skills_dir)
    yield {"skills_dir": skills_dir, "workspaces_dir": workspaces_dir, "base": base}


@pytest.fixture(scope="session")
def studio_servers(studio_workspace: dict[str, Path]) -> Iterator[dict[str, str]]:
    """Spawn backend + frontend dev servers and yield URLs."""
    for port, label in ((BACKEND_PORT, "backend"), (FRONTEND_PORT, "frontend")):
        if not _is_port_free(port):
            pytest.fail(f"Port {port} is occupied; cannot run e2e {label} server")

    venv_python = REPO_ROOT / ".venv" / "bin" / "python"
    backend_runner = Path(__file__).parent / "_backend_runner.py"
    backend_env = {
        **os.environ,
        "STUDIO_TEST_SKILLS_DIR": str(studio_workspace["skills_dir"]),
        "STUDIO_TEST_WORKSPACES_DIR": str(studio_workspace["workspaces_dir"]),
        "STUDIO_TEST_PORT": str(BACKEND_PORT),
        "PYTHONPATH": os.pathsep.join(
            [str(STUDIO_BACKEND), str(SRC_CORE), os.environ.get("PYTHONPATH", "")],
        ),
    }
    backend_log = studio_workspace["base"] / "backend.log"
    logger.info("spawning backend port=%s log=%s", BACKEND_PORT, backend_log)
    with backend_log.open("w", encoding="utf-8") as backend_out:
        backend_proc = subprocess.Popen(  # noqa: S603
            [str(venv_python), str(backend_runner)],
            cwd=REPO_ROOT,
            env=backend_env,
            stdout=backend_out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    try:
        _wait_for_url(f"{BACKEND_URL}/docs", timeout=20.0, label="studio-backend")
    except Exception:
        backend_proc.terminate()
        log_text = backend_log.read_text(encoding="utf-8", errors="replace") if backend_log.exists() else "<missing>"
        raise RuntimeError(f"backend startup failed; log:\n{log_text}") from None

    frontend_env = {
        **os.environ,
        "VITE_STUDIO_API_BASE_URL": f"{BACKEND_URL}/api",
    }
    frontend_log = studio_workspace["base"] / "frontend.log"
    logger.info("spawning frontend port=%s log=%s", FRONTEND_PORT, frontend_log)
    with frontend_log.open("w", encoding="utf-8") as frontend_out:
        frontend_proc = subprocess.Popen(  # noqa: S603,S607
            ["npm", "run", "dev", "--", "--port", str(FRONTEND_PORT), "--strictPort", "--host", "127.0.0.1"],
            cwd=STUDIO_FRONTEND,
            env=frontend_env,
            stdout=frontend_out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    try:
        _wait_for_url(FRONTEND_URL, timeout=45.0, label="studio-frontend")
    except Exception:
        frontend_proc.terminate()
        backend_proc.terminate()
        log_text = frontend_log.read_text(encoding="utf-8", errors="replace") if frontend_log.exists() else "<missing>"
        raise RuntimeError(f"frontend startup failed; log:\n{log_text}") from None

    try:
        yield {
            "backend_url": BACKEND_URL,
            "frontend_url": FRONTEND_URL,
            "api_base_url": API_BASE_URL,
        }
    finally:
        logger.info("tearing down studio servers")
        for proc in (frontend_proc, backend_proc):
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                proc.wait(timeout=3)


@pytest.fixture
def studio_page(page, studio_servers: dict[str, str]):  # type: ignore[no-untyped-def]
    """Navigate to the Studio frontend root and return the Playwright page."""
    page.goto(studio_servers["frontend_url"])
    return page
