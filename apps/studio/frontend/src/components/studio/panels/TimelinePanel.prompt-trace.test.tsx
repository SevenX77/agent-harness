import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type { CallbackEvent, EventEnvelope } from '@/api/types'
import { findPromptEvent } from '@/utils/trace'
import { PromptInspector } from '@/components/PromptInspector'

/**
 * D8 (prompt 回溯) for the *historical* trace path.
 *
 * The history TimelinePanel resolves a clicked row index against the run's
 * persisted EventEnvelope[] by mapping to payloads and walking back to the
 * driving prompt_captured event (findPromptEvent), then feeds that event to the
 * PromptInspector. The click-to-open transition is interactive (covered by
 * Playwright e2e); here we lock the resolution + render contract that replaced
 * the previous `onSelectPrompt={() => undefined}` no-op.
 */

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: ReactNode }) => <div data-slot="dialog">{children}</div>,
  DialogContent: ({ children }: { children: ReactNode }) => <div data-slot="dialog-content">{children}</div>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div data-slot="dialog-header">{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2 data-slot="dialog-title">{children}</h2>,
}))

vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: ReactNode }) => <div data-slot="tabs">{children}</div>,
  TabsContent: ({ children }: { children: ReactNode }) => <div data-slot="tabs-content">{children}</div>,
  TabsList: ({ children }: { children: ReactNode }) => <div data-slot="tabs-list">{children}</div>,
  TabsTrigger: ({ children }: { children: ReactNode }) => <button data-slot="tabs-trigger">{children}</button>,
}))

function envelope(seq: number, payload: Partial<CallbackEvent> & { event_type: string }): EventEnvelope {
  return {
    schema_version: 'studio.event.v1',
    stream_id: 'run:hist-1',
    seq,
    cursor: `run:hist-1:${seq}`,
    run_id: 'hist-1',
    event_type: payload.event_type,
    timestamp: '2026-06-14T00:00:00Z',
    payload: { schema_version: '1.0', timestamp: '2026-06-14T00:00:00Z', ...payload } as CallbackEvent,
  }
}

const historyEvents: EventEnvelope[] = [
  envelope(1, { event_type: 'prompt_captured', phase_name: 'review', template_source: 'review-template-body' }),
  envelope(2, { event_type: 'llm_call', phase_name: 'review' }),
]

describe('TimelinePanel historical prompt 回溯 (D8)', () => {
  it('resolves a clicked llm_call row back to its driving prompt_captured payload', () => {
    const resolved = findPromptEvent(historyEvents.map((item) => item.payload as CallbackEvent), 1)
    expect(resolved?.event_type).toBe('prompt_captured')
    expect(resolved?.template_source).toBe('review-template-body')
  })

  it('renders the PromptInspector with the resolved historical prompt event', () => {
    const resolved = findPromptEvent(historyEvents.map((item) => item.payload as CallbackEvent), 1)
    const html = renderToStaticMarkup(<PromptInspector promptEvent={resolved} onClose={() => undefined} />)

    expect(html).toContain('Prompt Inspector: review')
    expect(html).toContain('review-template-body')
  })

  it('keeps the inspector closed when no row is selected (null index path)', () => {
    const html = renderToStaticMarkup(<PromptInspector promptEvent={null} onClose={() => undefined} />)
    expect(html).toBe('')
  })
})
