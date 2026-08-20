import { describe, expect, it } from "vitest"
import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import { EDGE_STATUS_AT_RUN_END, boundaryNodeStatus, deriveEdgeStatuses } from "./edge-status-projection"

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
      paused: "paused",
    })
  })
})

describe("boundaryNodeStatus — the IO endpoints join the same status system", () => {
  it("is idle before the run touches the boundary", () => {
    expect(boundaryNodeStatus({}, "input")).toBe("idle")
    expect(boundaryNodeStatus({ "draft->review": "running" }, "output")).toBe("idle")
  })

  it("runs while the boundary's own edge segment is open, and succeeds when it closes", () => {
    expect(boundaryNodeStatus({ "__global_input__->draft": "running" }, "input")).toBe("running")
    expect(boundaryNodeStatus({ "__global_input__->draft": "done" }, "input")).toBe("success")
    expect(boundaryNodeStatus({ "review->__global_output__": "running" }, "output")).toBe("running")
    expect(boundaryNodeStatus({ "review->__global_output__": "done" }, "output")).toBe("success")
  })

  it("reads only the edges that touch ITS end of the graph", () => {
    const statuses = {
      "__global_input__->draft": "done" as const,
      "review->__global_output__": "running" as const,
    }

    expect(boundaryNodeStatus(statuses, "input")).toBe("success")
    expect(boundaryNodeStatus(statuses, "output")).toBe("running")
  })

  it("takes the worst answer when a boundary has several edges", () => {
    // The run died on one of the branches feeding Output: the endpoint did not
    // receive what it was owed, and saying "success" because a sibling arrived
    // would be the endpoint reporting on someone else's branch.
    expect(boundaryNodeStatus({
      "a->__global_output__": "done",
      "b->__global_output__": "failed",
    }, "output")).toBe("error")
    expect(boundaryNodeStatus({
      "a->__global_output__": "done",
      "b->__global_output__": "running",
    }, "output")).toBe("running")
    expect(boundaryNodeStatus({
      "a->__global_output__": "done",
      "b->__global_output__": "paused",
    }, "output")).toBe("paused")
  })
})
