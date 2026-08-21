"""Predict-mode tracing helpers.

The module stays private to keep Predict V2 observability out of the public
SDK surface while giving Studio a trace stream that is explicitly marked as
synthetic and cost-free.
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from graph_agent.callbacks.events import (
    LLMCallEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    PredictChainStartEvent,
)
from graph_agent.callbacks.tracing import TracingCallback

MockedSource = Literal["golden_case", "copilot", "heuristic_stub", "manual"]

_ZERO_USAGE_KEYS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "total_cost",
    "cost",
}


class PredictMockSourceCache:
    """Small in-process cache from interception events to phase trace finalizers."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sources: dict[str, MockedSource] = {}

    def record(self, phase_name: str, source: MockedSource) -> None:
        with self._lock:
            self._sources[phase_name] = source

    def get(self, phase_name: str) -> MockedSource | None:
        with self._lock:
            return self._sources.get(phase_name)

    def pop(self, phase_name: str) -> MockedSource | None:
        with self._lock:
            return self._sources.pop(phase_name, None)

    def clear(self) -> None:
        with self._lock:
            self._sources.clear()


_DEFAULT_SOURCE_CACHE = PredictMockSourceCache()


#: Durable per-run log of the mock source chosen for each phase. The cache above
#: is CONSUMED (popped) by the trace stamper at phase end, which happens before
#: the phase's output validator runs — so anything downstream of the model call
#: that needs to know which mock source produced this output reads the log, not
#: the cache.
_MOCK_SOURCE_LOG: dict[str, MockedSource] = {}


def record_mock_source(phase_name: str, source: MockedSource) -> None:
    """Record the source selected by the Predict interception layer."""

    _DEFAULT_SOURCE_CACHE.record(phase_name, source)
    _MOCK_SOURCE_LOG[phase_name] = source


def get_recorded_mock_source(phase_name: str) -> MockedSource | None:
    """Return the mock source chosen for a phase, surviving trace stamping."""

    return _MOCK_SOURCE_LOG.get(phase_name)


def get_mock_source(phase_name: str) -> MockedSource | None:
    """Return the cached source for a phase, if the gateway touched it."""

    return _DEFAULT_SOURCE_CACHE.get(phase_name)


def clear_mock_source_cache() -> None:
    """Clear process-local Predict source caches between tests or runs."""

    _DEFAULT_SOURCE_CACHE.clear()
    _MOCK_SOURCE_LOG.clear()


_VALIDATOR_DOWNGRADES: dict[str, str] = {}


def record_validator_downgrade(phase_name: str, message: str) -> None:
    """Record that a phase's author validator rejected its P2 placeholder stub
    output and the predict flight continued anyway (decision doc 2026-08-15
    predict-stub-validator-downgrade)."""

    _VALIDATOR_DOWNGRADES[phase_name] = message


def get_validator_downgrade(phase_name: str) -> str | None:
    """Return the recorded downgrade message for a phase, if any."""

    return _VALIDATOR_DOWNGRADES.get(phase_name)


def clear_validator_downgrades() -> None:
    """Clear process-local downgrade records between tests or runs."""

    _VALIDATOR_DOWNGRADES.clear()


class PredictTracingCallback(TracingCallback):
    """Tracing callback variant for Predict runs."""

    def __init__(
        self,
        *args: Any,
        source_cache: PredictMockSourceCache | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._source_cache = source_cache or _DEFAULT_SOURCE_CACHE
        self._root_metadata: dict[str, Any] = {}

    @property
    def root_metadata(self) -> dict[str, Any]:
        return self._root_metadata

    @property
    def phases(self) -> list[dict[str, Any]]:
        return self._phases

    @property
    def phases_in_progress(self) -> list[dict[str, Any]]:
        return self._phase_stack

    def on_chain_start(self, metadata: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """Mark the root run metadata as Predict before execution proceeds."""

        del kwargs
        root_metadata = metadata if metadata is not None else {}
        root_metadata["is_predict"] = True
        self._root_metadata = root_metadata
        self._write_event("predict_chain_start", "<root>", {"metadata": root_metadata})
        self._write_typed_event(PredictChainStartEvent(metadata=root_metadata))

    def _record_phase_start(self, event: PhaseStartEvent) -> None:
        """Start a Predict phase and retain business inputs for export."""

        super()._record_phase_start(event)
        if self._phase_stack:
            self._phase_stack[-1]["inputs"] = event.context

    def _record_phase_end(self, event: PhaseEndEvent) -> None:
        """Finalize a phase and tag it with the mock source it was served from.

        Nothing zeroes a spend here any more. A predict phase's spend was being
        expressed twice — once by zeroing a ``metrics`` dict on the way past,
        once by the phase's own ``input_tokens``/``output_tokens``, which only
        ever grow from ``LLMCallEvent``s and stay at 0 when the phase is stubbed.
        The second one is the answer, and it needs no help.
        """

        phase_name = event.phase_name
        source = self._source_cache.pop(phase_name)
        phase_count = len(self._phases)
        super()._record_phase_end(event)
        if len(self._phases) > phase_count:
            phase = self._phases[-1]
            phase["outputs"] = event.context
            # Which iteration this execution belongs to, so a reader can tell a
            # phase the PLAN repeats from a phase that came back. Imported here
            # rather than at module scope because graph_assembler imports the
            # runner, which imports this module. Empty outside any iterate.
            from graph_agent.core.graph_assembler import active_outer_ns

            phase["iteration_ns"] = active_outer_ns.get()
            if source is not None:
                phase["mocked_source"] = source
            downgrade = get_validator_downgrade(phase_name)
            if downgrade is not None:
                phase["validator_downgraded"] = downgrade

    def _record_llm_call(self, event: LLMCallEvent) -> None:
        """Record Predict LLM activity while forcing all usage counters to zero."""

        super()._record_llm_call(
            event.model_copy(
                update={
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "response_data": _zero_usage_values(event.response_data),
                }
            )
        )

    def save(self, output_dir: str | Path) -> str:
        """Persist the trace and include root Predict metadata in the summary."""

        file_path = super().save(output_dir)
        path = Path(file_path)
        trace = json.loads(path.read_text(encoding="utf-8"))
        trace["metadata"] = self._root_metadata
        path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        return file_path


def _zero_usage_values(payload: dict[str, Any]) -> dict[str, Any]:
    zeroed: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _ZERO_USAGE_KEYS:
            zeroed[key] = 0
        elif isinstance(value, dict):
            zeroed[key] = _zero_usage_values(value)
        else:
            zeroed[key] = value
    return zeroed


__all__ = [
    "PredictMockSourceCache",
    "PredictTracingCallback",
    "clear_mock_source_cache",
    "clear_validator_downgrades",
    "get_mock_source",
    "get_recorded_mock_source",
    "get_validator_downgrade",
    "record_mock_source",
    "record_validator_downgrade",
]
