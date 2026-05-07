from __future__ import annotations

from pathlib import Path

from app.core import paths


def test_resource_dir_prefers_studio_resource_dir_env() -> None:
    resource_dir = paths.resource_dir_from_env(
        {"STUDIO_RESOURCE_DIR": "/tmp/studio-resources"},
        Path("/repo"),
    )

    assert resource_dir == Path("/tmp/studio-resources")
    assert paths.default_skills_dir(resource_dir) == Path("/tmp/studio-resources/skills")
    assert paths.default_config_dir(resource_dir) == Path("/tmp/studio-resources/config")
    assert paths.default_workspaces_dir(resource_dir) == Path("/tmp/studio-resources/workspaces")


def test_resource_dir_uses_fallback_without_env() -> None:
    assert paths.resource_dir_from_env({}, Path("/repo")) == Path("/repo")
