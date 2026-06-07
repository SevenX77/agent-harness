from __future__ import annotations

import asyncio
import json
from typing import Literal
from unittest.mock import patch

from graph_agent_gateway.client_manager import LLMClientManager
from graph_agent_gateway.registry.schema import ResolvedRole, ResolvedRoute, RuntimePolicy
from langchain_core.messages import HumanMessage

from graph_agent.core._predict_internal.interception import PredictGatewayChatModel
from graph_agent.core._predict_internal.strategy import BaseMockStrategy

MockedSource = Literal["golden_case", "copilot", "heuristic_stub", "manual"]


class MemoryMockStrategy(BaseMockStrategy):
    def __init__(
        self,
        *,
        golden: dict[str, dict[str, object]] | None = None,
        overrides: dict[str, dict[str, object]] | None = None,
        override_source: MockedSource = "manual",
        schemas: dict[str, dict[str, object]] | None = None,
    ) -> None:
        self.golden = golden or {}
        self.overrides = overrides or {}
        self.override_source = override_source
        self.schemas = schemas or {}

    def has_phase(self, phase_name: str) -> bool:
        return (
            phase_name in self.golden or phase_name in self.overrides or phase_name in self.schemas
        )

    def has_golden_case(self, phase_name: str) -> bool:
        return phase_name in self.golden

    def get_golden_output(self, phase_name: str) -> dict[str, object]:
        return self.golden[phase_name]

    def has_manual_override(self, phase_name: str) -> bool:
        return phase_name in self.overrides

    def get_manual_override(self, phase_name: str) -> dict[str, object]:
        return self.overrides[phase_name]

    def get_manual_source(self, phase_name: str) -> MockedSource:
        return self.override_source

    def get_phase_schema(self, phase_name: str) -> dict[str, object] | None:
        return self.schemas.get(phase_name)


def _route(endpoint_id: str, model_name: str) -> ResolvedRoute:
    return ResolvedRoute(
        role_name="writer",
        route_id=f"{endpoint_id}:{model_name}",
        endpoint_id=endpoint_id,
        protocol="openai_compatible",
        base_url="https://provider.example/v1",
        credential_ref="test-cred-ref",
        credential_fingerprint=f"fp-{endpoint_id}",
        provider_model_id=model_name,
        canonical_id=model_name,
    )


def _role() -> ResolvedRole:
    return ResolvedRole(
        role_name="writer",
        system_prompt_prefix="",
        runtime_policy=RuntimePolicy(),
        routes=[_route("p1", "model-a")],
    )


def _model(strategy: BaseMockStrategy, phase_name: str = "draft") -> PredictGatewayChatModel:
    return PredictGatewayChatModel(
        "writer",
        _role(),
        mock_strategy=strategy,
        max_tokens=128,
        temperature=0.2,
        phase_name=phase_name,
    )


def _payload(result_content: object) -> dict[str, object]:
    assert isinstance(result_content, str)
    return json.loads(result_content)


def test_generate_uses_p0_golden_before_p1_override_and_p2_stub() -> None:
    model = _model(
        MemoryMockStrategy(
            golden={"draft": {"text": "golden"}},
            overrides={"draft": {"text": "manual"}},
            schemas={"draft": {"type": "object", "properties": {"text": {"type": "string"}}}},
        )
    )

    result = model._generate([HumanMessage(content="hi")])

    assert _payload(result.generations[0].message.content) == {"text": "golden"}
    assert result.llm_output is not None
    assert result.llm_output["mocked_source"] == "golden_case"


def test_generate_uses_p1_override_when_no_golden_case() -> None:
    model = _model(
        MemoryMockStrategy(
            overrides={"draft": {"text": "copilot predicted"}},
            override_source="copilot",
            schemas={"draft": {"type": "object", "properties": {"text": {"type": "string"}}}},
        )
    )

    result = model._generate([HumanMessage(content="hi")])
    message = result.generations[0].message

    assert _payload(message.content) == {"text": "copilot predicted"}
    assert message.response_metadata["mocked_source"] == "copilot"
    assert result.llm_output is not None
    assert result.llm_output["mocked_source"] == "copilot"


def test_generate_falls_back_to_p2_heuristic_stub() -> None:
    model = _model(
        MemoryMockStrategy(
            schemas={
                "draft": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "count": {"type": "integer"},
                    },
                }
            }
        )
    )

    result = model._generate([HumanMessage(content="hi")])

    assert _payload(result.generations[0].message.content) == {
        "count": 0,
        "text": "<mock_text>",
    }
    assert result.generations[0].message.response_metadata["mocked_source"] == "heuristic_stub"


def test_generate_sets_mock_metadata_and_zero_usage_without_provider_call() -> None:
    model = _model(MemoryMockStrategy(golden={"draft": {"text": "golden"}}))

    with (
        patch.object(LLMClientManager, "_probe_provider", side_effect=AssertionError("provider")),
        patch(
            "graph_agent_gateway.ordinary_chat._dispatch_provider_call",
            side_effect=AssertionError("provider"),
        ),
    ):
        result = model._generate([HumanMessage(content="hi")])

    message = result.generations[0].message
    assert message.id is not None
    assert message.id.startswith("mock_id_golden_case_draft_")
    assert message.response_metadata["created"] > 0
    assert message.response_metadata["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "total_cost": 0,
    }
    assert message.usage_metadata == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    assert result.llm_output is not None
    assert result.llm_output["usage"]["total_cost"] == 0
    assert result.generations[0].generation_info is not None
    assert result.generations[0].generation_info["id"] == message.id


def test_agenerate_matches_generate_behavior() -> None:
    model = _model(MemoryMockStrategy(overrides={"draft": {"text": "manual"}}))

    result = asyncio.run(model._agenerate([HumanMessage(content="hi")]))

    assert _payload(result.generations[0].message.content) == {"text": "manual"}
    assert result.llm_output is not None
    assert result.llm_output["mocked_source"] == "manual"


def test_astream_yields_single_complete_chunk() -> None:
    model = _model(MemoryMockStrategy(golden={"draft": {"text": "golden"}}))

    async def collect() -> list[object]:
        return [chunk async for chunk in model._astream([HumanMessage(content="hi")])]

    chunks = asyncio.run(collect())

    assert len(chunks) == 1
    chunk = chunks[0]
    assert _payload(chunk.message.content) == {"text": "golden"}
    assert chunk.message.response_metadata["mocked_source"] == "golden_case"
    assert chunk.message.chunk_position == "last"


def test_bind_tools_preserves_predict_gateway_and_mock_strategy() -> None:
    strategy = MemoryMockStrategy(golden={"draft": {"text": "golden"}})
    model = _model(strategy)

    bound = model.bind_tools(
        [
            {
                "name": "finish_task",
                "description": "finish",
                "parameters": {"type": "object", "properties": {}},
            }
        ]
    )

    assert isinstance(bound, PredictGatewayChatModel)
    assert bound.mock_strategy is strategy
    result = bound._generate([HumanMessage(content="hi")])
    assert result.llm_output is not None
    assert result.llm_output["mocked_source"] == "golden_case"
