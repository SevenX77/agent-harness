"""Unified graph-agent WorkflowState state and IO mapping helpers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from graph_agent.callbacks.events import PhaseOutcome
from graph_agent.core.edge_transition import active_phase_execution_id
from graph_agent.core.exceptions import GraphAgentFatalError, make_error_payload
from graph_agent.core.state import (
    BusinessData,
    FrameworkState,
    WorkflowState,
    coerce_business_data,
)

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


def _is_object_schema(schema: dict[str, Any]) -> bool:
    """True when a property subschema describes an object (so its own ``required``
    applies to the value's members)."""
    schema_type = schema.get("type")
    if schema_type == "object" or (isinstance(schema_type, list) and "object" in schema_type):
        return True
    return isinstance(schema.get("properties"), dict)


def _missing_required_inputs(
    filtered: dict[str, Any],
    schema: dict[str, Any] | None,
) -> list[str]:
    """Declared-required input fields — at EVERY object nesting level — absent
    from the sliced blackboard.

    ``required`` is walked recursively: a present object property whose subschema
    declares its own ``required`` has those sub-fields checked too, reported as a
    dotted path (``chapter.aa_number``). A nested required only bites when its
    parent object is present (standard JSON-Schema semantics) — an absent optional
    object is not a violation. This makes the input gate enforce the SAME
    required contract the output side's Draft2020 validator already enforces at
    every level (compile-rules §2.3 slice row), instead of only the top level.
    """
    return _missing_required_paths(filtered, schema, prefix="")


def _missing_required_paths(
    data: Any,
    schema: dict[str, Any] | None,
    *,
    prefix: str,
) -> list[str]:
    if not isinstance(schema, dict):
        return []
    data_map: dict[str, Any] = data if isinstance(data, dict) else {}
    missing: list[str] = []
    required = schema.get("required")
    if isinstance(required, list):
        for name in required:
            if isinstance(name, str) and name not in data_map:
                missing.append(prefix + name)
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for name, subschema in properties.items():
            if not isinstance(name, str) or name not in data_map:
                continue
            if isinstance(subschema, dict) and _is_object_schema(subschema):
                missing.extend(
                    _missing_required_paths(data_map[name], subschema, prefix=f"{prefix}{name}.")
                )
    return sorted(missing)


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
    #: Predict-only escape hatch. Called with (phase_id, message) when an author
    #: validator rejects the phase output; returning True means the caller took
    #: responsibility for the rejection (recorded it) and the flight continues on
    #: the unvalidated output. Absent or returning False keeps the failure fatal,
    #: which is the real-run contract.
    validator_downgrade_hook: Callable[[str, str], bool] | None = None

    def build_phase_input(self, state: WorkflowState) -> WorkflowState:
        """Filter global business data to only what is declared in the input schema."""
        data_obj = coerce_business_data(state.get("data"))
            
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

        # MVP1 contract (compile-rules §2.3): a declared-required input field
        # missing from the blackboard is a mapping failure, not a silent drop —
        # running the phase on partial input would produce an untraceable state.
        missing = _missing_required_inputs(filtered, self.input_schema)
        if missing:
            _phase_mapping_fatal(
                "phase required input fields missing from blackboard: " + ", ".join(missing),
                code="[F-v3-runtime-state-mapping-failed]",
                phase_id=self.phase_id,
                field_path=missing[0],
            )

        return WorkflowState(
            data=BusinessData.model_validate(filtered),
            # A phase plans for itself. `working_memory` holds one phase's own
            # notes — PLANNING_NUDGE asks the model to write down "本阶段的目标"
            # — so handing it the previous phase's notes lets an upstream plan
            # answer a downstream phase's planning gate: ExitControl's
            # `_working_memory_has_plan` only asks whether the key `plan` is
            # present, while its neighbour `_own_finish_payload` thirty lines up
            # already qualifies the same cross-boundary shape by phase name.
            # A phase that only talks then loses the planning nudge it had
            # earned and gets the generic one instead.
            #
            # Excavating an earlier phase is `read_artifact`'s job ("an earlier
            # phase's named output"); `query_working_memory` reads back "the
            # plan text recorded by update_working_memory" — its own. Emptying
            # the slot is what makes that docstring true.
            #
            # Input only, like `messages` below. The flow channel merges
            # `working_memory` per key (`_FLOW_DICT_MERGE_FIELDS`), so an
            # untouched empty slot unions to a no-op and a recorded plan
            # overwrites just `plan` — the iterate bookkeeping written into the
            # same dict by `_with_graph_iterate_signal` survives both.
            flow=flow_obj.model_copy(update={"working_memory": {}}),
            # A phase opens its own conversation. Round 8 of the nine-round
            # finalization ruled it directly — "phase 间默认强隔离(`messages = []`
            # by-design)+ 按需挖掘机制(context_access opt-in)" — and the opt-in
            # half is already live in `_cognitive_framework_tools`; this is the
            # default half, which had never been wired.
            #
            # The blackboard is what carries data between phases: a phase states
            # what it consumes in `io.inputs` and gets exactly that, filtered
            # right above. Handing it the previous phase's transcript as well
            # adds a second, undeclared inlet — one that three middlewares then
            # read as this phase's own traffic (LoopDetection's window,
            # ExecutionControl's dead-end scan, Compaction's token count), and
            # that delivers another phase's nudges and loop diagnostics as if
            # they were instructions to this one.
            #
            # This is the phase's INPUT only. `wrap_phase_output` still merges
            # whatever the phase produced back into the global channel, so the
            # run-level transcript, the checkpoint and HITL resume are unchanged.
            messages=[],
        )

    def wrap_phase_output(
        self,
        state: WorkflowState,
        updates: dict[str, Any] | WorkflowState,
        *,
        state_slice: dict[str, Any] | None = None,
        validator: PhaseValidator | None = None,
        validator_error_code: str | None = None,
    ) -> dict[str, Any]:
        """Validate updates against the output schema and return a channel delta.

        The delta holds only this phase's declared output fields (plus its
        `phase_outputs` entry and a flow delta). Returning deltas instead of
        the merged full state is what lets parallel phases in one superstep
        fold through the reducer channels instead of colliding (decision doc
        2026-08-15 engine-parallel-fanout-state-channels).
        """
        data_obj = coerce_business_data(state.get("data"))
            
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
            return {"data": {"phase_outputs": {self.phase_id: {}}}, "flow": {"current_phase": self.phase_id}, "messages": []}

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
                downgrade_hook=self.validator_downgrade_hook,
            )

        # Business fields must not use the framework _ prefix (same rule
        # StateManager.update_business enforces on the merge path).
        for key in updates_dict:
            if key.startswith("_"):
                raise ValueError(
                    f"BusinessData 不允许 _ 前缀字段: '{key}' (框架元字段必须用 update_framework)"
                )

        # Data delta: this phase's declared outputs plus its phase_outputs
        # entry (D7 per-node golden). Simple linear / agent / logic / subgraph /
        # reference phases route through wrap_phase_output exclusively;
        # batch/iterate/loop phases populate phase_outputs via
        # graph_assembler's delta helpers instead — mutually exclusive per
        # phase, so no double write. The reducer dict-merges phase_outputs per
        # phase key, so parallel branches each keep their own entry.
        data_delta: dict[str, Any] = dict(updates_dict)
        data_delta["phase_outputs"] = {self.phase_id: dict(updates_dict)}

        # Flow delta: a full FrameworkState from the node is diffed against
        # the pre-phase flow so only actual changes travel; dict deltas pass
        # through. current_phase is always this phase.
        flow_updates = updates.get("flow", {})
        flow_delta: dict[str, Any]
        if isinstance(flow_updates, FrameworkState):
            before_flow = state["flow"].model_dump()
            after_flow = flow_updates.model_dump()
            flow_delta = {
                key: value
                for key, value in after_flow.items()
                if before_flow.get(key) != value
            }
        elif isinstance(flow_updates, dict):
            flow_delta = dict(flow_updates)
        else:
            flow_delta = {}
        flow_delta["current_phase"] = self.phase_id
        # This phase execution's own identity, for the transitions leaving it:
        # a downstream fan-in reads its predecessors' entries instead of
        # inferring one upstream from ``current_phase``. Per-key merged on the
        # flow channel, so parallel siblings never overwrite each other.
        execution_id = active_phase_execution_id()
        if execution_id:
            flow_delta["phase_execution_ids"] = {self.phase_id: [execution_id]}

        messages_updates = updates.get("messages", [])
        return {
            "data": data_delta,
            "flow": flow_delta,
            "messages": list(messages_updates) if messages_updates else [],
        }


def _with_optional_fields_nullable(schema: Any) -> Any:
    """The finish gate's truth condition, applied to the raw schema.

    The gate's Pydantic projection deliberately makes every non-required field
    nullable (`schema_engine._optional_annotation`), so a payload carrying
    `optional_field: null` passes it. This validator judges the SAME payload;
    judging it by the raw schema — where `{type: string}` rejects null — killed
    submissions the gate had already accepted (run 2026-08-19T05-21-45_3aca03a5,
    phase `foreshadow`: accepted, phase_end, then fatal on
    `resolves_foreshadowing_id: None is not of type 'string'`). One schema, one
    truth condition: optional properties get the same null-tolerance here.
    Required fields keep the raw strictness — the gate has no
    `_optional_annotation` for them either.
    """
    if not isinstance(schema, dict):
        return schema
    transformed = dict(schema)
    properties = transformed.get("properties")
    if isinstance(properties, dict):
        required_names = set(transformed.get("required") or [])
        new_properties: dict[str, Any] = {}
        for name, prop_schema in properties.items():
            prop = _with_optional_fields_nullable(prop_schema)
            if name not in required_names and isinstance(prop, dict):
                prop = {"anyOf": [prop, {"type": "null"}]}
            new_properties[name] = prop
        transformed["properties"] = new_properties
    items = transformed.get("items")
    if isinstance(items, dict):
        transformed["items"] = _with_optional_fields_nullable(items)
    return transformed


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
    errors = sorted(
        Draft202012Validator(_with_optional_fields_nullable(schema)).iter_errors(updates),
        key=str,
    )
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
    downgrade_hook: Callable[[str, str], bool] | None = None,
) -> dict[str, Any]:
    try:
        result = validator(dict(output), dict(state_slice), phase_name=phase_id)
    except Exception as exc:  # noqa: BLE001 - user validator failures become runtime contract errors
        detail = f"phase validator failed: {type(exc).__name__}: {exc}"
        if downgrade_hook is not None and downgrade_hook(phase_id, detail):
            # Predict flying on a P2 placeholder stub: the validator judges
            # semantics the stub cannot have, so its rejection says nothing about
            # the skill. The hook recorded it; keep flying on the stub output.
            return dict(output)
        _phase_mapping_fatal(
            detail,
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


class PhaseLifecycle(Protocol):
    """Told when one phase execution opens and how it ended.

    The wrapper knows where an execution begins and ends — nothing else does,
    because building the phase input, running the node and checking the declared
    output contract are all inside it — but it has no business deciding what the
    host announces at those boundaries. So it reports, and the host emits.

    ``opened`` hands back the execution's identity and ``ended`` takes it back.
    Carrying the identity through a local of the running call is what keeps two
    concurrent executions of one phase (a fan-out, an ``iterate`` item) from
    swapping ends; an identity kept on the reporter would be shared by both.
    """

    def opened(self, phase_input: WorkflowState) -> str:
        """Announce the execution that is starting; return its identity."""
        ...

    def ended(
        self,
        execution_id: str,
        phase_input: WorkflowState,
        result: Any,
        *,
        status: PhaseOutcome,
    ) -> None:
        """Announce how the execution named by ``execution_id`` ended."""
        ...


@dataclass(frozen=True)
class PhaseWrapper:
    """Common wrapper used by Agent, LOGIC, SUBGRAPH and builtin runtime nodes."""

    mapper: StateMapper
    node_kind: str = "unknown"
    validator: PhaseValidator | None = None
    validator_error_code: str | None = None
    #: Who to tell that this phase execution opened and how it ended. ``None``
    #: for the runtime nodes the host does not announce (the builtin reference
    #: reader), which is every construction site that leaves it out.
    lifecycle: PhaseLifecycle | None = None

    def wrap(
        self,
        node: Callable[[WorkflowState], dict[str, Any] | WorkflowState],
    ) -> Callable[[WorkflowState], dict[str, Any]]:
        if getattr(node, "__graph_agent_phase_wrapped__", False):
            wrapped_kind = getattr(node, "__graph_agent_phase_node_kind__", "unknown")
            detail = f"double-wrap rejected: {wrapped_kind} node is already wrapped"
            raise GraphAgentFatalError(
                detail,
                payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
            )

        def _wrapped(state: WorkflowState) -> dict[str, Any]:
            lifecycle = self.lifecycle
            execution_id: str | None = None
            phase_input: WorkflowState | None = None
            result: Any = None
            # Failed until the phase gets all the way through, which includes
            # its output surviving the validator: a phase that reported
            # ``completed`` and then died in ``wrap_phase_output`` is exactly
            # the run that made this field necessary (E17).
            status: PhaseOutcome = "failed"
            try:
                # Prepare filtered type-safe inputs
                phase_input = self.mapper.build_phase_input(state)
                if lifecycle is not None:
                    execution_id = lifecycle.opened(phase_input)
                # Execute the phase node
                result = node(phase_input)
                # Map outputs type-safely back to WorkflowState
                mapped = self.mapper.wrap_phase_output(
                    state,
                    result,
                    state_slice=phase_input["data"].model_dump(),
                    validator=self.validator,
                    validator_error_code=self.validator_error_code,
                )
                status = "completed"
                return mapped
            except GraphAgentFatalError:
                raise
            except Exception as exc:
                detail = str(exc)
                raise GraphAgentFatalError(
                    detail,
                    payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", detail),
                ) from exc
            finally:
                # An execution that opened always closes, however it went: a
                # phase whose end frame never arrives leaves its node running
                # forever on the canvas. An input that never built opened
                # nothing, so there is nothing to close.
                if lifecycle is not None and execution_id is not None and phase_input is not None:
                    lifecycle.ended(execution_id, phase_input, result, status=status)

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
    "PhaseLifecycle",
    "PhaseWrapper",
    "ReaderSandboxState",
    "StateMapper",
    "filter_runtime_inputs",
    "phase_inputs_from_state",
    "phase_outputs_from_state",
    "schema_properties",
    "scratch_from_state",
]
