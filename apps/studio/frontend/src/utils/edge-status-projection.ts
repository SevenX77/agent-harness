import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import type { SkillNodeStatus } from "@/components/nodes"
import { INPUT_ID, OUTPUT_ID } from "@/components/nodes"
import { isInputBoundaryId, isOutputBoundaryId, upstreamPhasesOf } from "./edge-identity"
import { childPhasePath } from "./phase-path"
import { NODE_STATUS_AT_RUN_END, runVerdict, type RunVerdict } from "./run-status-projection"

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
 * The canvas edge ids one transition belongs to, in the SCOPE the engine ran it.
 *
 * A fan-in transition joins several upstream phases, and all of those edges took
 * part in it, so it yields one id per upstream. Both endpoints are named by the
 * canvas ids `buildEdges` mints, so a lookup by edge id is a lookup, not a
 * translation.
 *
 * Every id is prefixed by `subgraph_path`, the same way a phase's identity is
 * (canvas F7): `from_phases: []` means "nothing in THIS graph precedes it", and
 * inside a subgraph that is the CHILD's own entry, not the run's input. Reading
 * it as the root Input made every child graph's first phase mint a phantom
 * `__global_input__->setup` and light up the parent's Input endpoint — a
 * transition three levels down reported as the run receiving its input.
 */
function edgeIdsOfTransition(event: CallbackEvent): string[] {
  const to = typeof event.to_phase === "string" && event.to_phase !== "" ? event.to_phase : null
  if (to === null) return []
  const scope = typeof event.subgraph_path === "string" ? event.subgraph_path : ""
  const inScope = (id: string): string => (scope === "" ? id : childPhasePath(scope, id))
  const target = inScope(isOutputBoundaryId(to) ? OUTPUT_ID : to)
  const upstream = upstreamPhasesOf(event)
  if (upstream.length === 0) return [`${inScope(INPUT_ID)}->${target}`]
  return upstream.map((phase) => `${inScope(isInputBoundaryId(phase) ? INPUT_ID : phase)}->${target}`)
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
  gateVerdict?: RunVerdict | null,
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
  const verdict = runVerdict(events, metadata, runId, gateVerdict)
  if (verdict !== "running") {
    for (const [edgeId, status] of Object.entries(statuses)) {
      if (status === "running") statuses[edgeId] = EDGE_STATUS_AT_RUN_END[verdict]
    }
  }
  return statuses
}

/**
 * How the INPUT boundary stands in the run.
 *
 * Input and Output are not phases — nothing executes in them, so they have no
 * phase segment and never appeared in the node status map at all, which is why
 * they sat blank through every run while every other node lit up (PM: "INPUT/
 * OUTPUT 节点及其连线的显示与状态管理必须与普通 node/edge 统一").
 *
 * What Input DOES have is its own edge segments: the run's input leaves it
 * across real edges, bracketed by the same `edge_start`/`edge_end` the rest of
 * the board is drawn from, so its state IS the state of the edges leaving it.
 * Only the ones at ITS scope — a child graph's entry edge is scoped
 * (`segmentation.__global_input__->…`) and belongs to that child's own Input,
 * which is why the expanded preview passes its container path as `scope`.
 *
 * Several edges fold to the WORST of them. An endpoint fed by two branches
 * where one died did not receive what it was owed; reporting success because
 * the sibling arrived would have it speaking for a branch that is not its own.
 */
export function inputBoundaryStatus(
  statusByEdgeId: Record<string, EdgeRunStatus>,
  scope = "",
): SkillNodeStatus {
  const boundaryId = scope === "" ? INPUT_ID : childPhasePath(scope, INPUT_ID)
  let seen: EdgeRunStatus = "idle"
  for (const [edgeId, status] of Object.entries(statusByEdgeId)) {
    const [source] = edgeId.split("->")
    if (source !== boundaryId) continue
    if (EDGE_STATUS_SEVERITY[status] > EDGE_STATUS_SEVERITY[seen]) seen = status
  }
  return BOUNDARY_STATUS_FROM_EDGE[seen]
}

/**
 * How the OUTPUT boundary stands in the run — read from the phases that PRODUCE
 * the output, not from edges into the endpoint.
 *
 * Symmetry with Input would say "fold the edges at its end", and that is what
 * this did first. It left Output permanently Idle on a fully successful run,
 * because the symmetry is false: the engine emits a transition per real graph
 * hop, and the output boundary is not a hop. Verified on the whole event stream
 * of run `predict-2026-08-20T04-09-33` — every `edge_end` names a real
 * downstream phase, the last being `['story_analysis'] -> 'global_synthesis'`.
 * NOTHING is ever emitted toward the endpoint, so there are no edges to fold.
 *
 * The producing phases are the graph's own answer to "is the output ready": a
 * phase marked `output` finishing IS the run delivering that output. Folding
 * their statuses keeps the endpoint honest while it runs (one branch done, one
 * still going = still going), and the close table then does for it exactly what
 * it does for every node — a run at a terminal verdict leaves NOTHING running
 * (D7 铁律). A verdict-only rule was rejected for the same reason: it would
 * paint the endpoint "running" for the entire run, saying the output is being
 * produced from the first second.
 */
export function outputBoundaryStatus(
  statusByNodeId: Record<string, SkillNodeStatus>,
  outputPhasePaths: readonly string[],
  verdict: RunVerdict,
): SkillNodeStatus {
  if (outputPhasePaths.length === 0) return "idle"
  let seen: SkillNodeStatus = "idle"
  for (const phasePath of outputPhasePaths) {
    const status = statusByNodeId[phasePath] ?? "idle"
    if (NODE_STATUS_SEVERITY[status] > NODE_STATUS_SEVERITY[seen]) seen = status
  }
  if (verdict !== "running" && (seen === "running" || seen === "idle")) {
    return NODE_STATUS_AT_RUN_END[verdict]
  }
  return seen
}

/** Which phase state wins when the endpoint has several producers — worst first. */
const NODE_STATUS_SEVERITY: Readonly<Record<SkillNodeStatus, number>> = {
  idle: 0,
  success: 1,
  paused: 2,
  breakpoint: 3,
  running: 4,
  error: 5,
}

/** Which edge state wins when an endpoint has several — worst first. */
const EDGE_STATUS_SEVERITY: Readonly<Record<EdgeRunStatus, number>> = {
  idle: 0,
  done: 1,
  paused: 2,
  running: 3,
  failed: 4,
}

const BOUNDARY_STATUS_FROM_EDGE: Readonly<Record<EdgeRunStatus, SkillNodeStatus>> = {
  idle: "idle",
  running: "running",
  done: "success",
  failed: "error",
  paused: "paused",
}
