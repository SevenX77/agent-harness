from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("STUDIO_API_TOKEN", "studio-test-token")

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


@pytest.fixture(autouse=True)
def _community_catalog_neutralized_in_tests(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
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
    clear_backend_caches()
    yield
    clear_backend_caches()


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
    monkeypatch.setattr(config, "APP_SETTINGS_PATH", global_config_dir / "app_settings.json")
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
    (skill_dir / "phases" / "setup" / "actions").mkdir(parents=True)
    (skill_dir / "phases" / "setup" / "actions" / "__init__.py").write_text("", encoding="utf-8")
    (skill_dir / "phases" / "setup" / "actions" / "prepare.py").write_text(
        "def prepare(context):\n    context.set('prepared', True)\n    return {'prepared': True}\n",
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
    return target
