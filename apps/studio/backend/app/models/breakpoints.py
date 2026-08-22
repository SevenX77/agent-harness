"""Which nodes a skill stops before.

Studio-side run-time state per skill, kept in ``.workspace/runtime_config.json``
— not skill source, and disposable with the rest of the workspace.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BreakpointList(BaseModel):
    """Every node this skill stops before, sorted.

    Always the whole list, never a delta: a caller told only about the node it
    just touched would have to keep its own copy of the rest, which is a second
    truth about the same thing.
    """

    model_config = ConfigDict(extra="forbid")

    node_ids: list[str] = Field(default_factory=list)
