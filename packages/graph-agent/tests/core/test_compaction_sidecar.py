"""Unit tests for ``GraphAgentHarness._save_compaction_sidecar``.

The sidecar helper is a thin wrapper around ``StorageManager.save_artifact``
+ ``to_jsonable_dict``. Tests cover:

* ``storage_manager=None`` → returns None (no disk write).
* Happy path writes ``compaction_{idx}.json`` under ``_history/{run_id}``
  and returns the absolute path as a string. File contents round-trip
  through ``to_jsonable_dict``.
* A raising ``storage_manager`` is swallowed and returns None (the
  harness must never crash the run because a debug sidecar failed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from graph_agent.core.harness import GraphAgentHarness  # noqa: E402
from graph_agent.io.storage import StorageManager  # noqa: E402


class _RaisingStorageManager:
    """Drop-in for StorageManager whose save_artifact always raises.

    Used to prove the except-branch returns None without propagating.
    """

    def save_artifact(self, name: str, content: Any, phase: str | None = None) -> Path:
        raise RuntimeError("disk is on fire")


class TestSaveCompactionSidecar:
    """Contract tests for _save_compaction_sidecar."""

    def test_returns_none_when_no_storage_manager(self) -> None:
        result = GraphAgentHarness._save_compaction_sidecar(
            run_id="run-abc",
            idx=0,
            removed_messages=[{"role": "user", "content": "hi"}],
            storage_manager=None,
        )
        assert result is None

    def test_writes_sidecar_under_history_dir(self, tmp_path: Path) -> None:
        """File lands at ``phases/_history/{run_id}/compaction_{idx}.json``.

        The returned value is the absolute path as a string; the file
        content is a JSON document of the serialized messages.
        """
        storage = StorageManager(
            workspace_root=tmp_path,
            skill_id="unit-skill",
            run_id="run-xyz",
        )
        # Prime the run directory so save_artifact has somewhere to land.
        storage.get_output_dir()

        removed = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        result = GraphAgentHarness._save_compaction_sidecar(
            run_id="run-xyz",
            idx=3,
            removed_messages=removed,
            storage_manager=storage,
        )

        assert result is not None
        path = Path(result)
        assert path.exists()
        assert path.name == "compaction_3.json"
        # Sidecars live under phases/_history/{run_id}/ by convention so
        # Studio can group them by the originating run.
        assert "_history" in path.parts
        assert "run-xyz" in path.parts

        # Content is JSON-serialised via to_jsonable_dict — plain dicts
        # round-trip without modification.
        reloaded = json.loads(path.read_text(encoding="utf-8"))
        assert reloaded == removed

    def test_swallows_storage_failure(self) -> None:
        """A raising storage manager must not propagate; helper returns None."""
        result = GraphAgentHarness._save_compaction_sidecar(
            run_id="run-err",
            idx=7,
            removed_messages=[{"role": "user", "content": "x"}],
            storage_manager=_RaisingStorageManager(),
        )
        assert result is None
