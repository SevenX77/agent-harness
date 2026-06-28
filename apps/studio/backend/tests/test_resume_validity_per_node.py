"""B1 (n5-node fn#3): EngineAdapter.resume_validity per-node resume_allowed.

Pins spec F3 at the adapter boundary: once a resume targets a specific node,
``resume_allowed`` must be decided per-node against the affected-downstream slice
(so an unrelated side-branch stays resumable even when the whole-skill compare is
dirty), while the global Trace Resume path (no resume node) keeps the existing
whole-skill dirty gate.

These exercise the real ``EngineAdapter.resume_validity`` decision logic; the two
I/O boundaries it touches -- the runtime-state restore and the recompile-for-hash
-- are stubbed so the test controls exactly one variable: dirty + which node is
being resumed from. The dependency-graph slice itself is covered separately in
``test_resume_downstream.py``; here it is stubbed to a known affected set.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.core.adapters.engine import EngineAdapter

_SNAPSHOT_HASH = f"sha256:{'1' * 64}"
_CURRENT_HASH = f"sha256:{'2' * 64}"
_FINGERPRINT = f"sha256:{'3' * 64}"


def _make_dirty_adapter(monkeypatch: Any, *, affected: list[str]) -> EngineAdapter:
    """Build an in-process adapter wired to a dirty skill with a fixed slice.

    snapshot content_hash != current content_hash -> dirty. The downstream slice
    is fixed to ``affected`` so the test controls which nodes count as affected.
    """
    adapter = EngineAdapter(transport="in_process")

    class _FakeStore:
        def restore(self, *, run_id: str) -> SimpleNamespace:
            return SimpleNamespace(
                state={
                    "schema_version": "studio.runtime_state.v1",
                    "run_id": run_id,
                    "checkpoint_id": "checkpoint-1",
                    "checkpoint_ns": "",
                    "artifact_ref": {
                        "artifact_id": "fanout",
                        "content_hash": _SNAPSHOT_HASH,
                        "execution_fingerprint": _FINGERPRINT,
                    },
                },
            )

    monkeypatch.setattr(adapter, "_build_runtime_state_store", lambda: _FakeStore())
    monkeypatch.setattr(
        adapter,
        "compile",
        lambda _payload: {
            "artifact_id": "fanout",
            "content_hash": _CURRENT_HASH,
            "execution_fingerprint": _FINGERPRINT,
        },
    )
    monkeypatch.setattr(
        "app.services.skills.resolve_skill_dir",
        lambda _skill_id: "/tmp/fanout",
    )
    # The graph slice is exercised in test_resume_downstream.py; here pin it so the
    # per-node gate is the only variable under test.
    monkeypatch.setattr(
        adapter,
        "_affected_downstream_for_resume",
        lambda *, skill_id, resume_from_node_id, is_dirty: (affected if is_dirty else []),
    )
    return adapter


def test_resume_validity_allows_unrelated_sidebranch_when_dirty(monkeypatch: Any) -> None:
    """Dirty skill + resume from a node OUTSIDE the affected slice -> allowed (F3)."""
    adapter = _make_dirty_adapter(monkeypatch, affected=["b", "d"])

    result = adapter.resume_validity(
        {
            "skill_id": "fanout",
            "run_id": "run-1",
            "checkpoint_id": "checkpoint-1",
            "resume_from_node_id": "c",
        }
    )

    assert result["resume_allowed"] is True
    assert result["dirty_fields"] == ["content_hash"]


def test_resume_validity_blocks_affected_downstream_when_dirty(monkeypatch: Any) -> None:
    """Dirty skill + resume from a node INSIDE the affected slice -> blocked (F3)."""
    adapter = _make_dirty_adapter(monkeypatch, affected=["b", "d"])

    result = adapter.resume_validity(
        {
            "skill_id": "fanout",
            "run_id": "run-1",
            "checkpoint_id": "checkpoint-1",
            "resume_from_node_id": "d",
        }
    )

    assert result["resume_allowed"] is False
    assert result["reason"] == "dirty_upstream"


def test_resume_validity_global_resume_keeps_whole_skill_gate(monkeypatch: Any) -> None:
    """No resume node (global Trace Resume) keeps gating on any dirt (F3 caveat)."""
    adapter = _make_dirty_adapter(monkeypatch, affected=["b", "d"])

    result = adapter.resume_validity(
        {
            "skill_id": "fanout",
            "run_id": "run-1",
            "checkpoint_id": "checkpoint-1",
            # no resume_from_node_id -> global path
        }
    )

    assert result["resume_allowed"] is False
    assert result["reason"] == "dirty_upstream"
