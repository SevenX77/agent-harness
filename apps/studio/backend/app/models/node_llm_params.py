"""Node-level LLM generation-param overrides.

Node overrides are opt-in. ``enabled=False`` means the node inherits the role
settings entirely. When enabled, ``None`` still means "inherit this field from
the role". Overrides are Studio-side per skill+node state, not ``SKILL.md`` or
``llm_roles.yaml`` config truth.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NodeLlmParams(BaseModel):
    """Per-node override of the three role-level generation params."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    thinking: bool | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0)

    def is_empty(self) -> bool:
        """True when the node should not carry an override entry."""
        return not self.enabled


class NodeLlmParamsMap(BaseModel):
    """GET response: node id -> active override."""

    model_config = ConfigDict(extra="forbid")

    nodes: dict[str, NodeLlmParams] = Field(default_factory=dict)
