import type { CallbackEvent, EventEnvelope, RunMetadata } from "@/api/types"
import type { NodeActivity, NodeRuntime, SkillNodeStatus } from "@/components/GraphCanvas"
import { isEngineEventType } from "./engine-event-types"
import { isRootPhasePath, phasePathOf } from "./phase-path"

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
export type RunVerdict =
  | "running"
  | "paused"
  | "success"
  | "failed"
  | "cancelled"
  | "abandoned"

/**
 * What the streamed run_ended statuses mean in verdict terms.
 *
 * The engine's `interrupted` is a run that stopped to ask a human — it emits
 * an `InterruptedEvent` and then this status — so it folds to `paused`, the
 * verdict for "nothing is executing and it can continue". That is a different
 * situation from the record status `abandoned`, where nobody is coming back;
 * the two are spelled differently for exactly that reason.
 */
const RUN_ENDED_EVENT_VERDICT: Readonly<Record<string, RunVerdict>> = {
  completed: "success",
  crashed: "failed",
  interrupted: "paused",
}

/**
 * Whether this event ends the RUN, rather than ending one segment of it.
 *
 * `run_ended` fires whenever the engine returns, and a run that stopped at a
 * breakpoint or a question also returns — so the event alone cannot answer
 * this, and the two readers that asked it alone (the stream's terminal guard,
 * the copilot analysis bar) read a stopped run as a finished one. It has said
 * which of the three it was since it was written; the answer is to READ the
 * status, through the same table the verdict uses so they cannot disagree.
 *
 * An ending that does not say how it ended counts as an ending: mistaking a
 * stop for an ending freezes the live view, mistaking an ending for a stop
 * leaves a socket reconnecting and replaying the log forever, and a stop has
 * spelled itself `interrupted` for as long as the field has existed.
 */
export function endsTheRun(event: TraceEventInput): boolean {
  const payload = callbackPayload(event)
  if (payload.event_type !== "run_ended") return false
  return RUN_ENDED_EVENT_VERDICT[String(payload.status ?? "completed")] !== "paused"
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
  // Nothing failed and nobody asked — whatever was running the run left.
  // The node stopped where it stopped, which is what paused looks like.
  abandoned: "paused",
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
 * Three channels, ranked by how much each one can know:
 *
 * 1. The sealed run record. It carries the full status vocabulary, so only it
 *    separates `cancelled` from `paused`; it is the canonical seal the rest of
 *    Studio quotes.
 * 2. The gate the backend published when the run went terminal — the same step
 *    that wrote the record, so it speaks with the record's authority, just in
 *    coarser words. It exists as a channel because the record can fail to
 *    arrive: the read-back is an HTTP round trip, and when it errored there
 *    used to be nothing left and every derived status stayed `running` forever
 *    (ledger N5). The caller translates the gate's outcome; see
 *    `runVerdictFromGateOutcome`.
 * 3. The last streamed `run_ended`. It only knows the worker stopped, not what
 *    the stop WAS — and a resumed run ends more than once, so the final end is
 *    the one describing what the reader is looking at.
 *
 * None of the three: running.
 */
export function runVerdict(
  events: readonly TraceEventInput[] | null | undefined,
  metadata?: RunMetadata | null,
  runId?: string | null,
  gateVerdict?: RunVerdict | null,
): RunVerdict {
  const recorded = metadata?.status
  if (recorded && recorded !== "running") {
    return recorded
  }
  if (gateVerdict && gateVerdict !== "running") {
    return gateVerdict
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
  if (isEngineEventType(type)) return isKnownFailureEvent(event, type)
  return type.includes("error") || type.includes("fail")
}

function isPausedEvent(type: string, status: string | null | undefined): boolean {
  if (PAUSED_EVENT_TYPES.has(type)) return true
  if (type.includes("hitl") || type.includes("interrupt")) return true
  if (status === "paused" || status === "waiting_for_human") return true
  return false
}

/**
 * Which kind of stop a pausing event describes.
 *
 * `breakpoint` is the reader's own stopping point, and the phase it names has
 * NOT run — `interrupt_before` halts on the way in — so the card must say
 * "stopped here", not "did this". Anything else is a run with nothing
 * executing, which is all `paused` claims.
 *
 * Read from `InterruptedEvent.reason`, never inferred: a stop with no question
 * in it is equally a human-in-the-loop stop whose question failed to parse
 * (RUN_EXECUTION-16).
 */
function stoppedNodeStatus(event: CallbackEvent): SkillNodeStatus {
  return (event as { reason?: unknown }).reason === "breakpoint" ? "breakpoint" : "paused"
}

/**
 * Derive the per-node status map from an ordered trace event stream, keyed by
 * PHASE PATH (`phase-path.ts`) — so a phase executing inside an expanded
 * subgraph gets its own light instead of the container's, and two subgraphs
 * that each own a `review` never share one.
 *
 * Events are applied in arrival order, last-event-wins per phase. This lets a
 * phase that reports a failure and then progresses anyway end up green, while a
 * phase whose final state is a failure ends up red.
 *
 * The run's verdict then closes out whatever is still marked running: the run
 * owns "is anything executing", and its verdict reaches here even when the
 * stream died before a `run_ended` frame — the sealed record (`metadata`) and
 * the terminal gate (`gateVerdict`) are the other two channels (铁律 above).
 */
export function deriveNodeStatuses(
  events: readonly TraceEventInput[] | null | undefined,
  runId?: string | null,
  metadata?: RunMetadata | null,
  gateVerdict?: RunVerdict | null,
): Record<string, SkillNodeStatus> {
  const statuses: Record<string, SkillNodeStatus> = {}
  if (!events) return statuses
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    const eventRun = eventRunId(traceEvent, event)
    if (runId && eventRun && eventRun !== runId) continue
    const type = event.event_type || ""
    if (type === "run_ended") continue
    const phasePath = phasePathOf(event)
    if (!phasePath) continue
    if (isFailureEvent(event)) {
      statuses[phasePath] = "error"
    } else if (isPausedEvent(type, event.status)) {
      statuses[phasePath] = stoppedNodeStatus(event)
    } else if (type === "phase_start") {
      statuses[phasePath] = "running"
    } else if (type === "phase_end") {
      statuses[phasePath] = "success"
    }
  }
  const verdict = runVerdict(events, metadata, runId, gateVerdict)
  if (verdict !== "running") {
    for (const [phasePath, status] of Object.entries(statuses)) {
      if (status === "running") statuses[phasePath] = NODE_STATUS_AT_RUN_END[verdict]
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
    const phasePath = phasePathOf(event)
    if (!phasePath) continue
    if (type === "phase_start") {
      runtimes[phasePath] = { startedAtMs: at, endedAtMs: null }
    } else if (type === "phase_end") {
      const open = runtimes[phasePath]
      if (open) runtimes[phasePath] = { startedAtMs: open.startedAtMs, endedAtMs: at }
    }
  }
  if (runEndedAtMs !== null) {
    for (const [phasePath, runtime] of Object.entries(runtimes)) {
      if (runtime.endedAtMs === null) {
        runtimes[phasePath] = { startedAtMs: runtime.startedAtMs, endedAtMs: runEndedAtMs }
      }
    }
  }
  return runtimes
}

/**
 * How much work each node has done in this run — the tally behind a card's
 * "Call 3" while it runs and "3 calls" once it is over.
 *
 * Calls are counted from `prompt_captured`, which marks a call BEGINNING, not
 * from `llm_call`, which marks one ending. A running card is answering "what is
 * it doing NOW", and the call it is waiting on has begun and not ended: counting
 * endings would leave the card a call behind for the whole time the model is
 * thinking, which is precisely the interval the reader is watching.
 *
 * Unlike the clock in `deriveNodeRuntimes`, this does NOT reset when a phase
 * executes again. A duration describes one segment, so it takes the last one; a
 * tally describes work done, and an iterated phase really did every item's
 * share. Reporting only the last item would understate the node by a factor of
 * the item count.
 *
 * A phase with no calls yet has no entry at all, rather than an entry of zeros:
 * "it has not called anything" is what the card shows by staying silent, and an
 * explicit `0` would invite a "0 calls" readout that reads as a finding.
 *
 * `runningTool` is the tool whose `tool_call_started` has arrived and whose
 * `tool_call` has not. The two halves are paired by `tool_call_id` rather than
 * by arrival order, because one agent turn can hold several calls open at once
 * — with concurrent calls, "the most recent event" identifies nothing.
 */
export function deriveNodeActivity(
  events: readonly TraceEventInput[] | null | undefined,
  runId?: string | null,
): Record<string, NodeActivity> {
  const activity: Record<string, NodeActivity> = {}
  const openTools: Record<string, Map<string, string>> = {}
  if (!events) return activity
  for (const traceEvent of events) {
    const event = callbackPayload(traceEvent)
    const eventRun = eventRunId(traceEvent, event)
    if (runId && eventRun && eventRun !== runId) continue
    const type = event.event_type || ""
    if (type !== "prompt_captured" && type !== "tool_call" && type !== "tool_call_started") continue
    const phasePath = phasePathOf(event)
    if (!phasePath) continue
    const tally = activity[phasePath] ?? { llmCalls: 0, toolCalls: 0, runningTool: null }
    const open = openTools[phasePath] ?? new Map<string, string>()
    openTools[phasePath] = open
    if (type === "prompt_captured") {
      activity[phasePath] = { ...tally, llmCalls: tally.llmCalls + 1 }
      continue
    }
    const callId = typeof event.tool_call_id === "string" ? event.tool_call_id : ""
    const toolName = typeof event.tool_name === "string" ? event.tool_name : ""
    if (type === "tool_call_started") {
      if (callId) open.set(callId, toolName)
      // The tally counts calls MADE, and a call is made when it starts — the
      // same reason `prompt_captured` counts LLM calls. Its completion adds
      // nothing to count, it only closes what is open.
      activity[phasePath] = {
        ...tally,
        toolCalls: tally.toolCalls + 1,
        runningTool: toolName || tally.runningTool,
      }
      continue
    }
    const wasAnnounced = callId !== "" && open.has(callId)
    if (callId) open.delete(callId)
    activity[phasePath] = {
      ...tally,
      // A completion with no announcement is a call the agent node
      // reconstructed from the message list afterwards (it answered with a
      // Command and never closed its own step), so it was never counted.
      toolCalls: wasAnnounced ? tally.toolCalls : tally.toolCalls + 1,
      runningTool: lastOf(open),
    }
  }
  return activity
}

/** The most recently opened entry still in the map, or null when none is. */
function lastOf(open: Map<string, string>): string | null {
  let last: string | null = null
  for (const toolName of open.values()) last = toolName
  return last
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
    const phasePath = phasePathOf(event)
    if (!phasePath) continue
    const type = event.event_type || ""
    if (isFailureEvent(event)) {
      const message = failureMessageFromEvent(event)
      if (message) {
        messages[phasePath] = message
      } else {
        delete messages[phasePath]
      }
    } else if (type === "phase_start" || type === "phase_end" || isPausedEvent(type, event.status)) {
      // Phase progressed past / recovered from an earlier failure -> drop stale text.
      delete messages[phasePath]
    }
  }
  return messages
}

/**
 * The ROOT-graph phase executing right now, or null when nothing is.
 *
 * One rule with two consumers — the trace panel highlights this phase, and the
 * canvas animates the edge feeding it. Deriving it separately in each would let
 * the two disagree about what "running" means.
 *
 * Root-level on purpose: a phase running inside a subgraph means its container
 * is running too, and both are true at once. Answering with the container is
 * answering the question the readers actually asked — where the run stands on
 * the board in front of them (F7 决策 "现在在跑哪个 phase 答的是最外层那个").
 */
export function runningPhaseOf(
  statuses: Record<string, SkillNodeStatus>,
): string | null {
  const running = Object.entries(statuses)
    .find(([path, status]) => status === "running" && isRootPhasePath(path))
  return running?.[0] ?? null
}
