"""Behavior tests for the Compaction middleware slot (decision doc §3.6, PR D).

The slot wraps langchain's ``SummarizationMiddleware`` (user ruling P0-1:
trigger fraction 0.8, keep 20 messages) and adds the observability the
legacy WM-checkpoint compression used to provide: the full text of every
message removed from the context is written to a sidecar file under the
run directory, and a ``CompactionEvent`` with ``content_ref`` pointing at
that file is emitted.

These tests exercise the REAL ``SummarizationMiddleware`` end to end (only
the chat model is faked), so a langchain minor-version change that alters
the hook name, the trigger semantics, or the ``RemoveMessage(REMOVE_ALL)``
update protocol fails here loudly instead of silently disabling compaction.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from graph_agent.callbacks.base import Callback
from graph_agent.core.io_manager import IOManager
from graph_agent.core.state import BusinessData, FrameworkState, WorkflowState
from graph_agent.middleware import MVP0_MIDDLEWARE_ORDER_CONTRACT
from graph_agent.middleware.compaction import (
    COMPACTION_KEEP_MESSAGES,
    COMPACTION_TRIGGER_FRACTION,
    SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS,
    CompactionMiddleware,
    write_compaction_sidecar,
)
from graph_agent.middleware.factory import build_middleware_chain

_SUMMARY_TEXT = "[[compaction-summary]]"

# Small enough that thirty ordinary test messages blow past the 0.8
# fraction; the trigger math itself belongs to langchain and is not
# re-derived here.
_TINY_PROFILE = {"max_input_tokens": 50}


class _FakeSummaryModel:
    """The minimum surface SummarizationMiddleware touches on a model.

    ``_llm_type`` feeds langchain's token-counter tuning at construction
    time; ``profile`` feeds the fractional trigger; ``invoke``/``ainvoke``
    produce the summary message.
    """

    def __init__(self, *, profile: dict[str, Any] | None = None) -> None:
        self._llm_type = "fake-summary"
        if profile is not None:
            self.profile = profile

    def invoke(self, *args: Any, **kwargs: Any) -> AIMessage:
        return AIMessage(content=f"{_SUMMARY_TEXT}")

    async def ainvoke(self, *args: Any, **kwargs: Any) -> AIMessage:
        return AIMessage(content=f"{_SUMMARY_TEXT}")


class _RecordingCallback(Callback):
    def __init__(self) -> None:
        self.events: list[Any] = []

    def on_event(self, event: Any) -> None:
        self.events.append(event)


def _marker(index: int) -> str:
    # Long enough that a handful of messages crosses the tiny profile's
    # trigger threshold.
    return f"unique-compaction-marker-{index:03d} " + "content " * 6


def _messages(count: int) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for index in range(count):
        text = _marker(index)
        out.append(HumanMessage(content=text) if index % 2 == 0 else AIMessage(content=text))
    return out


def _state(messages: list[BaseMessage], run_dir: Path | None) -> WorkflowState:
    storage_config: dict[str, Any] = {"workspace_dir": "unused-by-compaction"}
    if run_dir is not None:
        storage_config["run_dir"] = str(run_dir)
    return {
        "data": BusinessData(),
        "flow": FrameworkState(
            thread_id="thread-1",
            run_id="run-1",
            persistent_storage_config=storage_config,
        ),
        "messages": messages,  # type: ignore[typeddict-item]
    }


def _middleware(
    *,
    profile: dict[str, Any] | None = _TINY_PROFILE,
    callbacks: list[Callback] | None = None,
) -> CompactionMiddleware:
    return CompactionMiddleware(
        model=_FakeSummaryModel(profile=profile),
        phase_name="phase-under-test",
        callbacks=callbacks,
    )


def _compaction_events(callback: _RecordingCallback) -> list[Any]:
    return [
        event
        for event in callback.events
        if getattr(event, "event_type", None) == "compaction"
    ]


# ---------------------------------------------------------------------------
# Order contract
# ---------------------------------------------------------------------------


def test_order_contract_pins_compaction_slot() -> None:
    """The 8-slot contract places Compaction after the MVP-3 core trio.

    Compaction acts through ``before_model`` — langchain applies every
    ``before_model`` state update before the model node runs, and
    ToolHistoryIntegrity repairs the outgoing request later, inside
    ``wrap_model_call`` at the model boundary — so the slot satisfies both
    §3.6 constraints (pre-model effect; repair semantics untouched) at any
    contract position. Position 4 keeps the pinned "core trio == contract
    prefix" invariant intact.
    """
    assert MVP0_MIDDLEWARE_ORDER_CONTRACT == (
        "Tracing",
        "ProtocolValidation",
        "CognitiveFlow",
        "ExecutionControl",
        "Compaction",
        "ToolError",
        "LoopDetection",
        "ExitControl",
    )


def test_factory_places_compaction_middleware_at_contract_slot() -> None:
    chain = build_middleware_chain(
        io_manager=IOManager([]),
        phase_name="main",
        compaction_model=_FakeSummaryModel(profile=_TINY_PROFILE),
        compaction_sidecar_writer=write_compaction_sidecar,
    )
    slot = MVP0_MIDDLEWARE_ORDER_CONTRACT.index("Compaction")
    assert isinstance(chain[slot], CompactionMiddleware)


def test_factory_without_model_still_builds_full_chain() -> None:
    """No model (e.g. bare test assembly) keeps the chain shape stable."""
    chain = build_middleware_chain(io_manager=IOManager([]), phase_name="main")
    slot = MVP0_MIDDLEWARE_ORDER_CONTRACT.index("Compaction")
    assert isinstance(chain[slot], CompactionMiddleware)
    assert len(chain) == len(MVP0_MIDDLEWARE_ORDER_CONTRACT)


# ---------------------------------------------------------------------------
# No-trigger path: zero behavior change
# ---------------------------------------------------------------------------


def test_below_threshold_changes_nothing(tmp_path: Path) -> None:
    callback = _RecordingCallback()
    middleware = _middleware(callbacks=[callback])
    state = _state(_messages(2), tmp_path)

    result = middleware.before_model(state, None)  # type: ignore[arg-type]

    assert result is None
    assert _compaction_events(callback) == []
    assert not (tmp_path / "compaction").exists()


def test_without_model_is_inert(tmp_path: Path) -> None:
    callback = _RecordingCallback()
    middleware = CompactionMiddleware(
        model=None, phase_name="phase-under-test", callbacks=[callback]
    )
    state = _state(_messages(40), tmp_path)

    assert middleware.before_model(state, None) is None  # type: ignore[arg-type]
    assert _compaction_events(callback) == []


# ---------------------------------------------------------------------------
# Trigger path: summarize, keep 20, sidecar, event
# ---------------------------------------------------------------------------


def test_trigger_keeps_recent_messages_and_summarizes(tmp_path: Path) -> None:
    middleware = _middleware(callbacks=[_RecordingCallback()])
    messages = _messages(30)
    state = _state(messages, tmp_path)

    result = middleware.before_model(state, None)  # type: ignore[arg-type]

    assert result is not None
    returned = result["messages"]
    assert isinstance(returned[0], RemoveMessage)
    assert returned[0].id == REMOVE_ALL_MESSAGES
    summary_messages = [
        message
        for message in returned[1:]
        if isinstance(message, HumanMessage) and _SUMMARY_TEXT in str(message.content)
    ]
    assert summary_messages, "the summarizer's summary message must replace removed history"
    preserved = returned[len(returned) - COMPACTION_KEEP_MESSAGES :]
    assert [m.id for m in preserved] == [m.id for m in messages[-COMPACTION_KEEP_MESSAGES:]]


def test_trigger_writes_sidecar_with_full_removed_text(tmp_path: Path) -> None:
    callback = _RecordingCallback()
    middleware = _middleware(callbacks=[callback])
    messages = _messages(30)
    state = _state(messages, tmp_path)

    result = middleware.before_model(state, None)  # type: ignore[arg-type]
    assert result is not None

    events = _compaction_events(callback)
    assert len(events) == 1
    event = events[0]
    removed_count = len(messages) - COMPACTION_KEEP_MESSAGES
    assert event.phase_name == "phase-under-test"
    assert event.removed_message_count == removed_count
    assert event.removed_summary

    assert event.content_ref is not None
    sidecar = Path(event.content_ref)
    assert sidecar.is_file()
    assert sidecar.parent == tmp_path / "compaction"

    raw = sidecar.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert payload["phase_name"] == "phase-under-test"
    assert payload["removed_message_count"] == removed_count
    for index in range(removed_count):
        assert _marker(index) in raw, f"sidecar must carry full text of removed message {index}"
    # Preserved messages stay in context; they do not belong in the sidecar.
    assert _marker(29) not in raw


def test_second_compaction_gets_a_fresh_sidecar_file(tmp_path: Path) -> None:
    callback = _RecordingCallback()
    middleware = _middleware(callbacks=[callback])

    first = middleware.before_model(_state(_messages(30), tmp_path), None)  # type: ignore[arg-type]
    second = middleware.before_model(_state(_messages(30), tmp_path), None)  # type: ignore[arg-type]

    assert first is not None and second is not None
    refs = [event.content_ref for event in _compaction_events(callback)]
    assert len(refs) == 2
    assert refs[0] != refs[1]
    assert all(ref and Path(ref).is_file() for ref in refs)


def test_async_hook_has_parity_with_sync(tmp_path: Path) -> None:
    callback = _RecordingCallback()
    middleware = _middleware(callbacks=[callback])
    messages = _messages(30)
    state = _state(messages, tmp_path)

    result = asyncio.run(middleware.abefore_model(state, None))  # type: ignore[arg-type]

    assert result is not None
    assert isinstance(result["messages"][0], RemoveMessage)
    events = _compaction_events(callback)
    assert len(events) == 1
    assert events[0].content_ref is not None
    assert Path(events[0].content_ref).is_file()


# ---------------------------------------------------------------------------
# Degraded storage face: compaction still happens, observability degrades
# ---------------------------------------------------------------------------


def test_missing_run_dir_compacts_but_emits_event_without_ref() -> None:
    callback = _RecordingCallback()
    middleware = _middleware(callbacks=[callback])
    state = _state(_messages(30), run_dir=None)

    result = middleware.before_model(state, None)  # type: ignore[arg-type]

    assert result is not None, "missing storage face must not disable compaction itself"
    events = _compaction_events(callback)
    assert len(events) == 1
    assert events[0].content_ref is None
    assert events[0].removed_message_count == 30 - COMPACTION_KEEP_MESSAGES


# ---------------------------------------------------------------------------
# Profile fallback (migrated `_ensure_summarization_profile` semantics)
# ---------------------------------------------------------------------------


def test_profileless_model_does_not_explode_at_construction() -> None:
    middleware = CompactionMiddleware(
        model=_FakeSummaryModel(profile=None), phase_name="phase-under-test"
    )
    # The fallback window is deliberately conservative; a couple of small
    # messages must stay far below the 0.8 trigger fraction.
    state = _state(_messages(2), run_dir=None)
    assert middleware.before_model(state, None) is None  # type: ignore[arg-type]
    # The wrapped summarizer must see the migrated fallback profile.
    summarizer = middleware._summarizer  # noqa: SLF001 — pins the migrated fallback value
    assert summarizer is not None
    assert summarizer.model.profile == {
        "max_input_tokens": SUMMARIZATION_FALLBACK_MAX_INPUT_TOKENS
    }


def test_parameters_match_p0_1_ruling() -> None:
    assert COMPACTION_TRIGGER_FRACTION == 0.8
    assert COMPACTION_KEEP_MESSAGES == 20
