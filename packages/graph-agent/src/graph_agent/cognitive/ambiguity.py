"""Non-blocking ambiguity reporting tool for GraphAgent phases."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)


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

    return json.dumps(
        {
            "status": "recorded",
            "index": len(reports) - 1,
            "type": ambiguity_type,
        },
        ensure_ascii=False,
    )
