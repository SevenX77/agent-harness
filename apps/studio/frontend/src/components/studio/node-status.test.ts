import { describe, expect, it } from "vitest"
import type { CallbackEvent, EventEnvelope } from "@/api/types"
import { deriveNodeErrorMessages, deriveNodeStatuses } from "./node-status"

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

  it("resets node lights by run_id instead of letting stale run events overwrite the active run", () => {
    const events = [
      envelope({ event_type: "phase_start", phase_name: "review" }, { runId: "run-current", seq: 1 }),
      envelope({ event_type: "interrupted", phase_name: "review", reason: "needs_human_input" }, { runId: "run-current", seq: 2 }),
      envelope({ event_type: "phase_end", phase_name: "review" }, { runId: "run-stale", seq: 99 }),
    ]

    expect(deriveNodeStatuses(events, "run-current")).toEqual({ review: "paused" })
  })

  it("keeps the newest attempt for a phase when an older attempt arrives later", () => {
    const events = [
      envelope({ event_type: "phase_start", phase_name: "draft", attempt: 2 }, { runId: "run-1", seq: 10 }),
      envelope({ event_type: "phase_end", phase_name: "draft", attempt: 1 }, { runId: "run-1", seq: 11 }),
    ]

    expect(deriveNodeStatuses(events, "run-1")).toEqual({ draft: "running" })
  })

  it("derives independent statuses for parallel branches from the same active run", () => {
    const events = [
      envelope({ event_type: "phase_start", phase_name: "planner" }, { runId: "run-1", seq: 1 }),
      envelope({ event_type: "phase_start", phase_name: "executor" }, { runId: "run-1", seq: 2 }),
      envelope({ event_type: "phase_end", phase_name: "planner" }, { runId: "run-1", seq: 3 }),
    ]

    expect(deriveNodeStatuses(events, "run-1")).toEqual({
      planner: "success",
      executor: "running",
    })
  })
})

describe("deriveNodeErrorMessages", () => {
  it("produces a per-node message from a validation_fail errors[] list (real event, not injected)", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "validation_fail", phase_name: "review", errors: ["missing field x", "bad type y"] }),
    ]

    expect(deriveNodeErrorMessages(events)).toEqual({ review: "missing field x; bad type y" })
  })

  it("produces a message from retry_exhausted final_errors[] and from internal_error error_message", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "retry_exhausted", phase_name: "draft", final_errors: ["attempt 1 failed", "attempt 2 failed"] }),
      event({ event_type: "internal_error", phase_name: "plan", error_message: "boom" }),
    ]

    expect(deriveNodeErrorMessages(events)).toEqual({
      draft: "attempt 1 failed; attempt 2 failed",
      plan: "boom",
    })
  })

  it("clears the message when the phase recovers (validation_fail then phase_end ends green)", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "validation_fail", phase_name: "review", errors: ["transient"], attempt: 0 }),
      event({ event_type: "phase_end", phase_name: "review", attempt: 1 }),
    ]

    // Consistent with deriveNodeStatuses: a recovered phase ends green with no error text.
    expect(deriveNodeStatuses(events)).toEqual({ review: "success" })
    expect(deriveNodeErrorMessages(events)).toEqual({})
  })

  it("returns an empty map when there are no failure events", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "draft" }),
      event({ event_type: "phase_end", phase_name: "draft" }),
    ]

    expect(deriveNodeErrorMessages(events)).toEqual({})
  })

  it("honors the run filter like deriveNodeStatuses (drops events from other runs)", () => {
    const events = [
      envelope({ event_type: "validation_fail", phase_name: "review", errors: ["wrong run"] }, { runId: "run-2", seq: 1 }),
      envelope({ event_type: "validation_fail", phase_name: "review", errors: ["right run"] }, { runId: "run-1", seq: 2 }),
    ]

    expect(deriveNodeErrorMessages(events, "run-1")).toEqual({ review: "right run" })
  })
})

// D7 (decision 2026-08-09), the "still shows running" defect: node status is
// derived per phase from phase_start/phase_end, but the RUN owns the fact
// "is anything still executing". `run_ended` is run-scoped (no phase_name), so
// before this it was dropped by the phase filter and a phase whose phase_end
// never arrived stayed spinning forever, on a run that was demonstrably over.
describe("deriveNodeStatuses run_ended clamp", () => {
  it("closes a phase left running when the run ended with the run's own verdict", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "draft" }),
      event({ event_type: "phase_end", phase_name: "draft" }),
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "run_ended", status: "completed" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ draft: "success", review: "success" })
  })

  it("marks the in-flight phase red when the run crashed", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "run_ended", status: "crashed" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ review: "error" })
  })

  it("marks the in-flight phase paused when the run was interrupted", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "run_ended", status: "interrupted" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ review: "paused" })
  })

  it("does not overwrite a phase that already reported its own outcome", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "validation_fail", phase_name: "review", errors: ["bad"] }),
      event({ event_type: "run_ended", status: "completed" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ review: "error" })
  })

  it("leaves a running phase running while the run is still going", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ review: "running" })
  })

  it("ignores a run_ended belonging to a different run", () => {
    const events = [
      envelope({ event_type: "phase_start", phase_name: "review" }, { runId: "run-1", seq: 1 }),
      envelope({ event_type: "run_ended", status: "crashed" }, { runId: "run-2", seq: 2 }),
    ]

    expect(deriveNodeStatuses(events, "run-1")).toEqual({ review: "running" })
  })

  it("clamps to the LAST run_ended when a resumed run ends twice", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "run_ended", status: "interrupted" }),
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "run_ended", status: "completed" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ review: "success" })
  })
})
