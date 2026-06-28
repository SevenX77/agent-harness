from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException


def test_run_dir_for_rejects_path_traversal_run_id(studio_roots: tuple[Path, Path]) -> None:
    del studio_roots
    from app.services.skills import run_dir_for

    with pytest.raises(HTTPException) as exc_info:
        run_dir_for("text-segmentation", "../outside")

    assert exc_info.value.detail["error_code"] == "INVALID_RUN_ID"


def test_golden_dir_for_rejects_path_traversal_golden_id(studio_roots: tuple[Path, Path]) -> None:
    del studio_roots
    from app.services.golden_diff import _golden_dir_for

    with pytest.raises(HTTPException) as exc_info:
        _golden_dir_for("text-segmentation", "../outside")

    assert exc_info.value.detail["error_code"] == "INVALID_RUN_ID"


def test_golden_headless_rejects_path_traversal_refs() -> None:
    from app.services.golden_headless import _find_file

    with pytest.raises(ValueError, match="Invalid artifact ref"):
        _find_file("../secret.json")


def test_engine_adapter_rejects_zip_members_outside_target(tmp_path: Path) -> None:
    from app.core.adapters.engine import _unzip_directory

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../escaped.txt", "nope")

    with pytest.raises(ValueError, match="Unsafe zip member"):
        _unzip_directory(payload.getvalue(), tmp_path / "target")

    assert not (tmp_path / "escaped.txt").exists()


def test_private_studio_skill_resolver_rejects_path_traversal_skill_id() -> None:
    from app.core.adapters.engine import _PrivateStudioSkillResolver

    resolver = _PrivateStudioSkillResolver()
    with pytest.raises(ValueError, match="Invalid skill_id"):
        resolver.resolve_skill("../text-segmentation")
