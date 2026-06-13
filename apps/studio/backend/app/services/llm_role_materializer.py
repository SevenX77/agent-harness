"""Studio Role authoring to gateway fallback-chain materialization."""

from __future__ import annotations

from app.core.adapters.gateway import GatewayAdapter
from app.models.llm_config import (
    LLMCredentialsFile,
    ModelBundle,
    RoleEntry,
)
from app.services.llm_health_store import SqliteLlmHealthStore


def materialize_role(
    role: RoleEntry,
    credentials: LLMCredentialsFile,
    health_store: SqliteLlmHealthStore,
) -> RoleEntry:
    """Generate a gateway-compatible fallback chain and report from Role authoring."""
    adapter = GatewayAdapter(transport="in_process")
    return adapter.materialize_role(
        {
            "role": role,
            "credentials": credentials,
            "health_store": health_store,
        }
    )


def materialize_model_bundle(
    bundle: ModelBundle,
    credentials: LLMCredentialsFile,
    health_store: SqliteLlmHealthStore,
) -> ModelBundle:
    """Generate a flat route chain for a user-authored model bundle."""
    adapter = GatewayAdapter(transport="in_process")
    return adapter.materialize_model_bundle(
        {
            "bundle": bundle,
            "credentials": credentials,
            "health_store": health_store,
        }
    )
