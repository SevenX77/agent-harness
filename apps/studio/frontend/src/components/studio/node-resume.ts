import type { CallbackEvent, EventEnvelope, ResumeValidityResponse } from '@/api/types'
import type { ResumeRunOptions } from '@/api/client'
import type { SkillNodeStatus } from '@/components/nodes'

export interface NodeResumeCheckpoint {
  checkpointId: string
  checkpointNs: string
}

/**
 * Build the node-level Resume request from a checkpoint-validity response (debug F2).
 *
 * The failed-node Resume button must anchor the resume at THIS node so the engine
 * reuses upstream checkpoints instead of replaying them (workflow 05 §"节点级 Resume").
 * `resume_from_node_id` therefore always carries the node id (validity's value when
 * present, the selected node id otherwise). Kept as a pure function so the
 * "resume carries resume_from_node_id" contract is unit-testable without the panel.
 */
export function nodeResumeOptionsFromValidity(
  validity: ResumeValidityResponse,
  nodeId: string,
): ResumeRunOptions {
  return {
    checkpointId: validity.checkpoint_id ?? undefined,
    checkpointNs: validity.checkpoint_ns ?? undefined,
    resumeFromNodeId: validity.resume_from_node_id ?? nodeId,
    resumeToNodeId: validity.resume_to_node_id ?? undefined,
  }
}

/**
 * Pick the node to anchor the resume-validity slice on for the AUTO dirty-downstream
 * graying (N5 atom #3, spec F3).
 *
 * The validity endpoint needs a `resume_from_node_id` to compute the affected-downstream
 * set. Pre-F-n5 that anchor was the node the user *selected* (so graying only happened on a
 * manual selection); F-n5 derives it automatically from the run: a failed run resumes from
 * its failed node, so that node is the natural anchor. Returns the first phase in `error`
 * state (deterministic over insertion order), or null when nothing failed.
 */
export function resumeAnchorNodeId(
  statusByNodeId: Record<string, SkillNodeStatus>,
): string | null {
  for (const [nodeId, status] of Object.entries(statusByNodeId)) {
    if (status === 'error') {
      return nodeId
    }
  }
  return null
}

interface DirtyDownstreamGate {
  skillId: string | null
  runId: string | null
  anchorNodeId: string | null
}

/**
 * Gate for the auto edit-watcher that derives the dirty-downstream set (N5 atom #3).
 *
 * Fires whenever an active skill + run + a resume anchor node all exist — independent of
 * which node the user has selected (removing the old `selectedNodeStatus === 'error'`
 * single-point trigger). The effect itself re-runs on an upstream edit because the skill
 * content hash it reads changes; this pure gate only encodes the always-on precondition.
 */
export function shouldDeriveDirtyDownstream({ skillId, runId, anchorNodeId }: DirtyDownstreamGate): boolean {
  return Boolean(skillId && runId && anchorNodeId)
}

/**
 * Project a resume-validity response into the set of nodes the canvas grays (N5 atom #3).
 *
 * Reads the backend's per-node `affected_downstream` slice verbatim (B1 made it per-node so
 * unrelated side-branches are absent and stay runnable). Empty for a clean / null validity,
 * so no node is grayed when there is nothing to resume from.
 */
export function dirtyDownstreamFromValidity(
  validity: ResumeValidityResponse | null | undefined,
): Set<string> {
  return new Set(validity?.affected_downstream ?? [])
}

type TraceEventInput = CallbackEvent | EventEnvelope

function callbackPayload(event: TraceEventInput): CallbackEvent {
  const maybeEnvelope = event as EventEnvelope
  if (maybeEnvelope.schema_version === 'studio.event.v1' && maybeEnvelope.payload) {
    return maybeEnvelope.payload as CallbackEvent
  }
  return event as CallbackEvent
}

function eventRunId(traceEvent: TraceEventInput, payload: CallbackEvent): string | null {
  const maybeEnvelope = traceEvent as EventEnvelope
  if (maybeEnvelope.schema_version === 'studio.event.v1' && typeof maybeEnvelope.run_id === 'string') {
    return maybeEnvelope.run_id
  }
  return typeof payload.run_id === 'string' ? payload.run_id : null
}

function stringField(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

export function nodeResumeCheckpointFromEvents(
  events: readonly TraceEventInput[] | null | undefined,
  nodeId: string,
  runId?: string | null,
): NodeResumeCheckpoint | null {
  if (!events) return null
  let checkpoint: NodeResumeCheckpoint | null = null
  for (const traceEvent of events) {
    const payload = callbackPayload(traceEvent)
    const payloadRunId = eventRunId(traceEvent, payload)
    if (runId && payloadRunId && payloadRunId !== runId) {
      continue
    }
    const phaseName = payload.phase_name || payload.current_phase || payload.to_phase
    if (phaseName !== nodeId) {
      continue
    }
    const checkpointId = stringField(payload.checkpoint_id)
    if (!checkpointId) {
      continue
    }
    checkpoint = {
      checkpointId,
      checkpointNs: stringField(payload.checkpoint_ns) ?? '',
    }
  }
  return checkpoint
}
