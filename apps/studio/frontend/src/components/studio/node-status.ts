import type { CallbackEvent } from "@/api/types"
import type { SkillNodeStatus } from "@/components/GraphCanvas"

// Engine event_types that mark a phase as failed (see
// packages/graph-agent/src/graph_agent/callbacks/events.py):
//   - validation_fail   — a phase validator returned errors for this attempt
//   - retry_exhausted   — retries ran out and the phase was force-degraded
// Neither contains the substring "error", so the older `.includes("error")`
// check left their node green. They are matched explicitly here.
const FAILURE_EVENT_TYPES: ReadonlySet<string> = new Set(["validation_fail", "retry_exhausted"])

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

/**
 * Derive the per-node status map from an ordered trace event stream.
 *
 * Events are applied in arrival order, last-event-wins per phase. This lets a
 * phase that fails validation but then retries and passes (validation_fail →
 * validation_pass / phase_end) end up green, while a phase whose final state is
 * a failure (validation_fail with no recovery, or retry_exhausted) ends up red.
 */
export function deriveNodeStatuses(events: readonly CallbackEvent[] | null | undefined): Record<string, SkillNodeStatus> {
  const statuses: Record<string, SkillNodeStatus> = {}
  if (!events) return statuses
  for (const event of events) {
    const phaseName = event.phase_name || event.current_phase
    if (!phaseName) continue
    const type = event.event_type || ""
    if (isFailureEvent(type, event.status)) {
      statuses[phaseName] = "error"
    } else if (type === "phase_start") {
      statuses[phaseName] = "running"
    } else if (type === "phase_end") {
      statuses[phaseName] = "success"
    }
  }
  return statuses
}
