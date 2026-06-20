import type { CallbackEvent, EventEnvelope } from '@/api/types'

/**
 * Shared, single-source HitL prompt extraction + resume-request building.
 *
 * Lives here (not inside TracePanel) so every HitL surface — the side-panel
 * TracePanel form and the node-anchored NodeToolbar box (F4) — derives the
 * pending prompt and the resume payload from one place. No second source of
 * truth.
 *
 * The payload shape is projected from the engine's InterruptedEvent
 * (packages/graph-agent/src/graph_agent/callbacks/events.py) which carries
 * phase_name / question / options / checkpoint_id / checkpoint_ns. It does NOT
 * carry tool_call_id or pending_tool_calls, so those degrade to null / [].
 */

export interface TraceHitlResumeRequest {
  content: string
  phaseName: string | null
  toolCallId: string | null
  checkpointId: string | null
  checkpointNs: string | null
}

export interface PendingHitlToolCall {
  toolCallId: string
  question: string
  options: string[]
}

export interface PendingHitlPrompt {
  phaseName: string | null
  question: string
  options: string[]
  toolCallId: string | null
  pendingToolCalls: PendingHitlToolCall[]
  checkpointId: string | null
  checkpointNs: string | null
}

function envelopePayload(event: EventEnvelope): CallbackEvent {
  return event.payload as CallbackEvent
}

function stringField(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function stringArrayField(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string' && item.trim() !== '')
    : []
}

function pendingToolCallsField(value: unknown): PendingHitlToolCall[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item): PendingHitlToolCall[] => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) return []
    const record = item as Record<string, unknown>
    const toolCallId = stringField(record.id) ?? stringField(record.tool_call_id)
    if (!toolCallId) return []
    return [{
      toolCallId,
      question: stringField(record.question)
        ?? stringField(record.prompt)
        ?? stringField(record.message)
        ?? toolCallId,
      options: stringArrayField(record.options),
    }]
  })
}

/** Whether a single trace event represents a HitL pause / clarification request. */
export function isHitlEvent(eventType: string, status: string | undefined): boolean {
  if (eventType === 'interrupted' || eventType === 'hitl' || eventType === 'human_input_required') return true
  if (eventType === 'pause' || eventType === 'paused') return true
  if (eventType.includes('hitl') || eventType.includes('interrupt')) return true
  return status === 'paused' || status === 'waiting_for_human'
}

/** Scan the stream backwards and project the most recent HitL pause prompt. */
export function latestHitlPrompt(events: readonly EventEnvelope[]): PendingHitlPrompt | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    const payload = envelopePayload(event)
    const eventType = event.event_type || payload.event_type || ''
    if (!isHitlEvent(eventType, payload.status)) continue
    const toolCallId = stringField(payload.tool_call_id) ?? stringField(payload.pending_tool_call_id)
    const pendingToolCalls = pendingToolCallsField(payload.pending_tool_calls)
    return {
      phaseName: payload.phase_name ?? payload.current_phase ?? null,
      question: stringField(payload.question)
        ?? stringField(payload.prompt)
        ?? stringField(payload.message)
        ?? 'Run paused for human input.',
      options: stringArrayField(payload.options),
      toolCallId,
      pendingToolCalls: pendingToolCalls.length > 0
        ? pendingToolCalls
        : toolCallId
          ? [{
              toolCallId,
              question: stringField(payload.question)
                ?? stringField(payload.prompt)
                ?? stringField(payload.message)
                ?? toolCallId,
              options: stringArrayField(payload.options),
            }]
          : [],
      checkpointId: stringField(payload.checkpoint_id),
      checkpointNs: stringField(payload.checkpoint_ns),
    }
  }
  return null
}

/** The tool call the answer is being routed to (auto when there is exactly one). */
export function effectiveToolCallId(
  prompt: PendingHitlPrompt | null,
  selectedToolCallId: string | null,
): string | null {
  if (!prompt) return null
  if (prompt.pendingToolCalls.length === 1) return prompt.pendingToolCalls[0].toolCallId
  return selectedToolCallId
}

/** When multiple pending tool calls exist, the user must pick one before submit. */
export function needsToolCallSelection(
  prompt: PendingHitlPrompt | null,
  selectedToolCallId: string | null,
): boolean {
  return Boolean(prompt && prompt.pendingToolCalls.length > 1 && !selectedToolCallId)
}

interface BuildHitlResumeRequestArgs {
  prompt: PendingHitlPrompt | null
  draft: string
  selectedToolCallId: string | null
}

/**
 * Pure builder: turn the current prompt + draft answer + selected tool call into
 * the resume request, or null when the answer cannot be submitted yet (no
 * prompt, empty draft, or an unresolved multi-tool-call choice). Keeping this
 * pure makes the submit contract unit-testable without a DOM.
 */
export function buildHitlResumeRequest({
  prompt,
  draft,
  selectedToolCallId,
}: BuildHitlResumeRequestArgs): TraceHitlResumeRequest | null {
  const content = draft.trim()
  if (!prompt || !content || needsToolCallSelection(prompt, selectedToolCallId)) return null
  return {
    content,
    phaseName: prompt.phaseName,
    toolCallId: effectiveToolCallId(prompt, selectedToolCallId) ?? prompt.toolCallId,
    checkpointId: prompt.checkpointId,
    checkpointNs: prompt.checkpointNs,
  }
}
