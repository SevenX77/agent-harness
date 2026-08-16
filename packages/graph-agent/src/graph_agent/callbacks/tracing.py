"""Phase-aware structured tracer. Builds trace in-memory, writes to JSON on save().

Phase structure is a first-class citizen — no heuristic guessing.

Usage::
    tracer = TracingCallback()
    result = run_skill(..., event_subscriber=tracer.on_event)
    tracer.save("/path/to/output")
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from graph_agent.callbacks.base import Callback
from graph_agent.callbacks.events import (
    CallbackEvent,
    CompactionEvent,
    DeadEndPrunedEvent,
    LLMCallEvent,
    NudgeEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    ToolCallEvent,
    WorkingMemoryUpdateEvent,
)

logger = logging.getLogger(__name__)


class TracingCallback(Callback):
    """Phase-aware structured tracer."""

    def __init__(self, trace_dir: str | Path | None = None) -> None:
        """Initialize in-memory trace state for one run."""
        self._run_id = uuid.uuid4().hex[:12]
        self._start_time: float = time.monotonic()
        self._start_iso: str = datetime.now(UTC).isoformat()
        self._phases: list[dict[str, Any]] = []
        self._phase_stack: list[dict[str, Any]] = []
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_llm_calls: int = 0
        self._total_tool_calls: int = 0
        self._trace_dir: Path | None = None
        self._jsonl_path: Path | None = None
        self._typed_jsonl_path: Path | None = None
        if trace_dir is not None:
            self.set_trace_dir(trace_dir)

    def set_trace_dir(self, trace_dir: str | Path) -> None:
        """Set trace output directory and initialize JSONL file paths."""
        self._trace_dir = Path(trace_dir)
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self._trace_dir / f"{self._run_id}.jsonl"
        # Task 3.6: fixed-name typed-event stream. One line per Pydantic
        # CallbackEvent (model_dump_json), appended in timestamp order.
        self._typed_jsonl_path = self._trace_dir / "trace.jsonl"

    def _write_event(self, event_type: str, phase: str, data: dict[str, Any]) -> None:
        """Append one structured event line to JSONL trace (legacy shape)."""
        if self._jsonl_path is None:
            return
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": self._run_id,
            "event_type": event_type,
            "phase": phase,
            "data": data,
        }
        with self._jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def _write_typed_event(self, event: CallbackEvent) -> None:
        """Append one Pydantic CallbackEvent as JSON to the typed trace stream.

        This is the Task 3.6 sink. The legacy per-run JSONL (``_write_event``)
        stays intact for tooling that depends on the old shape; the fixed
        ``trace.jsonl`` filename is the Studio-facing source of truth.
        """
        if self._typed_jsonl_path is None:
            return
        # See _TraceJsonlSink.emit: droppable frames stay out of the record.
        if not getattr(event, "persisted", True):
            return
        with self._typed_jsonl_path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def on_event(self, event: CallbackEvent) -> None:
        """Record one typed event: the raw line, plus the phase segments it builds.

        Every event lands here — this is the only entrypoint. The flat phase
        segments (``self._phases``, which Predict exports) are built by the
        ``_record_*`` methods below; subclasses that need to enrich a segment
        override those rather than intercepting the event stream.
        """
        self._write_typed_event(event)
        if isinstance(event, PhaseStartEvent):
            self._record_phase_start(event)
        elif isinstance(event, PhaseEndEvent):
            self._record_phase_end(event)
        elif isinstance(event, LLMCallEvent):
            self._record_llm_call(event)
        elif isinstance(event, ToolCallEvent):
            self._record_tool_call(event)
        elif isinstance(event, NudgeEvent):
            self._write_event(
                event.event_type,
                event.phase_name,
                {"count": event.nudge_count, "type": event.nudge_type},
            )
        elif isinstance(event, WorkingMemoryUpdateEvent):
            self._write_event(
                event.event_type,
                event.phase_name,
                {"content_length": event.content_length},
            )
        elif isinstance(event, DeadEndPrunedEvent):
            self._write_event(event.event_type, event.phase_name, {"summary": event.summary})
        elif isinstance(event, CompactionEvent):
            self._write_event(
                event.event_type,
                event.phase_name,
                {"removed_message_count": event.removed_message_count},
            )

    def _active_phase(self) -> dict[str, Any] | None:
        """Return the innermost active phase segment, if any."""
        if not self._phase_stack:
            return None
        return self._phase_stack[-1]

    def _record_phase_start(self, event: PhaseStartEvent) -> None:
        """Start a new phase trace segment."""
        phase_name = event.phase_name
        self._phase_stack.append(
            {
                "name": phase_name,
                "start_time": datetime.now(UTC).isoformat(),
                "_start_mono": time.monotonic(),
                "input_tokens": 0,
                "output_tokens": 0,
                "llm_calls": [],
                "tool_calls": [],
            }
        )
        self._write_event(
            event.event_type,
            phase_name,
            {"context_keys": list(event.context.keys())},
        )

    def _record_phase_end(self, event: PhaseEndEvent) -> None:
        """Finalize the active phase trace segment."""
        phase_name = event.phase_name
        phase_index = next(
            (
                idx
                for idx in range(len(self._phase_stack) - 1, -1, -1)
                if self._phase_stack[idx]["name"] == phase_name
            ),
            -1,
        )
        if phase_index < 0:
            return
        phase_data = self._phase_stack.pop(phase_index)
        start_mono = phase_data.pop("_start_mono", time.monotonic())
        phase_data["end_time"] = datetime.now(UTC).isoformat()
        phase_data["duration_sec"] = round(time.monotonic() - start_mono, 2)
        self._phases.append(phase_data)
        self._write_event(
            event.event_type,
            phase_name,
            {"context_keys": list(event.context.keys()), "metrics": event.metrics},
        )

    def _record_llm_call(self, event: LLMCallEvent) -> None:
        """Append one LLM event to the trace."""
        phase_name = event.phase_name
        input_tokens = event.input_tokens
        output_tokens = event.output_tokens
        self._total_llm_calls += 1
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        active_phase = self._active_phase()
        if active_phase:
            active_phase["input_tokens"] += input_tokens
            active_phase["output_tokens"] += output_tokens
            active_phase["llm_calls"].append(
                {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        self._write_event(
            event.event_type,
            phase_name,
            {
                "response": event.response_data,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            },
        )

    def _record_tool_call(self, event: ToolCallEvent) -> None:
        """Append one tool event to the trace."""
        self._total_tool_calls += 1
        active_phase = self._active_phase()
        if active_phase:
            active_phase["tool_calls"].append(
                {
                    "name": event.tool_name,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        self._write_event(
            event.event_type,
            event.phase_name,
            {
                "tool_name": event.tool_name,
                "args": event.args,
                "result": event.result,
                "duration_ms": (
                    round(event.duration_ms, 2) if event.duration_ms is not None else None
                ),
            },
        )

    def summary(self) -> dict[str, Any]:
        """Return run summary statistics."""
        total_duration = round(time.monotonic() - self._start_time, 2)
        return {
            "run_id": self._run_id,
            "start_time": self._start_iso,
            "total_duration_sec": total_duration,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_llm_calls": self._total_llm_calls,
            "total_tool_calls": self._total_tool_calls,
            "phase_count": len(self._phases),
        }

    def save(self, output_dir: str | Path) -> str:
        """Serialize trace to JSON and write to output_dir/{run_id}_summary.json."""
        total_duration = round(time.monotonic() - self._start_time, 2)
        trace = {
            "run_id": self._run_id,
            "start_time": self._start_iso,
            "end_time": datetime.now(UTC).isoformat(),
            "total_duration_sec": total_duration,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_llm_calls": self._total_llm_calls,
            "total_tool_calls": self._total_tool_calls,
            "phases": self._phases,
        }
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        if self._jsonl_path is None:
            self.set_trace_dir(out)
        file_path = out / f"{self._run_id}_summary.json"
        file_path.write_text(
            json.dumps(trace, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("[TracingCallback] Saved trace to %s", file_path)
        return str(file_path)
