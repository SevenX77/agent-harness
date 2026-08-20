import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import type { NodeRuntime, SkillNodeStatus } from "@/components/GraphCanvas"
import { ENGINE_EVENT_TYPES } from "./engine-events"

// ————————————————————————————————————————————————————————————————————————————
// run-status-projection (decision 2026-08-13 D7): the ONE module that turns
// (event stream, run record) into every derived "is anything still running"
// answer — canvas node lights, trace step spinners, the top-strip badge.
//
// 铁律: a run at a terminal state leaves NOTHING running. A missing end frame
// is not a reason to spin forever — the run's own verdict is the final input,
// and it can arrive on either channel: the streamed `run_ended` event, or the
// sealed run record when the stream died with the worker (crash, cancel).
// ————————————————————————————————————————————————————————————————————————————

/**
 * How the run stands, folded from both truth channels.
 *
 * `paused` is not terminal (a resume continues the run) but it still means
 * nothing is executing; `cancelled` is the user ending it, which is not a
 * failure (RunStatus's own definition in api/types.ts).
 */
export type RunVerdict = "running" | "paused" | "success" | "failed" | "cancelled"

/** What the streamed run_ended statuses mean in verdict terms. */
const RUN_ENDED_EVENT_VERDICT: Readonly<Record<string, RunVerdict>> = {
  completed: "success",
  crashed: "failed",
  interrupted: "paused",
}

/**
 * The registered close table for canvas nodes (D7 对照表): what a node still
 * marked running becomes when the run's verdict says nothing is executing.
 * `cancelled` closes to paused, not error — the node did not fail, the user
 * ended the run around it.
 */
export const NODE_STATUS_AT_RUN_END: Readonly<
  Record<Exclude<RunVerdict, "running">, SkillNodeStatus>
> = {
  success: "success",
  failed: "error",
  cancelled: "paused",
  paused: "paused",
}

type TraceEventInput = CallbackEvent | EventEnvelope

function callbackPayload(event: TraceEventInput): CallbackEvent {
  const maybeEnvelope = event as EventEnvelope
  if (maybeEnvelope.schema_version === "studio.event.v1" && maybeEnvelope.payload) {
    return maybeEnvelope.payload as CallbackEvent
  }
  return event as CallbackEvent
}

function eventRunId(traceEvent: TraceEventInput, payload: CallbackEvent): string | null {
  const maybeEnvelope = traceEvent as EventEnvelope
  if (maybeEnvelope.schema_version === "studio.event.v1" && typeof maybeEnvelope.run_id === "string") {
    return maybeEnvelope.run_id
  }
  return typeof payload.run_id === "string" ? payload.run_id : null
}

/**
 * The one answer to "how does this run stand".
 *
 * The sealed run record wins over the streamed event where both exist: the
 * stream reports how the worker stopped (`interrupted`), the record states
 * what that stop WAS (`cancelled` vs `paused`) — the record is the canonical
 * seal the rest of Studio quotes. With no record verdict, the last streamed
 * `run_ended` decides (a resumed run ends more than once; only the final end
 * describes the state the reader is looking at). With neither, it is running.
 */
export function runVerdict(
  events: readonly TraceEventInput[] | null | undefined,
  metadata?: RunMetadata | null,
  runId?: string | null,
): RunVerdict {
  const recorded = metadata?.status
  if (recorded && recorded !== "running") {
    return recorded
  }
  let fromEvents: RunVerdict | null = null
  for (const traceEvent of events ?? []) {
    const payload = callbackPayload(traceEvent)
    if (payload.event_type !== "run_ended") continue
    const eventRun = eventRunId(traceEvent, payload)
    if (runId && eventRun && eventRun !== runId) continue
    fromEvents = RUN_ENDED_EVENT_VERDICT[payload.status ?? "completed"] ?? "success"
  }
  return fromEvents ?? "running"
}

const PAUSED_EVENT_TYPES: ReadonlySet<string> = new Set([
  "hitl",
  "human_input_required",
  "interrupted",
  "pause",
  "paused",
])

/**
 * The two engine events that mean THIS phase failed.
 *
 * `protocol_violation` is a middleware finding the WorkflowState in breach of a
 * framework contract, emitted as it breaks the agent loop. A
 * `finish_task_verdict` carrying `verdict: "rejected"` is a submission failing
 * its checks and the model being sent back to redo it — the live successor of
 * the deleted `validation_fail`. The verdict, not the type, is the failure: the
 * same event also reports accepted and duplicate submissions.
 *
 * `tool_error_handled` is deliberately absent. The engine caught the tool
 * exception, handed it to the model as feedback and carried on, so the phase
 * has not failed — only its name suggests otherwise.
 */
function isKnownFailureEvent(event: CallbackEvent, type: string): boolean {
  if (type === "protocol_violation") return true
  return type === "finish_task_verdict" && event.verdict === "rejected"
}

/**
 * Decide whether a single trace event should mark its phase as failed (red).
 *
 * Three clauses, and the order between them is the point:
 *
 * 1. `status` is the event stating its own outcome, so it is believed for any
 *    event type — it is a report, not a guess about one.
 * 2. For a type this build knows the engine emits, the explicit table above is
 *    the WHOLE answer. What a known event means is never overruled by what its
 *    name looks like.
 * 3. Only a type this build has never heard of falls through to the name-shaped
 *    guess, so a failure event added to the engine after this build still turns
 *    its node red instead of passing unnoticed.
 */
function isFailureEvent(event: CallbackEvent): boolean {
  const type = event.event_type || ""
  const status = event.status
  if (status === "failed" || status === "error") return true
  if (ENGINE_EVENT_TYPES.has(type)) return isKnownFailureEvent(event, type)
  return type.includes("error") || type.includes("fail")
}

function isPausedEvent(type: string, status: string | null | undefined): boolean {
  if (PAUSED_EVENT_TYPES.has(type)) return true
  if (type.includes("hitl") || type.includes("interrupt")) return true
  if (status === "paused" || status === "waiting_for_human") return true
  return false
}

/**
 * Derive the per-node status map from an ordered trace event stream.
 *
 * Events are applied in arrival order, last-event-wins per phase. This lets a
 * phase that reports a failure and then progresses anyway end up green, while a
 * phase whose final state is a failure ends up red.
 *
 * The run's verdict then closes out whatever is still marked running: the run
 * owns "is anything executing", and its verdict reaches here even when the
 * stream died before a `run_ended` frame — the sealed record (`metadata`) is
 * the second channel (铁律 above).
 */
export function deriveNodeStatuses(
  events: readonly TraceEventInput[] | null | undefined,
  runId?: string | null,
  metadata?: RunMetadata | null,
): Record<string, SkillNodeStatus> {
  const statuses: Record<string, SkillNodeStatus> = {}
  if (!events) return statuses
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    const eventRun = eventRunId(traceEvent, event)
    if (runId && eventRun && eventRun !== runId) continue
    const type = event.event_type || ""
    if (type === "run_ended") continue
    const phaseName = event.phase_name || event.current_phase
    if (!phaseName) continue
    if (isFailureEvent(event)) {
      statuses[phaseName] = "error"
    } else if (isPausedEvent(type, event.status)) {
      statuses[phaseName] = "paused"
    } else if (type === "phase_start") {
      statuses[phaseName] = "running"
    } else if (type === "phase_end") {
      statuses[phaseName] = "success"
    }
  }
  const verdict = runVerdict(events, metadata, runId)
  if (verdict !== "running") {
    for (const [phaseName, status] of Object.entries(statuses)) {
      if (status === "running") statuses[phaseName] = NODE_STATUS_AT_RUN_END[verdict]
    }
  }
  return statuses
}

function eventTimeMs(event: CallbackEvent): number | null {
  const raw = event.timestamp
  if (typeof raw !== "string") return null
  const parsed = Date.parse(raw)
  return Number.isNaN(parsed) ? null : parsed
}

/**
 * Derive the per-node run-segment clock from an ordered trace event stream.
 *
 * A phase re-entered inside one run (a loop iteration, a retry) restarts its
 * clock: the reader is watching THIS attempt, not the sum of every attempt, so
 * `phase_start` always opens a fresh segment and the last attempt is the one
 * that survives. `phase_end` closes the segment it belongs to; anything still
 * open when the run itself ends is closed at the run's own end frame, which is
 * what stops a card ticking forever after the stream died mid-phase.
 */
export function deriveNodeRuntimes(
  events: readonly TraceEventInput[] | null | undefined,
  runId?: string | null,
): Record<string, NodeRuntime> {
  const runtimes: Record<string, NodeRuntime> = {}
  if (!events) return runtimes
  let runEndedAtMs: number | null = null
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    const eventRun = eventRunId(traceEvent, event)
    if (runId && eventRun && eventRun !== runId) continue
    const at = eventTimeMs(event)
    if (at === null) continue
    const type = event.event_type || ""
    if (type === "run_ended") {
      runEndedAtMs = at
      continue
    }
    const phaseName = event.phase_name || event.current_phase
    if (!phaseName) continue
    if (type === "phase_start") {
      runtimes[phaseName] = { startedAtMs: at, endedAtMs: null }
    } else if (type === "phase_end") {
      const open = runtimes[phaseName]
      if (open) runtimes[phaseName] = { startedAtMs: open.startedAtMs, endedAtMs: at }
    }
  }
  if (runEndedAtMs !== null) {
    for (const [phaseName, runtime] of Object.entries(runtimes)) {
      if (runtime.endedAtMs === null) {
        runtimes[phaseName] = { startedAtMs: runtime.startedAtMs, endedAtMs: runEndedAtMs }
      }
    }
  }
  return runtimes
}

function reasonList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === "string" && item.trim() !== "")
}

/**
 * Extract the human-readable failure reason from a failure event.
 *
 * The two live failure events name their reasons in different fields — a
 * rejected `finish_task_verdict` lists why the submission was refused in
 * `errors`, a `protocol_violation` lists the contracts it broke in
 * `violations` — and both also carry a whole-sentence `message` that stands in
 * when the list is empty.
 *
 * The field order is the backend's, deliberately: the run report's per-phase
 * error ledger reads the same waterfall in
 * `apps/studio/backend/app/services/run_report.py` (`_error_line`). One failure
 * described by two surfaces must not have them quoting different halves of it.
 * Returns null when no usable text is present.
 */
function failureMessageFromEvent(event: CallbackEvent): string | null {
  for (const list of [event.errors, event.violations]) {
    const reasons = reasonList(list)
    if (reasons.length > 0) return reasons.join("; ")
  }
  const message = event.message
  return typeof message === "string" && message.trim() !== "" ? message.trim() : null
}

/**
 * Derive the per-node failure-message map from an ordered trace event stream,
 * in lockstep with `deriveNodeStatuses`: same last-event-wins + run filter, so a
 * phase that fails then recovers (a failure event followed by phase_end) clears
 * its message, and a phase whose final state is a failure keeps the reason. This is
 * the PRODUCER for SkillNode's inline error text (data.errorMessage); without it
 * the failed-node red-light message has no source.
 */
export function deriveNodeErrorMessages(
  events: readonly TraceEventInput[] | null | undefined,
  runId?: string | null,
): Record<string, string> {
  const messages: Record<string, string> = {}
  if (!events) return messages
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    const eventRun = eventRunId(traceEvent, event)
    if (runId && eventRun && eventRun !== runId) continue
    const phaseName = event.phase_name || event.current_phase
    if (!phaseName) continue
    const type = event.event_type || ""
    if (isFailureEvent(event)) {
      const message = failureMessageFromEvent(event)
      if (message) {
        messages[phaseName] = message
      } else {
        delete messages[phaseName]
      }
    } else if (type === "phase_start" || type === "phase_end" || isPausedEvent(type, event.status)) {
      // Phase progressed past / recovered from an earlier failure -> drop stale text.
      delete messages[phaseName]
    }
  }
  return messages
}

/**
 * The phase executing right now, or null when nothing is.
 *
 * One rule with two consumers — the trace panel highlights this phase, and the
 * canvas animates the edge feeding it. Deriving it separately in each would let
 * the two disagree about what "running" means.
 */
export function runningPhaseOf(
  statuses: Record<string, SkillNodeStatus>,
): string | null {
  const running = Object.entries(statuses).find(([, status]) => status === "running")
  return running?.[0] ?? null
}
