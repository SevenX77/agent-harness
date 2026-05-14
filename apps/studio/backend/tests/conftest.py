from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("STUDIO_API_TOKEN", "studio-test-token")

REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIO_BACKEND = REPO_ROOT / "studio-backend"
SRC_CORE = REPO_ROOT / "src" / "core"

for path in (STUDIO_BACKEND, SRC_CORE):
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


@pytest.fixture
def studio_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    skills_dir = tmp_path / "skills"
    workspaces_dir = tmp_path / "workspaces"
    global_config_dir = tmp_path / "global-config"
    default_skills_root = global_config_dir / "Skills"
    skills_dir.mkdir()
    _write_graph_skill(skills_dir / "text-segmentation", "text-segmentation", "Text segments")
    _write_graph_skill(skills_dir / "event-extraction", "event-extraction", "Events")
    _write_graph_skill(skills_dir / "batch-analysis", "batch-analysis", "Batch")
    _write_graph_skill(skills_dir / "global-synthesis", "global-synthesis", "Global")
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "WORKSPACES_DIR", workspaces_dir)
    monkeypatch.setattr(config, "APP_SETTINGS_DIR", global_config_dir)
    monkeypatch.setattr(config, "SKILL_INDEX_PATH", global_config_dir / "skill_index.json")
    monkeypatch.setattr(config, "DEFAULT_SKILLS_ROOT", default_skills_root)
    clear_backend_caches()
    return skills_dir, workspaces_dir


@pytest.fixture
def client(studio_roots: tuple[Path, Path]) -> Iterator[TestClient]:
    del studio_roots
    test_client = AuthenticatedTestClient(create_app())
    test_client.headers["Authorization"] = f"Bearer {_TEST_TOKEN}"
    with test_client:
        yield test_client
    run_manager._runs.clear()
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
    (skill_dir / "script").mkdir(parents=True)
    (skill_dir / "script" / "__init__.py").write_text("", encoding="utf-8")
    (skill_dir / "script" / "logic.py").write_text(
        "def prepare(data):\n"
        "    data['prepared'] = True\n"
        "    return data\n",
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        f"""---
schema_version: "2.0"
name: {name}
description: {description}
type: graph
context_mapping:
  input_text: "{{input.input_text}}"
  prepared: ""
io:
  inputs:
    - name: input_text
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
""",
        encoding="utf-8",
    )


def copy_skill(src_root: Path, dst_root: Path, skill_id: str) -> Path:
    target = dst_root / "default" / "skills" / skill_id
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_root / skill_id, target)
    return target
