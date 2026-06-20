"""N4 atom #33: schema -> empty golden template for an agent node (create-path B).

For an agent node without golden, generate a structure-valid empty template from the
node's ``io.outputs`` JSON schema so the author can hand-fill expected values without a
copilot/run source. The schema resolution and the heuristic stub both live in the
engine; this service only orchestrates them through the allowlisted ``engine`` adapter
boundary (no direct SDK import — the import-boundary guard forbids it for services).
"""

from __future__ import annotations

import logging

from app.core.adapters.engine import generate_heuristic_stub
from app.core.adapters.transport_factory import build_engine_adapter
from app.core.exceptions import error_response, raise_error_response
from app.models.golden import GoldenTemplate
from app.services.skills import resolve_skill_dir

logger = logging.getLogger(__name__)


def generate_golden_template(skill_id: str, node_id: str) -> GoldenTemplate:
    """Resolve an agent node's output schema and emit a schema-valid empty template."""
    logger.info("golden_template action=start skill_id=%s node_id=%s", skill_id, node_id)
    skill_dir = resolve_skill_dir(skill_id)
    adapter = build_engine_adapter()
    output_schema = adapter.resolve_agent_node_output_schema(str(skill_dir), node_id)
    if output_schema is None:
        logger.warning(
            "golden_template decision=reject skill_id=%s node_id=%s reason=not_agent_node_or_no_schema",
            skill_id,
            node_id,
        )
        raise_error_response(
            error_response(
                error_code="golden.template_node_unavailable",
                http_status=422,
                message=f"No agent-node output schema for golden template: {node_id}",
                details={"skill_id": skill_id, "node_id": node_id},
                retry_strategy="not_retryable",
            )
        )
    template = generate_heuristic_stub(output_schema)
    logger.info(
        "golden_template action=end skill_id=%s node_id=%s template_keys=%s",
        skill_id,
        node_id,
        sorted(template.keys()),
    )
    return GoldenTemplate(
        skill_id=skill_id,
        node_id=node_id,
        schema=output_schema,  # alias for output_schema (populate_by_name)
        template=template,
    )


__all__ = ["generate_golden_template"]
