import type { CallbackEvent, EventEnvelope } from '@/api/types'

export interface NodeResumeCheckpoint {
  checkpointId: string
  checkpointNs: string
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
