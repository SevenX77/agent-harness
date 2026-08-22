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

/**
 * Whether a single trace event represents a HitL pause / clarification request.
 *
 * A run stopped at a BREAKPOINT is not one: nobody asked anything, and the
 * reader only has to say "go on". Shown as a prompt it puts up "HUMAN INPUT
 * REQUIRED" and an answer box over a question that does not exist — which is
 * what the real window did before `reason` was read here.
 *
 * The reason is read, never inferred from a missing question: an ask whose
 * question failed to parse looks identical, and hiding a real one is the worse
 * of the two mistakes. So only an explicit `breakpoint` is excluded; an
 * unlabelled stop is still treated as a prompt (RUN_EXECUTION-16).
 *
 * A `paused` STATUS is not one either, whatever the event is. The status names
 * the run's state — nothing is executing and it can continue — and being asked
 * something is only one of the ways to get there. Accepting it put the prompt
 * up over the resume's own audit record (`resume_applied`, carrying the
 * resulting `status: "paused"`), which asks nothing of anybody.
 * `waiting_for_human` stays, because that one says it in words.
 */
export function isHitlEvent(
  eventType: string,
  status: string | undefined,
  reason?: string | null,
): boolean {
  if (reason === 'breakpoint') return false
  if (eventType === 'interrupted' || eventType === 'hitl' || eventType === 'human_input_required') return true
  if (eventType === 'pause' || eventType === 'paused') return true
  if (eventType.includes('hitl') || eventType.includes('interrupt')) return true
  return status === 'waiting_for_human'
}

/** Scan the stream backwards and project the most recent HitL pause prompt. */
export function latestHitlPrompt(events: readonly EventEnvelope[]): PendingHitlPrompt | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index]
    const payload = envelopePayload(event)
    const eventType = event.event_type || payload.event_type || ''
    if (!isHitlEvent(eventType, payload.status, stringField(payload.reason))) continue
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
