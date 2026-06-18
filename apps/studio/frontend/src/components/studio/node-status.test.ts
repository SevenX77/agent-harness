import { describe, expect, it } from "vitest"
import type { CallbackEvent, EventEnvelope } from "@/api/types"
import { deriveNodeStatuses } from "./node-status"

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: "1.0",
    timestamp: "2026-06-15T00:00:00Z",
    ...partial,
  } as CallbackEvent
}

function envelope(partial: Partial<CallbackEvent> & { event_type: string }): EventEnvelope {
  return {
    schema_version: "studio.event.v1",
    stream_id: "run:run-1",
    seq: 1,
    cursor: "run:run-1:1",
    run_id: "run-1",
    event_type: partial.event_type,
    timestamp: "2026-06-15T00:00:00Z",
    payload: event(partial),
  }
}

describe("deriveNodeStatuses", () => {
  it("marks a phase red on a validation_fail event (the R26 bug)", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "validation_fail", phase_name: "review", errors: ["bad output"], retry_count: 0 }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ review: "error" })
  })

  it("derives node lights from EventEnvelope payloads", () => {
    const events = [
      envelope({ event_type: "phase_start", phase_name: "draft" }),
      envelope({ event_type: "phase_end", phase_name: "draft" }),
      envelope({ event_type: "validation_fail", phase_name: "review", errors: ["bad output"] }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ draft: "success", review: "error" })
  })

  it("marks a phase red when retries are exhausted", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "draft" }),
      event({ event_type: "retry_exhausted", phase_name: "draft", max_retries: 2, final_errors: ["still bad"] }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ draft: "error" })
  })

  it("marks a normal phase_end as success and a phase_start as running", () => {
    const finished = deriveNodeStatuses([
      event({ event_type: "phase_start", phase_name: "draft" }),
      event({ event_type: "phase_end", phase_name: "draft" }),
    ])
    expect(finished).toEqual({ draft: "success" })

    const inFlight = deriveNodeStatuses([
      event({ event_type: "phase_start", phase_name: "draft" }),
    ])
    expect(inFlight).toEqual({ draft: "running" })
  })

  it("lets a phase that fails validation then recovers end up green (last-event-wins)", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "validation_fail", phase_name: "review", errors: ["retry me"], retry_count: 0 }),
      event({ event_type: "validation_pass", phase_name: "review", retry_count: 1 }),
      event({ event_type: "phase_end", phase_name: "review" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ review: "success" })
  })

  it("keeps the existing error/failed detection (status field + 'error' event types)", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_end", phase_name: "a", status: "failed" }),
      event({ event_type: "some_error", phase_name: "b" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ a: "error", b: "error" })
  })

  it("ignores events with no phase and tolerates empty input", () => {
    expect(deriveNodeStatuses(null)).toEqual({})
    expect(deriveNodeStatuses([])).toEqual({})
    expect(
      deriveNodeStatuses([event({ event_type: "internal_error", error_type: "RuntimeError" })]),
    ).toEqual({})
  })
})
