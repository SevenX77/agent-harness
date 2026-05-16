from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
TOOL_PATH = REPO_ROOT / "packages" / "graph-agent" / "tools" / "dual_run_shadow.py"
HELLO_WORLD = REPO_ROOT / "skills" / "hello-world"


def _load_tool():
    spec = importlib.util.spec_from_file_location("dual_run_shadow", TOOL_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.tier1
def test_dual_run_shadow_hello_world_idempotency(tmp_path: Path) -> None:
    tool = _load_tool()
    output_path = tmp_path / "shadow.json"

    exit_code = tool.main(
        [
            str(HELLO_WORLD),
            "--input-json",
            '{"user_name":"Ada"}',
            "--chat-fixture",
            "hello-world",
            "--output",
            str(output_path),
        ]
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["mode"] == "idempotency"
    assert report["shadow_reference"] == "v21_repeat_run"
    assert report["match"] is True
    assert report["diff"] == {"missing": [], "extra": [], "mismatch": []}
    assert report["outputs"]["run_a"]["data"]["greet"]["greeting"] == "Hello, Ada!"
