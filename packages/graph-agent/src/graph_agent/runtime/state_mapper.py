"""V0.3.0 state and IO mapping helpers."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from graph_agent.core.exceptions import GraphAgentFatalError
from graph_agent.runtime.state import BlackboardState


def schema_properties(schema: dict[str, Any] | None) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    return {key for key in properties if isinstance(key, str)}


def filter_runtime_inputs(raw_inputs: dict[str, Any], schema: dict[str, Any] | None) -> dict[str, Any]:
    """Filter raw graph inputs to the declared inline input schema keys."""

    keys = schema_properties(schema)
    if not keys:
        return dict(raw_inputs)
    return {key: raw_inputs[key] for key in keys if key in raw_inputs}


@dataclass(frozen=True)
class StateMapper:
    """Build phase-local state slices and validate phase output keys."""

    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    def build_phase_input(self, state: BlackboardState) -> BlackboardState:
        phase_state: BlackboardState = {
            "data": filter_runtime_inputs(dict(state.get("data", {})), self.input_schema),
            "flow": deepcopy(state.get("flow", {})),
            "messages": list(state.get("messages", [])),
            "run_id": state.get("run_id"),
        }
        return phase_state

    def wrap_phase_output(self, output: dict[str, Any]) -> dict[str, Any]:
        data = output.get("data")
        if not isinstance(data, dict):
            return output
        allowed = schema_properties(self.output_schema)
        if not allowed:
            return output
        if len(data) == 1:
            nested = next(iter(data.values()))
            if isinstance(nested, dict) and set(nested).issubset(allowed):
                return output
        invalid = sorted(key for key in data if key not in allowed)
        if invalid:
            raise GraphAgentFatalError(
                "[F-v3-runtime-state-mapping-failed] phase wrote undeclared keys: "
                + ", ".join(invalid)
            )
        return output


@dataclass(frozen=True)
class PhaseWrapper:
    """Common wrapper used by Agent, LOGIC and SUBGRAPH runtime nodes."""

    mapper: StateMapper

    def wrap(self, node: Callable[[BlackboardState], dict[str, Any]]) -> Callable[[BlackboardState], dict[str, Any]]:
        def _wrapped(state: BlackboardState) -> dict[str, Any]:
            try:
                result = node(self.mapper.build_phase_input(state))
                return self.mapper.wrap_phase_output(result)
            except GraphAgentFatalError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise GraphAgentFatalError(
                    f"[F-v3-runtime-state-mapping-failed] {exc}"
                ) from exc

        return _wrapped


@dataclass(frozen=True)
class ReaderSandboxState:
    """Isolated state envelope for builtin reference reader execution."""

    skill_id: str
    phase_id: str
    root: Path
    timeout_s: int = 60

    def to_blackboard(self) -> BlackboardState:
        return {
            "data": {"skill_id": self.skill_id, "phase_id": self.phase_id},
            "flow": {"timeout_s": self.timeout_s},
            "messages": [],
            "run_id": None,
        }


__all__ = [
    "PhaseWrapper",
    "ReaderSandboxState",
    "StateMapper",
    "filter_runtime_inputs",
    "schema_properties",
]
