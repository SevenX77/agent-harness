"""Regression: IOManager.save_outputs must accept the canonical schema
``target`` value ``"artifact"`` — not just the legacy ``"artifact_manager"``.

Pre-fix bug (1.5 in 2026-04-26 cohesion plan): schema declares
``IoOutput.target: Literal["file", "artifact"]`` but
``IOManager.save_outputs`` dispatches on ``target == "artifact_manager"``
and falls through to the unknown-target ``raise ValueError`` branch for
the canonical name. Production skills (``story-deconstruction``,
``global-synthesis``, ``batch-analysis``) all use ``target: artifact``
— Pydantic accepts them, the loader hands them to IOManager, and the
save then crashes.

Pre-fix this crash was hidden by ``_save_outputs_via_io``'s blanket
``except Exception: logger.warning(...)`` (the bug fixed by 2.2).
After 2.2 propagates failures, the schema/runtime mismatch becomes a
visible production regression — fixing 1.5 is now required to keep
prod loading working.
"""
from __future__ import annotations

from pathlib import Path

from graph_agent.io.manager import IOManager


class TestIOManagerArtifactTargetAlignment:
    def test_save_outputs_accepts_target_artifact(self, tmp_path: Path) -> None:
        """``target: artifact`` (canonical schema value) must dispatch
        to the artifact saver, NOT raise ValueError."""
        save_calls: list[tuple[str, object]] = []

        def fake_saver(name: str, value: object, **_: object) -> str:
            save_calls.append((name, value))
            return f"/fake/{name}"

        io_mgr = IOManager(
            {
                "outputs": [
                    {"name": "story_framework", "target": "artifact"}
                ]
            }
        )

        result = io_mgr.save_outputs(
            context={"story_framework": {"chapters": 3}},
            artifact_saver=fake_saver,
            project_id="proj-x",
        )

        assert save_calls == [("story_framework", {"chapters": 3})], (
            "Output with target='artifact' (the schema-canonical value) "
            "must reach the artifact_saver. The legacy IOManager dispatched "
            "only on target=='artifact_manager' and raised ValueError on "
            "'artifact', breaking every prod skill that uses the value the "
            "schema literally accepts."
        )
        assert result == ["/fake/story_framework"]

    def test_save_outputs_still_accepts_legacy_artifact_manager(
        self, tmp_path: Path
    ) -> None:
        """Back-compat: ``target: artifact_manager`` (the legacy alias)
        must keep working. The schema rejects this value but in-process
        callers may still pass io_config dicts using the old name."""
        save_calls: list[tuple[str, object]] = []

        def fake_saver(name: str, value: object, **_: object) -> str:
            save_calls.append((name, value))
            return f"/fake/{name}"

        io_mgr = IOManager(
            {
                "outputs": [
                    {"name": "story_framework", "target": "artifact_manager"}
                ]
            }
        )

        io_mgr.save_outputs(
            context={"story_framework": {"x": 1}},
            artifact_saver=fake_saver,
            project_id="proj-x",
        )

        assert save_calls == [("story_framework", {"x": 1})]
