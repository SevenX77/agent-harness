"""A role, turned into the routes that will be tried for it.

This package is the role domain's whole public contract. Reaching past it into
one of its files couples the caller to where a definition happens to live
today.

Decision: docs/design/2026-08-10-gateway-module-tree-and-probing-decision.md
"""

from __future__ import annotations

from graph_agent_gateway.role.materialization import (
    NO_AVAILABLE_ROUTE,
    MaterializedRole,
    MaterializeRoleRequest,
    materialize_role,
)

__all__ = [
    "NO_AVAILABLE_ROUTE",
    "MaterializeRoleRequest",
    "MaterializedRole",
    "materialize_role",
]
