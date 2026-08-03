"""Bounded projections over a run trace (决议 2026-08-03 P4-C).

`get_run_detail` answers "how did the run end"; nothing answered "what happened
inside a phase". A CLI session diagnosing a stuck run therefore parsed
`trace.jsonl` with its own `python3` one-liners and ran `strings` over the
checkpoint WAL — it reached the right conclusion (exp-b-round3 found the
`io.outputs.required` defect that way) but every step of that evidence trail
bypassed the product's observability surface.

This module turns the same trace into two bounded answers: a per-phase tally of
what the agent loop actually did, and a filtered slice of events small enough to
hand back to a model. A trace runs to a quarter of a megabyte, so a full dump is
never an option — the established shape for that in this repo is a bounded query
(PR #499 replaced the registry dump with a bounded search).

Pure on purpose: the caller supplies the events, so every rule here is assertable
against a recorded trace instead of a live run.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.core.adapters.engine import EventEnvelope

#: A phase ends when its agent submits `finish_task` and the engine accepts it.
PHASE_COMPLETE_RESULT = "PHASE_COMPLETE"

#: How much of a rejection reason to keep per distinct reason.
REASON_CHAR_LIMIT = 240

#: How many distinct rejection reasons to report per phase.
TOP_REASONS = 5

#: Default and maximum events returned by one slice request.
DEFAULT_EVENT_LIMIT = 50
MAX_EVENT_LIMIT = 200

#: How much of a tool result to keep on a projected event.
RESULT_CHAR_LIMIT = 400


@dataclass
class PhaseTally:
    """What one phase's agent loop actually did."""

    iterations: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    submissions: int = 0
    rejections: int = 0
    accepted: int = 0
    rejection_reasons: Counter[str] = field(default_factory=Counter)

    def as_payload(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "submissions": self.submissions,
            "rejections": self.rejections,
            "accepted": self.accepted,
            "top_rejection_reasons": [
                {"reason": reason, "count": count}
                for reason, count in self.rejection_reasons.most_common(TOP_REASONS)
            ],
        }


def _phase_of(event: EventEnvelope) -> str:
    phase = event.payload.get("phase_name")
    return phase if isinstance(phase, str) and phase else "(run)"


def rejection_reason(result: str) -> str:
    """Reduce a rejected submission to the part that says why.

    Every rejection observed carries a banner line first and the concrete reasons
    after it, so the banner is dropped when there is more than one line. A
    single-line result is kept whole rather than guessed at.
    """
    lines = result.strip().split("\n")
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else result.strip()
    return body[:REASON_CHAR_LIMIT]


def summarize_phases(events: list[EventEnvelope]) -> dict[str, dict[str, Any]]:
    """Tally each phase's loop, submissions and rejection reasons."""
    tallies: dict[str, PhaseTally] = {}

    for event in events:
        tally = tallies.setdefault(_phase_of(event), PhaseTally())
        if event.event_type == "agent_loop_iteration":
            tally.iterations += 1
        elif event.event_type == "llm_call":
            tally.llm_calls += 1
        elif event.event_type == "tool_call":
            tally.tool_calls += 1
            if event.payload.get("tool_name") != "finish_task":
                continue
            tally.submissions += 1
            result = event.payload.get("result")
            if not isinstance(result, str) or not result.strip():
                continue
            if result.strip() == PHASE_COMPLETE_RESULT:
                tally.accepted += 1
            else:
                tally.rejections += 1
                tally.rejection_reasons[rejection_reason(result)] += 1

    return {phase: tally.as_payload() for phase, tally in tallies.items()}


def _truncate(value: Any, limit: int) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "…"
    return value


def project_event(event: EventEnvelope) -> dict[str, Any]:
    """Keep the fields that identify an event; drop the ones that dwarf a reply.

    `llm_call` carries the whole prompt and response, `run_started` the whole
    initial context — those belong in the run artifacts, not in a tool result.
    """
    payload = event.payload
    projected: dict[str, Any] = {
        "seq": event.seq,
        "event_type": event.event_type,
        "phase": _phase_of(event),
        "timestamp": event.timestamp.isoformat(),
    }
    if event.event_type == "agent_loop_iteration":
        projected["iteration"] = payload.get("iteration")
    elif event.event_type == "llm_call":
        projected["input_tokens"] = payload.get("input_tokens")
        projected["output_tokens"] = payload.get("output_tokens")
    elif event.event_type == "tool_call":
        projected["tool_name"] = payload.get("tool_name")
        projected["duration_ms"] = payload.get("duration_ms")
        projected["result"] = _truncate(payload.get("result"), RESULT_CHAR_LIMIT)
    elif event.event_type == "run_ended":
        projected["status"] = payload.get("status")
        projected["wall_time_seconds"] = payload.get("wall_time_seconds")
    if event.error_code:
        projected["error_code"] = event.error_code
    return projected


def slice_events(
    events: list[EventEnvelope],
    *,
    phase: str | None = None,
    event_types: list[str] | None = None,
    since_seq: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Filter, page and project a trace into a reply-sized slice."""
    wanted = set(event_types) if event_types else None
    matched = [
        event
        for event in events
        if (phase is None or _phase_of(event) == phase)
        and (wanted is None or event.event_type in wanted)
        and (since_seq is None or event.seq > since_seq)
    ]
    capped = max(1, min(limit or DEFAULT_EVENT_LIMIT, MAX_EVENT_LIMIT))
    page = matched[:capped]
    return {
        "events": [project_event(event) for event in page],
        "matched_total": len(matched),
        "returned": len(page),
        "next_seq": page[-1].seq if len(page) < len(matched) and page else None,
    }
