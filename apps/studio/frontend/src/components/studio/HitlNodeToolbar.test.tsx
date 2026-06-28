import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { HitlNodeToolbar } from './HitlNodeToolbar'

// NodeToolbar reads the React Flow store to position itself; in a static render
// we stub it (mirrors the existing node tests that mock '@xyflow/react'). We
// surface nodeId / isVisible / position as data-* so the test can assert the
// box is ANCHORED to the paused node with position=top (the F4 requirement).
const nodeToolbarCalls = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@xyflow/react', () => ({
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
  NodeToolbar: ({ nodeId, isVisible, position, children }: Record<string, unknown>) => {
    nodeToolbarCalls.push({ nodeId, isVisible, position })
    return (
      <div
        data-testid="node-toolbar"
        data-node-id={String(nodeId)}
        data-visible={String(isVisible)}
        data-position={String(position)}
      >
        {children as React.ReactNode}
      </div>
    )
  },
}))

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

const interruptedEvent = envelope({
  event_type: 'interrupted',
  phase_name: 'review',
  question: 'Approve the generated draft?',
  options: ['Approve', 'Revise'],
  checkpoint_id: 'checkpoint-review',
  checkpoint_ns: 'agent:review',
})

describe('HitlNodeToolbar (F4: node-anchored HitL input)', () => {
  it('anchors the floating box to the paused node above it with the prompt', () => {
    const html = renderToStaticMarkup(
      <HitlNodeToolbar traceEvents={[interruptedEvent]} onSubmitHitlResponse={() => undefined} />,
    )
    const lastCall = nodeToolbarCalls.at(-1)
    // Anchored to the node that went paused: nodeId == phase_name.
    expect(lastCall?.nodeId).toBe('review')
    // Above the node, and visible even though the node is not selected.
    expect(lastCall?.position).toBe('top')
    expect(lastCall?.isVisible).toBe(true)
    // Reuses the shared HitL form content (question + options + textarea).
    expect(html).toContain('Human input required')
    expect(html).toContain('Approve the generated draft?')
    expect(html).toContain('Approve')
    expect(html).toContain('Revise')
    expect(html).toContain('aria-label="Human response for review"')
  })

  it('renders nothing when there is no interrupt in the stream', () => {
    const running = envelope({ event_type: 'phase_start', phase_name: 'review' })
    const html = renderToStaticMarkup(
      <HitlNodeToolbar traceEvents={[running]} onSubmitHitlResponse={() => undefined} />,
    )
    expect(html).toBe('')
  })

  it('renders nothing for an empty event stream', () => {
    const html = renderToStaticMarkup(
      <HitlNodeToolbar traceEvents={[]} onSubmitHitlResponse={() => undefined} />,
    )
    expect(html).toBe('')
  })
})
