import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../api/types'
import { TracePanel } from './TracePanel'

const events = [
  {
    event_type: 'run_started',
    phase: 'phase1',
    timestamp: '2026-06-14T00:00:00Z',
    data: {},
  } as unknown as CallbackEvent,
]

function render(props: Partial<React.ComponentProps<typeof TracePanel>>): string {
  return renderToStaticMarkup(
    <TracePanel traceLogs={events} onSelectPrompt={() => undefined} {...props} />,
  )
}

describe('TracePanel Resume action', () => {
  it('shows a Resume button enabled when the run can be resumed', () => {
    const html = render({ canResume: true })
    expect(html).toContain('Resume')
    expect(html).toContain('aria-label="Resume run from last checkpoint"')
    // Enabled: the resume button markup should not carry the disabled attribute.
    const resumeButton = html.slice(html.indexOf('Resume run from last checkpoint') - 200, html.indexOf('Resume run from last checkpoint') + 200)
    expect(resumeButton).not.toContain('disabled=""')
  })

  it('disables Resume when there is no resumable run', () => {
    const html = render({ canResume: false })
    const idx = html.indexOf('Resume run from last checkpoint')
    // The disabled attribute follows aria-label + title on the same button.
    expect(html.slice(idx, idx + 200)).toContain('disabled')
  })

  it('shows a Resuming label while a resume is in flight', () => {
    const html = render({ canResume: true, resumeLoading: true })
    expect(html).toContain('Resuming')
  })

  it('omits Resume affordance content when there are no trace events', () => {
    const html = renderToStaticMarkup(
      <TracePanel traceLogs={[]} onSelectPrompt={() => undefined} canResume />,
    )
    // Empty state shows the waiting message, not the action bar.
    expect(html).toContain('Waiting for run events')
    expect(html).not.toContain('Resume run from last checkpoint')
  })
})
