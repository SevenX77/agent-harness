from __future__ import annotations

import contextlib
import json
import multiprocessing
import os
import shutil
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("STUDIO_API_TOKEN", "studio-test-token")
# Cross-platform bottom line (docs/development/CROSS_PLATFORM.md): child
# Python processes spawned by tests write UTF-8 regardless of host locale.
os.environ.setdefault("PYTHONUTF8", "1")

REPO_ROOT = Path(__file__).resolve().parents[4]
STUDIO_BACKEND = REPO_ROOT / "apps" / "studio" / "backend"
SRC_CORE = REPO_ROOT / "src" / "core"
GRAPH_AGENT_SRC = REPO_ROOT / "packages" / "graph-agent" / "src"
GRAPH_AGENT_GATEWAY_SRC = REPO_ROOT / "packages" / "graph-agent-gateway" / "src"

for path in (STUDIO_BACKEND, SRC_CORE, GRAPH_AGENT_SRC, GRAPH_AGENT_GATEWAY_SRC):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from app.core import config  # noqa: E402
from app.core.backends import clear_backend_caches  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.run_manager import run_manager  # noqa: E402
from app.services.terminal_manager import terminal_manager  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_TEST_TOKEN = "studio-test-token"

# Thread names that must never survive a test's teardown. Precise known-bad
# classes only, so this gate cannot flake on unrelated background machinery:
# - "studio-file-watcher": FileWatcherService.stop() must not return while its
#   daemon thread lives (a survivor keeps running rust/notify code into
#   interpreter shutdown and SIGSEGVs the Linux CI runners under coverage).
# - "QueueFeederThread": a multiprocessing.Queue used from the main process was
#   dropped without close() + join_thread() (the PR #259 leak class).
_FORBIDDEN_LEAKED_THREAD_NAMES = ("studio-file-watcher", "QueueFeederThread")


@pytest.fixture(autouse=True)
def _no_leaked_processes_or_native_threads() -> Iterator[None]:
    """Regression guard for the intermittent CI exit-139 (SIGSEGV after "N passed").

    Native resources that outlive a test keep running into interpreter/coverage
    teardown and crash the process on the Linux runners — always AFTER the whole
    suite passed, so nothing pointed at the leaking test. PR #259 fixed the leaked
    run/pty processes; run 28559658741 (2026-07-02) crashed again while leaked
    `studio-file-watcher` threads were still observable after teardowns. Fail the
    leaking test loudly instead of segfaulting after the summary line.
    """
    yield
    leaked_children = multiprocessing.active_children()
    assert not leaked_children, (
        "multiprocessing children survived this test's teardown (join/terminate/kill "
        f"them before returning): {[(child.pid, child.name) for child in leaked_children]}"
    )
    leaked_threads = [
        thread.name
        for thread in threading.enumerate()
        if thread.is_alive() and thread.name.startswith(_FORBIDDEN_LEAKED_THREAD_NAMES)
    ]
    assert not leaked_threads, (
        "known-crash-class threads survived this test's teardown (they SIGSEGV the "
        f"interpreter during CI coverage shutdown): {leaked_threads}"
    )


@pytest.fixture(autouse=True)
def _community_catalog_neutralized_in_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    """Keep the community catalog feature off the network during tests.

    Production ships the catalog ON by default (clean open API, baked gate URL +
    signing key, no token), so probe/contribute/sync paths would otherwise reach
    the real gate. Neutralize both read and write here — and scrub any leaked
    ``STUDIO_COMMUNITY_*`` shell env — so the default test state makes no network
    call. Tests that exercise the active paths opt back in explicitly (set the
    flag + a test gate/manifest URL and stub the client).
    """
    for var in (
        "STUDIO_COMMUNITY_UPLOAD_ENABLED",
        "STUDIO_COMMUNITY_GATE_URL",
        "STUDIO_COMMUNITY_PROTOCOL_MAJOR",
        "STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY",
        "STUDIO_COMMUNITY_CATALOG_MANIFEST_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("STUDIO_COMMUNITY_UPLOAD_ENABLED", "false")
    monkeypatch.setenv("STUDIO_COMMUNITY_GATE_URL", "")
    monkeypatch.setenv("STUDIO_COMMUNITY_CATALOG_SIGNING_PUBKEY", "")
    monkeypatch.setenv("STUDIO_COMMUNITY_CATALOG_MANIFEST_URL", "")
    monkeypatch.setenv(
        "STUDIO_RUNTIME_ACTIVITY_LOG_PATH",
        str(tmp_path / "runtime-activity" / "studio_runtime_activity.jsonl"),
    )
    clear_backend_caches()
    yield
    clear_backend_caches()


@pytest.fixture
def studio_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    workspaces_dir = tmp_path / "workspaces"
    global_config_dir = tmp_path / "global-config"
    default_skills_root = global_config_dir / "Skills"
    skills_dir = default_skills_root
    skills_dir.mkdir(parents=True)
    skill_index: dict[str, dict[str, str]] = {}
    for skill_id, description in (
        ("text-segmentation", "Text segments"),
        ("event-extraction", "Events"),
        ("batch-analysis", "Batch"),
        ("global-synthesis", "Global"),
    ):
        skill_dir = skills_dir / skill_id
        _write_graph_skill(skill_dir, skill_id, description)
        skill_index[skill_id] = {"absolute_path": str(skill_dir), "l2_remote_url": ""}
    monkeypatch.setattr(config, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", global_config_dir)
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", global_config_dir / "skill_index.json")
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", global_config_dir / "app_settings.json")
    monkeypatch.setattr(config, "DEFAULT_SKILLS_ROOT", default_skills_root)
    config.SKILL_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.SKILL_INDEX_PATH.write_text(json.dumps(skill_index), encoding="utf-8")
    clear_backend_caches()
    return skills_dir, workspaces_dir


@pytest.fixture
def client(studio_roots: tuple[Path, Path]) -> Iterator[TestClient]:
    del studio_roots
    test_client = AuthenticatedTestClient(create_app())
    test_client.headers["Authorization"] = f"Bearer {_TEST_TOKEN}"
    with test_client:
        yield test_client
    # Properly stop background runs/terminals before dropping references. Clearing the
    # dicts alone orphaned real multiprocessing.Process children + their Queue feeder
    # threads (and pty processes), which then SIGSEGV during interpreter/coverage
    # teardown — the flaky `exit 139 after "N passed"` on quality-gates.
    run_manager.reset_for_tests()
    for term_id in list(terminal_manager._sessions):
        with contextlib.suppress(Exception):
            terminal_manager.close(term_id)
    terminal_manager._sessions.clear()
    clear_backend_caches()


class AuthenticatedTestClient(TestClient):
    def websocket_connect(
        self,
        url: str,
        subprotocols: list[str] | None = None,
        **kwargs: object,
    ):  # type: ignore[no-untyped-def]
        return super().websocket_connect(_with_ws_token(url), subprotocols, **kwargs)


def _with_ws_token(url: str) -> str:
    if "token=" in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}token={_TEST_TOKEN}"


def _write_graph_skill(skill_dir: Path, name: str, description: str) -> None:
    (skill_dir / "phases" / "setup" / "actions").mkdir(parents=True)
    (skill_dir / "phases" / "setup" / "actions" / "__init__.py").write_text("", encoding="utf-8")
    (skill_dir / "phases" / "setup" / "actions" / "prepare.py").write_text(
        "def prepare(inputs):\n    return {'prepared': True}\n",
        encoding="utf-8",
    )
    (skill_dir / "GRAPH.md").write_text(
        f"""---
schema_version: "v0.3.0"
name: {name}
description: {description}
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
    required: [input_text]
    additionalProperties: false
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
    required: [prepared]
    additionalProperties: true
phases:
  - setup
---
<phase depends_on="input" output>setup</phase>
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "setup" / "LOGIC.md").write_text(
        """---
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
  outputs:
    type: object
    properties:
      prepared:
        type: boolean
---
<action>prepare</action>
""",
        encoding="utf-8",
    )


def copy_skill(src_root: Path, dst_root: Path, skill_id: str) -> Path:
    target = dst_root / "default" / "skills" / skill_id
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_root / skill_id, target)
    register_skill_index_entry(skill_id, target)
    return target


def register_skill_index_entry(skill_id: str, skill_dir: Path) -> None:
    index_path = config.SKILL_INDEX_PATH
    index_path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    raw[skill_id] = {"absolute_path": str(skill_dir), "l2_remote_url": ""}
    index_path.write_text(json.dumps(raw), encoding="utf-8")
