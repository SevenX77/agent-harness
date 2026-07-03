import { describe, expect, it } from 'vitest'

import type {
  CopilotEvent,
  CopilotMessage,
  CopilotTextDeltaEvent,
  CopilotThinkingDeltaEvent,
} from '../../types/copilot'
import { buildAssistantTranscript, formatProcessedDuration, partitionAssistantView } from './transcript'

function message(
  events: CopilotEvent[],
  content = '',
  status: CopilotMessage['status'] = 'running',
  createdAt = 1,
): CopilotMessage {
  return { id: 'assistant-1', role: 'assistant', content, events, status, createdAt }
}

function doneAt(id: string, receivedAt: number): CopilotEvent {
  return { id, type: 'done', status: 'success', receivedAt, raw: null }
}

function toolResult(id: string, success = true): CopilotEvent {
  return {
    id,
    type: 'tool_use_result',
    status: success ? 'success' : 'error',
    receivedAt: 1,
    raw: null,
    tool_name: 'Read',
    success,
    result_summary: 'ok',
  }
}

function textDelta(id: string, content: string): CopilotTextDeltaEvent {
  return { id, type: 'text_delta', status: 'running', receivedAt: 1, raw: null, content }
}

function thinkingDelta(id: string, content: string): CopilotThinkingDeltaEvent {
  return { id, type: 'thinking_delta', status: 'running', receivedAt: 1, raw: null, content }
}

function contextResolved(id: string): CopilotEvent {
  return { id, type: 'context_resolved', status: 'success', receivedAt: 1, raw: null, summary: 'ctx', detail: 'd' }
}

function toolUseStart(id: string): CopilotEvent {
  return { id, type: 'tool_use_start', status: 'running', receivedAt: 1, raw: null, tool_name: 'Read', tool_input: {} }
}

function doneEvent(id: string): CopilotEvent {
  return { id, type: 'done', status: 'success', receivedAt: 1, raw: null }
}

describe('buildAssistantTranscript', () => {
  // F8-5: the events array carries the full arrival order (text deltas
  // included); the transcript is rebuilt from it so thinking/tools/text render
  // interleaved in true chronological order, not "all text above all events".
  it('interleaves thinking, text and tool events in arrival order', () => {
    const segments = buildAssistantTranscript(
      message([
        contextResolved('c1'),
        thinkingDelta('th1', 'let me '),
        thinkingDelta('th2', 'reason'),
        textDelta('t1', 'Reading'),
        toolUseStart('tool1'),
        textDelta('t2', 'Answer'),
      ]),
    )

    expect(segments.map((s) => s.kind)).toEqual(['event', 'thinking', 'text', 'event', 'text'])
    expect(segments[1]).toMatchObject({ kind: 'thinking', content: 'let me reason' })
    expect(segments[2]).toMatchObject({ kind: 'text', content: 'Reading' })
    expect(segments[4]).toMatchObject({ kind: 'text', content: 'Answer' })
  })

  it('skips done events (no visual representation)', () => {
    const segments = buildAssistantTranscript(message([textDelta('t1', 'hi'), doneEvent('d1')]))

    expect(segments).toHaveLength(1)
    expect(segments[0]).toMatchObject({ kind: 'text', content: 'hi' })
  })

  it('falls back to message.content when no text deltas exist (persisted transcripts)', () => {
    const segments = buildAssistantTranscript(message([contextResolved('c1')], 'stored answer', 'success'))

    expect(segments.map((s) => s.kind)).toEqual(['event', 'text'])
    expect(segments[1]).toMatchObject({ kind: 'text', content: 'stored answer' })
  })

  it('returns no segments for an empty in-flight message', () => {
    expect(buildAssistantTranscript(message([]))).toEqual([])
  })
})

// R7-A (PM 2026-07-02「最后只保留最终输出，把上面所有过程收束到一个折叠的过程行，
// 加处理时间 processed 44s」): a settled turn splits into the collapsible PROCESS
// (thinking / tools / context / intermediate narration) and the final ANSWER
// (the last text run), plus the turn duration for the "Processed Ns" summary.
describe('partitionAssistantView', () => {
  it('splits the final text answer from the preceding process', () => {
    const view = partitionAssistantView(
      message(
        [
          contextResolved('c1'),
          thinkingDelta('th1', 'reason'),
          textDelta('t1', 'Reading the graph'),
          toolUseStart('tool1'),
          toolResult('tr1'),
          textDelta('t2', 'Final answer'),
          doneAt('d1', 45_000),
        ],
        'Reading the graphFinal answer',
        'success',
      ),
    )

    expect(view.process.map((s) => s.kind)).toEqual(['event', 'thinking', 'text', 'event', 'event'])
    expect(view.answer).toMatchObject({ content: 'Final answer' })
    expect(view.durationMs).toBe(44_999)
  })

  it('has a null answer when the turn produced only process (tools, no final text)', () => {
    const view = partitionAssistantView(
      message([thinkingDelta('th1', 'hmm'), toolUseStart('tool1'), doneAt('d1', 3_000)], '', 'success'),
    )

    expect(view.answer).toBeNull()
    expect(view.process.map((s) => s.kind)).toEqual(['thinking', 'event'])
    expect(view.durationMs).toBe(2_999)
  })

  it('reports null duration while the turn is still streaming (no done event)', () => {
    const view = partitionAssistantView(message([textDelta('t1', 'partial')]))

    expect(view.durationMs).toBeNull()
    expect(view.answer).toMatchObject({ content: 'partial' })
  })
})

describe('formatProcessedDuration', () => {
  it('formats sub-minute durations as seconds', () => {
    expect(formatProcessedDuration(44_999)).toBe('45s')
    expect(formatProcessedDuration(0)).toBe('0s')
  })

  it('formats minute-plus durations as m/s', () => {
    expect(formatProcessedDuration(60_000)).toBe('1m')
    expect(formatProcessedDuration(80_000)).toBe('1m 20s')
  })
})
