import type { CallbackEvent, EventEnvelope, ResumeValidityResponse } from '@/api/types'
import type { ResumeRunOptions } from '@/api/client'

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
