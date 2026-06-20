import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { HitlPromptForm } from './HitlPromptForm'
import { latestHitlPrompt } from './hitl-prompt'

function envelope(payload: Record<string, unknown>, seq = 1): EventEnvelope {
  return {
    schema_version: 'studio.event.v1',
    stream_id: 'run:run-1',
    seq,
    cursor: `run:run-1:${seq}`,
    run_id: 'run-1',
    event_type: String(payload.event_type ?? ''),
    timestamp: '2026-06-19T00:00:00Z',
    payload: {
      schema_version: '1.0',
      timestamp: '2026-06-19T00:00:00Z',
      ...payload,
    } as EventEnvelope['payload'],
  }
}

const singlePrompt = latestHitlPrompt([
  envelope({
    event_type: 'interrupted',
    phase_name: 'review',
    question: 'Approve the generated draft?',
    options: ['Approve', 'Revise'],
    checkpoint_id: 'checkpoint-review',
    checkpoint_ns: 'agent:review',
  }),
])

const multiPrompt = latestHitlPrompt([
  envelope({
    event_type: 'interrupted',
    phase_name: 'review',
    question: 'Choose the pending human input to answer.',
    pending_tool_calls: [
      { id: 'tool-a', question: 'Approve outline?', options: ['Approve outline', 'Revise outline'] },
      { id: 'tool-b', question: 'Approve citations?', options: ['Approve citations', 'Revise citations'] },
    ],
    checkpoint_id: 'checkpoint-review',
    checkpoint_ns: 'agent:review',
  }),
])

describe('HitlPromptForm (shared HitL form content)', () => {
  it('renders the question, options and a labelled textarea', () => {
    if (!singlePrompt) throw new Error('fixture prompt missing')
    const html = renderToStaticMarkup(
      <HitlPromptForm prompt={singlePrompt} onSubmitHitlResponse={() => undefined} />,
    )
    expect(html).toContain('Human input required')
    expect(html).toContain('Approve the generated draft?')
    expect(html).toContain('Approve')
    expect(html).toContain('Revise')
    expect(html).toContain('aria-label="Human response for review"')
    expect(html).toContain('checkpoint-review')
  })

  it('renders the pending-tool-call selector and blocks submit until one is chosen', () => {
    if (!multiPrompt) throw new Error('fixture prompt missing')
    const html = renderToStaticMarkup(
      <HitlPromptForm prompt={multiPrompt} onSubmitHitlResponse={() => undefined} />,
    )
    expect(html).toContain('Pending tool calls')
    expect(html).toContain('Approve outline?')
    expect(html).toContain('Approve citations?')
    expect(html).toContain('tool-a')
    expect(html).toContain('tool-b')
    expect(html).toContain('Select a pending tool call before submitting.')
    const submitSlice = html.slice(html.indexOf('Submit answer') - 240, html.indexOf('Submit answer') + 160)
    expect(submitSlice).toContain('disabled=""')
  })

  it('shows a submitting label while a resume is in flight', () => {
    if (!singlePrompt) throw new Error('fixture prompt missing')
    const html = renderToStaticMarkup(
      <HitlPromptForm prompt={singlePrompt} onSubmitHitlResponse={() => undefined} submitting />,
    )
    expect(html).toContain('Submitting')
  })
})
