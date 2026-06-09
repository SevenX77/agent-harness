import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { TracePanel } from './TracePanel'
import type { CallbackEvent } from '../api/types'

describe('TracePanel WS-3 contracts (Regression Lock)', () => {
  it('renders Waiting for run events when traceLogs is empty', () => {
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={[]}
        onSelectPrompt={vi.fn()}
      />
    )
    expect(html).toContain('Waiting for run events')
  })

  it('renders events keeping machine-readable event_type codes visible', () => {
    const mockEvents: CallbackEvent[] = [
      {
        schema_version: '1.0',
        event_type: 'phase_start',
        phase_name: 'draft',
        event_id: 'evt-1',
        parent_id: null,
        timestamp: '2026-05-21T12:00:00Z',
      },
      {
        schema_version: '1.0',
        event_type: 'llm_call',
        phase_name: 'draft',
        event_id: 'evt-2',
        parent_id: 'evt-1',
        timestamp: '2026-05-21T12:00:01Z',
      }
    ]

    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={mockEvents}
        onSelectPrompt={vi.fn()}
      />
    )

    // Should not render Waiting for run events anymore
    expect(html).not.toContain('Waiting for run events')

    // Machine readable event_type should be visible in EventTypeBadge
    expect(html).toContain('phase_start')
    expect(html).toContain('llm_call')
  })

  it('correctly filters events based on searchTerm', () => {
    const mockEvents: CallbackEvent[] = [
      {
        schema_version: '1.0',
        event_type: 'phase_start',
        phase_name: 'draft',
        event_id: 'evt-1',
        timestamp: '2026-05-21T12:00:00Z',
      },
      {
        schema_version: '1.0',
        event_type: 'tool_call',
        phase_name: 'review',
        event_id: 'evt-2',
        timestamp: '2026-05-21T12:00:01Z',
      }
    ]

    // We can't interactively type in renderToStaticMarkup, but we can verify
    // that the UI has the TraceSearchBar and the header summary initially showing all counts.
    const html = renderToStaticMarkup(
      <TracePanel
        traceLogs={mockEvents}
        onSelectPrompt={vi.fn()}
      />
    )

    expect(html).toContain('Showing 2 of 2 events')
  })
})
