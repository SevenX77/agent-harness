"""A phase keeps its declared inputs after a nudge.

`RuntimeInputMiddleware` delivers the phase's declared inputs as a JSON block on
every model call. It is a `wrap_model_call` middleware, so the block it inserts
is never written back to state: `factory.py:1409-1418` rebuilds
`ModelRequest.messages` from `state["messages"]` on every model node entry, the
transformed request reaches only `_execute_model_sync` (`factory.py:1424`), and
`_handle_model_output` (`factory.py:1173`) returns `{"messages": [output]}` —
the model's OUTPUT alone. So re-delivery per call is the design, not an accident.

The delivery criterion used to be a proxy: "does the history hold ANY
HumanMessage" (`runtime_input.py:64`). But every nudge, dead-end warning and
loop diagnostic is written into the conversation as a HumanMessage —
`exit_control.py:209,306,327`, `execution_control.py:241`,
`loop_detection.py:134` — so the first nudge a phase received permanently
silenced its own input block for every later turn.

Field evidence, run `2026-08-15T12-40-22_bb6e358a` of
`story-deconstruction-v3-lab` (DeepSeek V4 Flash), counted from `trace.jsonl`:
every phase that was never nudged got `runtime_input_injected` exactly as often
as it called the model (`stitch` 8/8, `aggregate` 7/7, `segment` 4/4,
`entity_and_characters` 4/4, `discover_dimensions` 3/3, `global_analysis` 2/2)
— which is itself the proof that delivery is per-call and not persisted. Every
phase that WAS nudged got exactly one, no matter how many turns it ran:
`system` 1 of 6 calls, `foreshadow` 1 of 5, `prop` 1 of 4, `spatiotemporal`
1 of 4, `tension` 1 of 4, `arc` 1 of 2, `retroactive` 1 of 2, `review` 3 of 15.
32 of the run's 77 model calls lost the block this way.

This is not a phase running blind: the authored system prompt interpolates its
own `{field}` placeholders (the first half of this same middleware). What is
lost is the engine's own structured copy of the declared inputs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from graph_agent.core.llm_provider import LLMProviderChunk, LLMProviderRequest
from graph_agent.core.runner import run_skill
from graph_agent.core.state import BusinessData, FrameworkState
from graph_agent.middleware.runtime_input import RuntimeInputMiddleware

# The literal opening of the engine's own input block. Authored `{key}`
# interpolation produces the value without this prefix, so counting on the
# prefix separates the engine's copy from the author's.
_BLOCK_PREFIX = "以下是本阶段的输入数据(JSON)"


# --------------------------------------------------------------------------
# unit level: the criterion itself
# --------------------------------------------------------------------------


class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)

    def of_type(self, event_type: str) -> list[Any]:
        return [e for e in self.events if getattr(e, "event_type", "") == event_type]


def _request(messages: list[Any], *, data: BusinessData | None = None) -> ModelRequest:
    return ModelRequest(
        model=cast(Any, object()),
        messages=messages,
        system_message=None,
        tool_choice=None,
        tools=[],
        response_format=None,
        state=cast(
            Any,
            {
                "data": data if data is not None else BusinessData(),
                "flow": FrameworkState(),
                "messages": messages,
            },
        ),
        runtime=cast(Any, None),
    )


def _blocks(messages: list[Any]) -> list[Any]:
    return [m for m in messages if _BLOCK_PREFIX in str(getattr(m, "content", ""))]


def _deliver(
    middleware: RuntimeInputMiddleware, request: ModelRequest
) -> ModelRequest:
    """Run the sync hook and hand back the request the model would have seen."""
    captured: list[ModelRequest] = []

    def handler(req: ModelRequest) -> Any:
        captured.append(req)
        return None

    middleware.wrap_model_call(request, handler)
    return captured[0]


def _data() -> BusinessData:
    return BusinessData.model_validate({"topic": "venus"})


# The three real shapes of HumanMessage that other middlewares write into the
# conversation. Each one used to silence input delivery for the rest of the phase.
_INTERRUPTIONS = [
    # exit_control.py:209,306,327 — a plain nudge, no name
    HumanMessage(content="你没有调用 finish_task,请继续。"),
    # execution_control.py:241
    HumanMessage(name="dead_end_warning", content="工具连续失败,换一条路。"),
    # loop_detection.py:134
    HumanMessage(
        name="loop_detection_diagnostic",
        content="检测到死循环!工具 `finish_task` 重复执行了 3 次。",
    ),
]


class TestANudgeDoesNotStopDelivery:
    def test_every_interruption_shape_still_gets_the_block(self) -> None:
        for interruption in _INTERRUPTIONS:
            middleware = RuntimeInputMiddleware("work", ("topic",))
            # A real turn-2 request cannot carry turn 1's block: the middleware
            # never writes it back to state, so state holds only the model's
            # output plus whatever the interrupting middleware appended.
            delivered = _deliver(
                middleware,
                _request(
                    [AIMessage(content="我想想。"), interruption],
                    data=_data(),
                ),
            )
            assert _blocks(delivered.messages), (
                "a phase must keep its declared inputs after being nudged; "
                f"interruption={interruption!r} messages={delivered.messages}"
            )

    def test_a_tool_conversation_in_progress_still_gets_the_block(self) -> None:
        """The common case: turn 3+ of a phase that is calling tools."""
        middleware = RuntimeInputMiddleware("work", ("topic",))
        delivered = _deliver(
            middleware,
            _request(
                [
                    AIMessage(
                        content="",
                        tool_calls=[{"name": "search", "args": {}, "id": "tc-1"}],
                    ),
                    ToolMessage(content="result", tool_call_id="tc-1"),
                    HumanMessage(content="继续。"),
                ],
                data=_data(),
            ),
        )
        assert _blocks(delivered.messages), delivered.messages


class TestDeliveryIsIdempotent:
    def test_running_the_hook_over_its_own_output_adds_no_second_block(self) -> None:
        middleware = RuntimeInputMiddleware("work", ("topic",))
        once = _deliver(middleware, _request([], data=_data()))
        twice = _deliver(middleware, once)

        assert len(_blocks(twice.messages)) == 1, (
            "the block carries a stable marker so a request that already has it "
            f"is left alone; got {twice.messages}"
        )

    def test_a_different_block_does_not_count_as_mine(self) -> None:
        """Only a byte-identical block means "already delivered".

        Two phases declaring different inputs produce different blocks, so
        neither may silence the other — that mistake is the whole defect,
        one message standing in for another.
        """
        data = BusinessData.model_validate({"topic": "venus", "other": "mars"})
        alpha = RuntimeInputMiddleware("alpha", ("topic",))
        beta = RuntimeInputMiddleware("beta", ("other",))
        from_alpha = _deliver(alpha, _request([], data=data))
        both = _deliver(beta, from_alpha)

        assert len(_blocks(both.messages)) == 2, (
            "beta declares its own inputs and must deliver them even though "
            f"alpha's block is present; got {both.messages}"
        )


class TestSyncAndAsyncAgree:
    async def _adeliver(
        self, middleware: RuntimeInputMiddleware, request: ModelRequest
    ) -> ModelRequest:
        captured: list[ModelRequest] = []

        async def handler(req: ModelRequest) -> Any:
            captured.append(req)
            return None

        await middleware.awrap_model_call(request, handler)
        return captured[0]

    def test_the_async_hook_delivers_exactly_what_the_sync_hook_delivers(self) -> None:
        import asyncio

        messages = [
            AIMessage(content="我想想。"),
            HumanMessage(content="你没有调用 finish_task,请继续。"),
        ]
        sync_out = _deliver(
            RuntimeInputMiddleware("work", ("topic",)),
            _request(list(messages), data=_data()),
        )
        async_out = asyncio.run(
            self._adeliver(
                RuntimeInputMiddleware("work", ("topic",)),
                _request(list(messages), data=_data()),
            )
        )

        assert [str(getattr(m, "content", "")) for m in async_out.messages] == [
            str(getattr(m, "content", "")) for m in sync_out.messages
        ]
        assert _blocks(async_out.messages)


class TestTheEventSaysWhatActuallyHappened:
    """Glass-box D4: 发「决定」不发「路过」——「注了输入」is on its decision list
    (`docs/design/2026-08-13-trace-goes-glass-box-decision.md:205`), so an event
    per actual delivery; a skipped delivery is 路过 and stays silent.
    """

    def test_each_delivery_is_its_own_event(self) -> None:
        recorder = Recorder()
        middleware = RuntimeInputMiddleware("work", ("topic",), callbacks=(recorder,))

        _deliver(middleware, _request([], data=_data()))
        _deliver(
            middleware,
            _request(
                [AIMessage(content="嗯"), HumanMessage(content="继续。")],
                data=_data(),
            ),
        )

        events = recorder.of_type("runtime_input_injected")
        assert len(events) == 2, (
            "the trace must report every turn the model was handed its inputs, "
            f"not only the first; got {events}"
        )
        assert all(e.keys == ["topic"] for e in events), events

    def test_a_skipped_delivery_says_nothing(self) -> None:
        recorder = Recorder()
        middleware = RuntimeInputMiddleware("work", ("topic",), callbacks=(recorder,))

        once = _deliver(middleware, _request([], data=_data()))
        _deliver(middleware, once)

        assert len(recorder.of_type("runtime_input_injected")) == 1, (
            "the second pass changed nothing, and 路过 is not an event: "
            f"{recorder.events}"
        )


# --------------------------------------------------------------------------
# integration: the real nudge, from the real middleware, through a real run
# --------------------------------------------------------------------------

_GRAPH_MD = """---
schema_version: "v0.3.0"
name: runtime-input-after-nudge
description: One agent phase that gets nudged on its first turn.
llm_role: analyst
io:
  inputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
  outputs:
    type: object
    required: [alpha_out]
    properties:
      alpha_out:
        type: string
phases: [alpha]
---
<phase depends_on="input" output>alpha</phase>
"""

_ALPHA_MD = """---
llm_role: analyst
io:
  inputs:
    type: object
    required: [text]
    properties:
      text:
        type: string
  outputs:
    type: object
    required: [alpha_out]
    properties:
      alpha_out:
        type: string
max_iterations: 5
validator: false
---
<role>PHASE_ALPHA_MARKER 你是 alpha。</role>

<goal>读取输入并提交。</goal>

<step id="S1" name="finish">调用 finish_task 提交 alpha_out。</step>
"""


class _RecordingProvider:
    """Turn 1 answers with plain text and no tool call — exactly what
    `ExitControlMiddleware` nudges, which is the HumanMessage under test."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def stream(self, request: LLMProviderRequest) -> Iterator[LLMProviderChunk]:
        messages = list(request.messages)
        humans = [m for m in messages if type(m).__name__ == "HumanMessage"]
        texts = [str(getattr(m, "content", "")) for m in humans]
        call_no = len(self.calls) + 1
        self.calls.append({"human_texts": texts, "n_messages": len(messages)})

        if call_no == 1:
            yield LLMProviderChunk(content="我先想一想。", metadata={})
            return
        yield LLMProviderChunk(
            content="",
            metadata={
                "tool_calls": [
                    {
                        "name": "finish_task",
                        "args": {
                            "reasoning": "done",
                            "business_data_md": "## out\n```json\n"
                            + json.dumps({"alpha_out": "ALPHA_ANSWER"}, ensure_ascii=False)
                            + "\n```\n",
                        },
                        "id": f"tc-{call_no}",
                    }
                ]
            },
        )


def _run(tmp_path: Path) -> tuple[_RecordingProvider, Any]:
    skill = tmp_path / "runtime-input-after-nudge"
    (skill / "phases" / "alpha").mkdir(parents=True)
    (skill / "GRAPH.md").write_text(_GRAPH_MD, encoding="utf-8")
    (skill / "phases" / "alpha" / "SKILL.md").write_text(_ALPHA_MD, encoding="utf-8")

    provider = _RecordingProvider()
    result = run_skill(
        skill,
        workspace_dir=tmp_path / "ws",
        unattended=True,
        llm_provider=provider,
        text="TEXT_INPUT_MARKER",
    )
    return provider, result


def test_a_phase_still_has_its_inputs_on_the_turn_after_a_nudge(
    tmp_path: Path,
) -> None:
    provider, result = _run(tmp_path)
    assert result.success, getattr(result, "error", None)
    assert len(provider.calls) >= 2, provider.calls

    first, second = provider.calls[0], provider.calls[1]
    assert any(_BLOCK_PREFIX in t for t in first["human_texts"]), first
    assert any("TEXT_INPUT_MARKER" in t for t in first["human_texts"]), first

    nudged = [t for t in second["human_texts"] if _BLOCK_PREFIX not in t]
    assert nudged, f"turn 2 should carry the nudge that caused it: {second}"
    assert any(_BLOCK_PREFIX in t for t in second["human_texts"]), (
        "the nudge that produced turn 2 must not cost the phase its declared "
        f"inputs: {provider.calls}"
    )
    assert any("TEXT_INPUT_MARKER" in t for t in second["human_texts"]), second


def test_the_block_appears_once_per_turn(tmp_path: Path) -> None:
    provider, result = _run(tmp_path)
    assert result.success, getattr(result, "error", None)
    for call in provider.calls:
        n = sum(1 for t in call["human_texts"] if _BLOCK_PREFIX in t)
        assert n == 1, f"expected exactly one input block per turn, got {n}: {call}"
