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

import pytest
from graph_agent.io.manager import IOManager


def test_io_manager_rejects_non_dict_io_config() -> None:
    with pytest.raises(TypeError, match="IOManager io_config must be a dict, got list"):
        IOManager([])  # type: ignore[arg-type]


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

    def test_artifact_saver_exception_propagates(self) -> None:
        """A real artifact_saver write failure must not be swallowed."""
        io_mgr = IOManager(
            {
                "outputs": [
                    {"name": "story_framework", "target": "artifact"}
                ]
            }
        )
        context = {"story_framework": {"chapters": 3}}

        def broken_saver(name: str, value: object, **_: object) -> str:
            raise OSError(f"disk full while saving {name}")

        with pytest.raises(IOError, match="disk full while saving story_framework"):
            io_mgr.save_outputs(
                context=context,
                artifact_saver=broken_saver,
                project_id="proj-x",
            )

        # MVP-2 T7: io_errors accumulate on the IOManager instance instead
        # of the (snapshot) context dict, so the caller can route them
        # into ``state['flow'].io_errors``. Context dict stays clean.
        assert "_io_errors" not in context
        assert io_mgr.io_errors == [
            "artifact_saver failed for 'story_framework': "
            "disk full while saving story_framework"
        ]

    def test_missing_required_runtime_input_raises(self) -> None:
        io_mgr = IOManager(
            {
                "inputs": [
                    {"name": "project_id", "source": "runtime"}
                ]
            }
        )

        with pytest.raises(
            ValueError, match="Required runtime input 'project_id' was not provided"
        ):
            io_mgr.load_inputs()

    def test_missing_optional_runtime_input_keeps_none(self) -> None:
        io_mgr = IOManager(
            {
                "inputs": [
                    {"name": "project_id", "source": "runtime", "required": False}
                ]
            }
        )

        assert io_mgr.load_inputs() == {"project_id": None}

    def test_missing_declared_output_raises_and_records_io_error(self) -> None:
        io_mgr = IOManager(
            {
                "outputs": [
                    {"name": "story_framework", "target": "file", "path": "out.json"}
                ]
            }
        )
        context: dict[str, object] = {}

        with pytest.raises(
            ValueError, match="Declared output 'story_framework' was not found"
        ):
            io_mgr.save_outputs(context=context)

        assert "_io_errors" not in context
        assert io_mgr.io_errors == [
            "Declared output 'story_framework' was not found in context"
        ]

    def test_missing_path_template_placeholder_raises(self) -> None:
        io_mgr = IOManager(
            {
                "outputs": [
                    {
                        "name": "story_framework",
                        "target": "file",
                        "path": "output/{context.project_id}/story.json",
                    }
                ]
            }
        )

        with pytest.raises(
            ValueError,
            match=r"Path template placeholder \{context\.project_id\} not found",
        ):
            io_mgr.save_outputs(context={"story_framework": {"chapters": 3}})

    def test_artifact_target_without_saver_raises_and_records_io_error(self) -> None:
        io_mgr = IOManager(
            {
                "outputs": [
                    {"name": "story_framework", "target": "artifact"}
                ]
            }
        )
        context = {"story_framework": {"chapters": 3}}

        with pytest.raises(
            ValueError, match="Artifact target output 'story_framework' has no saver"
        ):
            io_mgr.save_outputs(context=context)

        assert "_io_errors" not in context
        assert io_mgr.io_errors == [
            "Artifact target output 'story_framework' has no saver"
        ]
