"""Non-blocking ambiguity reporting tool for GraphAgent phases."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)

_REF_RE = re.compile(r"@reference:([A-Za-z0-9_-]+)")
_PROTOCOL_RE = re.compile(r"@protocol:([A-Za-z0-9_-]+)")


def log_ambiguity(
    question: str,
    ambiguity_type: Literal[
        "missing_info",
        "ambiguous_requirement",
        "approach_choice",
        "risk_confirmation",
        "suggestion",
    ],
    decision: str,
    reason: str = "",
    ctx: dict[str, Any] | None = None,
) -> str:
    """Record ambiguity without interrupting pipeline execution.

    Args:
        question: The unclear point encountered by the agent.
        ambiguity_type: Category of ambiguity.
        decision: The decision the agent chose for this run.
        reason: Optional rationale for the decision.
        ctx: Injected runtime context.
    """
    if ctx is None:
        logger.warning("log_ambiguity called without context, report ignored")
        return json.dumps(
            {
                "status": "ignored",
                "reason": "missing_context",
            },
            ensure_ascii=False,
        )

    reports = ctx.get("_ambiguity_reports")
    if not isinstance(reports, list):
        reports = []
        ctx["_ambiguity_reports"] = reports

    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "phase": ctx.get("_current_phase"),
        "type": ambiguity_type,
        "question": question,
        "decision": decision,
        "reason": reason,
    }
    reports.append(record)
    _emit_ambiguity_logged(ctx, record)

    return json.dumps(
        {
            "status": "recorded",
            "index": len(reports) - 1,
            "type": ambiguity_type,
        },
        ensure_ascii=False,
    )


def _emit_ambiguity_logged(ctx: dict[str, Any], record: dict[str, Any]) -> None:
    callbacks = ctx.get("_callbacks")
    if not isinstance(callbacks, list):
        return
    from graph_agent.callbacks.events import AmbiguityLoggedEvent

    question = str(record.get("question") or "")
    reason = str(record.get("reason") or "")
    payload = AmbiguityLoggedEvent(
        phase_name=record.get("phase"),
        ambiguity_type=str(record.get("type") or ""),
        question=question,
        decision=str(record.get("decision") or ""),
        reason=reason,
        related_refs=_REF_RE.findall(question + " " + reason),
        related_protocols=_PROTOCOL_RE.findall(question + " " + reason),
    )
    for callback in callbacks:
        on_event = getattr(callback, "on_event", None)
        if on_event is None:
            continue
        try:
            on_event(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ambiguity_logged callback failed: %s", exc)
