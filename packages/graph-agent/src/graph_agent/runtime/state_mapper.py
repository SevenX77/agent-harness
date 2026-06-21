"""Unified graph-agent WorkflowState state and IO mapping helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload
from graph_agent.core.state import BusinessData, FrameworkState, StateManager, WorkflowState

logger = logging.getLogger(__name__)

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
    """Filter raw inputs to the declared inline input schema keys."""
    keys = schema_properties(schema)
    if not keys:
        return dict(raw_inputs)
    return {key: raw_inputs[key] for key in keys if key in raw_inputs}


@dataclass(frozen=True)
class StateMapper:
    """Build phase-local state slices and validate phase output keys for WorkflowState."""

    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    phase_id: str = "unknown"

    def build_phase_input(self, state: WorkflowState) -> WorkflowState:
        """Filter global business data to only what is declared in the input schema."""
        data_obj = state.get("data")
        if isinstance(data_obj, dict):
            if "inputs" in data_obj or "phase_outputs" in data_obj:
                flat_data = {}
                if "inputs" in data_obj and isinstance(data_obj["inputs"], dict):
                    flat_data.update(data_obj["inputs"])
                if "phase_outputs" in data_obj and isinstance(data_obj["phase_outputs"], dict):
                    for p_val in data_obj["phase_outputs"].values():
                        if isinstance(p_val, dict):
                            flat_data.update(p_val)
                data_obj = BusinessData.model_validate(flat_data)
            else:
                data_obj = BusinessData.model_validate(data_obj)
        elif data_obj is None:
            data_obj = BusinessData()
            
        flow_obj = state.get("flow")
        if isinstance(flow_obj, dict):
            flow_obj = FrameworkState.model_validate(flow_obj)
        elif flow_obj is None:
            flow_obj = FrameworkState()

        raw_data = data_obj.model_dump()
        # phase_outputs is a reserved meta-accumulator (D7 per-node golden), not a
        # business input field. Strip it so it is never passed to a node and so a
        # parent's phase_outputs cannot leak into a child subgraph (whose input
        # schema may be empty/open) and corrupt the child's own accumulation.
        raw_data.pop("phase_outputs", None)
        filtered = filter_runtime_inputs(raw_data, self.input_schema)

        return WorkflowState(
            data=BusinessData.model_validate(filtered),
            flow=flow_obj.model_copy(),
            messages=list(state.get("messages", [])),
        )

    def wrap_phase_output(self, state: WorkflowState, updates: dict[str, Any] | WorkflowState) -> WorkflowState:
        """Validate updates against the output schema and merge into WorkflowState."""
        data_obj = state.get("data")
        if isinstance(data_obj, dict):
            if "inputs" in data_obj or "phase_outputs" in data_obj:
                flat_data = {}
                if "inputs" in data_obj and isinstance(data_obj["inputs"], dict):
                    flat_data.update(data_obj["inputs"])
                if "phase_outputs" in data_obj and isinstance(data_obj["phase_outputs"], dict):
                    for p_val in data_obj["phase_outputs"].values():
                        if isinstance(p_val, dict):
                            flat_data.update(p_val)
                data_obj = BusinessData.model_validate(flat_data)
            else:
                data_obj = BusinessData.model_validate(data_obj)
        elif data_obj is None:
            data_obj = BusinessData()
            
        flow_obj = state.get("flow")
        if isinstance(flow_obj, dict):
            flow_obj = FrameworkState.model_validate(flow_obj)
        elif flow_obj is None:
            flow_obj = FrameworkState()

        state = WorkflowState(
            data=data_obj,
            flow=flow_obj,
            messages=list(state.get("messages", [])),
        )

        is_workflow_state = (
            isinstance(updates, dict)
            and "data" in updates
            and "flow" in updates
            and "messages" in updates
            and not isinstance(updates.get("data"), dict)
        )
        if is_workflow_state:
            return cast(WorkflowState, updates)

        if not isinstance(updates, dict):
            return state

        # Extract only data/business updates
        updates_dict = updates.get("data", {}) if "data" in updates else {k: v for k, v in updates.items() if k not in ("flow", "messages")}
        if not isinstance(updates_dict, dict):
            updates_dict = {}

        # Drop the reserved phase_outputs meta-accumulator from a node/subgraph's
        # returned updates: a child graph's internal phase_outputs must not cross the
        # subgraph IO boundary into the parent's business namespace or output-schema
        # validation. The child's declared outputs remain as top-level flat fields,
        # so nothing real is lost; this phase's phase_outputs is re-derived below.
        if "phase_outputs" in updates_dict:
            updates_dict = {k: v for k, v in updates_dict.items() if k != "phase_outputs"}

        if "phase_outputs" in updates_dict or "inputs" in updates_dict:
            flat_updates = {}
            if "phase_outputs" in updates_dict and isinstance(updates_dict["phase_outputs"], dict):
                for p_val in updates_dict["phase_outputs"].values():
                    if isinstance(p_val, dict):
                        flat_updates.update(p_val)
            if "inputs" in updates_dict and isinstance(updates_dict["inputs"], dict):
                flat_updates.update(updates_dict["inputs"])
            updates_dict = flat_updates

        allowed = schema_properties(self.output_schema)
        if allowed:
            invalid = sorted(key for key in updates_dict if key not in allowed)
            if invalid:
                detail = "phase wrote undeclared keys: " + ", ".join(invalid)
                raise GraphAgentFatalError(
                    detail,
                    payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
                )

        # Merge updates type-safely into the business data namespace
        new_state = StateManager.update_business(state, **updates_dict)
        
        # Merge flow updates if present
        flow_updates = updates.get("flow", {})
        if isinstance(flow_updates, FrameworkState):
            new_state = WorkflowState(
                data=new_state["data"],
                flow=flow_updates,
                messages=new_state["messages"],
            )
        elif isinstance(flow_updates, dict) and flow_updates:
            new_state = StateManager.update_framework(new_state, **flow_updates)
            
        # Merge messages updates if present
        messages_updates = updates.get("messages", [])
        if messages_updates:
            new_state = WorkflowState(
                data=new_state["data"],
                flow=new_state["flow"],
                messages=list(messages_updates),
            )

        # Update current phase in framework state
        new_state = StateManager.update_framework(new_state, current_phase=self.phase_id)

        # Record this phase's outputs into the phase_outputs map keyed by phase_id
        # (D7 per-node golden). Simple linear / agent / logic / subgraph / reference
        # phases route through wrap_phase_output exclusively; batch/iterate/loop
        # phases populate phase_outputs via graph_assembler._with_phase_outputs
        # instead — the two sets are mutually exclusive per phase, so no double write.
        # This MUST be the final mutation: phase_outputs is not an output-schema key,
        # so it is written after the schema gate (above) and bypasses the updates
        # flatten path, mirroring _with_phase_outputs' accumulate semantics. An empty
        # phase records an empty entry (consistent with the batch/terminal path).
        existing_outputs = new_state["data"].model_dump().get("phase_outputs")
        merged_outputs = dict(existing_outputs) if isinstance(existing_outputs, dict) else {}
        merged_outputs[self.phase_id] = dict(updates_dict)
        new_state = StateManager.update_business(new_state, phase_outputs=merged_outputs)
        return new_state


def phase_inputs_from_state(state: WorkflowState) -> dict[str, Any]:
    return state["data"].model_dump()


def phase_outputs_from_state(state: WorkflowState) -> dict[str, dict[str, Any]]:
    # Bridge method returning a dictionary mapping the current phase to its business outputs
    phase_id = state["flow"].current_phase or "output"
    return {phase_id: state["data"].model_dump()}


def scratch_from_state(state: WorkflowState) -> dict[str, Any]:
    return state["flow"].working_memory or {}


def ensure_no_input_write(data: dict[str, Any]) -> None:
    # StateManager.update_business prevents _ prefixed writes; we can check if they try to write read-only fields
    pass


@dataclass(frozen=True)
class PhaseWrapper:
    """Common wrapper used by Agent, LOGIC, SUBGRAPH and builtin runtime nodes."""

    mapper: StateMapper
    node_kind: str = "unknown"

    def wrap(
        self,
        node: Callable[[WorkflowState], dict[str, Any] | WorkflowState],
    ) -> Callable[[WorkflowState], WorkflowState]:
        if getattr(node, "__graph_agent_phase_wrapped__", False):
            wrapped_kind = getattr(node, "__graph_agent_phase_node_kind__", "unknown")
            detail = f"double-wrap rejected: {wrapped_kind} node is already wrapped"
            raise GraphAgentFatalError(
                detail,
                payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
            )

        def _wrapped(state: WorkflowState) -> WorkflowState:
            try:
                # Prepare filtered type-safe inputs
                phase_input = self.mapper.build_phase_input(state)
                # Execute the phase node
                result = node(phase_input)
                # Map outputs type-safely back to WorkflowState
                return self.mapper.wrap_phase_output(state, result)
            except GraphAgentFatalError:
                raise
            except Exception as exc:
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

    def to_blackboard(self) -> WorkflowState:
        return WorkflowState(
            data=BusinessData.model_validate({
                "skill_id": self.skill_id,
                "phase_id": self.phase_id,
                "references": list(self.references or []),
                "max_output_tokens": self.max_output_tokens,
                "language": self.language,
                "timeout_s": self.timeout_s,
            }),
            flow=FrameworkState.model_validate({
                "timeout_s": self.timeout_s,
                "current_phase": self.phase_id,
            }),
            messages=[],
        )


__all__ = [
    "PhaseWrapper",
    "ReaderSandboxState",
    "StateMapper",
    "ensure_no_input_write",
    "filter_runtime_inputs",
    "phase_inputs_from_state",
    "phase_outputs_from_state",
    "schema_properties",
    "scratch_from_state",
]
