"""Studio wiring for the graph-agent gateway model resolver."""

from __future__ import annotations

from pathlib import Path

from graph_agent_gateway.resolver import ModelResolver

from app.core import config
from app.models.llm_config import RolesData
from app.services.llm_credentials import load_credentials
from app.services.llm_roles import load_roles_file

ROLES_PATH = config.REPO_ROOT / "config" / "llm_roles.yaml"


def build_gateway_model_resolver(roles_path: Path = ROLES_PATH) -> ModelResolver:
    """Build a fresh resolver from Studio-owned v4/v2 registry data."""

    credentials = load_credentials()
    roles = load_roles_file(roles_path) if roles_path.exists() else RolesData()
    return ModelResolver(registry_snapshot=roles.to_registry_snapshot(credentials))
