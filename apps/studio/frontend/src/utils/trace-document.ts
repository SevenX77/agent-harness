import type { CallbackEvent, JsonObject, JsonValue } from '../api/types'
import { eventMessage, eventPhase, eventTimeLabel, jsonText, tokenText } from './trace'

// ── Read-only full-trace document (n4-trace #18, spec 04 D4/D7) ─────────────
// "看完整 trace" is the whole run, grouped by node, read as a document rather
// than searched as a stream. This module is the projection; the panel renders
// it. Nothing here is abbreviated: a detail block carries its event's complete
// value and the panel decides how much of it to show at rest (decision
// 2026-08-08 D4 — the old character budget cut long blackboards down with no
// way to get the rest back, which made "full trace" untrue).

/** One structured value attached to a state (blackboard, inputs, variables, prompt). */
export interface TraceDocumentDetail {
  label: string
  /** The complete serialized value. Never elided. */
  content: string
}

/** One state (event) inside a node's block. */
export interface TraceDocumentEntry {
  /** 1-based position within its node block. */
  position: number
  eventType: string
  headline: string
  timeLabel: string | null
  tokens: string | null
  details: TraceDocumentDetail[]
  errorMessage: string | null
}

/** One node's block: every state that ran under that node, in order. */
export interface TraceDocumentSection {
  nodeId: string
  entries: TraceDocumentEntry[]
}

export interface TraceDocument {
  runId: string | null
  eventCount: number
  sections: TraceDocumentSection[]
}

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function detail(label: string, value: JsonValue | undefined): TraceDocumentDetail[] {
  if (value === undefined || value === null) {
    return []
  }
  const serialized = jsonText(value)
  if (serialized === '' || serialized === '{}' || serialized === '[]') {
    return []
  }
  return [{ label, content: serialized }]
}

/**
 * Every structured value a state carries: its blackboard snapshot, the inputs it
 * received, the prompt variables and the resolved prompt.
 */
function entryDetails(event: CallbackEvent): TraceDocumentDetail[] {
  const blackboard = isJsonObject(event.blackboard) ? event.blackboard : event.outputs
  const details = [
    ...detail('Blackboard', blackboard),
    ...detail('Inputs', event.inputs),
    ...detail('Variables', event.variables),
  ]
  if (Array.isArray(event.resolved_prompt) && event.resolved_prompt.length > 0) {
    details.push(...detail('Resolved prompt', event.resolved_prompt))
  }
  return details
}

/**
 * Project an ordered event list into the full-trace document: node blocks, each
 * holding its states in order, each state holding its complete detail.
 */
export function buildTraceDocument(events: CallbackEvent[]): TraceDocument {
  const runIdEvent = events.find((event) => typeof event.run_id === 'string')
  const document: TraceDocument = {
    runId: typeof runIdEvent?.run_id === 'string' ? runIdEvent.run_id : null,
    eventCount: events.length,
    sections: [],
  }

  let current: TraceDocumentSection | null = null
  for (const event of events) {
    const nodeId = eventPhase(event)
    if (!current || current.nodeId !== nodeId) {
      current = { nodeId, entries: [] }
      document.sections.push(current)
    }
    current.entries.push({
      position: current.entries.length + 1,
      eventType: event.event_type,
      headline: eventMessage(event),
      timeLabel: eventTimeLabel(event),
      tokens: tokenText(event) || null,
      details: entryDetails(event),
      errorMessage: typeof event.error_message === 'string' && event.error_message.trim() !== ''
        ? event.error_message
        : null,
    })
  }

  return document
}
