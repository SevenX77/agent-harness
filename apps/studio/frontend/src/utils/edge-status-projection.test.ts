import { describe, expect, it } from "vitest"
import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import { EDGE_STATUS_AT_RUN_END, deriveEdgeStatuses, inputBoundaryStatus, outputBoundaryStatus } from "./edge-status-projection"

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: "1.0",
    timestamp: "2026-08-20T00:00:00Z",
    ...partial,
  } as CallbackEvent
}

function envelope(
  partial: Partial<CallbackEvent> & { event_type: string },
  runId: string,
): EventEnvelope {
  return {
    schema_version: "studio.event.v1",
    stream_id: `run:${runId}`,
    seq: 1,
    cursor: `run:${runId}:1`,
    run_id: runId,
    event_type: partial.event_type,
    timestamp: "2026-08-20T00:00:00Z",
    payload: event({ run_id: runId, ...partial }),
  } as EventEnvelope
}

function metadata(status: RunMetadata["status"]): RunMetadata {
  return { run_id: "run-1", status } as RunMetadata
}

describe("deriveEdgeStatuses — an edge is a run segment with its own state", () => {
  it("opens on edge_start and closes on edge_end", () => {
    expect(deriveEdgeStatuses([
      event({ event_type: "edge_start", from_phases: ["draft"], to_phase: "review" }),
    ])).toEqual({ "draft->review": "running" })

    expect(deriveEdgeStatuses([
      event({ event_type: "edge_start", from_phases: ["draft"], to_phase: "review" }),
      event({ event_type: "edge_end", from_phases: ["draft"], to_phase: "review" }),
    ])).toEqual({ "draft->review": "done" })
  })

  it("lights every edge a fan-in transition joins", () => {
    // One transition, several upstreams: all of those edges took part in it.
    expect(deriveEdgeStatuses([
      event({ event_type: "edge_start", from_phases: ["draft", "research"], to_phase: "review" }),
    ])).toEqual({ "draft->review": "running", "research->review": "running" })
  })

  it("keys an empty upstream list to the Input boundary edge", () => {
    // from_phases is set from the compiled upstream phases, and a graph's first
    // phase has no predecessor — empty means the run input is what precedes it.
    expect(deriveEdgeStatuses([
      event({ event_type: "edge_end", from_phases: [], to_phase: "draft" }),
    ])).toEqual({ "__global_input__->draft": "done" })
  })

  it("keys either boundary alias to the canvas id the edge actually has", () => {
    expect(deriveEdgeStatuses([
      event({ event_type: "edge_end", from_phases: ["input"], to_phase: "draft" }),
      event({ event_type: "edge_end", from_phases: ["review"], to_phase: "output" }),
    ])).toEqual({
      "__global_input__->draft": "done",
      "review->__global_output__": "done",
    })
  })

  it("re-opens on a second attempt across the same edge", () => {
    // A loop crosses the same edge again; the reader watches THIS pass.
    expect(deriveEdgeStatuses([
      event({ event_type: "edge_start", from_phases: ["draft"], to_phase: "review" }),
      event({ event_type: "edge_end", from_phases: ["draft"], to_phase: "review" }),
      event({ event_type: "edge_start", from_phases: ["draft"], to_phase: "review" }),
    ])).toEqual({ "draft->review": "running" })
  })

  it("closes an open segment at the run's verdict — from either truth channel", () => {
    const openSegment = [event({ event_type: "edge_start", from_phases: ["draft"], to_phase: "review" })]
    expect(deriveEdgeStatuses([
      ...openSegment,
      event({ event_type: "run_ended", status: "crashed" }),
    ])).toEqual({ "draft->review": "failed" })
    // Stream died with the worker: only the sealed record says it is over.
    expect(deriveEdgeStatuses(openSegment, null, metadata("cancelled")))
      .toEqual({ "draft->review": "paused" })
    expect(deriveEdgeStatuses(openSegment, null, metadata("running")))
      .toEqual({ "draft->review": "running" })
  })

  it("leaves a closed segment alone when the run ends badly", () => {
    expect(deriveEdgeStatuses([
      event({ event_type: "edge_start", from_phases: ["draft"], to_phase: "review" }),
      event({ event_type: "edge_end", from_phases: ["draft"], to_phase: "review" }),
      event({ event_type: "edge_start", from_phases: ["review"], to_phase: "ship" }),
      event({ event_type: "run_ended", status: "crashed" }),
    ])).toEqual({ "draft->review": "done", "review->ship": "failed" })
  })

  it("ignores segments belonging to another run", () => {
    expect(deriveEdgeStatuses(
      [envelope({ event_type: "edge_start", from_phases: ["draft"], to_phase: "review" }, "run-2")],
      "run-1",
    )).toEqual({})
  })

  it("ignores events that are not the segment brackets", () => {
    expect(deriveEdgeStatuses([
      event({ event_type: "input_dispatch", from_phases: ["draft"], to_phase: "review" }),
      event({ event_type: "phase_start", phase_name: "review" }),
    ])).toEqual({})
  })

  it("has no status for an edge the run never crossed", () => {
    const statuses = deriveEdgeStatuses([
      event({ event_type: "edge_end", from_phases: ["draft"], to_phase: "review" }),
    ])
    expect(statuses["review->ship"]).toBeUndefined()
  })
})

describe("EDGE_STATUS_AT_RUN_END — the registered close table", () => {
  it("mirrors the node table, with done where a node says success", () => {
    expect(EDGE_STATUS_AT_RUN_END).toEqual({
      success: "done",
      failed: "failed",
      cancelled: "paused",
      abandoned: "paused",
      paused: "paused",
    })
  })
})

describe("an edge segment inside a subgraph belongs to that subgraph", () => {
  it("scopes the edge id by the container chain the engine stamped", () => {
    expect(deriveEdgeStatuses([
      event({ event_type: "edge_end", from_phases: ["setup"], to_phase: "segment", subgraph_path: "segmentation" }),
    ])).toEqual({ "segmentation.setup->segmentation.segment": "done" })
  })

  it("does NOT attribute a child graph's own first transition to the ROOT input", () => {
    // `from_phases: []` means "nothing in THIS graph precedes it". Inside a
    // subgraph that is the child's own entry, not the run's input — reading it
    // as the root Input boundary made every child graph's first phase light up
    // the parent's Input endpoint.
    expect(deriveEdgeStatuses([
      event({ event_type: "edge_start", from_phases: [], to_phase: "setup", subgraph_path: "segmentation" }),
    ])).toEqual({ "segmentation.__global_input__->segmentation.setup": "running" })
  })

  it("keeps two same-named edges in different subgraphs apart", () => {
    const statuses = deriveEdgeStatuses([
      event({ event_type: "edge_end", from_phases: ["a"], to_phase: "review", subgraph_path: "timeline" }),
      event({ event_type: "edge_start", from_phases: ["a"], to_phase: "review", subgraph_path: "characters" }),
    ])

    expect(statuses["timeline.a->timeline.review"]).toBe("done")
    expect(statuses["characters.a->characters.review"]).toBe("running")
  })
})

describe("the IO endpoints read the run at their own end of the graph", () => {
  it("takes Input from the ROOT input edges only", () => {
    expect(inputBoundaryStatus({ "__global_input__->draft": "done" })).toBe("success")
    // A child graph's entry edge is not this graph's input.
    expect(inputBoundaryStatus({ "segmentation.__global_input__->segmentation.setup": "failed" })).toBe("idle")
  })

  it("takes Output from the phases that produce it — no event ever reaches the endpoint", () => {
    // Verified on run predict-2026-08-20T04-09-33: every edge_end names a real
    // downstream phase, and the last one is `story_analysis -> global_synthesis`.
    // Nothing is emitted toward the output boundary, so folding its edges left
    // Output permanently Idle on a successful run.
    expect(outputBoundaryStatus({ global_synthesis: "success" }, ["global_synthesis"], "success")).toBe("success")
    expect(outputBoundaryStatus({ global_synthesis: "running" }, ["global_synthesis"], "running")).toBe("running")
    expect(outputBoundaryStatus({}, ["global_synthesis"], "running")).toBe("idle")
  })

  it("closes an Output the run never reached, by the same table as every node", () => {
    expect(outputBoundaryStatus({}, ["global_synthesis"], "failed")).toBe("error")
    expect(outputBoundaryStatus({}, ["global_synthesis"], "cancelled")).toBe("paused")
  })

  it("takes the worst of several producing phases", () => {
    expect(outputBoundaryStatus({ a: "success", b: "error" }, ["a", "b"], "failed")).toBe("error")
  })

  it("is idle when the graph declares no output phase at all", () => {
    expect(outputBoundaryStatus({ a: "success" }, [], "success")).toBe("idle")
  })
})
