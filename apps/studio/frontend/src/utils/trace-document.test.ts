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
  it('renders an empty-state document with no node ranges when there are no events', () => {
    const doc = buildTraceDocument([])
    expect(doc.text).toContain('No trace events captured yet')
    expect(doc.nodeRanges).toHaveLength(0)
  })

  it('renders a lightly-formatted document (human sentences, not raw jsonl)', () => {
    const doc = buildTraceDocument([
      event({ event_type: 'phase_start', phase_name: 'draft', run_id: 'run-1' }),
      event({ event_type: 'llm_call', phase_name: 'draft', input_tokens: 10, output_tokens: 5 }),
    ])

    // Document framing + readable sentences, not a JSON array dump.
    expect(doc.text).toContain('# Run trace · run-1')
    expect(doc.text).toContain('## draft')
    expect(doc.text).toContain('Phase started: draft')
    expect(doc.text).toContain('LLM call completed')
    expect(doc.text).toContain('tokens 10/5')
    // It must not be a raw jsonl / JSON.stringify of the event list.
    expect(doc.text).not.toContain('"event_type":')
    expect(doc.text).not.toContain('"schema_version"')
  })

  it('groups events by node/phase and exposes a line range per node for focus jumps', () => {
    const doc = buildTraceDocument([
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'phase_end', phase_name: 'draft' }),
      event({ event_type: 'phase_start', phase_name: 'review' }),
    ])

    const draft = doc.nodeRanges.find((range) => range.nodeId === 'draft')
    const review = doc.nodeRanges.find((range) => range.nodeId === 'review')
    expect(draft).toBeDefined()
    expect(review).toBeDefined()
    // Each range is a valid 1-based span and they do not overlap (sequential blocks).
    expect(draft!.startLine).toBeGreaterThan(0)
    expect(draft!.endLine).toBeGreaterThanOrEqual(draft!.startLine)
    expect(review!.startLine).toBeGreaterThan(draft!.endLine)

    // The heading really sits on the recorded start line.
    const lines = doc.text.split('\n')
    expect(lines[draft!.startLine - 1]).toBe('## draft')
    expect(lines[review!.startLine - 1]).toBe('## review')
  })

  it('inlines a state\'s full blackboard detail beneath its line (D7), not a one-off raw dump', () => {
    const doc = buildTraceDocument([
      event({ event_type: 'phase_end', phase_name: 'draft', outputs: { chapter_title: 'Prologue', word_count: 1200 } }),
    ])

    expect(doc.text).toContain('Blackboard:')
    expect(doc.text).toContain('chapter_title')
    expect(doc.text).toContain('Prologue')
  })

  it('truncates oversized state detail so a huge blackboard never floods the document', () => {
    const huge = 'z'.repeat(5000)
    const doc = buildTraceDocument([
      event({ event_type: 'phase_end', phase_name: 'draft', outputs: { blob: huge } }),
    ])

    expect(doc.text).toContain('truncated')
    expect(doc.text).not.toContain(huge)
  })
})
