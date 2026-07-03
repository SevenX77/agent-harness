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

/**
 * R7-A: a turn's renderable split into the collapsible PROCESS (thinking, tool
 * calls, context, any intermediate narration) and the final ANSWER (the last
 * text run). The panel shows the process live while streaming, then folds it
 * into one "Processed {duration}" line once settled, keeping only the answer
 * expanded — PM 2026-07-02「最后只保留最终输出，上面所有过程收束到一个折叠的过程行」.
 */
export interface AssistantView {
  process: TranscriptSegment[]
  answer: { id: string; content: string } | null
  durationMs: number | null
}

export function partitionAssistantView(message: CopilotMessage): AssistantView {
  const segments = buildAssistantTranscript(message)
  let answerIndex = -1
  for (let i = segments.length - 1; i >= 0; i -= 1) {
    if (segments[i].kind === 'text') {
      answerIndex = i
      break
    }
  }
  const answerSegment = answerIndex >= 0 ? segments[answerIndex] : null
  const answer =
    answerSegment && answerSegment.kind === 'text'
      ? { id: answerSegment.id, content: answerSegment.content }
      : null
  const process = answerIndex >= 0 ? segments.slice(0, answerIndex) : segments
  const done = message.events.find((event) => event.type === 'done')
  const durationMs = done ? Math.max(0, done.receivedAt - message.createdAt) : null
  return { process, answer, durationMs }
}

/** Compact "Processed 45s" / "1m 20s" duration label for the folded process row. */
export function formatProcessedDuration(ms: number): string {
  const totalSeconds = Math.round(ms / 1000)
  if (totalSeconds < 60) {
    return `${totalSeconds}s`
  }
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds === 0 ? `${minutes}m` : `${minutes}m ${seconds}s`
}
