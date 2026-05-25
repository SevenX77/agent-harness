"""V2.1 CompiledSkill to LangGraph assembly."""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from graph_agent.cognitive.context_facade import Context
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
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.loader import CompiledSkill, CompiledSubagent, PhaseDocument, SkillLoader
from graph_agent.core.manifest import (
    AgentNodeAST,
    GraphManifest,
    LogicNodeAST,
    SkillNodeAST,
    SubgraphNodeAST,
)
from graph_agent.core.skill_resolver_protocol import (
    SkillResolverProtocol,
    require_skill_resolver,
    resolve_skill_root,
)
from graph_agent.core.subagents import (
    SubagentValidationFailure,
    assert_subagent_depth_allowed,
    current_subagent_depth,
    validate_subagent_tool_args,
)
from graph_agent.middleware.factory import build_middleware_chain_cognitive_flow
from graph_agent.runtime.exit_contract import inject_exit_contract
from graph_agent.runtime.state import BlackboardState
from graph_agent.runtime.state_mapper import PhaseWrapper, StateMapper

MAX_REACT_TURNS = 8
logger = logging.getLogger(__name__)


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


def assemble_graph(
    compiled: CompiledSkill,
    *,
    chat_model: Any = None,
    max_patch_attempts: int = 3,
    skill_resolver: SkillResolverProtocol,
) -> CompiledStateGraph:
    """Assemble a V2.1 CompiledSkill into a compiled LangGraph."""

    resolver = require_skill_resolver(skill_resolver, caller="assemble_graph")
    builder = StateGraph(BlackboardState)
    node_by_phase = {node.phase_name: node for node in compiled.nodes}
    phase_ids: list[str] = []
    edges: list[tuple[str, str]] = []

    for phase_ref in compiled.manifest.phases:
        phase_doc = node_by_phase.get(phase_ref.id)
        if phase_doc is None:
            _graph_fatal(f"phase {phase_ref.id!r} has no parsed node")
        builder.add_node(
            phase_ref.id,
            _build_phase_node(
                phase_ref.id,
                phase_doc,
                compiled,
                chat_model,
                max_patch_attempts,
                resolver,
            ),
        )
        phase_ids.append(phase_ref.id)

    for phase_ref in compiled.manifest.phases:
        if not phase_ref.depends_on:
            builder.add_edge(START, phase_ref.id)
            edges.append(("START", phase_ref.id))
        else:
            for dep in phase_ref.depends_on:
                builder.add_edge(dep, phase_ref.id)
                edges.append((dep, phase_ref.id))

    for phase_id in _terminal_phase_ids(compiled.manifest):
        builder.add_edge(phase_id, END)
        edges.append((phase_id, "END"))

    return CompiledStateGraph(
        graph=builder.compile(),
        compiled_skill=compiled,
        phase_ids=phase_ids,
        edges=edges,
    )


def _build_phase_node(
    phase_id: str,
    phase_doc: PhaseDocument,
    compiled: CompiledSkill,
    chat_model: Any,
    max_patch_attempts: int,
    skill_resolver: SkillResolverProtocol,
) -> Any:
    ast = phase_doc.ast
    if isinstance(ast, LogicNodeAST):
        return _wrap_phase_runtime_node(ast, _build_logic_node(phase_id, ast, compiled))
    if isinstance(ast, SubgraphNodeAST):
        return _wrap_phase_runtime_node(
            ast,
            _build_subgraph_node(
                phase_doc,
                ast,
                chat_model,
                max_patch_attempts,
                skill_resolver,
            ),
        )
    if isinstance(ast, (AgentNodeAST, SkillNodeAST)):
        return _wrap_phase_runtime_node(
            ast,
            _build_skill_node(
                phase_id,
                phase_doc,
                ast,
                compiled,
                chat_model,
                max_patch_attempts,
                skill_resolver,
            ),
        )
    _graph_fatal(f"unknown phase mode for {phase_id!r}")


def _wrap_phase_runtime_node(phase_ast: Any, node: Any) -> Any:
    io = getattr(phase_ast, "io", None)
    if io is None:
        return node
    return PhaseWrapper(StateMapper(io.inputs, io.outputs)).wrap(node)


def _build_logic_node(
    phase_id: str,
    phase_ast: LogicNodeAST,
    compiled: CompiledSkill,
) -> Any:
    action = compiled.actions.resolve(phase_id, phase_ast.python_callable)
    action_def = compiled.actions.for_phase(phase_id).get(phase_ast.python_callable)
    action_path = action_def.path if action_def is not None else Path("<unknown>")
    action_line = getattr(getattr(action, "__code__", None), "co_firstlineno", 1)
    output_schema_keys = _logic_output_schema_keys(compiled)

    def _logic_node(state: BlackboardState) -> dict[str, Any]:
        before = dict(state.get("data", {}))
        data = dict(before)
        ctx = Context(data, phase_id=phase_id, run_id=state.get("run_id") or "default")
        result = action(ctx)
        updates = _dict_delta(before, data)
        if isinstance(result, dict):
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
) -> Any:
    sub_root = resolve_skill_root(skill_resolver, phase_ast.target_skill)
    sub_compiled = SkillLoader(validate_context_writes=False).compile_skill(
        sub_root,
        skill_resolver=skill_resolver,
    )
    sub_assembled = assemble_graph(
        sub_compiled,
        chat_model=chat_model,
        max_patch_attempts=max_patch_attempts,
        skill_resolver=skill_resolver,
    )

    def _subgraph_node(state: BlackboardState) -> dict[str, Any]:
        before_data = dict(state.get("data", {}))
        result = sub_assembled.graph.invoke(
            {
                "data": before_data,
                "flow": state.get("flow", {}),
                "messages": [],
                "run_id": state.get("run_id"),
            }
        )
        result_data = result.get("data", before_data)
        data_updates = (
            _dict_delta(before_data, result_data) if isinstance(result_data, dict) else {}
        )
        return {
            "data": data_updates,
            "flow": result.get("flow", state.get("flow", {})),
        }

    return _subgraph_node


def _build_skill_node(
    phase_id: str,
    phase_doc: PhaseDocument,
    phase_ast: AgentNodeAST | SkillNodeAST,
    compiled: CompiledSkill,
    chat_model: Any,
    max_patch_attempts: int,
    skill_resolver: SkillResolverProtocol,
) -> Any:
    business_tools = compiled.tools.for_phase(phase_id)
    if isinstance(phase_ast, AgentNodeAST):
        business_tools = [*business_tools, *_agent_resource_tools(phase_doc, phase_ast)]
    tool_by_name = {tool.name: tool for tool in business_tools}
    subagent_by_tool_name = _subagent_tool_map(phase_id, compiled)
    subagent_runtime_by_tool_name = _subagent_runtime_map(
        subagent_by_tool_name,
        chat_model=chat_model,
        max_patch_attempts=max_patch_attempts,
        skill_resolver=skill_resolver,
    )
    framework_tools = []
    critic_metrics: dict[str, Any] = {}

    for tool_name in phase_ast.tools:
        if _is_critic_tool_name(tool_name):
            critic_client = (
                LLMCriticClient(chat_model)
                if chat_model is not None
                else FakeCriticClient(CriticVerdict(passed=True, reasons=["stub"]))
            )
            critic_tool, metrics = build_critic_tool(
                tool_name,
                f"Review with {tool_name}",
                critic_client,
            )
            framework_tools.append(critic_tool)
            critic_metrics[tool_name] = metrics
        elif tool_name == "finish_task":
            continue
        elif tool_name not in tool_by_name:
            _graph_fatal(
                f"tool {tool_name!r} in SKILL phase {phase_id!r} not found in ToolRegistry "
                "and not a critic naming pattern"
            )

    output_schema = (
        compiled.raw.get("io", {}).get("outputs")
        if _is_terminal_phase(phase_id, compiled.manifest)
        else None
    )
    finish_task = build_finish_task_tool(
        output_schema if isinstance(output_schema, dict) else None,
        parse_finish_markdown,
        LLMMdPatchClient(chat_model) if chat_model is not None else None,
        max_patch_attempts=max_patch_attempts,
    )
    all_tools = [*business_tools, *framework_tools, finish_task]
    all_tools_by_name = {tool.name: tool for tool in all_tools}
    cognitive_flow = build_middleware_chain_cognitive_flow(phase_name=phase_id)

    def _skill_node(
        state: BlackboardState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        if chat_model is None:
            raise RuntimeError("[F-v3-graph] SKILL phase requires chat_model")

        data_updates: dict[str, Any] = {}
        flow = dict(state.get("flow", {}))
        messages = [
            SystemMessage(content=_agent_system_prompt(phase_id, phase_ast, compiled)),
            *state.get("messages", []),
        ]
        model = (
            chat_model.bind_tools(all_tools) if hasattr(chat_model, "bind_tools") else chat_model
        )

        max_turns = (
            phase_ast.max_iterations if isinstance(phase_ast, AgentNodeAST) else MAX_REACT_TURNS
        )
        for _ in range(max_turns):
            prompt_messages = (
                messages
                if isinstance(phase_ast, AgentNodeAST)
                else inject_exit_contract(messages, phase_ast.exit_contract)
            )
            response = model.invoke(prompt_messages)
            messages = [*prompt_messages, response]
            tool_calls = list(getattr(response, "tool_calls", []) or [])
            if not tool_calls:
                break
            for call in tool_calls:
                name = call.get("name")
                tool = all_tools_by_name.get(name)
                if tool is None:
                    _graph_fatal(f"LLM called unknown tool {name!r} in phase {phase_id!r}")
                call_args = call.get("args", {})
                if name in subagent_by_tool_name:
                    result = _invoke_subagent_tool_t21(
                        tool_name=name,
                        subagent=subagent_by_tool_name[name],
                        args=call_args if isinstance(call_args, dict) else {},
                        state=state,
                        flow=flow,
                        runtime=subagent_runtime_by_tool_name[name],
                        parent_config=config,
                    )
                else:
                    result = tool.invoke(call_args)
                messages.append(
                    ToolMessage(
                        content=json.dumps(result, ensure_ascii=False),
                        name=name,
                        tool_call_id=call.get("id", f"{name}-call"),
                    )
                )
                finish_response = cognitive_flow.handle_finish_task_tool_result(
                    tool_name=str(name or ""),
                    tool_result=result,
                    output_schema=output_schema if isinstance(output_schema, dict) else None,
                    flow=flow,
                    messages=messages,
                    critic_metrics=critic_metrics,
                )
                if finish_response is not None:
                    return finish_response
        response_state = {"flow": flow, "messages": messages}
        if data_updates:
            response_state["data"] = data_updates
        return response_state

    return _skill_node

def _subagent_tool_map(
    phase_id: str,
    compiled: CompiledSkill,
) -> dict[str, CompiledSubagent]:
    return {
        f"call_subagent_{subagent.name}": subagent
        for subagent in compiled.subagents_by_phase.get(phase_id, [])
    }


def _agent_system_prompt(
    phase_id: str,
    phase_ast: AgentNodeAST | SkillNodeAST,
    compiled: CompiledSkill,
) -> str:
    if not isinstance(phase_ast, AgentNodeAST):
        return phase_ast.system_prompt
    output_schema = (
        phase_ast.io.outputs
        if phase_ast.io is not None
        else compiled.raw.get("io", {}).get("outputs")
        if _is_terminal_phase(phase_id, compiled.manifest)
        else None
    )
    return apply_v030_cognitive_template(
        phase_name=phase_id,
        role=phase_ast.role,
        goal=phase_ast.goal,
        steps=[step.model_dump() for step in phase_ast.steps],
        protocols=[protocol.model_dump() for protocol in phase_ast.protocols],
        output_schema=output_schema if isinstance(output_schema, dict) else None,
        inline_examples=[
            example.content
            for example in phase_ast.examples
            if example.type == "inline" and example.content
        ],
        document_examples=[
            {"id": example.id, "summary": example.summary or ""}
            for example in phase_ast.examples
            if example.type == "document"
        ],
        role_prefix=resolve_role_prefix_from_llm_role(phase_ast.llm_role),
    )


def _agent_resource_tools(
    phase_doc: PhaseDocument,
    phase_ast: AgentNodeAST,
) -> list[Any]:
    root = _skill_root_for_phase_path(phase_doc.path)
    references = {item.id: item for item in phase_ast.references}
    examples = {item.id: item for item in phase_ast.examples}

    def read_reference(reference_id: str) -> str:
        spec = references.get(reference_id)
        if spec is None:
            raise GraphAgentFatalError(f"[F-v3-resource-reference-id-invalid] {reference_id!r}")
        return _read_skill_root_file(root, spec.path)

    def read_example(example_id: str) -> str:
        spec = examples.get(example_id)
        if spec is None:
            raise GraphAgentFatalError(f"[F-v3-resource-example-invalid] {example_id!r}")
        if spec.type == "inline":
            return spec.content or ""
        if spec.path is None:
            raise GraphAgentFatalError(f"[F-v3-resource-example-path-invalid] {example_id!r}")
        return _read_skill_root_file(root, spec.path)

    tools: list[Any] = []
    if references:
        tools.append(
            ToolDef(
                id="read_reference",
                phase_id=phase_doc.phase_name,
                path=phase_doc.path,
                func=read_reference,
                description="Read one declared reference by id.",
            )
        )
    if examples:
        tools.append(
            ToolDef(
                id="read_example",
                phase_id=phase_doc.phase_name,
                path=phase_doc.path,
                func=read_example,
                description="Read one declared example by id.",
            )
        )
    return [_structured_tool(tool) for tool in tools]


def _skill_root_for_phase_path(path: Path) -> Path:
    try:
        phase_index = path.parts.index("phases")
    except ValueError:
        return path.parent
    return Path(*path.parts[:phase_index])


def _read_skill_root_file(root: Path, relative_path: str) -> str:
    candidate = (root / relative_path).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise GraphAgentFatalError(
            f"[F-v3-resource-reference-path-invalid] {relative_path!r} escapes skill root"
        ) from exc
    if not candidate.is_file():
        raise GraphAgentFatalError(
            f"[F-v3-resource-reference-path-invalid] {relative_path!r} is not readable"
        )
    return candidate.read_text(encoding="utf-8")


def _invoke_subagent_tool_t21(
    *,
    tool_name: str,
    subagent: CompiledSubagent,
    args: dict[str, Any],
    state: BlackboardState | None = None,
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
    retry_counts[tool_name] = retry_count
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
                "parent_run_id": state.get("run_id") if state is not None else None,
                "retry_count": retry_count,
                "expected_schema": subagent.expected_schema,
            },
        )
        raise GraphAgentFatalError(str(exc)) from exc
    if isinstance(validation, SubagentValidationFailure):
        return validation.to_tool_result()
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
    max_patch_attempts: int,
    skill_resolver: SkillResolverProtocol,
) -> dict[str, _SubagentRuntime]:
    runtimes: dict[str, _SubagentRuntime] = {}
    for tool_name, subagent in subagent_by_tool_name.items():
        sub_compiled = SkillLoader(validate_context_writes=False).compile_skill(
            subagent.root,
            skill_resolver=skill_resolver,
        )
        sub_assembled = assemble_graph(
            sub_compiled,
            chat_model=chat_model,
            max_patch_attempts=max_patch_attempts,
            skill_resolver=skill_resolver,
        )
        runtimes[tool_name] = _SubagentRuntime(subagent=subagent, graph=sub_assembled.graph)
    return runtimes


def _invoke_subagent_once_t23(
    runtime: _SubagentRuntime,
    parent_state: BlackboardState,
    input_data: dict[str, Any],
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    before_data = dict(parent_state.get("data", {}))
    child_data = {**before_data, **input_data}
    result = runtime.graph.invoke(
        {
            "data": child_data,
            "flow": parent_state.get("flow", {}),
            "messages": [],
            "run_id": parent_state.get("run_id"),
        },
        config=config,
    )
    result_data = result.get("data", child_data)
    data_delta = _dict_delta(before_data, result_data) if isinstance(result_data, dict) else {}
    return {
        "status": "ok",
        "data": data_delta,
        "flow": result.get("flow", parent_state.get("flow", {})),
    }


def _invoke_subagent_many_t24(
    runtime: _SubagentRuntime,
    parent_state: BlackboardState,
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
                            "parent_run_id": parent_state.get("run_id"),
                            "child_run_id": child_run_id,
                        },
                    )
                    return {
                        "index": index,
                        "status": "error",
                        "subagent_name": runtime.subagent.name,
                        "error": str(exc),
                        "parent_run_id": parent_state.get("run_id"),
                        "child_run_id": child_run_id,
                    }
                return {
                    "index": index,
                    "status": "ok",
                    "subagent_name": runtime.subagent.name,
                    "data": result.get("data", {}),
                    "flow": result.get("flow", {}),
                    "parent_run_id": parent_state.get("run_id"),
                    "child_run_id": child_run_id,
                }

        return await asyncio.gather(*[_run_one(index, item) for index, item in enumerate(inputs)])

    return asyncio.run(_run_all())


def _subagent_runnable_config(
    *,
    parent_state: BlackboardState,
    parent_config: RunnableConfig | None,
    subagent_name: str,
    depth: int,
) -> RunnableConfig:
    parent_tags = list((parent_config or {}).get("tags") or [])
    parent_metadata = dict((parent_config or {}).get("metadata") or {})
    parent_run_id = str(parent_state.get("run_id") or parent_metadata.get("run_id") or "")
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


def _logic_output_schema_keys(compiled: CompiledSkill) -> set[str] | None:
    raw_keys = compiled.raw.get("io", {}).get("output_schema_keys")
    if raw_keys is None:
        return None
    if not isinstance(raw_keys, list):
        return set()
    return {key for key in raw_keys if isinstance(key, str)}


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
            raise GraphAgentFatalError(
                f"[F-v3-actions-keys] {action_path}:{action_line} "
                f"action wrote undeclared output key {key!r}"
            )


def _is_terminal_phase(phase_id: str, manifest: GraphManifest) -> bool:
    return not any(phase_id in phase.depends_on for phase in manifest.phases)


def _terminal_phase_ids(manifest: GraphManifest) -> list[str]:
    return [phase.id for phase in manifest.phases if _is_terminal_phase(phase.id, manifest)]


def _is_critic_tool_name(name: str) -> bool:
    lower = name.lower()
    return any(keyword in lower for keyword in ("critic", "reviewer", "auditor"))


def _graph_fatal(message: str) -> NoReturn:
    raise SkillLoadError(f"[F-v3-graph] {message}")


__all__ = [
    "CompiledStateGraph",
    "assemble_graph",
    "_is_terminal_phase",
    "_terminal_phase_ids",
]
