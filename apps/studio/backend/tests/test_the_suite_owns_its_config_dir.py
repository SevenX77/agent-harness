"""The suite must not read or write the developer's own Studio config dir.

`app.core.config.APP_SETTINGS_DIR` resolves, in production, to the per-user
application directory — `%APPDATA%/AgentStudio` on Windows, `~/Library/
Application Support/AgentStudio` on macOS, `~/.local/share/AgentStudio`
elsewhere. That directory holds the running app's live credentials, roles and
settings.

A suite that reads it is not testing the code, it is testing the machine: a
developer whose stored config predates a schema change gets failures CI never
sees (2026-08-22: thirteen backend tests failed on `extra_forbidden` for two
fields a merged PR had removed from the gateway contract, on a file the suite
had no business opening). A suite that WRITES it is worse — it edits the state
the running app is using.
"""

from __future__ import annotations

import os
from pathlib import Path

from app.core import config, paths


def _this_machine_s_own_studio_config_dir() -> Path:
    """Where production would put it here, with the suite's override taken away."""
    environ = {
        name: value
        for name, value in os.environ.items()
        if name not in ("STUDIO_CONFIG_DIR", "STUDIO_RESOURCE_DIR")
    }
    return paths.app_settings_dir(environ)


def test_the_config_dir_the_suite_uses_is_not_this_machine_s_own() -> None:
    machine_own = _this_machine_s_own_studio_config_dir()
    in_use = Path(config.APP_SETTINGS_DIR)

    assert in_use != machine_own, (
        "the suite is pointed at the developer's real Studio config dir; tests "
        f"read and write live app state there ({machine_own})"
    )
    assert machine_own not in in_use.parents, (
        f"the suite's config dir {in_use} sits inside the real one {machine_own}"
    )


def test_every_derived_path_follows_the_config_dir() -> None:
    """One redirect has to cover all of them, or a leak survives under a new name."""
    in_use = Path(config.APP_SETTINGS_DIR)

    for derived in (
        config.SKILL_INDEX_PATH,
        config.APP_SETTINGS_PATH,
        config.DEFAULT_SKILLS_ROOT,
        config.WORKSPACES_DIR,
    ):
        assert in_use in Path(derived).parents, (
            f"{derived} does not follow APP_SETTINGS_DIR ({in_use})"
        )
