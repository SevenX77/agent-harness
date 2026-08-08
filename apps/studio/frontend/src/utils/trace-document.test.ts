import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../api/types'
import { buildTraceDocument } from './trace-document'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

describe('buildTraceDocument (n4-trace #18 read-only full-trace document)', () => {
  it('is empty, with no sections, when there are no events', () => {
    const doc = buildTraceDocument([])

    expect(doc.sections).toHaveLength(0)
    expect(doc.eventCount).toBe(0)
    expect(doc.runId).toBeNull()
  })

  it('reads as human sentences, not raw jsonl', () => {
    const doc = buildTraceDocument([
      event({ event_type: 'phase_start', phase_name: 'draft', run_id: 'run-1' }),
      event({ event_type: 'llm_call', phase_name: 'draft', input_tokens: 10, output_tokens: 5 }),
    ])

    expect(doc.runId).toBe('run-1')
    expect(doc.sections).toHaveLength(1)
    const [start, call] = doc.sections[0].entries
    expect(start.headline).toContain('Phase started: draft')
    expect(call.headline).toContain('LLM call completed')
    expect(call.tokens).toBe('10/5')
  })

  it('groups events into one block per node, in run order', () => {
    const doc = buildTraceDocument([
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'phase_end', phase_name: 'draft' }),
      event({ event_type: 'phase_start', phase_name: 'review' }),
    ])

    expect(doc.sections.map((section) => section.nodeId)).toEqual(['draft', 'review'])
    expect(doc.sections[0].entries.map((entry) => entry.position)).toEqual([1, 2])
    expect(doc.sections[1].entries).toHaveLength(1)
  })

  it("carries a state's full blackboard detail (D7)", () => {
    const doc = buildTraceDocument([
      event({ event_type: 'input_dispatch', to_phase: 'draft', blackboard_snapshot: { chapter_title: 'Prologue', word_count: 1200 } }),
    ])

    const [blackboard] = doc.sections[0].entries[0].details
    expect(blackboard.label).toBe('Blackboard')
    expect(blackboard.content).toContain('chapter_title')
    expect(blackboard.content).toContain('Prologue')
  })

  it('keeps an oversized blackboard whole — the full trace is complete or it is not full', () => {
    // The document used to cut every detail at 1200 characters with no way to
    // reach the rest, so the one surface promising the WHOLE run was the one
    // surface that could not show it.
    const huge = 'z'.repeat(5000)
    const doc = buildTraceDocument([
      event({ event_type: 'input_dispatch', to_phase: 'draft', blackboard_snapshot: { blob: huge } }),
    ])

    const [blackboard] = doc.sections[0].entries[0].details
    expect(blackboard.content).toContain(huge)
    expect(blackboard.content).not.toContain('truncated')
  })

  it('carries an error message on the state that failed', () => {
    const doc = buildTraceDocument([
      event({ event_type: 'internal_error', phase_name: 'draft', error_message: 'boom' }),
    ])

    expect(doc.sections[0].entries[0].errorMessage).toBe('boom')
  })
})

describe('buildTraceDocument detail projection (engine field names)', () => {
  it('shows the blackboard an input_dispatch actually carries', () => {
    // The engine emits `blackboard_snapshot`; the document used to look for a
    // field called `blackboard`, so every real run rendered as bare headlines
    // with no content under them at all.
    const doc = buildTraceDocument([
      event({
        event_type: 'input_dispatch',
        to_phase: 'segment',
        changed_keys: ['chapter_content'],
        blackboard_snapshot: { chapter_content: 'once upon a time' },
        dispatched_keys: ['chapter_content'],
      }),
    ])

    const labels = doc.sections[0].entries[0].details.map((d) => d.label)
    expect(labels).toContain('Blackboard')
    const blackboard = doc.sections[0].entries[0].details.find((d) => d.label === 'Blackboard')
    expect(blackboard?.content).toContain('once upon a time')
  })

  it('shows what an llm_call sent and got back', () => {
    const doc = buildTraceDocument([
      event({
        event_type: 'llm_call',
        phase_name: 'segment',
        messages: [{ role: 'user', content: 'segment this' }],
        response_data: { content: 'here you go' },
      }),
    ])

    const details = doc.sections[0].entries[0].details
    expect(details.map((d) => d.label)).toEqual(['Messages', 'Response'])
    expect(details[0].content).toContain('segment this')
    expect(details[1].content).toContain('here you go')
  })

  it('shows a tool call\'s arguments and its result', () => {
    const doc = buildTraceDocument([
      event({
        event_type: 'tool_call',
        phase_name: 'segment',
        tool_name: 'Read',
        args: { path: 'chapter.md' },
        result: 'read 4kb',
      }),
    ])

    const details = doc.sections[0].entries[0].details
    expect(details.map((d) => d.label)).toEqual(['Args', 'Result'])
    expect(details[1].content).toBe('read 4kb')
  })

  it('shows the context a phase started and ended with', () => {
    const doc = buildTraceDocument([
      event({ event_type: 'phase_start', phase_name: 'setup', context: { topic: 'a' } }),
      event({ event_type: 'phase_end', phase_name: 'setup', context: { topic: 'b' }, metrics: { ms: 12 } }),
    ])

    expect(doc.sections[0].entries[0].details.map((d) => d.label)).toEqual(['Context'])
    expect(doc.sections[0].entries[1].details.map((d) => d.label)).toEqual(['Context', 'Metrics'])
  })

  it('leaves out empty structures so short states stay one line', () => {
    const doc = buildTraceDocument([
      event({ event_type: 'phase_start', phase_name: 'setup', context: {} }),
    ])

    expect(doc.sections[0].entries[0].details).toEqual([])
  })
})
