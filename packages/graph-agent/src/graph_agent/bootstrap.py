"""Bootstrap sequence for graph_agent startup."""

from __future__ import annotations

from graph_agent import patches
from graph_agent.settings import Settings


class Bootstrap:
    """Framework startup coordinator."""

    def __init__(self) -> None:
        self._patched = False
        self._settings: Settings | None = None

    @property
    def settings(self) -> Settings | None:
        """Return loaded settings, if load_settings has been called."""

        return self._settings

    def apply_patches(self) -> None:
        """Startup step 1: apply centralized monkey patches exactly once."""

        if self._patched:
            raise RuntimeError("Bootstrap.apply_patches() called twice")
        patches.apply_all()
        self._patched = True

    def load_settings(self, env_overrides: dict[str, str] | None = None) -> Settings:
        """Startup step 2: construct explicit Settings from environment."""

        self._settings = Settings.from_env(env_overrides=env_overrides)
        return self._settings


__all__ = ["Bootstrap"]
