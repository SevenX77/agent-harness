import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import { INPUT_ID, OUTPUT_ID } from "@/components/nodes"
import { isInputBoundaryId, isOutputBoundaryId, upstreamPhasesOf } from "./edge-identity"
import { runVerdict, type RunVerdict } from "./run-status-projection"

// ————————————————————————————————————————————————————————————————————————————
// edge-status-projection: an edge is a run SEGMENT, peer to a phase segment
// (engine decision 2026-08-15, edge-as-run-segment), so it has a state of its
// own — derived from its own `edge_start` / `edge_end` brackets, never inferred
// from whether the downstream node happens to be executing.
//
// The canvas used to infer it: `flowing = (target === runningPhase)`. That is a
// guess with two failures. A fan-in lit every incoming edge at once when only
// one of them was carrying, and the whole vocabulary was "moving / not moving"
// — no way to say "this edge finished" or "the run died right here".
// ————————————————————————————————————————————————————————————————————————————

/**
 * How one edge stands in the run.
 *
 * `done`, not `success`: a transition has no pass/fail of its own, it either
 * completed or it did not. Failure belongs to the run that died inside it.
 */
export type EdgeRunStatus = "idle" | "running" | "done" | "failed" | "paused"

/**
 * What an edge segment still open becomes when the run's verdict says nothing
 * is executing. Same shape and same 铁律 as the node table
 * (`NODE_STATUS_AT_RUN_END`): a run at a terminal state leaves NOTHING running,
 * and that rule cannot hold for nodes but not for edges — the reader is looking
 * at one board.
 */
export const EDGE_STATUS_AT_RUN_END: Readonly<
  Record<Exclude<RunVerdict, "running">, EdgeRunStatus>
> = {
  success: "done",
  failed: "failed",
  cancelled: "paused",
  paused: "paused",
}

type TraceEventInput = CallbackEvent | EventEnvelope

function callbackPayload(traceEvent: TraceEventInput): CallbackEvent {
  const maybeEnvelope = traceEvent as EventEnvelope
  if (maybeEnvelope.schema_version === "studio.event.v1" && maybeEnvelope.payload) {
    return maybeEnvelope.payload as CallbackEvent
  }
  return traceEvent as CallbackEvent
}

function eventRunId(traceEvent: TraceEventInput, payload: CallbackEvent): string | null {
  const maybeEnvelope = traceEvent as EventEnvelope
  if (maybeEnvelope.schema_version === "studio.event.v1" && typeof maybeEnvelope.run_id === "string") {
    return maybeEnvelope.run_id
  }
  return typeof payload.run_id === "string" ? payload.run_id : null
}

/**
 * The canvas edge ids one transition belongs to.
 *
 * A fan-in transition joins several upstream phases, and all of those edges
 * took part in it, so it yields one id per upstream. An EMPTY upstream list is
 * the root transition — the run input, not a phase, is what precedes it — and
 * both boundaries are named by the canvas ids `buildEdges` mints, so a lookup
 * by edge id is a lookup, not a translation.
 */
function edgeIdsOfTransition(event: CallbackEvent): string[] {
  const to = typeof event.to_phase === "string" && event.to_phase !== "" ? event.to_phase : null
  if (to === null) return []
  const target = isOutputBoundaryId(to) ? OUTPUT_ID : to
  const upstream = upstreamPhasesOf(event)
  if (upstream.length === 0) return [`${INPUT_ID}->${target}`]
  return upstream.map((phase) => `${isInputBoundaryId(phase) ? INPUT_ID : phase}->${target}`)
}

/**
 * Derive the per-edge status map from an ordered trace event stream, keyed by
 * the canvas edge id (`source->target`).
 *
 * Applied in arrival order, last bracket wins: a loop that crosses the same
 * edge again re-opens it, because the reader is watching this pass, not the
 * sum of every pass. Whatever is still open when the run reaches a verdict is
 * closed by the table above, on either truth channel — the streamed `run_ended`
 * or the sealed record when the stream died with the worker.
 */
export function deriveEdgeStatuses(
  events: readonly TraceEventInput[] | null | undefined,
  runId?: string | null,
  metadata?: RunMetadata | null,
): Record<string, EdgeRunStatus> {
  const statuses: Record<string, EdgeRunStatus> = {}
  if (!events) return statuses
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    const eventRun = eventRunId(traceEvent, event)
    if (runId && eventRun && eventRun !== runId) continue
    const type = event.event_type || ""
    if (type !== "edge_start" && type !== "edge_end") continue
    const opening = type === "edge_start"
    for (const edgeId of edgeIdsOfTransition(event)) {
      statuses[edgeId] = opening ? "running" : "done"
    }
  }
  const verdict = runVerdict(events, metadata, runId)
  if (verdict !== "running") {
    for (const [edgeId, status] of Object.entries(statuses)) {
      if (status === "running") statuses[edgeId] = EDGE_STATUS_AT_RUN_END[verdict]
    }
  }
  return statuses
}
