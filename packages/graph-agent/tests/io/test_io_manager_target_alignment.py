"""IOManager target contract (MVP1 r3): ``file`` is the only per-field target.

Artifact persistence moved wholly to the host runtime_config ``artifacts`` manifest
(``graph_agent.io.artifact_manifest``); the former per-field
``target: 'artifact'`` and its ``artifact_manager`` legacy alias were deleted
in the same change (no-backward-compat).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graph_agent.io.manager import IOManager


def test_io_manager_rejects_non_dict_io_config() -> None:
    with pytest.raises(TypeError, match="IOManager io_config must be a dict, got list"):
        IOManager([])  # type: ignore[arg-type]


class TestIOManagerTargetContract:
    def test_target_file_saves_to_output_dir(self, tmp_path: Path) -> None:
        io_mgr = IOManager({"outputs": [{"name": "report", "target": "file"}]})

        saved = io_mgr.save_outputs({"report": {"ok": True}}, output_dir=tmp_path)

        assert saved == [str(tmp_path / "report.json")]

    @pytest.mark.parametrize("target", ["artifact", "artifact_manager"])
    def test_per_field_artifact_targets_are_rejected(
        self, tmp_path: Path, target: str
    ) -> None:
        io_mgr = IOManager({"outputs": [{"name": "story_framework", "target": target}]})

        with pytest.raises(ValueError, match="runtime_config artifacts manifest"):
            io_mgr.save_outputs({"story_framework": {}}, output_dir=tmp_path)

    def test_missing_required_runtime_input_raises(self) -> None:
        io_mgr = IOManager({"inputs": [{"name": "project_id", "source": "runtime"}]})

        with pytest.raises(
            ValueError, match="Required runtime input 'project_id' was not provided"
        ):
            io_mgr.load_inputs()

    def test_missing_optional_runtime_input_keeps_none(self) -> None:
        io_mgr = IOManager(
            {"inputs": [{"name": "project_id", "source": "runtime", "required": False}]}
        )

        assert io_mgr.load_inputs() == {"project_id": None}

    def test_missing_declared_output_raises_and_records_io_error(self) -> None:
        io_mgr = IOManager(
            {"outputs": [{"name": "story_framework", "target": "file", "path": "out.json"}]}
        )
        context: dict[str, object] = {}

        with pytest.raises(ValueError, match="Declared output 'story_framework' was not found"):
            io_mgr.save_outputs(context=context)

        assert "_io_errors" not in context
        assert io_mgr.io_errors == ["Declared output 'story_framework' was not found in context"]

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
