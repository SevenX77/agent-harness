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

from graph_agent.callbacks.events import PredictChainStartEvent
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


def record_mock_source(phase_name: str, source: MockedSource) -> None:
    """Record the source selected by the Predict interception layer."""

    _DEFAULT_SOURCE_CACHE.record(phase_name, source)


def get_mock_source(phase_name: str) -> MockedSource | None:
    """Return the cached source for a phase, if the gateway touched it."""

    return _DEFAULT_SOURCE_CACHE.get(phase_name)


def clear_mock_source_cache() -> None:
    """Clear process-local Predict source cache between tests or runs."""

    _DEFAULT_SOURCE_CACHE.clear()


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

    def on_phase_start(self, phase_name: str, context: dict[str, Any]) -> None:
        """Start a Predict phase and retain business inputs for export."""

        super().on_phase_start(phase_name, context)
        if self._phase_stack:
            self._phase_stack[-1]["inputs"] = context

    def on_phase_end(
        self,
        phase_name: str,
        context: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        """Finalize a phase with zeroed metrics and cached mock source metadata."""

        zeroed_metrics = _zero_usage_values(metrics)
        source = self._source_cache.pop(phase_name)
        if source is not None:
            zeroed_metrics["mocked_source"] = source
        phase_count = len(self._phases)
        super().on_phase_end(phase_name, context, zeroed_metrics)
        if len(self._phases) > phase_count:
            phase = self._phases[-1]
            phase["outputs"] = context
            phase["metrics"] = zeroed_metrics
            if source is not None:
                phase["mocked_source"] = source

    def on_llm_call(
        self,
        phase_name: str,
        input_tokens: int,
        output_tokens: int,
        *,
        messages: list[dict[str, Any]] | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """Record Predict LLM activity while forcing all usage counters to zero."""

        zeroed_response = _zero_usage_values(response_data or {})
        super().on_llm_call(
            phase_name,
            0,
            0,
            messages=messages,
            response_data=zeroed_response,
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
    "get_mock_source",
    "record_mock_source",
]
