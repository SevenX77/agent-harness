import type { CopilotEvent, CopilotMessage } from '../../types/copilot'

/**
 * F8-5: one renderable slice of an assistant message, in arrival order.
 * `text` renders as markdown prose, `thinking` as a collapsible Thought block,
 * `event` through the per-event renderers (tool bubbles, context card, …).
 */
export type TranscriptSegment =
  | { kind: 'text'; id: string; content: string }
  | { kind: 'thinking'; id: string; content: string }
  | { kind: 'event'; id: string; event: CopilotEvent }

/**
 * Rebuild the assistant transcript from the ordered events array (text deltas
 * are stored there too), merging same-type delta runs so a streamed answer is
 * one markdown segment per uninterrupted run — not "all text above all events",
 * which loses the true thinking → tool → answer chronology. Persisted messages
 * without text deltas fall back to `message.content` (the accumulated text
 * truth) as a trailing text segment.
 */
export function buildAssistantTranscript(message: CopilotMessage): TranscriptSegment[] {
  const segments: TranscriptSegment[] = []
  let sawText = false
  for (const event of message.events) {
    if (event.type === 'text_delta' || event.type === 'thinking_delta') {
      const kind = event.type === 'text_delta' ? 'text' : 'thinking'
      sawText = sawText || kind === 'text'
      const last = segments[segments.length - 1]
      if (last && last.kind === kind) {
        last.content += event.content
      } else {
        segments.push({ kind, id: event.id, content: event.content })
      }
    } else if (event.type !== 'done') {
      segments.push({ kind: 'event', id: event.id, event })
    }
  }
  if (!sawText && message.content) {
    segments.push({ kind: 'text', id: `${message.id}-content`, content: message.content })
  }
  return segments
}
