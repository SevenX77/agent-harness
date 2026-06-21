import type { CallbackEvent, JsonObject, JsonValue } from '../api/types'
import { eventMessage, eventPhase, jsonText, tokenText } from './trace'

// ── Read-only full-trace document (n4-trace #18, spec 04 D4/D7) ─────────────
// "看完整 trace" is the whole run rendered as a lightly-formatted, human-readable
// document (NOT raw jsonl) shown in a read-only editor. The document groups
// events by node/phase so focusing a node (atom #17) can jump the editor to that
// node's line range, and surfaces each state's full blackboard detail inline
// (D7: "点状态→只读看完整黑板详情，深层可折叠") instead of a one-off JSON dump.

export interface TraceNodeRange {
  /** Node / phase id this block belongs to (matches eventPhase). */
  nodeId: string
  /** Human label for the block heading. */
  label: string
  /** 1-based first line of this node's block in the document. */
  startLine: number
  /** 1-based last line of this node's block in the document. */
  endLine: number
}

export interface TraceDocument {
  /** The full lightly-formatted document text. */
  text: string
  /** Per-node line ranges so a focused node can reveal its block. */
  nodeRanges: TraceNodeRange[]
}

/** Cap on how much blackboard / payload detail is inlined per event (D7 depth guard). */
const DETAIL_CHAR_BUDGET = 1200

function isJsonObject(value: JsonValue | undefined): value is JsonObject {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function indentBlock(text: string, indent: string): string[] {
  return text.split('\n').map((line) => `${indent}${line}`)
}

/** Render one structured detail (blackboard / variables / payload) under a state. */
function detailLines(label: string, value: JsonValue | undefined): string[] {
  if (value === undefined || value === null) {
    return []
  }
  const serialized = jsonText(value)
  if (serialized === '' || serialized === '{}' || serialized === '[]') {
    return []
  }
  const clipped = serialized.length > DETAIL_CHAR_BUDGET
    ? `${serialized.slice(0, DETAIL_CHAR_BUDGET)}\n… (${serialized.length} chars total, truncated)`
    : serialized
  return [`    ${label}:`, ...indentBlock(clipped, '      ')]
}

/**
 * Collect the human-readable detail lines for a single state (event): its
 * blackboard snapshot, prompt variables, resolved prompt and error, each as a
 * collapsible-style indented block. Falls back to nothing when the event has no
 * structured detail worth showing (keeps short events to a single line).
 */
function stateDetailLines(event: CallbackEvent): string[] {
  const lines: string[] = []
  const blackboard = isJsonObject(event.blackboard) ? event.blackboard : event.outputs
  lines.push(...detailLines('Blackboard', blackboard))
  lines.push(...detailLines('Inputs', event.inputs))
  lines.push(...detailLines('Variables', event.variables))
  if (Array.isArray(event.resolved_prompt) && event.resolved_prompt.length > 0) {
    lines.push(...detailLines('Resolved prompt', event.resolved_prompt))
  }
  if (typeof event.error_message === 'string' && event.error_message.trim() !== '') {
    lines.push(`    Error: ${event.error_message}`)
  }
  return lines
}

function stateHeadline(event: CallbackEvent, position: number): string {
  const tokens = tokenText(event)
  const tokenSuffix = tokens ? `  ·  tokens ${tokens}` : ''
  return `  ${position}. [${event.event_type}] ${eventMessage(event)}${tokenSuffix}`
}

/**
 * Build the read-only full-trace document for a run.
 *
 * Pure projection of the ordered event list into a lightly-formatted document
 * grouped by node/phase, tracking each node's line range so a focused node can
 * be revealed in the editor. No raw jsonl — every state reads as a sentence with
 * its blackboard detail nested beneath it.
 */
export function buildTraceDocument(events: CallbackEvent[]): TraceDocument {
  if (events.length === 0) {
    return { text: 'No trace events captured yet.', nodeRanges: [] }
  }

  const lines: string[] = []
  const nodeRanges: TraceNodeRange[] = []
  const runId = events.find((event) => typeof event.run_id === 'string')?.run_id
  lines.push(`# Run trace${typeof runId === 'string' ? ` · ${runId}` : ''}`)
  lines.push(`${events.length} events`)
  lines.push('')

  let currentNodeId: string | null = null
  let currentRange: TraceNodeRange | null = null
  let positionInNode = 0

  for (const event of events) {
    const nodeId = eventPhase(event)
    if (nodeId !== currentNodeId) {
      if (currentRange) {
        currentRange.endLine = lines.length
        nodeRanges.push(currentRange)
      }
      currentNodeId = nodeId
      positionInNode = 0
      lines.push(`## ${nodeId}`)
      currentRange = { nodeId, label: nodeId, startLine: lines.length, endLine: lines.length }
    }
    positionInNode += 1
    lines.push(stateHeadline(event, positionInNode))
    lines.push(...stateDetailLines(event))
  }

  if (currentRange) {
    currentRange.endLine = lines.length
    nodeRanges.push(currentRange)
  }

  return { text: lines.join('\n'), nodeRanges }
}
