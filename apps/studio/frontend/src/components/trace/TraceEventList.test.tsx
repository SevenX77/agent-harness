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
      activePhase={null}
      selectedEventId={null}
      linkEnabled={false}
      onSelectPrompt={() => {}}
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
    expect(html).toContain('data-trace-event-count="100"')
  })

  it('gives rows no fixed height, so a row is as tall as what it contains', () => {
    const html = markup(3)

    expect(html).not.toContain('min-height:128px')
    expect(html).not.toContain('height:128px')
  })
})
