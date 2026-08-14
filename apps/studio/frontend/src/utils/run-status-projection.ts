import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import type { SkillNodeStatus } from "@/components/GraphCanvas"

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

// Engine event_types that mark a phase as failed (see
// packages/graph-agent/src/graph_agent/callbacks/events.py):
//   - validation_fail   — a phase validator returned errors for this attempt
//   - retry_exhausted   — retries ran out and the phase was force-degraded
// Neither contains the substring "error", so the older `.includes("error")`
// check left their node green. They are matched explicitly here.
const FAILURE_EVENT_TYPES: ReadonlySet<string> = new Set(["validation_fail", "retry_exhausted"])
const PAUSED_EVENT_TYPES: ReadonlySet<string> = new Set([
  "hitl",
  "human_input_required",
  "interrupted",
  "pause",
  "paused",
])

/**
 * Decide whether a single trace event should mark its phase as failed (red).
 *
 * A phase fails when the event is an engine failure event (validation_fail /
 * retry_exhausted), when its event_type carries "error"/"fail" (covers
 * internal_error and any future failure types), or when its `status` field is
 * "failed"/"error".
 */
function isFailureEvent(type: string, status: string | null | undefined): boolean {
  if (FAILURE_EVENT_TYPES.has(type)) return true
  if (type.includes("error") || type.includes("fail")) return true
  if (status === "failed" || status === "error") return true
  return false
}

function isPausedEvent(type: string, status: string | null | undefined): boolean {
  if (PAUSED_EVENT_TYPES.has(type)) return true
  if (type.includes("hitl") || type.includes("interrupt")) return true
  if (status === "paused" || status === "waiting_for_human") return true
  return false
}

function numberField(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function eventAttempt(event: CallbackEvent): number | null {
  return numberField(event.attempt)
    ?? numberField(event.attempt_number)
    ?? numberField(event.retry_count)
    ?? numberField(event.metadata?.attempt)
    ?? numberField(event.metadata?.attempt_number)
}

/**
 * Derive the per-node status map from an ordered trace event stream.
 *
 * Events are applied in arrival order, last-event-wins per phase. This lets a
 * phase that fails validation but then retries and passes (validation_fail →
 * validation_pass / phase_end) end up green, while a phase whose final state is
 * a failure (validation_fail with no recovery, or retry_exhausted) ends up red.
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
  const attempts: Record<string, number> = {}
  if (!events) return statuses
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    const eventRun = eventRunId(traceEvent, event)
    if (runId && eventRun && eventRun !== runId) continue
    const type = event.event_type || ""
    if (type === "run_ended") continue
    const phaseName = event.phase_name || event.current_phase
    if (!phaseName) continue
    const attempt = eventAttempt(event)
    const latestAttempt = attempts[phaseName]
    if (attempt !== null && latestAttempt !== undefined && attempt < latestAttempt) continue
    if (attempt !== null) attempts[phaseName] = attempt
    if (isFailureEvent(type, event.status)) {
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

/**
 * Extract the human-readable failure reason from a failure event. Mirrors the
 * engine event shapes (events.py): internal_error carries `error_message`,
 * validation_fail carries `errors: list[str]`, retry_exhausted carries
 * `final_errors: list[str]`. Returns null when no usable text is present.
 */
function failureMessageFromEvent(event: CallbackEvent): string | null {
  const direct = event.error_message
  if (typeof direct === "string" && direct.trim() !== "") return direct.trim()
  for (const list of [event.final_errors, event.errors]) {
    if (Array.isArray(list)) {
      const msgs = list.filter((item): item is string => typeof item === "string" && item.trim() !== "")
      if (msgs.length > 0) return msgs.join("; ")
    }
  }
  return null
}

/**
 * Derive the per-node failure-message map from an ordered trace event stream,
 * in lockstep with `deriveNodeStatuses`: same last-event-wins + run filter, so a
 * phase that fails then recovers (validation_fail -> phase_end) clears its
 * message, and a phase whose final state is a failure keeps the reason. This is
 * the PRODUCER for SkillNode's inline error text (data.errorMessage); without it
 * the failed-node red-light message has no source.
 */
export function deriveNodeErrorMessages(
  events: readonly TraceEventInput[] | null | undefined,
  runId?: string | null,
): Record<string, string> {
  const messages: Record<string, string> = {}
  const attempts: Record<string, number> = {}
  if (!events) return messages
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    const eventRun = eventRunId(traceEvent, event)
    if (runId && eventRun && eventRun !== runId) continue
    const phaseName = event.phase_name || event.current_phase
    if (!phaseName) continue
    const attempt = eventAttempt(event)
    const latestAttempt = attempts[phaseName]
    if (attempt !== null && latestAttempt !== undefined && attempt < latestAttempt) continue
    if (attempt !== null) attempts[phaseName] = attempt
    const type = event.event_type || ""
    if (isFailureEvent(type, event.status)) {
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
