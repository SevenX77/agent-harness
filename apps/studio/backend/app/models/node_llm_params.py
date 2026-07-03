"""Node-level LLM generation-param overrides (PR3).

The three role-level generation params (``thinking`` / ``max_output_tokens`` /
``temperature``) may be overridden per node directly — no enable switch, an unset
field means "inherit the role value". Overrides are NOT skill source (llm params
are gateway-domain config truth; SKILL.md only holds symbolic references), so
they persist in the Studio backend keyed by ``skill + phase``, mirroring the
compare-candidates store. The run-time resolver seam that applies these is wired
by the orchestrator; this module is only the model.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NodeLlmParams(BaseModel):
    """Per-node override of the three role-level generation params.

    Every field is optional; ``None`` means "inherit the role value". A node
    whose params are all ``None`` carries no override and is not persisted."""

    model_config = ConfigDict(extra="forbid")

    thinking: bool | None = None
    max_output_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0)

    def is_empty(self) -> bool:
        """True when no param is set (all-null → no override to persist)."""
        return (
            self.thinking is None
            and self.max_output_tokens is None
            and self.temperature is None
        )


class NodeLlmParamsMap(BaseModel):
    """GET response: node id -> its override (only nodes with an override)."""

    model_config = ConfigDict(extra="forbid")

    nodes: dict[str, NodeLlmParams] = Field(default_factory=dict)
