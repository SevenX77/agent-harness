"""V2.1 CompiledSkill to LangGraph assembly."""

import asyncio
import json
import logging
import uuid
from copy import deepcopy
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
from graph_agent.core.builtin_subagents import ReferenceReaderRuntime
from graph_agent.core.exceptions import GraphAgentFatalError, SkillLoadError
from graph_agent.core.loader import CompiledSkill, CompiledSubagent, PhaseDocument, SkillLoader
from graph_agent.core.manifest import (
    AgentNodeAST,
    GraphManifest,
    LogicNodeAST,
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
from graph_agent.runtime.state import BlackboardState
from graph_agent.runtime.state_mapper import (
    PhaseWrapper,
    StateMapper,
    phase_inputs_from_state,
    phase_outputs_from_state,
)
from graph_agent.tools.builtin.read_example import read_declared_example
from graph_agent.tools.builtin.read_reference import read_declared_reference, read_resource_file

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
                max_patch_attempts,
                resolver,
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
        return _wrap_phase_runtime_node(
            phase_id,
            ast,
            _build_logic_node(phase_id, ast, compiled),
            node_kind="logic",
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
            ),
            node_kind="subgraph",
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
                max_patch_attempts,
                skill_resolver,
            ),
            node_kind="agent",
        )
    _graph_fatal(f"unknown phase mode for {phase_id!r}")


def _wrap_phase_runtime_node(phase_id: str, phase_ast: Any, node: Any, *, node_kind: str) -> Any:
    io = getattr(phase_ast, "io", None)
    input_schema = getattr(io, "inputs", None) if io is not None else None
    output_schema = getattr(io, "outputs", None) if io is not None else None
    return PhaseWrapper(
        StateMapper(input_schema, output_schema, phase_id=phase_id),
        node_kind=node_kind,
    ).wrap(node)


def _build_logic_node(
    phase_id: str,
    phase_ast: LogicNodeAST,
    compiled: CompiledSkill,
) -> Any:
    action_names = phase_ast.actions
    output_schema_keys = _schema_output_keys(phase_ast.io.outputs)

    def _logic_node(state: BlackboardState) -> dict[str, Any]:
        before = phase_inputs_from_state(state)
        data = dict(before)
        ctx = Context(data, phase_id=phase_id, run_id=state.get("run_id") or "default")
        updates = _dict_delta(before, data)
        for action_name in action_names:
            action = compiled.actions.resolve(phase_id, action_name)
            action_def = compiled.actions.for_phase(phase_id).get(action_name)
            action_path = action_def.path if action_def is not None else Path("<unknown>")
            action_line = getattr(getattr(action, "__code__", None), "co_firstlineno", 1)
            result = action(ctx)
            delta = _dict_delta(before | updates, data)
            _validate_logic_update_keys(delta, output_schema_keys, action_path, action_line)
            updates.update(delta)
            if not isinstance(result, dict):
                raise GraphAgentFatalError(
                    f"[F-v3-logic-action-return-invalid] {action_path}:{action_line} "
                    f"action returned {type(result).__name__}, expected dict"
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
        child_input = phase_inputs_from_state(state)
        child_flow = _child_flow(state.get("flow", {}))
        result = sub_assembled.graph.invoke(
            {
                "data": {"inputs": child_input, "phase_outputs": {}, "scratch": {}},
                "flow": child_flow,
                "messages": [],
                "run_id": state.get("run_id"),
            }
        )
        outputs = phase_outputs_from_state(result)
        data_updates = _deterministic_child_phase_outputs(outputs)
        return {
            "data": data_updates,
            "flow": result.get("flow", child_flow),
        }

    return _subgraph_node


def _build_skill_node(
    phase_id: str,
    phase_doc: PhaseDocument,
    phase_ast: AgentNodeAST,
    compiled: CompiledSkill,
    chat_model: Any,
    max_patch_attempts: int,
    skill_resolver: SkillResolverProtocol,
) -> Any:
    knowledge_base_markdown = _build_reference_reader_markdown(
        phase_id=phase_id,
        phase_doc=phase_doc,
        phase_ast=phase_ast,
        compiled=compiled,
    )
    business_tools = compiled.tools.for_phase(phase_id)
    business_tools = [*business_tools, *_agent_resource_tools(phase_doc, phase_ast, compiled)]
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
        if _is_terminal_phase(phase_id, compiled.manifest, compiled)
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
            SystemMessage(
                content=_agent_system_prompt(
                    phase_id,
                    phase_ast,
                    compiled,
                    knowledge_base_markdown=knowledge_base_markdown,
                )
            ),
            *state.get("messages", []),
        ]
        model = (
            chat_model.bind_tools(all_tools) if hasattr(chat_model, "bind_tools") else chat_model
        )

        max_turns = phase_ast.max_iterations
        for _ in range(max_turns):
            prompt_messages = messages
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
    try:
        result = runtime.run() if hasattr(runtime, "run") else runtime.initial_state()
        markdown = result.get("markdown") if isinstance(result, dict) else None
        if isinstance(markdown, str) and markdown.strip():
            return markdown
        return _fallback_reference_reader_markdown(root, references, "empty reader output")
    except GraphAgentFatalError as exc:
        if "[F-v3-resource-reference-path-invalid]" in str(exc):
            raise
        logger.warning("[F-v3-reference-reader-failed] %s", exc)
        return _fallback_reference_reader_markdown(root, references, str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[F-v3-reference-reader-failed] %s", exc)
        return _fallback_reference_reader_markdown(root, references, str(exc))


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
            error_code="[F-v3-resource-reference-path-invalid]",
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
    def _reference_reader_node(state: BlackboardState) -> dict[str, Any]:
        inputs = phase_inputs_from_state(state)
        path = inputs.get("path")
        if not isinstance(path, str):
            raise GraphAgentFatalError("[F-v3-reference-reader-failed] missing reference path")
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
        error_code="[F-v3-resource-reference-path-invalid]",
    )


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
    child_flow = _child_flow(parent_state.get("flow", {}))
    result = runtime.graph.invoke(
        {
            "data": {"inputs": dict(input_data), "phase_outputs": {}, "scratch": {}},
            "flow": child_flow,
            "messages": [],
            "run_id": parent_state.get("run_id"),
        },
        config=config,
    )
    result_outputs = phase_outputs_from_state(result)
    data_delta = _deterministic_child_phase_outputs(result_outputs)
    return {
        "status": "ok",
        "data": data_delta,
        "flow": result.get("flow", child_flow),
    }


def _child_flow(parent_flow: Any) -> dict[str, Any]:
    flow = deepcopy(parent_flow) if isinstance(parent_flow, dict) else {}
    flow["subagent_depth"] = current_subagent_depth(flow) + 1
    return flow


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


def _deterministic_child_phase_outputs(
    phase_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    data_delta: dict[str, Any] = {}
    for phase_id in sorted(phase_outputs):
        for key, value in phase_outputs[phase_id].items():
            if key in data_delta:
                raise GraphAgentFatalError(
                    "[F-v3-runtime-state-mapping-failed] duplicate child output key "
                    f"{key!r} from phase {phase_id!r}"
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
                raise GraphAgentFatalError(
                    f"[F-v3-logic-output-field-undeclared] {action_path}:{action_line} "
                    f"action wrote undeclared output key {key!r}"
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
    raise SkillLoadError(f"[F-v3-graph] {message}")


__all__ = [
    "CompiledStateGraph",
    "assemble_graph",
    "_is_terminal_phase",
    "_terminal_phase_ids",
]
