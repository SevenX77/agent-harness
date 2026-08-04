"""闸门结果领域事件(决议 2026-08-03「能力对等与状态对等」D2/D3)。

前端的闸门状态只由它自己发起的动作推进,于是 copilot 经 MCP 跑完 compile/predict/run
之后,工具栏、错误抽屉、Trace 面板全都不动。这里提供闸门在**完成之后**广播的一条
领域事件,让"谁发起的"不再决定"前端知不知道"。

两条约束写在这个模块里,而不是散在调用点:

- **发布点属于 service 层**。HTTP 路由与 MCP 工具的公共下游只有 service;发在
  router 上,MCP 路径就不会发事件,状态对等在实现层即被破坏。
- **载荷钉住数据集**。前端据 `skill_id` 与 `content_hash`/`run_id` 只重算对应
  skill 的闸门状态,不做宽泛刷新(AGENTS.md「Server-authoritative state +
  event-driven revalidation」)。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from app.services.event_bus import STUDIO_EVENTS_TOPIC, event_bus

logger = logging.getLogger(__name__)

SKILL_GATE_EVENT_TYPE = "skill_gate"

Gate = Literal["compile", "predict", "run"]
#: ``paused`` (waiting to be resumed) and ``stopped`` (ended by the user) are
#: neither failures: a surface told "fail" would show an error report for a defect
#: that never was, and one told "pass" would hide that the run never finished.
GateOutcome = Literal["started", "pass", "fail", "paused", "stopped"]


def build_skill_gate_event(
    *,
    skill_id: str,
    gate: Gate,
    outcome: GateOutcome,
    content_hash: str | None = None,
    run_id: str | None = None,
    defect_count: int = 0,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble one gate-outcome event payload.

    A failed gate carries its full aggregated defect set, because the receiver must
    render the SAME list every other surface renders; a receiver that re-derived its
    own would be the parallel validation pass the diagnostics-SSOT rule forbids.
    """
    return {
        "type": SKILL_GATE_EVENT_TYPE,
        "timestamp": datetime.now(UTC).isoformat(),
        "source": "service",
        "skill_id": skill_id,
        "gate": gate,
        "outcome": outcome,
        "content_hash": content_hash,
        "run_id": run_id,
        "defect_count": defect_count,
        "errors": errors or [],
    }


async def publish_skill_gate(
    *,
    skill_id: str,
    gate: Gate,
    outcome: GateOutcome,
    content_hash: str | None = None,
    run_id: str | None = None,
    defect_count: int = 0,
    errors: list[dict[str, Any]] | None = None,
) -> None:
    """Broadcast one gate outcome; never let the broadcast break the gate."""
    event = build_skill_gate_event(
        skill_id=skill_id,
        gate=gate,
        outcome=outcome,
        content_hash=content_hash,
        run_id=run_id,
        defect_count=defect_count,
        errors=errors,
    )
    try:
        await event_bus.publish(STUDIO_EVENTS_TOPIC, event)
    except Exception:
        logger.exception(
            "phase=publish_skill_gate action=publish status=failed payload=%s",
            event,
        )


def publish_skill_gate_from_thread(
    *,
    skill_id: str,
    gate: Gate,
    outcome: GateOutcome,
    content_hash: str | None = None,
    run_id: str | None = None,
    defect_count: int = 0,
) -> None:
    """Broadcast from synchronous gate code (predict runs the graph inline)."""
    event = build_skill_gate_event(
        skill_id=skill_id,
        gate=gate,
        outcome=outcome,
        content_hash=content_hash,
        run_id=run_id,
        defect_count=defect_count,
    )
    try:
        event_bus.broadcast_from_thread(event)
    except Exception:
        logger.exception(
            "phase=publish_skill_gate action=broadcast_from_thread status=failed payload=%s",
            event,
        )
