from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

import graph_agent.core.graph_assembler as graph_assembler
from graph_agent.core._predict_internal.interception import PredictGatewayChatModel
from graph_agent.core._predict_internal.strategy import BaseMockStrategy
from graph_agent.core.compiler import compile_skill
from graph_agent.core.io_manager import IOManager
from graph_agent.core.loader import CompiledSubagent
from graph_agent.core.schema_engine import SchemaEngine
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware.cognitive_flow import CognitiveFlowMiddleware
from graph_agent.middleware.execution_control import ExecutionControlMiddleware
from graph_agent.middleware.factory import build_middleware_chain
from graph_agent.middleware.protocol_validation import ProtocolValidationMiddleware
from graph_agent_gateway.client_manager import LLMClientManager
from graph_agent_gateway.registry.schema import ResolvedRole, ResolvedRoute, RuntimePolicy


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _agent_skill(root: Path, *, max_iterations: int = 2) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: ws-e1-create-agent-core
io:
  inputs:
    type: object
    properties:
      topic:
        type: string
  outputs:
    type: object
    properties:
      answer:
        type: string
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
phase_config:
  max_iterations: {max_iterations}
  llm_role: graph_agent
  tools:
    - lookup
    - finish_task
  references:
    - id: Guide
      path: refs/guide.md
      summary: Primary guide.
---
<role>
Boundary verifier.
</role>
<goal>
Use @reference:Guide and @tool:lookup, then call @tool:finish_task.
</goal>
""",
    )
    _write(root / "refs" / "guide.md", "Reference body for the system prompt.")
    _write(
        root / "phases" / "main" / "tools" / "lookup.py",
        "def lookup(topic: str) -> str:\n"
        "    return f'lookup:{topic}'\n",
    )


def _subagent_child_skill(root: Path) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: ws-e1-subagent-child
io:
  inputs:
    type: object
    properties:
      text:
        type: string
    required: [text]
  outputs:
    type: object
    properties: {}
phases:
  - child
---
<phase depends_on="input" output>child</phase>
""",
    )
    _write(
        root / "phases" / "child" / "SKILL.md",
        """---
phase_config:
  max_iterations: 1
  llm_role: graph_agent
---
<role>
Child expert.
</role>
<goal>
Echo the provided text.
</goal>
""",
    )


def _subagent_parent_skill(root: Path, target_skill: str) -> None:
    _write(
        root / "GRAPH.md",
        """---
schema_version: "v0.3.0"
name: ws-e1-subagent-parent
io:
  inputs:
    type: object
    properties:
      text:
        type: string
  outputs:
    type: object
    properties: {}
phases:
  - main
---
<phase depends_on="input" output>main</phase>
""",
    )
    _write(
        root / "phases" / "main" / "SKILL.md",
        f"""---
phase_config:
  max_iterations: 3
  llm_role: graph_agent
  subagents:
    - name: child_expert
      target_skill: {target_skill}
      description: Echoes text from a child expert skill.
---
<role>
Parent coordinator.
</role>
<goal>
Call @subagent:child_expert with the input text.
</goal>
""",
    )


class _NoToolChatModel:
    def __init__(self) -> None:
        self.bound_tool_names: list[str] = []

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> "_NoToolChatModel":
        del kwargs
        self.bound_tool_names = [str(getattr(tool, "name", "")) for tool in tools]
        return self

    def invoke(self, messages: list[Any]) -> AIMessage:
        del messages
        return AIMessage(content="no tool calls")


class _PredictAwareResolver:
    def __init__(self, model: Any) -> None:
        self.model = model
        self.calls: list[dict[str, Any]] = []

    def resolve(
        self,
        llm_role: str,
        *,
        callbacks: tuple[Any, ...],
        phase_name: str,
        predict_context: Any = None,
    ) -> Any:
        self.calls.append(
            {
                "llm_role": llm_role,
                "callbacks": callbacks,
                "phase_name": phase_name,
                "predict_context": predict_context,
            }
        )
        return self.model


class _StaticChatModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "ws-e1-static"

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])


class _LoopingToolChatModel(BaseChatModel):
    invocations: int = 0
    fail_after: int = 4

    @property
    def _llm_type(self) -> str:
        return "ws-e1-looping-tool"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> "_LoopingToolChatModel":
        del tools, kwargs
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.invocations += 1
        if self.invocations > self.fail_after:
            raise AssertionError("phase max_iterations did not stop the agent loop")
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "lookup",
                    "args": {"topic": "contracts"},
                    "id": f"lookup-{self.invocations}",
                }
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


class _FinishTaskArgs(BaseModel):
    reasoning: str = ""
    diagnostics_md: str = ""
    business_data_md: str


class _FinishToolOutput(BaseModel):
    answer: str


class _OneFinishCallModel(BaseChatModel):
    emitted: bool = False

    @property
    def _llm_type(self) -> str:
        return "ws-e1-one-finish-call"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> "_OneFinishCallModel":
        del tools, kwargs
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        if self.emitted:
            message = AIMessage(content="done")
        else:
            self.emitted = True
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "diagnostics_md": "checked",
                            "business_data_md": "## item-1\n- answer: ok\n",
                        },
                        "id": "finish-1",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


class _OneSubagentCallModel(BaseChatModel):
    emitted: bool = False

    @property
    def _llm_type(self) -> str:
        return "ws-e1-one-subagent-call"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> "_OneSubagentCallModel":
        del tools, kwargs
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        if self.emitted:
            message = AIMessage(content="done")
        else:
            self.emitted = True
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "call_subagent_child_expert",
                        "args": {"inputs": [{"text": "contracts"}]},
                        "id": "subagent-1",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


class _MemoryMockStrategy(BaseMockStrategy):
    def __init__(self, output: dict[str, Any]) -> None:
        self.output = output

    def has_phase(self, phase_name: str) -> bool:
        return phase_name == "main"

    def has_golden_case(self, phase_name: str) -> bool:
        return self.has_phase(phase_name)

    def get_golden_output(self, phase_name: str) -> dict[str, Any]:
        if not self.has_phase(phase_name):
            raise KeyError(phase_name)
        return self.output


def _resolved_role() -> ResolvedRole:
    route = ResolvedRoute(
        role_name="graph_agent",
        route_id="mock-endpoint:mock-route",
        endpoint_id="mock-endpoint",
        protocol="openai_compatible",
        base_url="https://provider.example/v1",
        credential_ref="test-credential",
        credential_fingerprint="fp-test",
        provider_model_id="mock-model",
        canonical_id="mock-model",
    )
    return ResolvedRole(
        role_name="graph_agent",
        system_prompt_prefix="",
        runtime_policy=RuntimePolicy(),
        routes=[route],
    )


def test_agent_phase_constructs_create_agent_with_workflow_state_boundaries(
    monkeypatch: Any,
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path, max_iterations=2)
    model = _NoToolChatModel()
    resolver = _PredictAwareResolver(model)
    predict_context = object()
    checkpointer = InMemorySaver()
    captured: dict[str, Any] = {}

    class _Agent:
        def invoke(self, input: Any, config: Any | None = None) -> Any:
            captured["agent_input"] = input
            captured["agent_config"] = config or {}
            return input

    def fake_create_agent(**kwargs: Any) -> _Agent:
        captured["create_agent_kwargs"] = kwargs
        return _Agent()

    monkeypatch.setattr(graph_assembler, "create_agent", fake_create_agent, raising=False)

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = graph_assembler.assemble_graph(
        compiled,
        model_resolver=resolver,
        skill_resolver=mock_skill_resolver,
        checkpointer=checkpointer,
        predict_context=predict_context,
    ).graph
    graph.invoke(
        {"data": {"topic": "contracts"}, "flow": {"thread_id": "outer-thread"}, "messages": []},
        config={"configurable": {"thread_id": "outer-thread"}},
    )

    assert "create_agent_kwargs" in captured, (
        "live AGENT phase must construct LangChain create_agent instead of running "
        "the hand-written model/tool loop in graph_assembler.py"
    )
    kwargs = captured["create_agent_kwargs"]
    assert kwargs["model"] is model
    assert kwargs["state_schema"] is WorkflowState
    assert getattr(kwargs["checkpointer"], "base_checkpointer", kwargs["checkpointer"]) is checkpointer
    assert "<knowledge_base>" in str(kwargs["system_prompt"])

    tool_names = {str(getattr(tool, "name", "")) for tool in kwargs["tools"]}
    assert {"lookup", "read_reference", "finish_task"} <= tool_names

    finish_tool = next(tool for tool in kwargs["tools"] if getattr(tool, "name", "") == "finish_task")
    assert set(finish_tool.args_schema.model_fields) >= {
        "reasoning",
        "diagnostics_md",
        "business_data_md",
    }
    assert "markdown" not in finish_tool.args_schema.model_fields

    middleware_names = [type(middleware).__name__ for middleware in kwargs["middleware"]]
    assert middleware_names == [
        "ProtocolValidationMiddleware",
        "CognitiveFlowMiddleware",
        "ExecutionControlMiddleware",
        "TracingMiddleware",
        "ToolErrorHandlingMiddleware",
        "LoopDetectionMiddleware",
    ]

    agent_input = captured["agent_input"]
    assert set(agent_input) >= {"data", "flow", "messages"}

    agent_config = captured["agent_config"]
    configurable = dict(agent_config.get("configurable", {}))
    assert configurable["thread_id"] == "outer-thread"
    assert "main" in str(configurable["checkpoint_ns"])
    assert "agent" in str(configurable["checkpoint_ns"])
    assert configurable["max_iterations"] == 2
    assert int(agent_config["recursion_limit"]) < 10000

    assert resolver.calls == [
        {
            "llm_role": "graph_agent",
            "callbacks": (),
            "phase_name": "main",
            "predict_context": predict_context,
        }
    ]


def test_default_langchain_agent_state_drops_workflow_data_and_flow() -> None:
    agent = create_agent(model=_StaticChatModel(), tools=[])

    result = agent.invoke(
        {
            "data": BusinessData.model_validate({"topic": "contracts"}),
            "flow": FrameworkState.model_validate({"thread_id": "outer-thread"}),
            "messages": [],
        }
    )

    assert set(result) == {"messages"}
    assert "data" not in result
    assert "flow" not in result


def test_first_three_middleware_slots_run_in_minimal_create_agent_loop(
    monkeypatch: Any,
) -> None:
    calls: list[tuple[str, str]] = []
    protocol_before = ProtocolValidationMiddleware.before_model
    protocol_after = ProtocolValidationMiddleware.after_model
    cognitive_wrap = CognitiveFlowMiddleware.wrap_tool_call
    execution_before = ExecutionControlMiddleware.before_model
    execution_after = ExecutionControlMiddleware.after_model

    def spy_protocol_before(self: Any, state: Any, runtime: Any) -> Any:
        calls.append(("ProtocolValidationMiddleware", "before_model"))
        return protocol_before(self, state, runtime)

    def spy_protocol_after(self: Any, state: Any, runtime: Any) -> Any:
        calls.append(("ProtocolValidationMiddleware", "after_model"))
        return protocol_after(self, state, runtime)

    def spy_cognitive_wrap(self: Any, request: Any, handler: Any) -> Any:
        calls.append(("CognitiveFlowMiddleware", "wrap_tool_call"))
        return cognitive_wrap(self, request, handler)

    def spy_execution_before(self: Any, state: Any, runtime: Any) -> Any:
        calls.append(("ExecutionControlMiddleware", "before_model"))
        return execution_before(self, state, runtime)

    def spy_execution_after(self: Any, state: Any, runtime: Any) -> Any:
        calls.append(("ExecutionControlMiddleware", "after_model"))
        return execution_after(self, state, runtime)

    monkeypatch.setattr(ProtocolValidationMiddleware, "before_model", spy_protocol_before)
    monkeypatch.setattr(ProtocolValidationMiddleware, "after_model", spy_protocol_after)
    monkeypatch.setattr(CognitiveFlowMiddleware, "wrap_tool_call", spy_cognitive_wrap)
    monkeypatch.setattr(ExecutionControlMiddleware, "before_model", spy_execution_before)
    monkeypatch.setattr(ExecutionControlMiddleware, "after_model", spy_execution_after)

    def _finish_task(
        reasoning: str = "",
        diagnostics_md: str = "",
        business_data_md: str = "",
    ) -> dict[str, str]:
        del reasoning, diagnostics_md
        return {"business_data_md": business_data_md}

    finish_tool = StructuredTool.from_function(
        func=_finish_task,
        name="finish_task",
        description="Submit final business markdown.",
        args_schema=_FinishTaskArgs,
    )
    schema_engine = SchemaEngine()
    middleware = build_middleware_chain(
        io_manager=IOManager([]),
        schema_engine=schema_engine,
        current_phase_schema=_FinishToolOutput,
        phase_name="main",
    )
    agent = create_agent(
        model=_OneFinishCallModel(),
        tools=[finish_tool],
        middleware=middleware,
        state_schema=WorkflowState,
    )

    result = agent.invoke(
        {
            "data": BusinessData.model_validate({}),
            "flow": FrameworkState.model_validate({"thread_id": "run-1"}),
            "messages": [],
        },
        config={"configurable": {"thread_id": "run-1"}},
    )

    assert result["flow"].finish_task_result is not None
    assert ("ProtocolValidationMiddleware", "before_model") in calls
    assert ("ProtocolValidationMiddleware", "after_model") in calls
    assert ("CognitiveFlowMiddleware", "wrap_tool_call") in calls
    assert ("ExecutionControlMiddleware", "before_model") in calls
    assert ("ExecutionControlMiddleware", "after_model") in calls


def test_phase_max_iterations_stops_repeated_tool_loop(
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path, max_iterations=2)
    chat = _LoopingToolChatModel()

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = graph_assembler.assemble_graph(
        compiled,
        chat_model=chat,
        skill_resolver=mock_skill_resolver,
    ).graph
    graph.invoke(
        {"data": {"topic": "contracts"}, "flow": {"thread_id": "run-1"}, "messages": []},
        config={"configurable": {"thread_id": "run-1"}},
    )

    assert chat.invocations == 2


def test_create_agent_subagent_tool_uses_engine_dispatch_not_loader_placeholder(
    monkeypatch: Any,
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "demo.child"
    _subagent_child_skill(child)
    _subagent_parent_skill(parent, "demo.child")
    chat = _OneSubagentCallModel()
    dispatch_calls: list[dict[str, Any]] = []

    def fake_invoke_subagent_tool_t21(**kwargs: Any) -> dict[str, Any]:
        dispatch_calls.append(kwargs)
        return {
            "ok": True,
            "tool_name": kwargs["tool_name"],
            "subagent_name": kwargs["subagent"].name,
            "results": [{"status": "ok", "data": {"echo": "contracts"}}],
        }

    monkeypatch.setattr(
        graph_assembler,
        "_invoke_subagent_tool_t21",
        fake_invoke_subagent_tool_t21,
    )

    compiled = compile_skill(parent, cache=False, skill_resolver=mock_skill_resolver)
    graph = graph_assembler.assemble_graph(
        compiled,
        chat_model=chat,
        skill_resolver=mock_skill_resolver,
    ).graph
    graph.invoke(
        {"data": {"text": "contracts"}, "flow": {"thread_id": "run-1"}, "messages": []},
        config={"configurable": {"thread_id": "run-1"}},
    )

    assert dispatch_calls, (
        "create_agent must receive a subagent tool wired to engine dispatch; "
        "the loader placeholder must not be the callable that LangGraph executes"
    )
    call = dispatch_calls[0]
    assert call["tool_name"] == "call_subagent_child_expert"
    assert call["args"] == {"inputs": [{"text": "contracts"}]}
    assert call["subagent"].name == "child_expert"
    assert call["runtime"] is not None
    assert call["state"]["flow"].thread_id == "run-1"


def test_predict_gateway_model_stays_predict_bound_and_zero_usage(
    monkeypatch: Any,
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    _agent_skill(tmp_path, max_iterations=1)
    predict_model = PredictGatewayChatModel(
        "graph_agent",
        _resolved_role(),
        mock_strategy=_MemoryMockStrategy({"answer": "mocked"}),
        phase_name="main",
    )
    resolver = _PredictAwareResolver(predict_model)
    captured: dict[str, Any] = {}

    class _Agent:
        def invoke(self, input: Any, config: Any | None = None) -> Any:
            del config
            return input

    def fake_create_agent(**kwargs: Any) -> _Agent:
        captured["bound_model"] = kwargs["model"].bind_tools(kwargs["tools"])
        return _Agent()

    monkeypatch.setattr(graph_assembler, "create_agent", fake_create_agent, raising=False)

    compiled = compile_skill(tmp_path, cache=False, skill_resolver=mock_skill_resolver)
    graph = graph_assembler.assemble_graph(
        compiled,
        model_resolver=resolver,
        skill_resolver=mock_skill_resolver,
        predict_context=object(),
    ).graph
    graph.invoke(
        {"data": {"topic": "contracts"}, "flow": {"thread_id": "run-1"}, "messages": []},
        config={"configurable": {"thread_id": "run-1"}},
    )

    assert "bound_model" in captured, "create_agent must bind tools without losing predict mode"
    bound_model = captured["bound_model"]
    assert isinstance(bound_model, PredictGatewayChatModel)
    with (
        patch.object(LLMClientManager, "_probe_provider", side_effect=AssertionError("provider")),
        patch(
            "graph_agent_gateway.gateway_chat_model.RouteChatModelFactory.build",
            side_effect=AssertionError("provider"),
        ),
    ):
        response = bound_model.invoke([HumanMessage(content="predict")])

    assert response.usage_metadata == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert response.response_metadata["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0,
    }
    assert resolver.calls[0]["predict_context"] is not None


class _TwoInvalidSubagentCallModel(BaseChatModel):
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "ws-e1-two-invalid-subagent-calls"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> "_TwoInvalidSubagentCallModel":
        del tools, kwargs
        return self

    def _generate(
        self,
        messages: list[Any],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.calls += 1
        if self.calls == 1:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "call_subagent_child_expert",
                        "args": {"inputs": [{"invalid_field": "contracts"}]},
                        "id": "subagent-1",
                    }
                ],
            )
        elif self.calls == 2:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "call_subagent_child_expert",
                        "args": {"inputs": [{"invalid_field": "contracts"}]},
                        "id": "subagent-2",
                    }
                ],
            )
        else:
            message = AIMessage(content="done")
        return ChatResult(generations=[ChatGeneration(message=message)])


class _SubagentRetryInput(BaseModel):
    text: str


def _compiled_retry_subagent(root: Path) -> CompiledSubagent:
    schema = _SubagentRetryInput.model_json_schema()
    return CompiledSubagent(
        parent_phase_id="main",
        name="child_expert",
        target_skill="demo.child",
        description="Child expert.",
        root=root,
        input_schema=schema,
        input_model=_SubagentRetryInput,
        expected_schema=schema,
    )


def test_subagent_validation_retry_count_ignores_successful_calls(tmp_path: Path) -> None:
    flow: dict[str, Any] = {"subagent_validation_retries": {}}
    subagent = _compiled_retry_subagent(tmp_path / "child")

    for index in range(11):
        result = graph_assembler._invoke_subagent_tool_t21(
            tool_name="call_subagent_child_expert",
            subagent=subagent,
            args={"inputs": [{"text": f"ok-{index}"}]},
            flow=flow,
        )
        assert result["ok"] is True

    assert flow["subagent_validation_retries"] == {}


def test_subagent_validation_retry_count_clears_after_success(tmp_path: Path) -> None:
    flow: dict[str, Any] = {"subagent_validation_retries": {}}
    subagent = _compiled_retry_subagent(tmp_path / "child")

    first = graph_assembler._invoke_subagent_tool_t21(
        tool_name="call_subagent_child_expert",
        subagent=subagent,
        args={"inputs": [{"invalid_field": "contracts"}]},
        flow=flow,
    )
    assert first["ok"] is False
    assert flow["subagent_validation_retries"] == {"call_subagent_child_expert": 1}

    second = graph_assembler._invoke_subagent_tool_t21(
        tool_name="call_subagent_child_expert",
        subagent=subagent,
        args={"inputs": [{"text": "contracts"}]},
        flow=flow,
    )
    assert second["ok"] is True
    assert flow["subagent_validation_retries"] == {}


def test_create_agent_subagent_tool_persists_retry_count(
    monkeypatch: Any,
    tmp_path: Path,
    mock_skill_resolver: object,
) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "demo.child"
    _subagent_child_skill(child)
    _subagent_parent_skill(parent, "demo.child")
    chat = _TwoInvalidSubagentCallModel()

    dispatch_flows: list[dict[str, Any]] = []
    original_invoke = graph_assembler._invoke_subagent_tool_t21

    def spy_invoke_subagent_tool_t21(**kwargs: Any) -> dict[str, Any]:
        from graph_agent.core.graph_assembler import parent_state_var
        parent_state = parent_state_var.get(None)
        assert kwargs["state"] is parent_state, "state passed to _invoke_subagent_tool_t21 must be the real parent state"

        flow = kwargs.get("flow")
        retries = {}
        if flow is not None:
            if isinstance(flow, dict):
                retries = dict(flow.get("subagent_validation_retries", {}))
            else:
                retries = dict(getattr(flow, "subagent_validation_retries", {}))
        dispatch_flows.append(retries)
        return original_invoke(**kwargs)

    monkeypatch.setattr(
        graph_assembler,
        "_invoke_subagent_tool_t21",
        spy_invoke_subagent_tool_t21,
    )

    captured_tools: list[Any] = []
    original_create_agent = graph_assembler.create_agent

    def fake_create_agent(**kwargs: Any) -> Any:
        captured_tools.extend(kwargs.get("tools", []))
        return original_create_agent(**kwargs)

    monkeypatch.setattr(graph_assembler, "create_agent", fake_create_agent)

    from langgraph.checkpoint.memory import InMemorySaver
    saver = InMemorySaver()
    compiled = compile_skill(parent, cache=False, skill_resolver=mock_skill_resolver)
    graph = graph_assembler.assemble_graph(
        compiled,
        chat_model=chat,
        skill_resolver=mock_skill_resolver,
        checkpointer=saver,
    ).graph
    graph.invoke(
        {"data": {"text": "contracts"}, "flow": {"thread_id": "run-1"}, "messages": []},
        config={"configurable": {"thread_id": "run-1"}},
    )
    checkpoint_state = saver.get_tuple({"configurable": {"thread_id": "run-1"}})
    assert checkpoint_state is not None
    res = checkpoint_state.checkpoint["channel_values"]

    assert len(dispatch_flows) == 2
    assert dispatch_flows[0] == {}
    assert dispatch_flows[1] == {"call_subagent_child_expert": 1}

    assert res["flow"].subagent_validation_retries == {"call_subagent_child_expert": 2}

    subagent_tool = next(t for t in captured_tools if t.name == "call_subagent_child_expert")
    inputs_schema = subagent_tool.args_schema.model_json_schema()["properties"]["inputs"]
    assert inputs_schema["items"]["properties"]["text"]["type"] == "string"
    assert inputs_schema["items"]["required"] == ["text"]
    assert subagent_tool.args_schema.model_validate(
        {"inputs": [{"invalid_field": "contracts"}]}
    ).inputs == [{"invalid_field": "contracts"}]
    assert subagent_tool.metadata is not None
    assert subagent_tool.metadata.get("kind") == "subagent"
    assert subagent_tool.metadata.get("subagent_name") == "child_expert"
    assert "target_skill" in subagent_tool.metadata
    assert "subagent_root" in subagent_tool.metadata
    assert "expected_schema" in subagent_tool.metadata
