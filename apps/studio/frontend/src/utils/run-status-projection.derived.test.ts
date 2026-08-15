import { describe, expect, it } from "vitest"
import type { CallbackEvent, EventEnvelope } from "@/api/types"
import { deriveNodeErrorMessages, deriveNodeStatuses } from "./run-status-projection"

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
  it("derives node lights from EventEnvelope payloads", () => {
    const events = [
      envelope({ event_type: "phase_start", phase_name: "draft" }),
      envelope({ event_type: "phase_end", phase_name: "draft" }),
      envelope({ event_type: "protocol_violation", phase_name: "review", violations: ["bad output"] }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ draft: "success", review: "error" })
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

  it("lets a phase that reports a failure and then finishes end up green (last-event-wins)", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({ event_type: "finish_task_verdict", phase_name: "review", verdict: "rejected", errors: ["redo this"] }),
      event({ event_type: "phase_end", phase_name: "review" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ review: "success" })
  })

  it("believes an event that reports its own outcome in a status field", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_end", phase_name: "a", status: "failed" }),
    ]

    expect(deriveNodeStatuses(events)).toEqual({ a: "error" })
  })

  it("ignores events with no phase and tolerates empty input", () => {
    expect(deriveNodeStatuses(null)).toEqual({})
    expect(deriveNodeStatuses([])).toEqual({})
    expect(
      deriveNodeStatuses([event({ event_type: "some_error", error_type: "RuntimeError" })]),
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

// Which events mean "this phase failed" is an explicit table for every event
// type this build knows the engine emits; the name-shaped guess is reserved for
// types it has never heard of. Locked here because the two layers are easy to
// collapse back into one, and collapsing them is exactly what painted a node
// red for an error the engine had already handled.
describe("deriveNodeStatuses failure table (known events vs unknown fallback)", () => {
  it("marks the phase red on a protocol_violation", () => {
    expect(
      deriveNodeStatuses([
        event({ event_type: "phase_start", phase_name: "review" }),
        event({ event_type: "protocol_violation", phase_name: "review", violations: ["missing tool result"] }),
      ]),
    ).toEqual({ review: "error" })
  })

  it("marks the phase red on a REJECTED finish_task_verdict and leaves the other verdicts alone", () => {
    expect(
      deriveNodeStatuses([
        event({ event_type: "finish_task_verdict", phase_name: "review", verdict: "rejected", errors: ["schema"] }),
      ]),
    ).toEqual({ review: "error" })

    // The same event type reports the submission that was TAKEN; only the
    // verdict tells them apart, so the type alone must not decide.
    expect(
      deriveNodeStatuses([
        event({ event_type: "phase_start", phase_name: "review" }),
        event({ event_type: "finish_task_verdict", phase_name: "review", verdict: "accepted", item_count: 3 }),
      ]),
    ).toEqual({ review: "running" })

    expect(
      deriveNodeStatuses([
        event({ event_type: "phase_start", phase_name: "review" }),
        event({ event_type: "finish_task_verdict", phase_name: "review", verdict: "duplicate" }),
      ]),
    ).toEqual({ review: "running" })
  })

  // The engine caught the tool exception, handed it to the model as feedback
  // and carried on. Only the event's NAME says "error"; the phase did not fail.
  it("does NOT mark the phase red on tool_error_handled, whose name contains 'error'", () => {
    expect(
      deriveNodeStatuses([
        event({ event_type: "phase_start", phase_name: "draft" }),
        event({
          event_type: "tool_error_handled",
          phase_name: "draft",
          tool_name: "Read",
          error: "FileNotFoundError: nope.txt",
          message: "Read failed; the model was told and continued.",
        }),
      ]),
    ).toEqual({ draft: "running" })

    expect(
      deriveNodeStatuses([
        event({ event_type: "phase_start", phase_name: "draft" }),
        event({ event_type: "tool_error_handled", phase_name: "draft", tool_name: "Read", error: "boom" }),
        event({ event_type: "phase_end", phase_name: "draft" }),
      ]),
    ).toEqual({ draft: "success" })
  })

  // A failure event added to the engine after this build must still light the
  // node red rather than pass unnoticed — that is what the fallback is for.
  it("still catches an event type this build has never heard of by its name", () => {
    expect(
      deriveNodeStatuses([
        event({ event_type: "budget_exceeded_error", phase_name: "a" }),
        event({ event_type: "guardrail_fail", phase_name: "b" }),
      ]),
    ).toEqual({ a: "error", b: "error" })
  })
})

describe("deriveNodeErrorMessages", () => {
  it("quotes the errors[] a rejected finish_task_verdict carries", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "phase_start", phase_name: "review" }),
      event({
        event_type: "finish_task_verdict",
        phase_name: "review",
        verdict: "rejected",
        errors: ["missing field x", "bad type y"],
        message: "Submission refused.",
      }),
    ]

    // The list is the specific reason; the sentence is the fallback for when
    // there is no list, so a present list must not be passed over for it.
    expect(deriveNodeErrorMessages(events)).toEqual({ review: "missing field x; bad type y" })
  })

  it("quotes the violations[] a protocol_violation carries", () => {
    const events: CallbackEvent[] = [
      event({
        event_type: "protocol_violation",
        phase_name: "draft",
        boundary: "after_model",
        violations: ["tool_calls: unanswered call c1", "state: missing result"],
        message: "Contract broken.",
      }),
    ]

    expect(deriveNodeErrorMessages(events)).toEqual({
      draft: "tool_calls: unanswered call c1; state: missing result",
    })
  })

  it("falls back to the event's own sentence when it carries an empty list", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "protocol_violation", phase_name: "draft", violations: [], message: "Contract broken." }),
      event({ event_type: "finish_task_verdict", phase_name: "plan", verdict: "rejected", message: "No parsable items." }),
    ]

    expect(deriveNodeErrorMessages(events)).toEqual({
      draft: "Contract broken.",
      plan: "No parsable items.",
    })
  })

  // The engine handled the tool error and ran on. Quoting it here would print
  // "why this node is red" for a node that is not red.
  it("writes no message for tool_error_handled", () => {
    const events: CallbackEvent[] = [
      event({
        event_type: "tool_error_handled",
        phase_name: "draft",
        tool_name: "Bash",
        error: "CalledProcessError: exit 1",
        message: "Bash failed; the model was told and continued.",
      }),
    ]

    expect(deriveNodeErrorMessages(events)).toEqual({})
  })

  it("clears the message when the phase recovers (a failure then phase_end ends green)", () => {
    const events: CallbackEvent[] = [
      event({ event_type: "protocol_violation", phase_name: "review", violations: ["transient"] }),
      event({ event_type: "phase_end", phase_name: "review" }),
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
      envelope({ event_type: "protocol_violation", phase_name: "review", violations: ["wrong run"] }, { runId: "run-2", seq: 1 }),
      envelope({ event_type: "protocol_violation", phase_name: "review", violations: ["right run"] }, { runId: "run-1", seq: 2 }),
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
      event({ event_type: "protocol_violation", phase_name: "review", violations: ["bad"] }),
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
