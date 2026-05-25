"""Studio wiring for the graph-agent gateway model resolver."""

from __future__ import annotations

from pathlib import Path

from graph_agent_gateway.resolver import ModelResolver

from app.core import config
from app.services.llm_credentials import credentials_path

ROLES_PATH = config.REPO_ROOT / "config" / "llm_roles.yaml"


def build_gateway_model_resolver(roles_path: Path = ROLES_PATH) -> ModelResolver:
    """Build a fresh resolver from Studio's v4/v2 LLM registry files."""

    return ModelResolver(
        credentials_path=credentials_path(),
        roles_path=roles_path,
    )
