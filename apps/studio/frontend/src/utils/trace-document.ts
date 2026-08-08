import type { CallbackEvent, JsonValue } from '../api/types'
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

/**
 * The structured fields the engine's events actually carry, in reading order,
 * with the name a person would call them.
 *
 * Taken from the event contracts in
 * `packages/graph-agent/src/graph_agent/callbacks/events.py` — the document is
 * only as complete as this list is faithful. It once looked for `blackboard` /
 * `inputs` / `outputs`, which no engine event emits, so every real run rendered
 * as bare headlines with nothing beneath them.
 */
const DETAIL_FIELDS: ReadonlyArray<readonly [field: string, label: string]> = [
  ['initial_context', 'Initial context'],
  ['blackboard_snapshot', 'Blackboard'],
  ['changed_keys', 'Changed keys'],
  ['dispatched_keys', 'Dispatched keys'],
  ['context', 'Context'],
  ['variables', 'Variables'],
  ['resolved_prompt', 'Resolved prompt'],
  ['messages', 'Messages'],
  ['response_data', 'Response'],
  ['args', 'Args'],
  ['result', 'Result'],
  ['content', 'Working memory'],
  ['errors', 'Errors'],
  ['feedback', 'Feedback'],
  ['evidence', 'Evidence'],
  ['payload', 'Payload'],
  ['metadata', 'Metadata'],
  ['metrics', 'Metrics'],
  ['final_context', 'Final context'],
]

function detailContent(value: JsonValue | undefined): string | null {
  if (value === undefined || value === null) {
    return null
  }
  // A plain string is already the readable form; quoting it would only add noise.
  const serialized = typeof value === 'string' ? value : jsonText(value)
  const trimmed = serialized.trim()
  if (trimmed === '' || trimmed === '{}' || trimmed === '[]') {
    return null
  }
  return serialized
}

/** Every structured value this state carries, complete and in reading order. */
function entryDetails(event: CallbackEvent): TraceDocumentDetail[] {
  const details: TraceDocumentDetail[] = []
  for (const [field, label] of DETAIL_FIELDS) {
    const content = detailContent(event[field])
    if (content !== null) {
      details.push({ label, content })
    }
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
