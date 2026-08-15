import { describe, expect, it } from "vitest"
import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import {
  NODE_STATUS_AT_RUN_END,
  deriveNodeErrorMessages,
  deriveNodeStatuses,
  runVerdict,
  runningPhaseOf,
} from "./run-status-projection"

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: "1.0",
    timestamp: "2026-06-15T00:00:00Z",
    ...partial,
  } as CallbackEvent
}

function envelope(
  partial: Partial<CallbackEvent> & { event_type: string },
  options: { runId?: string; seq?: number } = {},
): EventEnvelope {
  const runId = options.runId ?? partial.run_id ?? "run-1"
  const seq = options.seq ?? 1
  return {
    schema_version: "studio.event.v1",
    stream_id: `run:${runId}`,
    seq,
    cursor: `run:${runId}:${seq}`,
    run_id: runId,
    event_type: partial.event_type,
    timestamp: "2026-06-15T00:00:00Z",
    payload: event({ run_id: runId, ...partial }),
  }
}

function metadata(status: RunMetadata["status"]): RunMetadata {
  return { run_id: "run-1", status } as RunMetadata
}

describe("runVerdict — the one answer to 'how does this run stand'", () => {
  it("is running when neither the stream nor the record states an end", () => {
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(runVerdict(events, null)).toBe("running")
    expect(runVerdict(events, metadata("running"))).toBe("running")
  })

  it("maps the run_ended event verdicts", () => {
    expect(runVerdict([event({ event_type: "run_ended", status: "completed" })], null)).toBe("success")
    expect(runVerdict([event({ event_type: "run_ended", status: "crashed" })], null)).toBe("failed")
    expect(runVerdict([event({ event_type: "run_ended", status: "interrupted" })], null)).toBe("paused")
  })

  it("takes the run record's word when the stream never delivered run_ended", () => {
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(runVerdict(events, metadata("cancelled"))).toBe("cancelled")
    expect(runVerdict(events, metadata("failed"))).toBe("failed")
    expect(runVerdict(events, metadata("success"))).toBe("success")
    expect(runVerdict(events, metadata("paused"))).toBe("paused")
  })

  it("prefers the sealed record over the streamed event where both exist", () => {
    // A stop kills the worker: the stream says interrupted, the record says
    // cancelled. The record is the canonical seal.
    const events = [event({ event_type: "run_ended", status: "interrupted" })]
    expect(runVerdict(events, metadata("cancelled"))).toBe("cancelled")
  })

  it("last run_ended wins across a resumed run", () => {
    const events = [
      event({ event_type: "run_ended", status: "interrupted" }),
      event({ event_type: "run_ended", status: "completed" }),
    ]
    expect(runVerdict(events, null)).toBe("success")
  })

  it("ignores other runs' run_ended when scoped to a run id", () => {
    const events = [
      envelope({ event_type: "run_ended", status: "completed" }, { runId: "run-2" }),
    ]
    expect(runVerdict(events, null, "run-1")).toBe("running")
  })
})

describe("deriveNodeStatuses — 铁律: a run at a terminal state leaves nothing running", () => {
  it("closes a mid-flight node from the run record alone (cancel with a dead stream)", () => {
    // The crash/cancel case the real window showed: the worker dies, run_ended
    // never streams, the backend seals the record. The node must not spin.
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(deriveNodeStatuses(events, null, metadata("cancelled"))).toEqual({ draft: "paused" })
    expect(deriveNodeStatuses(events, null, metadata("failed"))).toEqual({ draft: "error" })
  })

  it("still closes from the run_ended event as before", () => {
    const events = [
      event({ event_type: "phase_start", phase_name: "draft" }),
      event({ event_type: "run_ended", status: "crashed" }),
    ]
    expect(deriveNodeStatuses(events)).toEqual({ draft: "error" })
  })

  it("leaves settled nodes alone when closing the running ones", () => {
    const events = [
      event({ event_type: "phase_start", phase_name: "draft" }),
      event({ event_type: "phase_end", phase_name: "draft" }),
      event({ event_type: "phase_start", phase_name: "review" }),
    ]
    expect(deriveNodeStatuses(events, null, metadata("cancelled"))).toEqual({
      draft: "success",
      review: "paused",
    })
  })

  it("keeps running nodes running while the run is live", () => {
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(deriveNodeStatuses(events, null, metadata("running"))).toEqual({ draft: "running" })
  })
})

describe("NODE_STATUS_AT_RUN_END — the registered node close table", () => {
  it("covers every non-running verdict, closing to a non-running node status", () => {
    expect(NODE_STATUS_AT_RUN_END).toEqual({
      success: "success",
      failed: "error",
      cancelled: "paused",
      paused: "paused",
    })
  })
})

describe("deriveNodeErrorMessages / runningPhaseOf — migrated behaviors", () => {
  it("keeps the failure reason for a failed phase", () => {
    const events = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "protocol_violation", phase_name: "review", violations: ["bad output"] }),
    ]
    expect(deriveNodeErrorMessages(events)).toEqual({ review: "bad output" })
  })

  it("names the phase that is executing right now", () => {
    const statuses = deriveNodeStatuses([
      event({ event_type: "phase_start", phase_name: "draft" }),
    ])
    expect(runningPhaseOf(statuses)).toBe("draft")
  })
})
