"""Phase-aware structured tracer. Builds trace in-memory, writes to JSON on save().

Replaces the old TraceExporter (LangSmith-based). Phase structure is a first-class

citizen — no heuristic guessing.

Usage::
    tracer = TracingCallback()
    harness = GraphAgentHarness(phases=..., callbacks=[tracer])
    result = harness.run(...)
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

from graph_agent.callbacks.base import (
    EVENT_AMBIGUITY_REPORT,
    EVENT_COMPACTION,
    EVENT_DEAD_END_PRUNED,
    EVENT_FINISH_TASK,
    EVENT_LLM_CALL,
    EVENT_NUDGE,
    EVENT_PHASE_END,
    EVENT_PHASE_START,
    EVENT_RETRY,
    EVENT_TOOL_CALL,
    EVENT_VALIDATION_FAIL,
    EVENT_WORKING_MEMORY_UPDATE,
    Callback,
)
from graph_agent.callbacks.events import (
    AmbiguityReportEvent,
    CallbackEvent,
    CompactionEvent,
    DeadEndPrunedEvent,
    FinishTaskEvent,
    LLMCallEvent,
    NudgeEvent,
    PhaseEndEvent,
    PhaseStartEvent,
    RetryEvent,
    ToolCallEvent,
    ValidationFailEvent,
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
        self._typed_jsonl_path = self._trace_dir / "tracing.jsonl"

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
        ``tracing.jsonl`` filename is the new Studio-facing source of truth.
        """
        if self._typed_jsonl_path is None:
            return
        with self._typed_jsonl_path.open("a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def on_event(self, event: CallbackEvent) -> None:
        """New-style sink: log the typed event to tracing.jsonl.

        Emitters that call ``cb.on_event(event)`` directly (for example the
        forthcoming ``TracingClientProxy`` in Step 4 and the ``parallel_map``
        builtin in Task 4.3) bypass the legacy on_* dispatch entirely and
        land here. We deliberately do NOT call the base-class dispatcher,
        which would double-count events that also flow through the legacy
        hooks below.
        """
        self._write_typed_event(event)

    def _active_phase(self) -> dict[str, Any] | None:
        """Return the innermost active phase segment, if any."""
        if not self._phase_stack:
            return None
        return self._phase_stack[-1]

    def on_phase_start(self, phase_name: str, context: dict[str, Any]) -> None:
        """Start a new phase trace segment."""
        self._phase_stack.append(
            {
                "name": phase_name,
                "start_time": datetime.now(UTC).isoformat(),
                "_start_mono": time.monotonic(),
                "input_tokens": 0,
                "output_tokens": 0,
                "llm_calls": [],
                "tool_calls": [],
                "validation": {"passed": True, "retries": 0, "errors": []},
            }
        )
        self._write_event(
            EVENT_PHASE_START,
            phase_name,
            {"context_keys": list(context.keys())},
        )
        self._write_typed_event(PhaseStartEvent(phase_name=phase_name, context=context))

    def on_phase_end(
        self,
        phase_name: str,
        context: dict[str, Any],
        metrics: dict[str, Any],
    ) -> None:
        """Finalize the active phase trace segment."""
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
            EVENT_PHASE_END,
            phase_name,
            {"context_keys": list(context.keys()), "metrics": metrics},
        )
        self._write_typed_event(
            PhaseEndEvent(phase_name=phase_name, context=context, metrics=metrics)
        )

    def on_llm_call(
        self,
        phase_name: str,
        input_tokens: int,
        output_tokens: int,
        *,
        messages: list[dict[str, Any]] | None = None,
        response_data: dict[str, Any] | None = None,
    ) -> None:
        """Append one LLM event to the trace."""
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
            EVENT_LLM_CALL,
            phase_name,
            {
                "messages": messages or [],
                "response": response_data or {},
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            },
        )
        self._write_typed_event(
            LLMCallEvent(
                phase_name=phase_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                messages=messages,
                response_data=response_data,
            )
        )

    def on_tool_call(
        self,
        phase_name: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
        *,
        duration_ms: float | None = None,
    ) -> None:
        """Append one tool event to the trace."""
        self._total_tool_calls += 1
        active_phase = self._active_phase()
        if active_phase:
            active_phase["tool_calls"].append(
                {
                    "name": tool_name,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
        self._write_event(
            EVENT_TOOL_CALL,
            phase_name,
            {
                "tool_name": tool_name,
                "args": args,
                "result": result,
                "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
            },
        )
        self._write_typed_event(
            ToolCallEvent(
                phase_name=phase_name,
                tool_name=tool_name,
                args=args,
                result=result,
                duration_ms=duration_ms,
            )
        )

    def on_validation_fail(
        self,
        phase_name: str,
        errors: list[str],
        retry_count: int,
    ) -> None:
        """Record validator failure in the trace."""
        # Harden against validators that return str / tuple / iterable
        # instead of list[str] — surfaced from the first real story-
        # deconstruction run; old behaviour silently appended a str which
        # the typed event rightfully rejects.
        if isinstance(errors, str):
            errors_list = [errors]
        elif errors is None:
            errors_list = []
        else:
            try:
                errors_list = [str(e) for e in errors]
            except TypeError:
                errors_list = [str(errors)]

        active_phase = self._active_phase()
        if active_phase:
            active_phase["validation"]["passed"] = False
            active_phase["validation"]["errors"].extend(errors_list)
        self._write_event(
            EVENT_VALIDATION_FAIL,
            phase_name,
            {"passed": False, "errors": errors_list, "retry_count": retry_count},
        )
        self._write_typed_event(
            ValidationFailEvent(phase_name=phase_name, errors=errors_list, retry_count=retry_count)
        )

    def on_retry(
        self,
        phase_name: str,
        target_phase: str,
        feedback: list[str],
    ) -> None:
        """Record retry routing in the trace."""
        active_phase = self._active_phase()
        if active_phase:
            active_phase["validation"]["retries"] += 1
        self._write_event(
            EVENT_RETRY,
            phase_name,
            {"target_phase": target_phase, "feedback": feedback},
        )
        self._write_typed_event(
            RetryEvent(phase_name=phase_name, target_phase=target_phase, feedback=feedback)
        )

    def on_finish_task(
        self,
        phase_name: str,
        reasoning: str,
        evidence: list[str],
    ) -> None:
        """Record finish_task output in the trace."""
        self._write_event(
            EVENT_FINISH_TASK,
            phase_name,
            {"reasoning": reasoning, "evidence": evidence},
        )
        self._write_typed_event(
            FinishTaskEvent(phase_name=phase_name, reasoning=reasoning, evidence=evidence)
        )

    def on_nudge(
        self,
        phase_name: str,
        nudge_count: int,
        nudge_type: str = "standard",
    ) -> None:
        """Record a cognitive nudge in the trace."""
        self._write_event(
            EVENT_NUDGE,
            phase_name,
            {"count": nudge_count, "type": nudge_type},
        )
        self._write_typed_event(
            NudgeEvent(phase_name=phase_name, nudge_count=nudge_count, nudge_type=nudge_type)
        )

    def on_working_memory_update(
        self,
        phase_name: str,
        content_length: int,
    ) -> None:
        """Record working-memory update in the trace."""
        self._write_event(
            EVENT_WORKING_MEMORY_UPDATE,
            phase_name,
            {"content_length": content_length},
        )
        self._write_typed_event(
            WorkingMemoryUpdateEvent(phase_name=phase_name, content_length=content_length)
        )

    def on_dead_end_pruned(
        self,
        phase_name: str,
        summary: str,
    ) -> None:
        """Record dead-end pruning in the trace."""
        self._write_event(
            EVENT_DEAD_END_PRUNED,
            phase_name,
            {"summary": summary},
        )
        self._write_typed_event(DeadEndPrunedEvent(phase_name=phase_name, summary=summary))

    def on_compaction(
        self,
        phase_name: str,
        removed_pairs: int,
    ) -> None:
        """Record history compaction in the trace."""
        self._write_event(
            EVENT_COMPACTION,
            phase_name,
            {"removed_pairs": removed_pairs},
        )
        self._write_typed_event(CompactionEvent(phase_name=phase_name, removed_pairs=removed_pairs))

    def on_ambiguity_report(
        self,
        phase_name: str,
        ambiguity_type: str,
        question: str,
        decision: str,
    ) -> None:
        """Record ambiguity feedback in the trace."""
        self._write_event(
            EVENT_AMBIGUITY_REPORT,
            phase_name,
            {
                "ambiguity_type": ambiguity_type,
                "question": question,
                "decision": decision,
            },
        )
        self._write_typed_event(
            AmbiguityReportEvent(
                phase_name=phase_name,
                ambiguity_type=ambiguity_type,
                question=question,
                decision=decision,
            )
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
