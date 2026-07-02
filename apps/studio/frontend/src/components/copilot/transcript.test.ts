import { describe, expect, it } from 'vitest'

import type {
  CopilotEvent,
  CopilotMessage,
  CopilotTextDeltaEvent,
  CopilotThinkingDeltaEvent,
} from '../../types/copilot'
import { buildAssistantTranscript } from './transcript'

function message(events: CopilotEvent[], content = '', status: CopilotMessage['status'] = 'running'): CopilotMessage {
  return { id: 'assistant-1', role: 'assistant', content, events, status, createdAt: 1 }
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
