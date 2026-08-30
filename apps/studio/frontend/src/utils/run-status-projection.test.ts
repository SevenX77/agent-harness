import { describe, expect, it } from "vitest"
import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import {
  NODE_STATUS_AT_RUN_END,
  deriveNodeErrorMessages,
  deriveNodeStatuses,
  runVerdict,
  deriveNodeRuntimes,
  deriveNodeActivity,
  runningPhaseOf,
  goldenSeedableRunId,
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

  // The gate that says a run ended is published by the same backend step that
  // seals the record, and it names the outcome. It is therefore a third truth
  // channel, ranked between the two that were already here: below the record
  // (which distinguishes cancelled from paused with the full status vocabulary)
  // and above the stream (which only knows the worker stopped). Without it the
  // 铁律 has a hole — kill a worker and the record read-back can fail, leaving
  // the stream with no run_ended and every derived status on "running" forever.
  it("closes the run from the gate's own verdict when the record never arrived", () => {
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(runVerdict(events, null, "run-1", "failed")).toBe("failed")
    expect(runVerdict(events, null, "run-1", "success")).toBe("success")
  })

  it("still prefers the sealed record over the gate", () => {
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(runVerdict(events, metadata("cancelled"), "run-1", "failed")).toBe("cancelled")
  })

  it("prefers the gate over the stream — the stream cannot tell a stop from a pause", () => {
    const events = [event({ event_type: "run_ended", status: "interrupted" })]
    expect(runVerdict(events, null, "run-1", "cancelled")).toBe("cancelled")
  })

  it("reports a run whose worker vanished as abandoned, not as still running", () => {
    // The backend reconciles the record when nobody holds the run's worker lock
    // (ledger C1). The projection has to carry that word through, or the badge
    // reads `running` from a record that already gave up saying so.
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(runVerdict(events, metadata("abandoned"))).toBe("abandoned")
  })

  it("keeps the engine's interrupted apart from an abandoned record", () => {
    // Same-looking word, opposite situations: the engine emits run_ended
    // `interrupted` when a run stops to ask a human — someone is expected back,
    // so it folds to `paused`. `abandoned` means nobody is coming back.
    expect(runVerdict([event({ event_type: "run_ended", status: "interrupted" })], null)).toBe("paused")
    expect(runVerdict([], metadata("abandoned"))).toBe("abandoned")
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

  it("closes a mid-flight node from the gate verdict alone (record read-back failed)", () => {
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(deriveNodeStatuses(events, null, null, "failed")).toEqual({ draft: "error" })
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

  it("closes a mid-flight node when the record says the worker was abandoned", () => {
    // The app was closed mid-run: no run_ended, no gate, and the record only
    // learned the truth when the next sidecar found nobody holding the lock.
    // The node stopped where it stopped — it neither failed nor succeeded.
    const events = [event({ event_type: "phase_start", phase_name: "draft" })]
    expect(deriveNodeStatuses(events, null, metadata("abandoned"))).toEqual({ draft: "paused" })
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
      abandoned: "paused",
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

describe("deriveNodeRuntimes", () => {
  it("times a finished phase from its own start and end frames", () => {
    const runtimes = deriveNodeRuntimes([
      event({
        event_type: "phase_start",
        phase_name: "draft",
        timestamp: "2026-06-15T00:00:00Z",
      }),
      event({
        event_type: "phase_end",
        phase_name: "draft",
        timestamp: "2026-06-15T00:00:12.500Z",
      }),
    ])
    expect(runtimes.draft).toEqual({ startedAtMs: Date.parse("2026-06-15T00:00:00Z"), endedAtMs: Date.parse("2026-06-15T00:00:12.500Z") })
  })

  it("leaves a still-running phase open-ended so the card can tick", () => {
    const runtimes = deriveNodeRuntimes([
      event({ event_type: "phase_start", phase_name: "draft", timestamp: "2026-06-15T00:00:00Z" }),
    ])
    expect(runtimes.draft).toEqual({ startedAtMs: Date.parse("2026-06-15T00:00:00Z"), endedAtMs: null })
  })

  it("keeps the LAST attempt's clock when a phase runs twice in one run", () => {
    const runtimes = deriveNodeRuntimes([
      event({ event_type: "phase_start", phase_name: "draft", timestamp: "2026-06-15T00:00:00Z" }),
      event({ event_type: "phase_end", phase_name: "draft", timestamp: "2026-06-15T00:00:05Z" }),
      event({ event_type: "phase_start", phase_name: "draft", timestamp: "2026-06-15T00:00:20Z" }),
      event({ event_type: "phase_end", phase_name: "draft", timestamp: "2026-06-15T00:00:26Z" }),
    ])
    expect(runtimes.draft).toEqual({ startedAtMs: Date.parse("2026-06-15T00:00:20Z"), endedAtMs: Date.parse("2026-06-15T00:00:26Z") })
  })

  it("ignores frames belonging to another run", () => {
    const runtimes = deriveNodeRuntimes(
      [
        envelope({ event_type: "phase_start", phase_name: "draft", timestamp: "2026-06-15T00:00:00Z" }, { runId: "run-2" }),
      ],
      "run-1",
    )
    expect(runtimes.draft).toBeUndefined()
  })

  it("closes an open clock at the run's own end so a dead stream stops ticking", () => {
    const runtimes = deriveNodeRuntimes(
      [
        event({ event_type: "phase_start", phase_name: "draft", timestamp: "2026-06-15T00:00:00Z" }),
        event({ event_type: "run_ended", timestamp: "2026-06-15T00:00:30Z", status: "completed" }),
      ],
    )
    expect(runtimes.draft).toEqual({ startedAtMs: Date.parse("2026-06-15T00:00:00Z"), endedAtMs: Date.parse("2026-06-15T00:00:30Z") })
  })
})

describe("run projections key by phase path, so a subgraph's insides are visible", () => {
  it("keys a phase inside a subgraph under its container chain", () => {
    const statuses = deriveNodeStatuses([
      event({ event_type: "phase_start", phase_name: "event_timeline" }),
      event({ event_type: "phase_start", phase_name: "extract", subgraph_path: "event_timeline" }),
      event({ event_type: "phase_end", phase_name: "extract", subgraph_path: "event_timeline" }),
      event({ event_type: "phase_start", phase_name: "score", subgraph_path: "event_timeline" }),
    ])

    expect(statuses).toEqual({
      event_timeline: "running",
      "event_timeline.extract": "success",
      "event_timeline.score": "running",
    })
  })

  it("keeps two same-named phases in different subgraphs apart", () => {
    const statuses = deriveNodeStatuses([
      event({ event_type: "phase_end", phase_name: "review", subgraph_path: "timeline" }),
      event({ event_type: "protocol_violation", phase_name: "review", subgraph_path: "characters" }),
    ])

    expect(statuses).toEqual({ "timeline.review": "success", "characters.review": "error" })
  })

  it("gives an inner phase its own failure reason and its own clock", () => {
    const events = [
      event({
        event_type: "phase_start",
        phase_name: "extract",
        timestamp: "2026-08-20T00:00:00Z",
      }),
      event({
        event_type: "protocol_violation",
        phase_name: "extract",
        subgraph_path: "event_timeline",
        violations: ["missing output"],
        timestamp: "2026-08-20T00:00:04Z",
      }),
    ]

    expect(deriveNodeErrorMessages(events)["event_timeline.extract"]).toBe("missing output")
    expect(deriveNodeErrorMessages(events).extract).toBeUndefined()
    expect(deriveNodeRuntimes(events).extract).toEqual({
      startedAtMs: Date.parse("2026-08-20T00:00:00Z"),
      endedAtMs: null,
    })
  })

  it("closes an inner phase still running at the run's verdict, like any other", () => {
    expect(deriveNodeStatuses([
      event({ event_type: "phase_start", phase_name: "extract", subgraph_path: "event_timeline" }),
      event({ event_type: "run_ended", status: "crashed" }),
    ])).toEqual({ "event_timeline.extract": "error" })
  })

  it("answers 'which phase is running' at ROOT level", () => {
    // A phase running inside a subgraph means its container is running too; the
    // reader wants the position on the board they are looking at.
    expect(runningPhaseOf({
      event_timeline: "running",
      "event_timeline.extract": "running",
    })).toBe("event_timeline")
    expect(runningPhaseOf({ "event_timeline.extract": "running" })).toBeNull()
  })
})

describe("deriveNodeActivity", () => {
  it("counts the calls a phase has begun, so a running card can say which one it is on", () => {
    const activity = deriveNodeActivity([
      event({ event_type: "phase_start", phase_name: "draft" }),
      event({ event_type: "prompt_captured", phase_name: "draft" }),
      event({ event_type: "llm_call", phase_name: "draft" }),
      event({ event_type: "prompt_captured", phase_name: "draft" }),
    ])
    // Three would be a lie and two-minus-one a different one: the third call
    // has not started. `prompt_captured` marks a call BEGINNING, which is the
    // question a running card answers.
    expect(activity.draft).toEqual({ llmCalls: 2, toolCalls: 0, runningTool: null })
  })

  it("counts the tools a phase reached for", () => {
    const activity = deriveNodeActivity([
      event({ event_type: "prompt_captured", phase_name: "draft" }),
      event({ event_type: "tool_call", phase_name: "draft", tool_name: "read_file" }),
      event({ event_type: "tool_call", phase_name: "draft", tool_name: "write_file" }),
    ])
    expect(activity.draft).toEqual({ llmCalls: 1, toolCalls: 2, runningTool: null })
  })

  it("adds up EVERY execution of an iterated phase, not just the last one", () => {
    // The clock deliberately keeps only the last attempt, because a duration is
    // about one segment. A tally is about work done, and an iterated phase
    // really did all of it — reporting one item's share would understate the
    // node by a factor of the item count.
    const activity = deriveNodeActivity([
      event({ event_type: "phase_start", phase_name: "work" }),
      event({ event_type: "prompt_captured", phase_name: "work" }),
      event({ event_type: "phase_end", phase_name: "work" }),
      event({ event_type: "phase_start", phase_name: "work" }),
      event({ event_type: "prompt_captured", phase_name: "work" }),
      event({ event_type: "phase_end", phase_name: "work" }),
    ])
    expect(activity.work).toEqual({ llmCalls: 2, toolCalls: 0, runningTool: null })
  })

  it("keeps each subgraph child on its own path, like every other projection", () => {
    const activity = deriveNodeActivity([
      event({ event_type: "prompt_captured", phase_name: "extract", subgraph_path: "timeline" }),
      event({ event_type: "prompt_captured", phase_name: "extract" }),
    ])
    expect(activity["timeline.extract"]).toEqual({ llmCalls: 1, toolCalls: 0, runningTool: null })
    expect(activity.extract).toEqual({ llmCalls: 1, toolCalls: 0, runningTool: null })
  })

  it("ignores frames belonging to another run", () => {
    const activity = deriveNodeActivity(
      [envelope({ event_type: "prompt_captured", phase_name: "draft" }, { runId: "run-2" })],
      "run-1",
    )
    expect(activity.draft).toBeUndefined()
  })

  it("reports nothing for a phase that has not called anything yet", () => {
    const activity = deriveNodeActivity([event({ event_type: "phase_start", phase_name: "draft" })])
    expect(activity.draft).toBeUndefined()
  })
})

describe("deriveNodeActivity names the tool that is still running", () => {
  it("reports the tool whose start arrived and whose end has not", () => {
    const activity = deriveNodeActivity([
      event({ event_type: "prompt_captured", phase_name: "draft" }),
      event({
        event_type: "tool_call_started",
        phase_name: "draft",
        tool_call_id: "t1",
        tool_name: "read_file",
      }),
    ])
    expect(activity.draft?.runningTool).toBe("read_file")
  })

  it("forgets the tool once its own completion arrives", () => {
    // Paired by tool_call_id, not by arrival order: an agent turn can have
    // several calls open at once, so "the last event" identifies nothing.
    const activity = deriveNodeActivity([
      event({ event_type: "tool_call_started", phase_name: "draft", tool_call_id: "t1", tool_name: "read_file" }),
      event({ event_type: "tool_call", phase_name: "draft", tool_call_id: "t1", tool_name: "read_file" }),
    ])
    expect(activity.draft?.runningTool).toBeNull()
    expect(activity.draft?.toolCalls).toBe(1)
  })

  it("keeps naming the one still open when a sibling finishes first", () => {
    const activity = deriveNodeActivity([
      event({ event_type: "tool_call_started", phase_name: "draft", tool_call_id: "t1", tool_name: "read_file" }),
      event({ event_type: "tool_call_started", phase_name: "draft", tool_call_id: "t2", tool_name: "grep" }),
      event({ event_type: "tool_call", phase_name: "draft", tool_call_id: "t1", tool_name: "read_file" }),
    ])
    expect(activity.draft?.runningTool).toBe("grep")
  })

  it("counts a call once even though both halves arrive", () => {
    const activity = deriveNodeActivity([
      event({ event_type: "tool_call_started", phase_name: "draft", tool_call_id: "t1", tool_name: "read_file" }),
      event({ event_type: "tool_call", phase_name: "draft", tool_call_id: "t1", tool_name: "read_file" }),
    ])
    expect(activity.draft?.toolCalls).toBe(1)
  })
})

describe("goldenSeedableRunId", () => {
  // J-X.6 (批示轮三 R3-11): the copilot analysis bar must only offer to seed
  // goldens from a REAL run. A predict reaches the live-run seat through server
  // adoption, and its trace is refused promotion by the backend
  // (PREDICT_TRACE_CANNOT_BE_GOLDEN) — offering it is a dead-end Confirm that
  // calls a stub rehearsal "Run finished".
  //
  // J-X.9 (用户裁决 2026-08-30「失败 run 不弹条」): finishing is not enough
  // either — the offer reads "fill the missing goldens from this run's output",
  // and only a SUCCESSFUL run has the complete output that sentence promises.
  // A crashed run seeded an empty {} golden; cancelled/abandoned runs stopped
  // mid-way for the same reason. The gate therefore asks HOW the run stands
  // (RunVerdict), not merely whether it stopped.
  it("offers a real run once its verdict is success", () => {
    expect(goldenSeedableRunId({ runId: "run-1", runKind: "run", verdict: "success" })).toBe("run-1")
  })

  it("never offers a predict, whatever its verdict", () => {
    expect(goldenSeedableRunId({ runId: "pred-1", runKind: "predict", verdict: "success" })).toBeNull()
    expect(goldenSeedableRunId({ runId: "pred-1", runKind: "predict", verdict: "running" })).toBeNull()
  })

  it("treats an absent kind as a run (pre-kind rows mean run)", () => {
    expect(goldenSeedableRunId({ runId: "run-2", runKind: undefined, verdict: "success" })).toBe("run-2")
  })

  it("offers nothing for a run that ended any way but success", () => {
    expect(goldenSeedableRunId({ runId: "run-3", runKind: "run", verdict: "failed" })).toBeNull()
    expect(goldenSeedableRunId({ runId: "run-3", runKind: "run", verdict: "cancelled" })).toBeNull()
    expect(goldenSeedableRunId({ runId: "run-3", runKind: "run", verdict: "abandoned" })).toBeNull()
    expect(goldenSeedableRunId({ runId: "run-3", runKind: "run", verdict: "paused" })).toBeNull()
  })

  it("offers nothing while the run is still going or absent", () => {
    expect(goldenSeedableRunId({ runId: "run-3", runKind: "run", verdict: "running" })).toBeNull()
    expect(goldenSeedableRunId({ runId: null, runKind: "run", verdict: "success" })).toBeNull()
  })
})
