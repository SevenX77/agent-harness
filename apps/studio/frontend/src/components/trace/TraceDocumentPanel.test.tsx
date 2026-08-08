import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../../api/types'
import { TraceDocumentPanel } from './TraceDocumentPanel'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

function render(events: CallbackEvent[], focusNodeId?: string | null): string {
  return renderToStaticMarkup(<TraceDocumentPanel events={events} focusNodeId={focusNodeId} />)
}

describe('TraceDocumentPanel (n4-trace #18)', () => {
  it('renders a labelled full-trace document surface', () => {
    const html = render([event({ event_type: 'phase_start', phase_name: 'draft' })])

    expect(html).toContain('aria-label="Full trace document"')
    expect(html).toContain('Full Trace')
  })

  it('reads as a document, not as an editor', () => {
    // A panel nobody can edit must not wear editor chrome: no Monaco, no line
    // numbers, no code-editor theme (decision 2026-08-08 D4).
    const html = render([event({ event_type: 'phase_start', phase_name: 'draft' })])

    expect(html).not.toContain('monaco')
    expect(html).not.toContain('data-readonly')
  })

  it('groups the run into one block per node, with human sentences', () => {
    const html = render([
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'llm_call', phase_name: 'draft' }),
      event({ event_type: 'phase_start', phase_name: 'review' }),
    ])

    expect(html).toContain('data-trace-doc-node="draft"')
    expect(html).toContain('data-trace-doc-node="review"')
    expect(html).toContain('Phase started: draft')
    expect(html).toContain('LLM call completed')
    expect(html).not.toContain('&quot;schema_version&quot;')
  })

  it('shows a long value in full rather than cutting it off', () => {
    const huge = 'z'.repeat(5000)
    const html = render([event({ event_type: 'phase_end', phase_name: 'draft', outputs: { blob: huge } })])

    expect(html).toContain(huge)
    expect(html).not.toContain('truncated')
  })

  it('reports the event count in the header', () => {
    const html = render([
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'phase_end', phase_name: 'draft' }),
    ])

    expect(html).toContain('2 events')
  })
})
