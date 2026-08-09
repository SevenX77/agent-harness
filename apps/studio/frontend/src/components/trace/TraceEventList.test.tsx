import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CallbackEvent } from '../../api/types'
import type { IndexedTraceEvent } from '../../hooks/useTraceFilter'
import { TraceEventList } from './TraceEventList'

function indexedEvents(count: number): IndexedTraceEvent[] {
  return Array.from({ length: count }, (_unused, index) => ({
    index,
    event: {
      schema_version: '1.0',
      timestamp: `2026-08-08T00:00:${String(index).padStart(2, '0')}Z`,
      event_type: 'phase_start',
      phase_name: `node-${index}`,
    } as CallbackEvent,
  }))
}

function markup(count: number): string {
  return renderToStaticMarkup(
    <TraceEventList
      events={indexedEvents(count)}
      selectedEventId={null}
    />,
  )
}

describe('TraceEventList', () => {
  it('renders every event, so the scroll region covers the whole trace', () => {
    // The list used to window rows into fixed 128px slots while spacing them a
    // further 20px apart, so the scroll container was always shorter than what
    // it held and the tail of a run could not be reached.
    const html = markup(100)

    expect(html.match(/role="option"/g)).toHaveLength(100)
    expect(html).toContain('data-trace-step-count="100"')
  })

  it('gives rows no fixed height, so a row is as tall as what it contains', () => {
    const html = markup(3)

    expect(html).not.toContain('min-height:128px')
    expect(html).not.toContain('height:128px')
  })
})

describe('TraceEventList step expansion (decision 2026-08-09 D4)', () => {
  function stepEvents(): IndexedTraceEvent[] {
    return [
      { index: 0, event: { schema_version: '1.0', timestamp: '2026-08-09T00:00:00Z', event_type: 'prompt_captured', phase_name: 'draft' } as CallbackEvent },
      { index: 1, event: { schema_version: '1.0', timestamp: '2026-08-09T00:00:01Z', event_type: 'llm_call', phase_name: 'draft' } as CallbackEvent },
      { index: 2, event: { schema_version: '1.0', timestamp: '2026-08-09T00:00:02Z', event_type: 'prompt_captured', phase_name: 'review' } as CallbackEvent },
    ]
  }

  it('opens a running step and folds a finished one, without being told', () => {
    // Two steps: draft answered, review still waiting. The unfinished one is
    // where the reader's attention belongs, so it is the one left open.
    const html = renderToStaticMarkup(
      <TraceEventList events={stepEvents()} selectedEventId={null} />,
    )

    expect(html).toContain('data-trace-step-count="2"')
    expect(html).toContain('data-trace-step-status="running"')
    expect(html).toContain('data-trace-step-status="done"')
    expect(html.match(/aria-expanded="true"/g)).toHaveLength(1)
    expect(html.match(/aria-expanded="false"/g)).toHaveLength(1)
  })
})
