import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { CallbackEvent } from '../api/types'

// MonacoPanel imports the heavy Monaco editor at module scope. Stub it so this stays
// a pure SSR render-contract test; the stub surfaces the props the panel passes in
// (value + readOnly) so we can assert the document is read-only and not raw jsonl.
vi.mock('@monaco-editor/react', () => ({
  default: ({ value, options }: { value?: string; options?: { readOnly?: boolean } }) => (
    <pre data-readonly={options?.readOnly ? 'true' : 'false'}>{value}</pre>
  ),
}))

const { TraceDocumentPanel } = await import('./MonacoPanel')

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

function render(events: CallbackEvent[], focusNodeId?: string | null): string {
  return renderToStaticMarkup(
    <TraceDocumentPanel events={events} isDarkMode={false} focusNodeId={focusNodeId} />,
  )
}

describe('TraceDocumentPanel (n4-trace #18)', () => {
  it('renders a labelled read-only full-trace document surface', () => {
    const html = render([event({ event_type: 'phase_start', phase_name: 'draft' })])

    expect(html).toContain('aria-label="Full trace document"')
    expect(html).toContain('Full Trace')
    // The editor is mounted read-only — users read, they do not edit the trace.
    expect(html).toContain('data-readonly="true"')
  })

  it('feeds the editor a lightly-formatted document, not raw jsonl', () => {
    const html = render([
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'llm_call', phase_name: 'draft' }),
    ])

    expect(html).toContain('## draft')
    expect(html).toContain('Phase started: draft')
    expect(html).toContain('LLM call completed')
    expect(html).not.toContain('&quot;event_type&quot;')
  })

  it('reports the event count in the header', () => {
    const html = render([
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'phase_end', phase_name: 'draft' }),
    ])

    expect(html).toContain('2 events')
  })
})
