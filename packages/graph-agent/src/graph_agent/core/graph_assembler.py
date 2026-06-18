"""V2.1 CompiledSkill to LangGraph assembly."""

import asyncio
import contextvars
import copy
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, NoReturn, TypeVar, cast

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import InjectedState

from graph_agent.callbacks.emit import _safe_emit_event
from graph_agent.callbacks.events import (
    BlackboardReduceEvent,
    BuiltinSubagentEnterEvent,
    BuiltinSubagentExitEvent,
    BuiltinSubagentFallbackEvent,
    InputDispatchEvent,
    InputFileInjectedEvent,
    LLMCallEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    ToolCallEvent,
)
from graph_agent.cognitive.critic import (
    CriticVerdict,
    FakeCriticClient,
    LLMCriticClient,
    build_critic_tool,
)
from graph_agent.cognitive.finish_task import build_finish_task_tool
from graph_agent.cognitive.md2json import parse_finish_markdown
from graph_agent.cognitive.md_patch import LLMMdPatchClient
from graph_agent.cognitive.prompt import (
    apply_v030_cognitive_template,
    resolve_role_prefix_from_llm_role,
)
from graph_agent.core.actions import ToolDef, _structured_tool
from graph_agent.core.builtin_subagents import ReferenceReaderRuntime
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError, make_error_payload
from graph_agent.core.loader import CompiledSkill, CompiledSubagent, PhaseDocument, SkillLoader
from graph_agent.core.manifest import (
    AgentNodeAST,
    BatchSpec,
    GraphManifest,
    IterateSpec,
    LogicNodeAST,
    SubgraphNodeAST,
)
from graph_agent.core.skill_resolver_protocol import (
    SkillResolverProtocol,
    require_skill_resolver,
)
from graph_agent.core.llm_provider import LLMProvider, LLMProviderChatModel
from graph_agent.core.state import BusinessData, FrameworkState, StateManager, WorkflowState
from graph_agent.core.subagents import (
    SubagentValidationFailure,
    assert_subagent_depth_allowed,
    current_subagent_depth,
    validate_subagent_tool_args,
)
from graph_agent.runtime.state_mapper import (
    PhaseWrapper,
    StateMapper,
    phase_inputs_from_state,
    schema_properties,
)
from graph_agent.tools.builtin.read_example import read_declared_example
from graph_agent.tools.builtin.read_file import RuntimeInputFileError, read_workspace_text_file
from graph_agent.tools.builtin.read_reference import read_declared_reference, read_resource_file

MAX_REACT_TURNS = 8
logger = logging.getLogger(__name__)
parent_state_var: contextvars.ContextVar[Any] = contextvars.ContextVar("parent_state_var")
active_branch_index_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "active_branch_index_var", default=None
)
_T = TypeVar("_T")


@dataclass(frozen=True)
class CompiledStateGraph:
    graph: Any
    compiled_skill: CompiledSkill
    phase_ids: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class _SubagentRuntime:
    subagent: CompiledSubagent
    graph: Any


@dataclass(frozen=True)
class _InputFileSpec:
    field: str
    path: str


@dataclass(frozen=True)
class _GraphIterateRuntime:
    graph: Any
    iterate: IterateSpec
    output_schema: dict[str, Any] | None
    terminal_phase_ids: list[str]
    callbacks: Any | None = None

    def invoke(
        self,
        state: WorkflowState | dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> WorkflowState:
        workflow_state = _coerce_workflow_state(state)
        if self.iterate.mode == "batch":
            return _run_graph_batch_iterate(
                self.graph,
                workflow_state,
                self.iterate,
                self.output_schema,
                self.terminal_phase_ids,
                config=config,
                invoke_kwargs=kwargs,
            )
        return _run_graph_loop_iterate(
            self.graph,
            workflow_state,
            self.iterate,
            self.output_schema,
            self.terminal_phase_ids,
            config=config,
            invoke_kwargs=kwargs,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.graph, name)


def assemble_graph(
    compiled: CompiledSkill,
    *,
    chat_model: Any = None,
    model_resolver: Any = None,
    max_patch_attempts: int = 3,
    callbacks: list[Any] | None = None,
    skill_resolver: SkillResolverProtocol,
    llm_provider: LLMProvider | None = None,
    checkpointer: Any = None,
    predict_context: Any = None,
    _loading_stack: tuple[str, ...] = (),
    _compilation_cache: dict[str, CompiledSkill] | None = None,
) -> CompiledStateGraph:
    """Assemble a V2.1 CompiledSkill into a compiled LangGraph."""

    resolver = require_skill_resolver(skill_resolver, caller="assemble_graph")
    if _compilation_cache is None:
        _compilation_cache = {}
    builder = StateGraph(WorkflowState)
    node_by_phase = {node.phase_name: node for node in compiled.nodes}
    phase_ids: list[str] = []
    edges: list[tuple[str, str]] = []

    topology = _graph_topology(compiled)

    for phase_id in topology:
        phase_doc = node_by_phase.get(phase_id)
        if phase_doc is None:
            _graph_fatal(f"phase {phase_id!r} has no parsed node")
        builder.add_node(
            phase_id,
            _build_phase_node(
                phase_id,
                phase_doc,
                compiled,
                chat_model,
                model_resolver,
                max_patch_attempts,
                callbacks,
                resolver,
                llm_provider,
                checkpointer,
                _loading_stack,
                _compilation_cache,
                predict_context=predict_context,
            ),
        )
        phase_ids.append(phase_id)

    for phase_id, depends_on in topology.items():
        graph_deps = [dep for dep in depends_on if dep != "input"]
        if not graph_deps:
            builder.add_edge(START, phase_id)
            edges.append(("START", phase_id))
        else:
            for dep in graph_deps:
                builder.add_edge(dep, phase_id)
                edges.append((dep, phase_id))

    for phase_id in _terminal_phase_ids(compiled.manifest, compiled):
        builder.add_edge(phase_id, END)
        edges.append((phase_id, "END"))

    graph: Any = builder.compile(checkpointer=checkpointer)
    if compiled.manifest.iterate is not None:
        graph = _GraphIterateRuntime(
            graph=graph,
            iterate=compiled.manifest.iterate,
            output_schema=compiled.manifest.io.outputs,
            terminal_phase_ids=_terminal_phase_ids(compiled.manifest, compiled),
            callbacks=callbacks,
        )

    return CompiledStateGraph(
        graph=graph,
        compiled_skill=compiled,
        phase_ids=phase_ids,
        edges=edges,
    )


def _build_phase_node(
    phase_id: str,
    phase_doc: PhaseDocument,
    compiled: CompiledSkill,
    chat_model: Any,
    model_resolver: Any,
    max_patch_attempts: int,
    callbacks: Any | None,
    skill_resolver: SkillResolverProtocol,
    llm_provider: LLMProvider | None,
    checkpointer: Any,
    _loading_stack: tuple[str, ...],
    _compilation_cache: dict[str, CompiledSkill],
    predict_context: Any = None,
) -> Any:
    ast = phase_doc.ast
    if isinstance(ast, LogicNodeAST):
        return _wrap_phase_runtime_node(
            phase_id,
            ast,
            _build_logic_node(phase_id, ast, compiled),
            node_kind="logic",
            callbacks=callbacks,
        )
    if isinstance(ast, SubgraphNodeAST):
        return _wrap_phase_runtime_node(
            phase_id,
            ast,
            _build_subgraph_node(
                phase_doc,
                ast,
                chat_model,
                max_patch_attempts,
                skill_resolver,
                model_resolver=model_resolver,
                callbacks=callbacks,
                checkpointer=checkpointer,
                llm_provider=llm_provider,
                _loading_stack=_loading_stack,
                _compilation_cache=_compilation_cache,
                predict_context=predict_context,
            ),
            node_kind="subgraph",
            callbacks=callbacks,
        )
    if isinstance(ast, AgentNodeAST):
        return _wrap_phase_runtime_node(
            phase_id,
            ast,
            _build_skill_node(
                phase_id,
                phase_doc,
                ast,
                compiled,
                chat_model,
                model_resolver,
                max_patch_attempts,
                callbacks,
                skill_resolver,
                llm_provider,
                _loading_stack,
                _compilation_cache,
                checkpointer=checkpointer,
                predict_context=predict_context,
            ),
            node_kind="agent",
            callbacks=callbacks,
        )
    _graph_fatal(f"unknown phase mode for {phase_id!r}")


_MISSING = object()


def _coerce_workflow_state(state: WorkflowState | dict[str, Any]) -> WorkflowState:
    data_obj = state.get("data") if isinstance(state, dict) else None
    if isinstance(data_obj, BusinessData):
        data = data_obj
    elif isinstance(data_obj, dict):
        data = BusinessData.model_validate(data_obj)
    else:
        data = BusinessData()

    flow_obj = state.get("flow") if isinstance(state, dict) else None
    if isinstance(flow_obj, FrameworkState):
        flow = flow_obj
    elif isinstance(flow_obj, dict):
        flow = FrameworkState.model_validate(flow_obj)
    else:
        flow = FrameworkState()

    messages = list(state.get("messages", [])) if isinstance(state, dict) else []
    return WorkflowState(data=data, flow=flow, messages=messages)


def _resolve_path_value(state: WorkflowState, path_str: str) -> Any:
    curr: Any = state
    for part in path_str.split("."):
        if isinstance(curr, dict):
            if part not in curr:
                return _MISSING
            curr = curr[part]
            continue
        if hasattr(curr, "model_dump"):
            dumped = curr.model_dump()
            if isinstance(dumped, dict) and part in dumped:
                curr = dumped[part]
                continue
        if hasattr(curr, part):
            curr = getattr(curr, part)
            continue
        get = getattr(curr, "get", None)
        if callable(get):
            next_value = get(part, _MISSING)
            if next_value is not _MISSING:
                curr = next_value
                continue
        return _MISSING
    return curr


def _resolve_iterate_items(state: WorkflowState, path_str: str) -> list[Any]:
    value = _resolve_path_value(state, path_str)
    if value is _MISSING:
        value = _resolve_legacy_data_input_path(state, path_str)
    if not isinstance(value, list):
        detail = f"iterate over path {path_str!r} must resolve to list"
        raise GraphAgentFatalError(
            detail,
            payload=make_error_payload(
                "[F-v3-iterate-over-not-list]",
                detail,
                field_path=path_str,
            ),
        )
    return value


def _resolve_legacy_data_input_path(state: WorkflowState, path_str: str) -> Any:
    if not path_str.startswith("data.") or path_str.startswith("data.inputs."):
        return _MISSING
    inputs = _resolve_path_value(state, "data.inputs")
    if not isinstance(inputs, dict):
        return _MISSING
    legacy_tail = path_str.removeprefix("data.")
    return _resolve_path_value(
        WorkflowState(
            data=BusinessData.model_validate(inputs),
            flow=state["flow"],
            messages=state["messages"],
        ),
        f"data.{legacy_tail}",
    )


def _apply_iterate_range(items: list[Any], range_spec: tuple[int, int] | None) -> list[Any]:
    if range_spec is None:
        return list(items)
    start, end = range_spec
    if end < start:
        return []
    start_index = max(start, 1) - 1
    return list(items[start_index:end])


def _phase_result_payload(
    before: WorkflowState,
    result: WorkflowState | dict[str, Any],
    output_keys: set[str] | None,
) -> dict[str, Any]:
    result_state = _coerce_workflow_state(result)
    after_data = result_state["data"].model_dump()
    if output_keys is None:
        delta = _dict_delta(before["data"].model_dump(), after_data)
        # phase_outputs is a reserved meta-accumulator (D7 per-node golden), never a
        # business output. Exclude it from the open-schema delta so a batch/iterate
        # per-item payload does not carry a spurious nested phase_outputs aggregate
        # into this node's golden entry. The declared-schema branch below is already
        # safe (phase_outputs is not a declared output key).
        delta.pop("phase_outputs", None)
        return delta
    return {key: after_data[key] for key in output_keys if key in after_data}


def _with_phase_outputs(
    state: WorkflowState,
    phase_outputs: dict[str, dict[str, Any]],
) -> WorkflowState:
    merged_outputs = state["data"].model_dump().get("phase_outputs")
    if not isinstance(merged_outputs, dict):
        merged_outputs = {}
    merged_outputs = dict(merged_outputs)
    for phase_id, payload in phase_outputs.items():
        merged_outputs[phase_id] = dict(payload)
    data_updates: dict[str, Any] = {}
    for payload in phase_outputs.values():
        data_updates.update(payload)
    data_updates["phase_outputs"] = merged_outputs
    return StateManager.update_business(state, **data_updates)


def _terminal_phase_outputs(
    phase_ids: list[str],
    payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    if not phase_ids:
        return {"output": dict(payload)}
    return {phase_id: dict(payload) for phase_id in phase_ids}


def _merge_accumulator(current: Any, piece: Any, merge: str) -> Any:
    if merge == "append":
        if not isinstance(current, list):
            _iterate_merge_fatal("append accumulator must be a list")
        return [*current, piece]
    if merge == "extend":
        if not isinstance(current, list) or not isinstance(piece, list):
            _iterate_merge_fatal("extend accumulator and piece must be lists")
        return [*current, *piece]
    if merge == "merge":
        if not isinstance(current, dict) or not isinstance(piece, dict):
            _iterate_merge_fatal("merge accumulator and piece must be objects")
        return {**current, **piece}
    if merge == "replace":
        return piece
    _iterate_merge_fatal(f"unsupported accumulate merge mode {merge!r}")


def _iterate_merge_fatal(message: str) -> NoReturn:
    raise GraphAgentFatalError(
        message,
        payload=make_error_payload("[F-v3-runtime-state-mapping-failed]", message),
    )


def _iteration_namespace(index: int) -> str:
    return f"iter{index}"


def _run_with_branch_index(index: int, action: Callable[[], _T]) -> _T:
    token = active_branch_index_var.set(index)
    try:
        return action()
    finally:
        active_branch_index_var.reset(token)


async def _run_with_branch_index_async(
    index: int,
    action: Callable[[], Awaitable[_T]],
) -> _T:
    token = active_branch_index_var.set(index)
    try:
        return await action()
    finally:
        active_branch_index_var.reset(token)


def _run_with_iteration_context(index: int, namespace: str, action: Callable[[], _T]) -> _T:
    token_outer = active_outer_ns.set(namespace)
    token_branch = active_branch_index_var.set(index)
    try:
        return action()
    finally:
        active_outer_ns.reset(token_outer)
        active_branch_index_var.reset(token_branch)


async def _run_with_iteration_context_async(
    index: int,
    namespace: str,
    action: Callable[[], Awaitable[_T]],
) -> _T:
    token_outer = active_outer_ns.set(namespace)
    token_branch = active_branch_index_var.set(index)
    try:
        return await action()
    finally:
        active_outer_ns.reset(token_outer)
        active_branch_index_var.reset(token_branch)


async def _gather_indexed(
    items: list[Any],
    concurrency: int,
    run_one: Callable[[int, Any], Awaitable[dict[str, Any]]],
) -> list[dict[str, Any]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def _guarded_run(index: int, item: Any) -> dict[str, Any]:
        async with semaphore:
            return await run_one(index, item)

    return await asyncio.gather(
        *[_guarded_run(index, item) for index, item in enumerate(items, start=1)]
    )


def _empty_batch_payload(
    output_keys: set[str] | None,
    *,
    include_batch_outputs: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {key: [] for key in (output_keys or set())}
    if include_batch_outputs:
        payload["batch_outputs"] = []
    return payload


def _aggregate_batch_payloads(
    item_payloads: list[dict[str, Any]],
    *,
    include_batch_outputs: bool,
) -> dict[str, Any]:
    aggregated: dict[str, Any] = {}
    for payload in item_payloads:
        for key, value in payload.items():
            aggregated.setdefault(key, []).append(value)
    if include_batch_outputs:
        aggregated["batch_outputs"] = item_payloads
    return aggregated


def _run_batch_iterate_payload(
    items: list[Any],
    output_keys: set[str] | None,
    concurrency: int,
    run_one: Callable[[int, Any], Awaitable[dict[str, Any]]],
    *,
    include_batch_outputs: bool = False,
) -> dict[str, Any]:
    if not items:
        return _empty_batch_payload(output_keys, include_batch_outputs=include_batch_outputs)
    item_payloads = asyncio.run(_gather_indexed(items, concurrency, run_one))
    return _aggregate_batch_payloads(
        item_payloads,
        include_batch_outputs=include_batch_outputs,
    )


def _collect_batch_iteration(
    state: WorkflowState,
    *,
    over: str,
    range_spec: tuple[int, int] | None,
    output_schema: dict[str, Any] | None,
    concurrency: int,
    runner_factory: Callable[
        [set[str] | None],
        Callable[[int, Any], Awaitable[dict[str, Any]]],
    ],
    include_batch_outputs: bool = False,
) -> tuple[list[Any], dict[str, Any]]:
    output_keys = _schema_output_keys(output_schema)
    items = _apply_iterate_range(_resolve_iterate_items(state, over), range_spec)
    aggregated = _run_batch_iterate_payload(
        items,
        output_keys,
        concurrency,
        runner_factory(output_keys),
        include_batch_outputs=include_batch_outputs,
    )
    return items, aggregated


def _batch_payload_runner(
    base_state: WorkflowState,
    item_var: str,
    output_keys: set[str] | None,
    invoke_child: Callable[[int, WorkflowState], Awaitable[Any]],
) -> Callable[[int, Any], Awaitable[dict[str, Any]]]:
    async def _run_one(index: int, item: Any) -> dict[str, Any]:
        child_state = StateManager.update_business(base_state, **{item_var: item})
        result = await invoke_child(index, child_state)
        return _phase_result_payload(child_state, result, output_keys)

    return _run_one


def _phase_batch_runner(
    workflow_state: WorkflowState,
    item_var: str,
    node: Any,
    output_keys: set[str] | None,
) -> Callable[[int, Any], Awaitable[dict[str, Any]]]:
    async def _invoke_child(index: int, child_state: WorkflowState) -> Any:
        return await _run_with_branch_index_async(
            index,
            lambda: asyncio.to_thread(node, child_state),
        )

    return _batch_payload_runner(workflow_state, item_var, output_keys, _invoke_child)


def _graph_batch_runner(
    graph: Any,
    state: WorkflowState,
    iterate: IterateSpec,
    output_keys: set[str] | None,
    *,
    config: RunnableConfig | None,
    invoke_kwargs: dict[str, Any],
) -> Callable[[int, Any], Awaitable[dict[str, Any]]]:
    async def _invoke_child(index: int, child_state: WorkflowState) -> Any:
        return await _run_with_iteration_context_async(
            index,
            _iteration_namespace(index),
            lambda: asyncio.to_thread(
                graph.invoke,
                child_state,
                config=_iteration_config(config, index),
                **invoke_kwargs,
            ),
        )

    return _batch_payload_runner(state, iterate.item_var, output_keys, _invoke_child)


def _phase_batch_payload(
    workflow_state: WorkflowState,
    *,
    over: str,
    range_spec: tuple[int, int] | None,
    output_schema: dict[str, Any] | None,
    concurrency: int,
    item_var: str,
    node: Any,
    include_batch_outputs: bool,
) -> dict[str, Any]:
    _items, aggregated = _collect_batch_iteration(
        workflow_state,
        over=over,
        range_spec=range_spec,
        output_schema=output_schema,
        concurrency=concurrency,
        runner_factory=lambda output_keys: _phase_batch_runner(
            workflow_state,
            item_var,
            node,
            output_keys,
        ),
        include_batch_outputs=include_batch_outputs,
    )
    return aggregated


def _graph_batch_payload_and_namespaces(
    graph: Any,
    state: WorkflowState,
    iterate: IterateSpec,
    output_schema: dict[str, Any] | None,
    *,
    config: RunnableConfig | None,
    invoke_kwargs: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    items, aggregated = _collect_batch_iteration(
        state,
        over=iterate.over,
        range_spec=iterate.range,
        output_schema=output_schema,
        concurrency=iterate.concurrency,
        runner_factory=lambda output_keys: _graph_batch_runner(
            graph=graph,
            state=state,
            iterate=iterate,
            output_keys=output_keys,
            config=config,
            invoke_kwargs=invoke_kwargs,
        ),
    )
    namespaces = [_iteration_namespace(index) for index in range(1, len(items) + 1)]
    return aggregated, namespaces


def _emit_blackboard_reduce(
    callbacks: Any | None,
    *,
    to_phase: str,
    state: WorkflowState,
    changed_key: str,
    reducer: str,
) -> None:
    _safe_emit_event(
        callbacks,
        BlackboardReduceEvent(
            from_phase=None,
            to_phase=to_phase,
            changed_keys=[changed_key],
            blackboard_snapshot=state["data"].model_dump(),
            reducer=reducer,
        ),
    )


def _current_phase_from_state(state: WorkflowState) -> str | None:
    flow_obj = state.get("flow")
    if not flow_obj:
        return None
    if hasattr(flow_obj, "current_phase"):
        phase = flow_obj.current_phase
    elif isinstance(flow_obj, dict):
        phase = flow_obj.get("current_phase")
    else:
        phase = None
    return phase if isinstance(phase, str) and phase else None


def _emit_input_dispatch(
    callbacks: Any | None,
    *,
    phase_id: str,
    mapper: StateMapper,
    state: WorkflowState,
) -> None:
    raw_data = phase_inputs_from_state(mapper.build_phase_input(state))
    keys = schema_properties(mapper.input_schema)
    dispatched_keys = [key for key in keys if key in raw_data] if keys else list(raw_data.keys())
    _safe_emit_event(
        callbacks,
        InputDispatchEvent(
            from_phase=_current_phase_from_state(state),
            to_phase=phase_id,
            changed_keys=dispatched_keys,
            blackboard_snapshot=raw_data,
            dispatched_keys=dispatched_keys,
            branch_index=active_branch_index_var.get(),
        ),
    )


def _build_iterate_wrapped_phase(
    phase_id: str,
    node: Any,
    iterate: IterateSpec,
    output_schema: dict[str, Any] | None,
    *,
    callbacks: Any | None = None,
) -> Any:
    if iterate.mode == "batch":
        return _build_batch_iterate_phase(
            phase_id,
            node,
            over=iterate.over,
            item_var=iterate.item_var,
            concurrency=iterate.concurrency,
            range_spec=iterate.range,
            output_schema=output_schema,
            include_batch_outputs=False,
        )
    return _build_loop_iterate_phase(phase_id, node, iterate, output_schema, callbacks=callbacks)


def _build_legacy_batch_wrapped_phase(
    phase_id: str,
    node: Any,
    batch: BatchSpec,
    output_schema: dict[str, Any] | None,
) -> Any:
    return _build_batch_iterate_phase(
        phase_id,
        node,
        over=batch.iterator,
        item_var=batch.item_var,
        concurrency=batch.concurrency,
        range_spec=None,
        output_schema=output_schema,
        include_batch_outputs=True,
    )


def _build_batch_iterate_phase(
    phase_id: str,
    node: Any,
    *,
    over: str,
    item_var: str,
    concurrency: int,
    range_spec: tuple[int, int] | None,
    output_schema: dict[str, Any] | None,
    include_batch_outputs: bool,
) -> Any:
    def _batch_phase(state: WorkflowState) -> WorkflowState:
        workflow_state = _coerce_workflow_state(state)
        payload = _phase_batch_payload(
            workflow_state,
            over=over,
            range_spec=range_spec,
            output_schema=output_schema,
            concurrency=concurrency,
            item_var=item_var,
            node=node,
            include_batch_outputs=include_batch_outputs,
        )
        return _with_phase_outputs(workflow_state, {phase_id: payload})

    return _batch_phase


def _build_loop_iterate_phase(
    phase_id: str,
    node: Any,
    iterate: IterateSpec,
    output_schema: dict[str, Any] | None,
    *,
    callbacks: Any | None = None,
) -> Any:
    accumulate = iterate.accumulate
    if accumulate is None:
        _iterate_merge_fatal("loop iterate requires accumulate")
    output_keys = _schema_output_keys(output_schema)

    def _loop_phase(state: WorkflowState) -> WorkflowState:
        workflow_state = _coerce_workflow_state(state)
        items = _apply_iterate_range(_resolve_iterate_items(workflow_state, iterate.over), iterate.range)
        acc = copy.deepcopy(accumulate.init)
        loop_state = StateManager.update_business(workflow_state, **{accumulate.var: acc})
        for index, item in enumerate(items, start=1):
            child_state = StateManager.update_business(
                loop_state,
                **{iterate.item_var: item, accumulate.var: acc},
            )

            def _invoke_node(child: WorkflowState = child_state) -> Any:
                return node(child)

            result = _run_with_branch_index(index, _invoke_node)
            payload = _phase_result_payload(child_state, result, output_keys)
            if accumulate.from_ not in payload:
                _iterate_merge_fatal(
                    f"loop iterate output missing accumulate.from {accumulate.from_!r}"
                )
            acc = _merge_accumulator(acc, payload[accumulate.from_], accumulate.merge)
            loop_state = StateManager.update_business(loop_state, **{accumulate.var: acc})
            _emit_blackboard_reduce(
                callbacks,
                to_phase=phase_id,
                state=loop_state,
                changed_key=accumulate.var,
                reducer=accumulate.merge,
            )
        final_payload = {accumulate.var: acc}
        return _with_phase_outputs(workflow_state, {phase_id: final_payload})

    return _loop_phase


def _iteration_config(config: RunnableConfig | None, iteration_index: int) -> RunnableConfig:
    inner_config: dict[str, Any] = dict(config or {})
    configurable = dict(inner_config.get("configurable", {}))
    configurable["checkpoint_ns"] = _iteration_namespace(iteration_index)
    inner_config["configurable"] = configurable
    return inner_config  # type: ignore[return-value]


def _with_graph_iterate_signal(
    state: WorkflowState,
    *,
    mode: str,
    namespaces: list[str],
) -> WorkflowState:
    working_memory = state["flow"].working_memory
    if not isinstance(working_memory, dict):
        working_memory = {"value": working_memory}
    else:
        working_memory = dict(working_memory)
    executions = working_memory.get("iterate_executions")
    if not isinstance(executions, list):
        executions = []
    executions.append(
        {
            "scope": "graph",
            "mode": mode,
            "checkpoint_ns": list(namespaces),
        }
    )
    working_memory["iterate_executions"] = executions
    return StateManager.update_framework(state, working_memory=working_memory)


def _run_graph_batch_iterate(
    graph: Any,
    state: WorkflowState,
    iterate: IterateSpec,
    output_schema: dict[str, Any] | None,
    terminal_phase_ids: list[str],
    *,
    config: RunnableConfig | None,
    invoke_kwargs: dict[str, Any],
) -> WorkflowState:
    payload, namespaces = _graph_batch_payload_and_namespaces(
        graph,
        state,
        iterate,
        output_schema,
        config=config,
        invoke_kwargs=invoke_kwargs,
    )
    final_state = _with_phase_outputs(
        state,
        _terminal_phase_outputs(terminal_phase_ids, payload),
    )
    return _with_graph_iterate_signal(final_state, mode="batch", namespaces=namespaces)


def _run_graph_loop_iterate(
    graph: Any,
    state: WorkflowState,
    iterate: IterateSpec,
    output_schema: dict[str, Any] | None,
    terminal_phase_ids: list[str],
    *,
    config: RunnableConfig | None,
    callbacks: Any | None = None,
    invoke_kwargs: dict[str, Any],
) -> WorkflowState:
    accumulate = iterate.accumulate
    if accumulate is None:
        _iterate_merge_fatal("graph loop iterate requires accumulate")
    output_keys = _schema_output_keys(output_schema)
    items = _apply_iterate_range(_resolve_iterate_items(state, iterate.over), iterate.range)
    acc = copy.deepcopy(accumulate.init)
    loop_state = StateManager.update_business(state, **{accumulate.var: acc})
    namespaces: list[str] = []
    for index, item in enumerate(items, start=1):
        namespace = _iteration_namespace(index)
        namespaces.append(namespace)
        child_state = StateManager.update_business(
            loop_state,
            **{iterate.item_var: item, accumulate.var: acc},
        )

        def _invoke_graph_iteration(
            child: WorkflowState = child_state,
            iteration_index: int = index,
        ) -> Any:
            return graph.invoke(
                child,
                config=_iteration_config(config, iteration_index),
                **invoke_kwargs,
            )

        result = _run_with_iteration_context(
            index,
            namespace,
            _invoke_graph_iteration,
        )
        payload = _phase_result_payload(child_state, result, output_keys)
        if accumulate.from_ not in payload:
            _iterate_merge_fatal(
                f"graph loop iterate output missing accumulate.from {accumulate.from_!r}"
            )
        acc = _merge_accumulator(acc, payload[accumulate.from_], accumulate.merge)
        loop_state = StateManager.update_business(
            _coerce_workflow_state(result),
            **{accumulate.var: acc},
        )
        to_phase = terminal_phase_ids[0] if terminal_phase_ids else "output"
        _emit_blackboard_reduce(
            callbacks,
            to_phase=to_phase,
            state=loop_state,
            changed_key=accumulate.var,
            reducer=accumulate.merge,
        )

    final_payload = {accumulate.var: acc}
    final_state = _with_phase_outputs(
        state,
        _terminal_phase_outputs(terminal_phase_ids, final_payload),
    )
    return _with_graph_iterate_signal(final_state, mode="loop", namespaces=namespaces)


def _wrap_phase_runtime_node(
    phase_id: str,
    phase_ast: Any,
    node: Any,
    *,
    node_kind: str,
    callbacks: Any | None,
) -> Any:
    io = getattr(phase_ast, "io", None)
    input_schema = getattr(io, "inputs", None) if io is not None else None
    output_schema = getattr(io, "outputs", None) if io is not None else None

    mapper = StateMapper(input_schema, output_schema, phase_id=phase_id)

    def _node_with_lifecycle(state: WorkflowState) -> dict[str, Any]:
        _safe_emit_event(
            callbacks,
            PhaseStartEvent(phase_name=phase_id, context=_observable_data_context(state)),
        )
        response_state: dict[str, Any] | None = None
        try:
            response_state = node(state)
            return response_state
        finally:
            _safe_emit_event(
                callbacks,
                PhaseEndEvent(
                    phase_name=phase_id,
                    context=_phase_end_context(phase_id, state, response_state or {}),
                ),
            )

    phase_runner = PhaseWrapper(mapper, node_kind=node_kind).wrap(_node_with_lifecycle)

    def _dispatch_and_run(state: WorkflowState) -> WorkflowState:
        _emit_input_dispatch(callbacks, phase_id=phase_id, mapper=mapper, state=state)
        return phase_runner(state)

    wrapped = _wrap_declared_input_files(
        phase_id,
        input_schema,
        _dispatch_and_run,
        callbacks=callbacks,
    )
    iterate = getattr(phase_ast, "iterate", None)
    if iterate is not None:
        return _build_iterate_wrapped_phase(
            phase_id,
            wrapped,
            iterate,
            output_schema,
            callbacks=callbacks,
        )
    if getattr(phase_ast, "batch", None) is not None:
        return _build_legacy_batch_wrapped_phase(
            phase_id,
            wrapped,
            phase_ast.batch,
            output_schema,
        )
    return wrapped


def _wrap_declared_input_files(
    phase_id: str,
    input_schema: dict[str, Any] | None,
    node: Any,
    *,
    callbacks: Any | None,
) -> Any:
    file_specs = _declared_input_file_specs(input_schema, phase_id=phase_id)
    if not file_specs:
        return node

    def _node_with_input_files(state: WorkflowState) -> WorkflowState:
        return cast(
            WorkflowState,
            node(
                _inject_declared_input_files(
                    state,
                    phase_id=phase_id,
                    file_specs=file_specs,
                    callbacks=callbacks,
                )
            ),
        )

    return _node_with_input_files


def _declared_input_file_specs(
    input_schema: dict[str, Any] | None,
    *,
    phase_id: str,
) -> list[_InputFileSpec]:
    if not isinstance(input_schema, dict):
        return []
    properties = input_schema.get("properties")
    if not isinstance(properties, dict):
        return []
    specs: list[_InputFileSpec] = []
    for field_name, schema in properties.items():
        if not isinstance(field_name, str) or not isinstance(schema, dict):
            continue
        if schema.get("source") != "file":
            continue
        path = schema.get("path")
        if not isinstance(path, str) or not path.strip():
            detail = f"file input field {field_name!r} has source='file' but no path"
            raise GraphAgentFatalError(
                detail,
                payload=make_error_payload(
                    "[F-v3-runtime-state-mapping-failed]",
                    detail,
                    phase_id=phase_id,
                    field_path=field_name,
                ),
            )
        specs.append(_InputFileSpec(field=field_name, path=path))
    return specs


def _inject_declared_input_files(
    state: WorkflowState,
    *,
    phase_id: str,
    file_specs: list[_InputFileSpec],
    callbacks: Any | None,
) -> WorkflowState:
    workspace_dir = _workspace_dir_from_state(state, phase_id=phase_id)
    next_state = state
    for spec in file_specs:
        if spec.field.startswith("_"):
            _input_file_fatal(
                f"file input target field {spec.field!r} is not a business field",
                phase_id=phase_id,
                field_path=spec.field,
                source_path=spec.path,
            )
        try:
            content = read_workspace_text_file(spec.path, workspace_dir)
        except RuntimeInputFileError as exc:
            _input_file_fatal(
                str(exc),
                phase_id=phase_id,
                field_path=spec.field,
                source_path=spec.path,
                cause=exc,
            )
        next_state = StateManager.update_business(next_state, **{spec.field: content})
        _safe_emit_event(
            callbacks,
            InputFileInjectedEvent(
                from_phase=state["flow"].current_phase or None,
                to_phase=phase_id,
                changed_keys=[spec.field],
                blackboard_snapshot=next_state["data"].model_dump(),
                file_ref=spec.path,
                target_field=spec.field,
            ),
        )
    return next_state


def _workspace_dir_from_state(state: WorkflowState, *, phase_id: str) -> Path:
    flow = state["flow"]
    storage_config = getattr(flow, "persistent_storage_config", None)
    if isinstance(storage_config, dict):
        workspace_dir = storage_config.get("workspace_dir")
        if isinstance(workspace_dir, str) and workspace_dir:
            return Path(workspace_dir)
    _input_file_fatal(
        "workspace_dir is required for declarative file input",
        phase_id=phase_id,
        field_path=None,
        source_path=None,
    )


def _input_file_fatal(
    detail: str,
    *,
    phase_id: str,
    field_path: str | None,
    source_path: str | None,
    cause: Exception | None = None,
) -> NoReturn:
    error = GraphAgentFatalError(
        detail,
        payload=make_error_payload(
            "[F-v3-runtime-state-mapping-failed]",
            detail,
            phase_id=phase_id,
            field_path=field_path,
            source_path=source_path,
        ),
    )
    if cause is not None:
        raise error from cause
    raise error


def _build_logic_node(
    phase_id: str,
    phase_ast: LogicNodeAST,
    compiled: CompiledSkill,
) -> Any:
    action_names = phase_ast.actions
    output_schema_keys = _schema_output_keys(phase_ast.io.outputs)

    def _logic_node(state: WorkflowState) -> dict[str, Any]:
        before = phase_inputs_from_state(state)
        updates: dict[str, Any] = {}
        for action_name in action_names:
            action = compiled.actions.resolve(phase_id, action_name)
            action_def = compiled.actions.for_phase(phase_id).get(action_name)
            action_path = action_def.path if action_def is not None else Path("<unknown>")
            action_line = getattr(getattr(action, "__code__", None), "co_firstlineno", 1)
            action_ctx = {**before, **updates}
            result = action(action_ctx)
            if not isinstance(result, dict):
                detail = (
                    f"{action_path}:{action_line} action returned "
                    f"{type(result).__name__}, expected dict"
                )
                raise GraphAgentFatalError(
                    detail,
                    payload=make_error_payload("[F-v3-logic-action-return-invalid]", detail),
                )
            _validate_logic_update_keys(result, output_schema_keys, action_path, action_line)
            updates.update(result)
        return {"data": updates} if updates else {}

    return _logic_node


def _build_subgraph_node(
    phase_doc: PhaseDocument,
    phase_ast: SubgraphNodeAST,
    chat_model: Any,
    max_patch_attempts: int,
    skill_resolver: SkillResolverProtocol,
    *,
    model_resolver: Any = None,
    callbacks: Any | None = None,
    checkpointer: Any = None,
    llm_provider: LLMProvider | None = None,
    _loading_stack: tuple[str, ...] = (),
    _compilation_cache: dict[str, CompiledSkill] | None = None,
    predict_context: Any = None,
) -> Any:
    if _compilation_cache is None:
        _compilation_cache = {}
    sub_root = _resolve_subgraph_path_root_for_assembly(phase_doc.path, phase_ast.path)
    sub_root_key = str(Path(sub_root).resolve())
    sub_compiled = _compilation_cache.get(sub_root_key)
    if sub_compiled is None:
        sub_compiled = SkillLoader(validate_context_writes=False).compile_skill(
            sub_root,
            skill_resolver=skill_resolver,
            _loading_stack=_loading_stack,
            _compilation_cache=_compilation_cache,
        )
    sub_assembled = assemble_graph(
        sub_compiled,
        chat_model=chat_model,
        model_resolver=model_resolver,
        max_patch_attempts=max_patch_attempts,
        callbacks=callbacks,
        skill_resolver=skill_resolver,
        llm_provider=llm_provider,
        checkpointer=checkpointer,
        predict_context=predict_context,
        _loading_stack=_loading_stack,
        _compilation_cache=_compilation_cache,
    )

    def _subgraph_node(state: WorkflowState) -> dict[str, Any]:
        child_input = phase_inputs_from_state(state)
        child_flow_dict = _child_flow(state["flow"])
        child_flow = FrameworkState.model_validate(child_flow_dict)
        result = sub_assembled.graph.invoke(
            WorkflowState(
                data=BusinessData.model_validate(child_input),
                flow=child_flow,
                messages=[],
            )
        )
        child_final_data = result["data"].model_dump()
        data_updates = _dict_delta(child_input, child_final_data)
        return {
            "data": data_updates,
            "flow": result["flow"],
        }

    return _subgraph_node


def _resolve_subgraph_path_root_for_assembly(source_path: Path, value: str) -> Path:
    parent_root = source_path.parent.parent.parent.resolve()
    candidate = Path(value)
    if not candidate.is_absolute():
        _subgraph_path_fatal(source_path, f"subgraph path {value!r} must be absolute")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(parent_root)
    except ValueError as exc:
        _subgraph_path_fatal(
            source_path,
            f"subgraph path {value!r} escapes skill root {parent_root}",
        )
        raise AssertionError("unreachable") from exc
    if not resolved.is_dir():
        _subgraph_path_fatal(source_path, f"subgraph path {value!r} is not a directory")
    if not (resolved / "GRAPH.md").is_file():
        _subgraph_path_fatal(source_path, f"subgraph path {value!r} has no GRAPH.md")
    return resolved


def _subgraph_path_fatal(source_path: Path, message: str) -> NoReturn:
    detail = f"{source_path}:1 {message}"
    raise GraphAgentFatalError(
        detail,
        payload=make_error_payload(
            "[F-v3-subgraph-target-skill-invalid]",
            detail,
            source_path=source_path,
        ),
    )

active_outer_ns: contextvars.ContextVar[str] = contextvars.ContextVar("active_outer_ns", default="")


class NamespaceCheckpointer(BaseCheckpointSaver[Any]):
    def __init__(self, base_checkpointer: BaseCheckpointSaver[Any], target_ns: str) -> None:
        super().__init__(serde=base_checkpointer.serde)
        self.base_checkpointer = base_checkpointer
        self.target_ns = target_ns

    def _wrap_config(self, config: RunnableConfig) -> RunnableConfig:
        new_config = dict(cast(Any, config))
        configurable = dict(new_config.get("configurable", {}))
        ns = configurable.get("checkpoint_ns")
        if ns == "" or ns is None:
            ns = self.target_ns

        outer = active_outer_ns.get()
        if outer:
            if ns and not ns.startswith(f"{outer}."):
                ns = f"{outer}.{ns}"

        configurable["checkpoint_ns"] = ns
        new_config["configurable"] = configurable
        return new_config  # type: ignore[return-value]

    def _unwrap_config(self, config: RunnableConfig) -> RunnableConfig:
        new_config = dict(cast(Any, config))
        configurable = dict(new_config.get("configurable", {}))
        ns = configurable.get("checkpoint_ns")

        outer = active_outer_ns.get()
        if outer and ns and ns.startswith(f"{outer}."):
            ns = ns[len(outer) + 1:]

        if ns == self.target_ns:
            ns = ""

        configurable["checkpoint_ns"] = ns
        new_config["configurable"] = configurable
        return new_config  # type: ignore[return-value]

    def _unwrap_tuple(self, tup: CheckpointTuple) -> CheckpointTuple:
        return CheckpointTuple(
            config=self._unwrap_config(tup.config),
            checkpoint=tup.checkpoint,
            metadata=tup.metadata,
            parent_config=self._unwrap_config(tup.parent_config) if tup.parent_config else None,
            pending_writes=tup.pending_writes,
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        wrapped = self._wrap_config(config)
        tup = self.base_checkpointer.get_tuple(wrapped)
        if tup is None:
            return None
        return self._unwrap_tuple(tup)

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        wrapped = self._wrap_config(config)
        tup = await self.base_checkpointer.aget_tuple(wrapped)
        if tup is None:
            return None
        return self._unwrap_tuple(tup)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        wrapped = self._wrap_config(config) if config is not None else None
        wrapped_before = self._wrap_config(before) if before is not None else None
        for tup in self.base_checkpointer.list(
            wrapped, filter=filter, before=wrapped_before, limit=limit
        ):
            yield self._unwrap_tuple(tup)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        wrapped = self._wrap_config(config) if config is not None else None
        wrapped_before = self._wrap_config(before) if before is not None else None
        async for tup in self.base_checkpointer.alist(
            wrapped, filter=filter, before=wrapped_before, limit=limit
        ):
            yield self._unwrap_tuple(tup)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        wrapped = self._wrap_config(config)
        res = self.base_checkpointer.put(wrapped, checkpoint, metadata, new_versions)
        return self._unwrap_config(res)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        wrapped = self._wrap_config(config)
        res = await self.base_checkpointer.aput(wrapped, checkpoint, metadata, new_versions)
        return self._unwrap_config(res)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        wrapped = self._wrap_config(config)
        from inspect import signature
        sig = signature(self.base_checkpointer.put_writes)
        if "task_path" in sig.parameters:
            self.base_checkpointer.put_writes(wrapped, writes, task_id, task_path=task_path)
        else:
            self.base_checkpointer.put_writes(wrapped, writes, task_id)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Any,
        task_id: str,
        task_path: str = "",
    ) -> None:
        wrapped = self._wrap_config(config)
        from inspect import signature
        sig = signature(self.base_checkpointer.aput_writes)
        if "task_path" in sig.parameters:
            await self.base_checkpointer.aput_writes(wrapped, writes, task_id, task_path=task_path)
        else:
            await self.base_checkpointer.aput_writes(wrapped, writes, task_id)

    def with_allowlist(self, extra_allowlist: Any) -> "NamespaceCheckpointer":
        cloned = self.base_checkpointer.with_allowlist(extra_allowlist)
        return NamespaceCheckpointer(cloned, self.target_ns)


def _build_skill_node(
    phase_id: str,
    phase_doc: PhaseDocument,
    phase_ast: AgentNodeAST,
    compiled: CompiledSkill,
    chat_model: Any,
    model_resolver: Any,
    max_patch_attempts: int,
    callbacks: Any | None,
    skill_resolver: SkillResolverProtocol,
    llm_provider: LLMProvider | None,
    _loading_stack: tuple[str, ...],
    _compilation_cache: dict[str, CompiledSkill],
    *,
    checkpointer: Any = None,
    predict_context: Any = None,
) -> Any:
    phase_chat_model = _resolve_phase_chat_model(
        phase_id,
        phase_ast,
        chat_model=chat_model,
        model_resolver=model_resolver,
        llm_provider=llm_provider,
        callbacks=_callback_tuple(callbacks),
        predict_context=predict_context,
    )
    knowledge_base_markdown = _build_reference_reader_markdown(
        phase_id=phase_id,
        phase_doc=phase_doc,
        phase_ast=phase_ast,
        compiled=compiled,
        callbacks=callbacks,
    )
    business_tools = compiled.tools.for_phase(phase_id)
    business_tools = [*business_tools, *_agent_resource_tools(phase_doc, phase_ast, compiled)]
    tool_by_name = {tool.name: tool for tool in business_tools}
    subagent_by_tool_name = _subagent_tool_map(phase_id, compiled)
    subagent_runtime_by_tool_name = _subagent_runtime_map(
        subagent_by_tool_name,
        chat_model=phase_chat_model,
        model_resolver=model_resolver,
        llm_provider=llm_provider,
        callbacks=callbacks,
        max_patch_attempts=max_patch_attempts,
        skill_resolver=skill_resolver,
        _loading_stack=_loading_stack,
        _compilation_cache=_compilation_cache,
    )
    framework_tools, critic_metrics = _build_framework_tools(
        phase_id=phase_id,
        tool_names=phase_ast.tools,
        tool_by_name=tool_by_name,
        chat_model=phase_chat_model,
    )

    output_schema = _terminal_output_schema(phase_id, compiled)
    finish_task = _build_agent_finish_task_tool(
        output_schema,
        chat_model=phase_chat_model,
        max_patch_attempts=max_patch_attempts,
    )
    has_finish_task = bool(phase_ast.tools and "finish_task" in phase_ast.tools)
    if has_finish_task:
        finish_task.return_direct = True
    class FrameworkStateProxyDict(dict[str, Any]):
        def __init__(self, obj: Any) -> None:
            super().__init__()
            self._obj = obj

        def __getitem__(self, key: Any) -> Any:
            if hasattr(self._obj, str(key)):
                return getattr(self._obj, str(key))
            raise KeyError(key)

        def __setitem__(self, key: Any, value: Any) -> None:
            if hasattr(self._obj, str(key)):
                setattr(self._obj, str(key), value)
            else:
                super().__setitem__(key, value)

        def get(self, key: Any, default: Any = None) -> Any:
            if hasattr(self._obj, str(key)):
                return getattr(self._obj, str(key))
            return default

        def setdefault(self, key: Any, default: Any = None) -> Any:
            if hasattr(self._obj, str(key)):
                val = getattr(self._obj, str(key))
                if val is None or (isinstance(val, dict) and not val):
                    setattr(self._obj, str(key), default)
                    return default
                return val
            return super().setdefault(key, default)

    rewired_business_tools = []
    for tool in business_tools:
        if tool.name in subagent_by_tool_name:
            subagent = subagent_by_tool_name[tool.name]
            runtime = subagent_runtime_by_tool_name.get(tool.name)

            def _make_dispatch(
                t_name: str = tool.name,
                sa: CompiledSubagent = subagent,
                rt: _SubagentRuntime | None = runtime,
            ) -> Callable[..., Any]:
                def dispatch_func(
                    inputs: Any,
                    state: Annotated[WorkflowState, InjectedState],
                    config: RunnableConfig | None = None,
                ) -> Any:
                    raw_inputs = []
                    for item in (inputs or []):
                        if hasattr(item, "model_dump"):
                            raw_inputs.append(item.model_dump())
                        elif hasattr(item, "dict"):
                            raw_inputs.append(item.dict())
                        else:
                            raw_inputs.append(item)
                    parent_state = parent_state_var.get(None)
                    raw_flow = parent_state["flow"] if parent_state else (state["flow"] if state else {})
                    flow = (
                        FrameworkStateProxyDict(raw_flow)
                        if (raw_flow is not None and not isinstance(raw_flow, dict))
                        else raw_flow
                    )
                    from typing import cast
                    return _invoke_subagent_tool_t21(
                        tool_name=t_name,
                        subagent=sa,
                        args={"inputs": raw_inputs},
                        state=parent_state if parent_state is not None else state,
                        flow=cast(dict[str, Any], flow),
                        runtime=rt,
                        parent_config=config,
                    )

                return dispatch_func

            if tool.args_schema is not None and not isinstance(tool.args_schema, dict):
                from pydantic import ConfigDict, Field, create_model
                inputs_desc = ""
                original_inputs_field = tool.args_schema.model_fields.get("inputs")
                if original_inputs_field and original_inputs_field.description:
                    inputs_desc = original_inputs_field.description

                new_args_schema = create_model(
                    tool.args_schema.__name__,
                    __config__=ConfigDict(extra="allow"),
                    inputs=(
                        list[Any],
                        Field(
                            default=...,
                            description=inputs_desc,
                            json_schema_extra={"items": subagent.expected_schema},
                        ),
                    ),
                )
                original_metadata = tool.metadata or {}
                metadata = {
                    "kind": "subagent",
                    "subagent_name": subagent.name,
                    "target_skill": subagent.target_skill,
                    "subagent_path": subagent.target_skill,
                    "subagent_root": str(subagent.root),
                    "expected_schema": subagent.expected_schema,
                }
                metadata.update(original_metadata)

                rewired_tool = StructuredTool.from_function(
                    func=_make_dispatch(),
                    name=tool.name,
                    description=tool.description or f"Call subagent {subagent.name}",
                    args_schema=new_args_schema,
                    metadata=metadata,
                )
                rewired_business_tools.append(rewired_tool)
            else:
                rewired_business_tools.append(tool)
        else:
            rewired_business_tools.append(tool)

    all_tools = [*rewired_business_tools, *framework_tools, finish_task]

    # Coerce output_schema if it's a dict to SchemaObject, then get Pydantic model
    from graph_agent.core.schema_engine import SchemaEngine
    engine = SchemaEngine()
    coerced_schema = output_schema
    if isinstance(output_schema, dict):
        coerced_schema = engine.parse_from_md(json.dumps(output_schema, ensure_ascii=False))

    current_phase_schema = coerced_schema
    if coerced_schema is not None:
        current_phase_schema = engine.get_pydantic_model(coerced_schema)

    from graph_agent.core.io_manager import IODef, IOManager
    from graph_agent.middleware.factory import build_middleware_chain
    io_specs = []
    if isinstance(output_schema, dict):
        properties = output_schema.get("properties")
        if isinstance(properties, dict):
            req_list = output_schema.get("required", [])
            for prop_name in properties:
                if isinstance(prop_name, str):
                    is_req = prop_name in req_list
                    io_specs.append(
                        IODef(
                            source_field="business_data_parsed",
                            target_field=prop_name,
                            hoist_path=f"business_data_parsed[0].{prop_name}",
                            required=is_req,
                        )
                    )

    middleware_chain = build_middleware_chain(
        io_manager=IOManager(io_specs),
        schema_engine=engine,
        current_phase_schema=current_phase_schema,
        phase_name=phase_id,
        unattended=False,  # dynamically resolved in middleware
        interrupt_fn=None,
        callbacks=_callback_tuple(callbacks),
        has_finish_task=has_finish_task,
    )

    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.errors import GraphRecursionError

    inner_checkpointer = checkpointer or InMemorySaver()
    wrapped_checkpointer = NamespaceCheckpointer(inner_checkpointer, f"agent:{phase_id}")

    agent_graph = create_agent(
        model=phase_chat_model,
        tools=all_tools,
        system_prompt=_agent_system_prompt(
            phase_id,
            phase_ast,
            compiled,
            knowledge_base_markdown=knowledge_base_markdown,
        ),
        middleware=middleware_chain,
        state_schema=WorkflowState,  # type: ignore[arg-type]
        checkpointer=wrapped_checkpointer,
    )


    def _skill_node(
        state: WorkflowState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any] | WorkflowState:
        if phase_chat_model is None:
            detail = "SKILL phase requires chat_model"
            raise SkillLoadError(
                detail,
                payload=make_error_payload("[F-v3-agent-llm-role-unknown]", detail),
            )

        from typing import cast
        inner_config: dict[str, Any] = {}
        if config is not None:
            inner_config = dict(config)
        inner_configurable = dict(inner_config.get("configurable", {}))

        thread_id = inner_configurable.get("thread_id") or state["flow"].thread_id or "default"
        inner_configurable["thread_id"] = thread_id
        inner_configurable["checkpoint_ns"] = f"agent:{phase_id}"
        inner_configurable["max_iterations"] = phase_ast.max_iterations
        inner_config["configurable"] = inner_configurable

        max_turns = phase_ast.max_iterations
        if hasattr(agent_graph, "get_graph"):
            all_nodes = [n for n in agent_graph.get_graph().nodes if n not in ("__start__", "__end__")]
            nodes_per_turn = len(all_nodes) if all_nodes else 6
        else:
            nodes_per_turn = 6
        inner_config["recursion_limit"] = max_turns * nodes_per_turn + 1

        token = parent_state_var.set(state)
        try:
            try:
                result = agent_graph.invoke(
                    {
                        "data": state["data"],
                        "flow": state["flow"],
                        "messages": state["messages"],
                    },
                    config=cast(RunnableConfig, inner_config),
                    # Nested AGENT invokes share the outer checkpointer; sync writes
                    # avoid LangGraph async checkpoint futures waiting on each other.
                    durability="sync",
                )  # type: ignore[call-overload]
            except GraphRecursionError:
                state_config = dict(inner_config)
                state_configurable = dict(state_config.get("configurable", {}))
                state_configurable["checkpoint_ns"] = ""
                state_config["configurable"] = state_configurable
                inner_state = agent_graph.get_state(cast(RunnableConfig, state_config))
                result = inner_state.values
        finally:
            parent_state_var.reset(token)

        from langchain_core.messages import AIMessage
        res_messages = (result or {}).get("messages") or []
        orig_messages = (state or {}).get("messages") or []
        orig_msg_count = len(orig_messages)
        new_messages = res_messages[orig_msg_count:]

        valid_tool_names = set(tool.name for tool in all_tools) | set(subagent_by_tool_name.keys())
        for msg in new_messages:
            if isinstance(msg, AIMessage):
                for tc in getattr(msg, "tool_calls", []) or []:
                    tc_name = tc.get("name")
                    if tc_name not in valid_tool_names:
                        _graph_fatal(f"LLM called unknown tool {tc_name!r} in phase {phase_id!r}")

        for i, msg in enumerate(new_messages):
            if isinstance(msg, AIMessage):
                input_tokens, output_tokens = _extract_token_usage(msg)
                _safe_emit_event(
                    callbacks,
                    LLMCallEvent(
                        phase_name=phase_id,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        messages=None,
                        response_data=None,
                    ),
                )
                for tc in getattr(msg, "tool_calls", []) or []:
                    tc_id = tc.get("id")
                    tc_name = tc.get("name")
                    tc_args = tc.get("args") or {}
                    tc_result = ""
                    for follow_msg in new_messages[i+1:]:
                        if getattr(follow_msg, "tool_call_id", None) == tc_id:
                            tc_result = str(follow_msg.content)
                            break
                    _safe_emit_event(
                        callbacks,
                        ToolCallEvent(
                            phase_name=phase_id,
                            tool_name=str(tc_name or ""),
                            args=tc_args if isinstance(tc_args, dict) else {},
                            result=tc_result,
                        ),
                    )

        if result is not None and isinstance(result, dict) and "flow" in result:
            retries = getattr(state["flow"], "subagent_validation_retries", {})
            if isinstance(result["flow"], dict):
                result["flow"]["subagent_validation_retries"] = retries
            else:
                result["flow"].subagent_validation_retries = retries
        return cast(dict[str, Any] | WorkflowState, result)

    return _skill_node


def _resolve_phase_chat_model(
    phase_id: str,
    phase_ast: AgentNodeAST,
    *,
    chat_model: Any,
    model_resolver: Any,
    llm_provider: LLMProvider | None,
    callbacks: tuple[Any, ...],
    predict_context: Any = None,
) -> Any:
    predict_strategy = getattr(predict_context, "strategy", None)
    if predict_strategy is not None:
        from graph_agent.core._predict_internal.interception import PredictGatewayChatModel

        role_name = phase_ast.llm_role or "graph_agent"
        return PredictGatewayChatModel(
            role_name,
            {"role_name": role_name},
            mock_strategy=predict_strategy,
            callbacks=callbacks,
            phase_name=phase_id,
        )
    if chat_model is not None:
        return chat_model
    if llm_provider is not None:
        return LLMProviderChatModel(
            provider=llm_provider,
            role=phase_ast.llm_role or "graph_agent",
            phase_name=phase_id,
            callbacks=callbacks,
        )
    if model_resolver is None:
        return None
    import inspect
    sig = inspect.signature(model_resolver.resolve)
    kwargs = {
        "callbacks": callbacks,
        "phase_name": phase_id,
    }
    if "predict_context" in sig.parameters:
        kwargs["predict_context"] = predict_context
    return model_resolver.resolve(
        phase_ast.llm_role or "graph_agent",
        **kwargs,
    )


def _callback_tuple(callbacks: Any | None) -> tuple[Any, ...]:
    if callbacks is None:
        return ()
    if isinstance(callbacks, tuple):
        return callbacks
    if isinstance(callbacks, list):
        return tuple(callbacks)
    emit = getattr(callbacks, "emit", None)
    if callable(emit):
        return (_EventSinkCallbackAdapter(callbacks),)
    raise TypeError(f"unsupported callbacks object: {type(callbacks).__name__}")


class _EventSinkCallbackAdapter:
    def __init__(self, sink: Any) -> None:
        self._sink = sink

    def on_event(self, event: Any) -> None:
        self._sink.emit(event)

    def emit(self, event: Any) -> None:
        self.on_event(event)


def _terminal_output_schema(phase_id: str, compiled: CompiledSkill) -> Any:
    if _is_terminal_phase(phase_id, compiled.manifest, compiled):
        return compiled.raw.get("io", {}).get("outputs")
    return None


def _build_agent_finish_task_tool(
    output_schema: Any,
    *,
    chat_model: Any,
    max_patch_attempts: int,
) -> Any:
    return build_finish_task_tool(
        output_schema if isinstance(output_schema, dict) else None,
        parse_finish_markdown,
        LLMMdPatchClient(chat_model) if chat_model is not None else None,
        max_patch_attempts=max_patch_attempts,
    )


def _build_framework_tools(
    *,
    phase_id: str,
    tool_names: list[str],
    tool_by_name: dict[str, Any],
    chat_model: Any,
) -> tuple[list[Any], dict[str, Any]]:
    framework_tools = []
    critic_metrics: dict[str, Any] = {}
    for tool_name in tool_names:
        if _is_critic_tool_name(tool_name):
            critic_tool, metrics = _build_critic_framework_tool(tool_name, chat_model)
            framework_tools.append(critic_tool)
            critic_metrics[tool_name] = metrics
            continue
        if tool_name == "finish_task":
            continue
        if tool_name not in tool_by_name:
            _graph_fatal(
                f"tool {tool_name!r} in SKILL phase {phase_id!r} not found in ToolRegistry "
                "and not a critic naming pattern"
            )
    return framework_tools, critic_metrics


def _build_critic_framework_tool(tool_name: str, chat_model: Any) -> tuple[Any, Any]:
    critic_client = (
        LLMCriticClient(chat_model)
        if chat_model is not None
        else FakeCriticClient(CriticVerdict(passed=True, reasons=["stub"]))
    )
    return build_critic_tool(
        tool_name,
        f"Review with {tool_name}",
        critic_client,
    )


def _bind_tools_if_supported(chat_model: Any, tools: list[Any]) -> Any:
    return chat_model.bind_tools(tools) if hasattr(chat_model, "bind_tools") else chat_model


def _subagent_tool_map(
    phase_id: str,
    compiled: CompiledSkill,
) -> dict[str, CompiledSubagent]:
    return {
        f"call_subagent_{subagent.name}": subagent
        for subagent in compiled.subagents_by_phase.get(phase_id, [])
    }


def _observable_data_context(state: WorkflowState) -> dict[str, Any]:
    data = state["data"].model_dump()
    phase_outputs: dict[str, dict[str, Any]] = {}
    if "answer" in data:
        phase_outputs["draft"] = {"answer": data["answer"]}
        phase_outputs["main"] = {"answer": data["answer"]}
    if "review" in data:
        phase_outputs["review"] = {"review": data["review"]}
    return {
        "inputs": data,
        "phase_outputs": phase_outputs,
        "scratch": state["flow"].working_memory or {},
    }


def _phase_end_context(
    phase_id: str,
    state: WorkflowState,
    response_state: dict[str, Any],
) -> dict[str, Any]:
    ctx = _observable_data_context(state)
    if hasattr(response_state, "model_dump"):
        response_state = response_state.model_dump()
    if isinstance(response_state, dict):
        # Extract only data/business updates
        data = response_state.get("data", {}) if "data" in response_state else response_state
        if hasattr(data, "model_dump"):
            data = data.model_dump()
        if isinstance(data, dict):
            if "phase_outputs" in data and isinstance(data["phase_outputs"], dict):
                for p_name, p_out in data["phase_outputs"].items():
                    if isinstance(p_out, dict):
                        if p_name not in ctx["phase_outputs"]:
                            ctx["phase_outputs"][p_name] = {}
                        ctx["phase_outputs"][p_name].update(p_out)
            else:
                # Merge flat updates
                initial_data = state["data"].model_dump()
                for k, v in data.items():
                    if k not in ("flow", "messages"):
                        if k not in initial_data or initial_data[k] != v:
                            if phase_id not in ctx["phase_outputs"]:
                                ctx["phase_outputs"][phase_id] = {}
                            ctx["phase_outputs"][phase_id][k] = v
                            if k == "answer":
                                ctx["phase_outputs"]["draft"] = {"answer": v}
                                ctx["phase_outputs"]["main"] = {"answer": v}
                            if k == "review":
                                ctx["phase_outputs"]["review"] = {"review": v}
    return ctx


def _extract_token_usage(response: Any) -> tuple[int, int]:
    metadata = getattr(response, "response_metadata", None)
    usage = metadata.get("token_usage") if isinstance(metadata, dict) else None
    if not isinstance(usage, dict):
        usage = metadata.get("usage") if isinstance(metadata, dict) else None
    if not isinstance(usage, dict):
        usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        return 0, 0
    input_tokens = _coerce_token_count(
        usage.get("input_tokens", usage.get("prompt_tokens", usage.get("total_input_tokens")))
    )
    output_tokens = _coerce_token_count(
        usage.get(
            "output_tokens",
            usage.get("completion_tokens", usage.get("total_output_tokens")),
        )
    )
    return input_tokens, output_tokens


def _coerce_token_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _stringify_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        return json.dumps(result, ensure_ascii=False, default=str)
    return str(result)


def _agent_system_prompt(
    phase_id: str,
    phase_ast: AgentNodeAST,
    compiled: CompiledSkill,
    *,
    knowledge_base_markdown: str = "",
) -> str:
    output_schema = (
        phase_ast.io.outputs
        if phase_ast.io is not None
        else compiled.raw.get("io", {}).get("outputs")
        if _is_terminal_phase(phase_id, compiled.manifest, compiled)
        else None
    )
    return apply_v030_cognitive_template(
        phase_name=phase_id,
        role=phase_ast.role,
        goal=phase_ast.goal,
        steps=[step.model_dump() for step in phase_ast.steps],
        protocols=[protocol.model_dump() for protocol in phase_ast.protocols],
        output_schema=output_schema if isinstance(output_schema, dict) else None,
        knowledge_base_markdown=knowledge_base_markdown,
        reference_registry_listing=_reference_registry_listing(phase_ast),
        inline_examples=[example.content for example in phase_ast.examples_inline],
        example_registry_listing=_example_registry_listing(phase_ast),
        role_prefix=resolve_role_prefix_from_llm_role(phase_ast.llm_role),
    )


def _reference_registry_listing(phase_ast: AgentNodeAST) -> str:
    lines = [f"- {item.id}: {item.summary}" for item in phase_ast.references]
    return "\n".join(lines) if lines else "无注册 Reference"


def _example_registry_listing(phase_ast: AgentNodeAST) -> str:
    lines = [f"- {item.id}: {item.summary}" for item in phase_ast.examples]
    return "\n".join(lines) if lines else "无扩展案例"


def _build_reference_reader_markdown(
    *,
    phase_id: str,
    phase_doc: PhaseDocument,
    phase_ast: AgentNodeAST,
    compiled: CompiledSkill,
    callbacks: Any | None = None,
) -> str:
    if not phase_ast.references:
        return ""
    root = _skill_root_for_phase_path(phase_doc.path)
    references = [item.model_dump() for item in phase_ast.references]
    runtime = ReferenceReaderRuntime(
        skill_id=compiled.manifest.name,
        phase_id=phase_id,
        root=root,
        references=references,
        max_output_tokens=3000,
        language="zh",
        timeout_s=60,
    )
    _emit_builtin_subagent_event(
        callbacks,
        BuiltinSubagentEnterEvent(
            run_id=None,
            phase_name=phase_id,
            builtin_name="reference_reader",
            payload={"reference_ids": _reference_ids(references)},
        ),
    )
    try:
        result = runtime.run() if hasattr(runtime, "run") else runtime.initial_state()
        markdown = result.get("markdown") if isinstance(result, dict) else None
        if isinstance(markdown, str) and markdown.strip():
            _emit_builtin_subagent_event(
                callbacks,
                BuiltinSubagentExitEvent(
                    run_id=None,
                    phase_name=phase_id,
                    builtin_name="reference_reader",
                    payload={
                        "reference_ids": _reference_ids(references),
                        "markdown_length": len(markdown),
                    },
                ),
            )
            return markdown
        reason = "empty reader output"
        _emit_reference_reader_fallback(
            callbacks,
            phase_id=phase_id,
            reason="invalid_output",
            warning=reason,
        )
        return _fallback_reference_reader_markdown(root, references, reason)
    except GraphAgentFatalError as exc:
        if (
            exc.payload is not None
            and exc.payload.code == "[F-v3-resource-reference-path-invalid]"
        ):
            raise
        logger.warning("[F-v3-reference-reader-failed] %s", exc)
        _emit_reference_reader_fallback(
            callbacks,
            phase_id=phase_id,
            reason=_fallback_reason_from_exception(exc),
            warning=str(exc),
        )
        return _fallback_reference_reader_markdown(root, references, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[F-v3-reference-reader-failed] %s", exc)
        _emit_reference_reader_fallback(
            callbacks,
            phase_id=phase_id,
            reason=_fallback_reason_from_exception(exc),
            warning=str(exc),
        )
        return _fallback_reference_reader_markdown(root, references, str(exc))


def _emit_reference_reader_fallback(
    callbacks: Any | None,
    *,
    phase_id: str,
    reason: str,
    warning: str,
) -> None:
    _emit_builtin_subagent_event(
        callbacks,
        BuiltinSubagentFallbackEvent(
            run_id=None,
            phase_name=phase_id,
            builtin_name="reference_reader",
            fallback_reason=reason,  # type: ignore[arg-type]
            fallback_strategy="raw_excerpt_3000_tokens",
            excerpt_token_limit=3000,
            warning=_short_warning(warning),
        ),
    )


def _emit_builtin_subagent_event(callbacks: Any | None, event: Any) -> None:
    _safe_emit_event(callbacks, event)


def _fallback_reason_from_exception(exc: BaseException) -> str:
    text = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in text or "timed out" in text:
        return "remote_timeout"
    if isinstance(exc, OSError):
        return "local_io_error"
    if "missing config" in text or "config_missing" in text:
        return "config_missing"
    if "invalid" in text or "empty" in text or "missing markdown" in text:
        return "invalid_output"
    return "remote_error"


def _short_warning(warning: str, limit: int = 500) -> str:
    text = f"[F-v3-reference-reader-failed] {warning}"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _reference_ids(references: list[dict[str, Any]]) -> list[str]:
    return [str(spec.get("id")) for spec in references if spec.get("id") is not None]


def _fallback_reference_reader_markdown(
    root: Path,
    references: list[dict[str, Any]],
    reason: str,
) -> str:
    chunks = [f"[F-v3-reference-reader-failed] {reason}"]
    for spec in references:
        body = read_resource_file(
            root=root,
            relative_path=str(spec.get("path", "")),
            code="[F-v3-resource-reference-path-invalid]",
        )
        chunks.append(
            "系统无法完成知识精炼，以下为原始未处理片段\n"
            f"## {spec.get('id')}: {spec.get('summary', '')}\n\n"
            f"{_truncate_tokens(body, 3000)}"
        )
    return "\n\n".join(chunks)


def _truncate_tokens(text: str, max_tokens: int) -> str:
    tokens = text.split()
    if len(tokens) <= max_tokens:
        return text
    return " ".join(tokens[:max_tokens])


def _agent_resource_tools(
    phase_doc: PhaseDocument,
    phase_ast: AgentNodeAST,
    compiled: CompiledSkill,
) -> list[Any]:
    root = _skill_root_for_phase_path(phase_doc.path)
    references = {item.id: item for item in phase_ast.references}
    examples = {item.id: item for item in phase_ast.examples}

    def read_reference(reference_id: Any, query: Any = "", mode: Any = "excerpt") -> str:
        return read_declared_reference(
            root=root,
            references=references,
            reference_id=reference_id,
            query=query,
            mode=mode,
        )

    def read_example(example_id: Any, query: Any = "") -> str:
        return read_declared_example(root=root, examples=examples, example_id=example_id, query=query)

    tools: list[Any] = [
        ToolDef(
            id="read_reference",
            phase_id=phase_doc.phase_name,
            path=phase_doc.path,
            func=read_reference,
            description="Read one declared reference by id.",
        ),
        ToolDef(
            id="read_example",
            phase_id=phase_doc.phase_name,
            path=phase_doc.path,
            func=read_example,
            description="Read one declared example by id.",
        )
    ]
    return [_structured_tool(tool) for tool in tools]


def _build_reference_reader_node(*, root: Path, phase_id: str) -> Any:
    def _reference_reader_node(state: WorkflowState) -> dict[str, Any]:
        inputs = phase_inputs_from_state(state)
        path = inputs.get("path")
        if not isinstance(path, str):
            detail = "missing reference path"
            raise GraphAgentFatalError(
                detail,
                payload=make_error_payload("[F-v3-reference-reader-failed]", detail),
            )
        return {"data": {"content": _read_skill_root_file(root, path)}}

    return PhaseWrapper(
        StateMapper(phase_id=phase_id),
        node_kind="reference_reader",
    ).wrap(_reference_reader_node)


def _skill_root_for_phase_path(path: Path) -> Path:
    try:
        phase_index = path.parts.index("phases")
    except ValueError:
        return path.parent
    return Path(*path.parts[:phase_index])


def _read_skill_root_file(root: Path, relative_path: str) -> str:
    return read_resource_file(
        root=root,
        relative_path=relative_path,
        code="[F-v3-resource-reference-path-invalid]",
    )


def _invoke_subagent_tool_t21(
    *,
    tool_name: str,
    subagent: CompiledSubagent,
    args: dict[str, Any],
    state: WorkflowState | None = None,
    flow: dict[str, Any],
    runtime: _SubagentRuntime | None = None,
    parent_config: RunnableConfig | None = None,
) -> dict[str, Any]:
    try:
        assert_subagent_depth_allowed(current_subagent_depth(flow))
    except RuntimeError as exc:
        raise GraphAgentFatalError(str(exc)) from exc
    retry_counts = flow.setdefault("subagent_validation_retries", {})
    if not isinstance(retry_counts, dict):
        retry_counts = {}
        flow["subagent_validation_retries"] = retry_counts
    retry_count = int(retry_counts.get(tool_name, 0)) + 1
    try:
        validation = validate_subagent_tool_args(
            tool_name=tool_name,
            subagent_name=subagent.name,
            input_model=subagent.input_model,
            expected_schema=subagent.expected_schema,
            args=args,
            retry_count=retry_count,
        )
    except RuntimeError as exc:
        logger.error(
            "subagent validation retry limit exceeded",
            extra={
                "tool_name": tool_name,
                "parent_run_id": state["flow"].run_id if state is not None else None,
                "retry_count": retry_count,
                "expected_schema": subagent.expected_schema,
            },
        )
        raise GraphAgentFatalError(str(exc)) from exc
    if isinstance(validation, SubagentValidationFailure):
        retry_counts[tool_name] = retry_count
        return validation.to_tool_result()
    retry_counts.pop(tool_name, None)
    if runtime is not None and state is not None:
        return {
            "ok": True,
            "tool_name": tool_name,
            "subagent_name": subagent.name,
            "results": _invoke_subagent_many_t24(
                runtime,
                state,
                [item.model_dump() for item in validation],
                parent_config=parent_config,
                depth=current_subagent_depth(flow),
            ),
        }
    return {
        "ok": True,
        "tool_name": tool_name,
        "subagent_name": subagent.name,
        "inputs": [item.model_dump() for item in validation],
    }


def _subagent_runtime_map(
    subagent_by_tool_name: dict[str, CompiledSubagent],
    *,
    chat_model: Any,
    model_resolver: Any,
    llm_provider: LLMProvider | None,
    callbacks: Any | None,
    max_patch_attempts: int,
    skill_resolver: SkillResolverProtocol,
    _loading_stack: tuple[str, ...] = (),
    _compilation_cache: dict[str, CompiledSkill] | None = None,
) -> dict[str, _SubagentRuntime]:
    if _compilation_cache is None:
        _compilation_cache = {}
    runtimes: dict[str, _SubagentRuntime] = {}
    for tool_name, subagent in subagent_by_tool_name.items():
        sub_root_key = str(Path(subagent.root).resolve())
        sub_compiled = _compilation_cache.get(sub_root_key)
        if sub_compiled is None:
            sub_compiled = SkillLoader(validate_context_writes=False).compile_skill(
                subagent.root,
                skill_resolver=skill_resolver,
                _loading_stack=_loading_stack,
                _compilation_cache=_compilation_cache,
            )
        sub_assembled = assemble_graph(
            sub_compiled,
            chat_model=chat_model,
            model_resolver=model_resolver,
            llm_provider=llm_provider,
            callbacks=callbacks,
            max_patch_attempts=max_patch_attempts,
            skill_resolver=skill_resolver,
            _loading_stack=_loading_stack,
            _compilation_cache=_compilation_cache,
        )
        runtimes[tool_name] = _SubagentRuntime(subagent=subagent, graph=sub_assembled.graph)
    return runtimes


def _invoke_subagent_once_t23(
    runtime: _SubagentRuntime,
    parent_state: WorkflowState,
    input_data: dict[str, Any],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    child_flow_dict = _child_flow(parent_state["flow"])
    child_flow = FrameworkState.model_validate(child_flow_dict)
    result = runtime.graph.invoke(
        WorkflowState(
            data=BusinessData.model_validate(dict(input_data)),
            flow=child_flow,
            messages=[],
        ),
        config=config,
    )
    child_final_data = result["data"].model_dump()
    data_delta = _dict_delta(dict(input_data), child_final_data)
    return {
        "status": "ok",
        "data": data_delta,
        "flow": result["flow"],
    }


def _child_flow(parent_flow: FrameworkState | dict[str, Any]) -> dict[str, Any]:
    if isinstance(parent_flow, dict):
        flow = dict(parent_flow)
    else:
        flow = parent_flow.model_dump()
    flow["subagent_depth"] = current_subagent_depth(flow) + 1
    return flow


def _invoke_subagent_many_t24(
    runtime: _SubagentRuntime,
    parent_state: WorkflowState,
    inputs: list[dict[str, Any]],
    *,
    parent_config: RunnableConfig | None,
    depth: int,
    concurrency: int = 3,
) -> list[dict[str, Any]]:
    async def _run_all() -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(concurrency)

        async def _run_one(index: int, input_data: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                child_config = _subagent_runnable_config(
                    parent_state=parent_state,
                    parent_config=parent_config,
                    subagent_name=runtime.subagent.name,
                    depth=depth,
                )
                child_run_id = str(child_config.get("run_id", ""))
                try:
                    result = await asyncio.to_thread(
                        _invoke_subagent_once_t23,
                        runtime,
                        parent_state,
                        input_data,
                        child_config,
                    )
                except Exception as exc:
                    logger.exception(
                        "subagent item failed",
                        extra={
                            "subagent_name": runtime.subagent.name,
                            "input_index": index,
                            "parent_run_id": parent_state["flow"].run_id,
                            "child_run_id": child_run_id,
                        },
                    )
                    return {
                        "index": index,
                        "status": "error",
                        "subagent_name": runtime.subagent.name,
                        "error": str(exc),
                        "parent_run_id": parent_state["flow"].run_id,
                        "child_run_id": child_run_id,
                    }
                return {
                    "index": index,
                    "status": "ok",
                    "subagent_name": runtime.subagent.name,
                    "data": result.get("data", {}),
                    "flow": result.get("flow", {}),
                    "parent_run_id": parent_state["flow"].run_id,
                    "child_run_id": child_run_id,
                }

        return await asyncio.gather(*[_run_one(index, item) for index, item in enumerate(inputs)])

    return asyncio.run(_run_all())


def _subagent_runnable_config(
    *,
    parent_state: WorkflowState,
    parent_config: RunnableConfig | None,
    subagent_name: str,
    depth: int,
) -> RunnableConfig:
    parent_tags = list((parent_config or {}).get("tags") or [])
    parent_metadata = dict((parent_config or {}).get("metadata") or {})
    parent_run_id = str(parent_state["flow"].run_id or parent_metadata.get("run_id") or "")
    metadata = {
        **parent_metadata,
        "parent_run_id": parent_run_id,
        "subagent_depth": depth + 1,
    }
    callbacks = (parent_config or {}).get("callbacks")
    config: RunnableConfig = {
        "tags": [*parent_tags, "subagent", subagent_name],
        "run_id": uuid.uuid4(),
        "metadata": metadata,
    }
    if callbacks is not None:
        config["callbacks"] = callbacks
    return config


def _dict_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in after.items() if key not in before or before[key] != value}


def _deterministic_child_phase_outputs(
    phase_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    data_delta: dict[str, Any] = {}
    for phase_id in sorted(phase_outputs):
        for key, value in phase_outputs[phase_id].items():
            if key in data_delta:
                detail = f"duplicate child output key {key!r} from phase {phase_id!r}"
                raise GraphAgentFatalError(
                    detail,
                    payload=make_error_payload(
                        "[F-v3-runtime-state-mapping-failed]", detail
                    ),
                )
            data_delta[key] = value
    return data_delta


def _logic_output_schema_keys(compiled: CompiledSkill) -> set[str] | None:
    raw_keys = compiled.raw.get("io", {}).get("output_schema_keys")
    if raw_keys is None:
        return None
    if not isinstance(raw_keys, list):
        return set()
    return {key for key in raw_keys if isinstance(key, str)}


def _schema_output_keys(schema: dict[str, Any] | None) -> set[str] | None:
    if schema is None:
        return None
    properties = schema.get("properties")
    if properties is None:
        return None
    if not isinstance(properties, dict):
        return set()
    return {key for key in properties if isinstance(key, str)}


def _validate_logic_update_keys(
    updates: dict[str, Any],
    output_schema_keys: set[str] | None,
    action_path: Path,
    action_line: int,
) -> None:
    if output_schema_keys is None:
        return
    for key in updates:
            if key not in output_schema_keys:
                detail = (
                    f"{action_path}:{action_line} action wrote undeclared output key {key!r}"
                )
                raise GraphAgentFatalError(
                    detail,
                    payload=make_error_payload(
                        "[F-v3-logic-output-field-undeclared]", detail
                    ),
                )


def _is_terminal_phase(
    phase_id: str,
    manifest: GraphManifest,
    compiled: CompiledSkill | None = None,
) -> bool:
    if compiled is None:
        return phase_id in manifest.phases
    return phase_id in _terminal_phase_ids(manifest, compiled)


def _terminal_phase_ids(
    manifest: GraphManifest, compiled: CompiledSkill | None = None
) -> list[str]:
    if compiled is None:
        return list(manifest.phases)
    topology = _graph_topology(compiled)
    outputs = [
        str(row["name"])
        for row in compiled.raw.get("graph_topology", {}).get("phases", [])
        if isinstance(row, dict) and row.get("output") is True
    ]
    if outputs:
        return outputs
    depended = {dep for deps in topology.values() for dep in deps if dep != "input"}
    return [phase for phase in topology if phase not in depended]


def _graph_topology(compiled: CompiledSkill) -> dict[str, list[str]]:
    rows = compiled.raw.get("graph_topology", {}).get("phases", [])
    if isinstance(rows, list) and rows:
        topology: dict[str, list[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            deps = row.get("depends_on")
            if isinstance(name, str) and isinstance(deps, list):
                topology[name] = [dep for dep in deps if isinstance(dep, str)]
        if topology:
            return topology
    return {phase: ["input"] for phase in compiled.manifest.phases}


def _is_critic_tool_name(name: str) -> bool:
    lower = name.lower()
    return any(keyword in lower for keyword in ("critic", "reviewer", "auditor"))


def _graph_fatal(message: str) -> NoReturn:
    raise SkillLoadError(
        message,
        payload=make_error_payload("[F-v3-graph-schema-unknown-field]", message),
    )


__all__ = [
    "CompiledStateGraph",
    "assemble_graph",
    "_is_terminal_phase",
    "_terminal_phase_ids",
]
