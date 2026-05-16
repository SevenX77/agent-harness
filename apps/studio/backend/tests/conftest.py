from __future__ import annotations

import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIO_BACKEND = REPO_ROOT / "studio-backend"
SRC_CORE = REPO_ROOT / "src" / "core"

for path in (STUDIO_BACKEND, SRC_CORE):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from app.core import config  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.run_manager import run_manager  # noqa: E402
from app.services.terminal_manager import terminal_manager  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def studio_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    skills_dir = tmp_path / "skills"
    workspaces_dir = tmp_path / "workspaces"
    skills_dir.mkdir()
    _write_graph_skill(skills_dir / "text-segmentation", "text-segmentation", "Text segments")
    _write_graph_skill(skills_dir / "event-extraction", "event-extraction", "Events")
    _write_graph_skill(skills_dir / "batch-analysis", "batch-analysis", "Batch")
    _write_graph_skill(skills_dir / "global-synthesis", "global-synthesis", "Global")
    monkeypatch.setattr(config, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(config, "WORKSPACES_DIR", workspaces_dir)
    return skills_dir, workspaces_dir


@pytest.fixture
def client(studio_roots: tuple[Path, Path]) -> Iterator[TestClient]:
    del studio_roots
    with TestClient(create_app()) as test_client:
        yield test_client
    run_manager._runs.clear()
    terminal_manager._sessions.clear()


def _write_graph_skill(skill_dir: Path, name: str, description: str) -> None:
    (skill_dir / "io").mkdir(parents=True)
    (skill_dir / "phases" / "setup" / "actions").mkdir(parents=True)
    (skill_dir / "phases" / "setup" / "actions" / "prepare.py").write_text(
        "from graph_agent.cognitive.context_facade import Context\n"
        "def prepare(context: Context) -> None:\n"
        "    context.set('prepared', {'ok': True})\n",
        encoding="utf-8",
    )
    (skill_dir / "GRAPH.md").write_text(
        f"""---
name: {name}
description: {description}
schema_version: "2.1"
---
<input src="io/inputs.json" />
<output src="io/outputs.json" />
<phase id="setup" src="phases/setup" />
""",
        encoding="utf-8",
    )
    (skill_dir / "io" / "inputs.json").write_text(
        """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {"input_text": {"type": "string"}},
  "required": ["input_text"],
  "additionalProperties": false
}
""",
        encoding="utf-8",
    )
    (skill_dir / "io" / "outputs.json").write_text(
        """{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {"prepared": {"type": "object"}},
  "required": ["prepared"],
  "additionalProperties": true
}
""",
        encoding="utf-8",
    )
    (skill_dir / "phases" / "setup" / "LOGIC.md").write_text(
        """---
mode: logic
name: setup
---
<python_callable>
prepare
</python_callable>
""",
        encoding="utf-8",
    )


def copy_skill(src_root: Path, dst_root: Path, skill_id: str) -> Path:
    target = dst_root / "default" / "skills" / skill_id
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_root / skill_id, target)
    return target
