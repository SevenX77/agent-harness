"""V0.3.0 state and IO mapping helpers."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload
from graph_agent.runtime.state import BlackboardData, BlackboardState, normalize_blackboard_data


def schema_properties(schema: dict[str, Any] | None) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return set()
    return {key for key in properties if isinstance(key, str)}


def filter_runtime_inputs(
    raw_inputs: dict[str, Any],
    schema: dict[str, Any] | None,
) -> dict[str, Any]:
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
    phase_id: str = "unknown"

    def build_phase_input(self, state: BlackboardState) -> BlackboardState:
        data = normalize_blackboard_data(state.get("data"))
        phase_outputs = deepcopy(data["phase_outputs"])
        phase_state: BlackboardState = {
            "data": {
                "inputs": filter_runtime_inputs(
                    _phase_local_inputs(data["inputs"], phase_outputs),
                    self.input_schema,
                ),
                "phase_outputs": phase_outputs,
                "scratch": {},
            },
            "flow": deepcopy(state.get("flow", {})),
            "messages": [],
            "run_id": state.get("run_id"),
        }
        return phase_state

    def wrap_phase_output(self, output: dict[str, Any]) -> dict[str, Any]:
        data = output.get("data")
        if not isinstance(data, dict):
            return output
        if any(key in data for key in ("inputs", "phase_outputs", "scratch")):
            normalized = normalize_blackboard_data(data)
            if normalized["inputs"]:
                detail = "data.inputs is read-only"
                raise GraphAgentFatalError(
                    detail,
                    payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
                )
            return {**output, "data": normalized}
        allowed = schema_properties(self.output_schema)
        if allowed:
            invalid = sorted(key for key in data if key not in allowed)
            if invalid:
                detail = "phase wrote undeclared keys: " + ", ".join(invalid)
                raise GraphAgentFatalError(
                    detail,
                    payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
                )
        return {
            **output,
            "data": {
                "inputs": {},
                "phase_outputs": {self.phase_id: dict(data)},
                "scratch": {},
            },
        }


def _phase_local_inputs(
    raw_inputs: dict[str, Any],
    phase_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    inputs = dict(raw_inputs)
    for output in phase_outputs.values():
        for key, value in output.items():
            inputs.setdefault(key, value)
    return inputs


def phase_output(data: dict[str, Any], phase_id: str) -> BlackboardData:
    if "inputs" in data:
        detail = "data.inputs is read-only"
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
        )
    return {"inputs": {}, "phase_outputs": {phase_id: dict(data)}, "scratch": {}}


def phase_inputs_from_state(state: BlackboardState) -> dict[str, Any]:
    return normalize_blackboard_data(state.get("data"))["inputs"]


def phase_outputs_from_state(state: BlackboardState) -> dict[str, dict[str, Any]]:
    return normalize_blackboard_data(state.get("data"))["phase_outputs"]


def scratch_from_state(state: BlackboardState) -> dict[str, Any]:
    return normalize_blackboard_data(state.get("data"))["scratch"]


def ensure_no_input_write(data: dict[str, Any]) -> None:
    if "inputs" in data:
        detail = "data.inputs is read-only"
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
        )


@dataclass(frozen=True)
class PhaseWrapper:
    """Common wrapper used by Agent, LOGIC, SUBGRAPH and builtin runtime nodes."""

    mapper: StateMapper
    node_kind: str = "unknown"

    def wrap(
        self,
        node: Callable[[BlackboardState], dict[str, Any]],
    ) -> Callable[[BlackboardState], dict[str, Any]]:
        if getattr(node, "__graph_agent_phase_wrapped__", False):
            wrapped_kind = getattr(node, "__graph_agent_phase_node_kind__", "unknown")
            detail = f"double-wrap rejected: {wrapped_kind} node is already wrapped"
            raise GraphAgentFatalError(
                detail,
                payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
            )

        def _wrapped(state: BlackboardState) -> dict[str, Any]:
            try:
                result = node(self.mapper.build_phase_input(state))
                return self.mapper.wrap_phase_output(result)
            except GraphAgentFatalError:
                raise
            except Exception as exc:  # noqa: BLE001
                detail = str(exc)
                raise GraphAgentFatalError(
                    detail,
                    payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
                ) from exc

        wrapped_attrs = cast(Any, _wrapped)
        wrapped_attrs.__graph_agent_phase_wrapped__ = True
        wrapped_attrs.__graph_agent_phase_node_kind__ = self.node_kind
        return _wrapped


@dataclass(frozen=True)
class ReaderSandboxState:
    """Isolated state envelope for builtin reference reader execution."""

    skill_id: str
    phase_id: str
    root: Path
    references: list[dict[str, Any]] | None = None
    max_output_tokens: int = 3000
    language: str = "zh"
    timeout_s: int = 60

    def to_blackboard(self) -> BlackboardState:
        return {
            "data": {
                "inputs": {
                    "skill_id": self.skill_id,
                    "phase_id": self.phase_id,
                    "references": list(self.references or []),
                    "max_output_tokens": self.max_output_tokens,
                    "language": self.language,
                    "timeout_s": self.timeout_s,
                },
                "phase_outputs": {},
                "scratch": {},
            },
            "flow": {"timeout_s": self.timeout_s},
            "messages": [],
            "run_id": None,
        }


__all__ = [
    "PhaseWrapper",
    "ReaderSandboxState",
    "StateMapper",
    "ensure_no_input_write",
    "filter_runtime_inputs",
    "phase_inputs_from_state",
    "phase_output",
    "phase_outputs_from_state",
    "schema_properties",
    "scratch_from_state",
]
