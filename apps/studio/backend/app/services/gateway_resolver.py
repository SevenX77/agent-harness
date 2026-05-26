"""Studio wiring for the graph-agent gateway model resolver."""

from __future__ import annotations

from pathlib import Path

from graph_agent_gateway.llm_config import RolesData as GatewayRolesData
from graph_agent_gateway.resolver import ModelResolver

from app.core import config
from app.services.llm_roles import load_roles_file

ROLES_PATH = config.REPO_ROOT / "config" / "llm_roles.yaml"


def build_gateway_model_resolver(roles_path: Path = ROLES_PATH) -> ModelResolver:
    """Build a fresh resolver from Studio's persisted LLM role registry."""

    studio_roles = load_roles_file(roles_path)
    gateway_roles = GatewayRolesData.model_validate(
        studio_roles.model_dump(mode="json", exclude={"migration_required"})
    )
    return ModelResolver(roles_data=gateway_roles)
