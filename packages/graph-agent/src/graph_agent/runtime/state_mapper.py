"""Unified graph-agent WorkflowState state and IO mapping helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload
from graph_agent.core.state import BusinessData, FrameworkState, StateManager, WorkflowState

logger = logging.getLogger(__name__)
PhaseValidator = Callable[..., dict[str, Any] | None]

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


def _project_full_data_to_phase_updates(
    after_data: dict[str, Any],
    before_data: dict[str, Any],
    output_schema: dict[str, Any] | None,
    phase_id: str,
) -> dict[str, Any]:
    phase_outputs = after_data.get("phase_outputs")
    if isinstance(phase_outputs, dict):
        own_outputs = phase_outputs.get(phase_id)
        if isinstance(own_outputs, dict):
            return dict(own_outputs)

    output_keys = schema_properties(output_schema)
    if output_keys:
        return {key: after_data[key] for key in output_keys if key in after_data}

    return {
        key: value
        for key, value in after_data.items()
        if key != "phase_outputs" and before_data.get(key) != value
    }


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

    def wrap_phase_output(
        self,
        state: WorkflowState,
        updates: dict[str, Any] | WorkflowState,
        *,
        state_slice: dict[str, Any] | None = None,
        validator: PhaseValidator | None = None,
        validator_error_code: str | None = None,
    ) -> WorkflowState:
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
        before_data = data_obj.model_dump()

        is_workflow_state = (
            isinstance(updates, dict)
            and "data" in updates
            and "flow" in updates
            and "messages" in updates
            and not isinstance(updates.get("data"), dict)
        )
        if is_workflow_state:
            workflow_updates = cast(WorkflowState, updates)
            after_data = workflow_updates["data"].model_dump()
            updates = {
                "data": _project_full_data_to_phase_updates(
                    after_data,
                    before_data,
                    self.output_schema,
                    self.phase_id,
                ),
                "flow": workflow_updates["flow"],
                "messages": workflow_updates["messages"],
            }

        if not isinstance(updates, dict):
            return state

        # Extract only data/business updates
        updates_dict = updates.get("data", {}) if "data" in updates else {k: v for k, v in updates.items() if k not in ("flow", "messages")}
        if not isinstance(updates_dict, dict):
            updates_dict = {}

        if "phase_outputs" in updates_dict or "inputs" in updates_dict:
            flat_updates = {}
            if "phase_outputs" in updates_dict and isinstance(updates_dict["phase_outputs"], dict):
                own_outputs = updates_dict["phase_outputs"].get(self.phase_id)
                if isinstance(own_outputs, dict):
                    flat_updates.update(own_outputs)
                elif schema_properties(self.output_schema):
                    flat_updates.update(
                        {
                            key: updates_dict[key]
                            for key in schema_properties(self.output_schema)
                            if key in updates_dict
                        }
                    )
                else:
                    for p_val in updates_dict["phase_outputs"].values():
                        if isinstance(p_val, dict):
                            flat_updates.update(p_val)
            if not flat_updates and "inputs" in updates_dict and isinstance(updates_dict["inputs"], dict):
                flat_updates.update(updates_dict["inputs"])
            updates_dict = flat_updates

        _validate_phase_updates_against_schema(
            updates_dict,
            self.output_schema,
            code="[F-v3-runtime-state-mapping-failed]",
            phase_id=self.phase_id,
        )

        if validator is not None:
            updates_dict = _run_phase_validator(
                validator,
                output=updates_dict,
                state_slice=state_slice or {},
                phase_id=self.phase_id,
                output_schema=self.output_schema,
                code=validator_error_code or "[F-v3-agent-validator-failed]",
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


def _validate_phase_updates_against_schema(
    updates: dict[str, Any],
    schema: dict[str, Any] | None,
    *,
    code: str,
    phase_id: str,
) -> None:
    allowed = schema_properties(schema)
    if allowed:
        invalid = sorted(key for key in updates if key not in allowed)
        if invalid:
            _phase_mapping_fatal(
                "phase wrote undeclared keys: " + ", ".join(invalid),
                code=code,
                phase_id=phase_id,
                field_path=invalid[0],
            )
    if not isinstance(schema, dict) or not schema:
        return
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        _phase_mapping_fatal(
            f"phase output schema invalid: {exc.message}",
            code=code,
            phase_id=phase_id,
        )
    errors = sorted(Draft202012Validator(schema).iter_errors(updates), key=str)
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or None
        _phase_mapping_fatal(
            f"phase output schema validation failed: {first.message}",
            code=code,
            phase_id=phase_id,
            field_path=path,
        )


def _run_phase_validator(
    validator: PhaseValidator,
    *,
    output: dict[str, Any],
    state_slice: dict[str, Any],
    phase_id: str,
    output_schema: dict[str, Any] | None,
    code: str,
) -> dict[str, Any]:
    try:
        result = validator(dict(output), dict(state_slice), phase_name=phase_id)
    except Exception as exc:  # noqa: BLE001 - user validator failures become runtime contract errors
        _phase_mapping_fatal(
            f"phase validator failed: {type(exc).__name__}: {exc}",
            code=code,
            phase_id=phase_id,
        )
    if result is None:
        return dict(output)
    if not isinstance(result, dict):
        _phase_mapping_fatal(
            f"phase validator returned {type(result).__name__}, expected None or dict",
            code=code,
            phase_id=phase_id,
        )
    _validate_phase_updates_against_schema(
        result,
        output_schema,
        code=code,
        phase_id=phase_id,
    )
    return dict(result)


def _phase_mapping_fatal(
    detail: str,
    *,
    code: str,
    phase_id: str,
    field_path: str | None = None,
) -> None:
    raise GraphAgentFatalError(
        detail,
        payload=make_error_payload(
            code,
            detail,
            phase_id=phase_id,
            field_path=field_path,
        ),
    )


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
    validator: PhaseValidator | None = None
    validator_error_code: str | None = None

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
                return self.mapper.wrap_phase_output(
                    state,
                    result,
                    state_slice=phase_input["data"].model_dump(),
                    validator=self.validator,
                    validator_error_code=self.validator_error_code,
                )
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
