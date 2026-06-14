import { describe, expect, it } from 'vitest'
import { normalizeCopilotEvent } from './copilot'

describe('normalizeCopilotEvent', () => {
  // F1: the backend now streams a thinking_delta event; it must normalize to a
  // first-class thinking event (collapsible Thought), never fall to "unknown".
  it('maps a thinking_delta payload to a thinking event with its content', () => {
    const event = normalizeCopilotEvent(
      { type: 'thinking_delta', content: 'let me reason...' },
      'evt-1',
    )

    expect(event.type).toBe('thinking_delta')
    expect(event).toMatchObject({ id: 'evt-1', status: 'running', content: 'let me reason...' })
  })

  it('maps a text_delta payload to a text event', () => {
    const event = normalizeCopilotEvent({ type: 'text_delta', content: 'answer' }, 'evt-2')

    expect(event.type).toBe('text_delta')
    expect(event).toMatchObject({ status: 'running', content: 'answer' })
  })

  it('falls back to unknown for a thinking_delta missing string content', () => {
    const event = normalizeCopilotEvent({ type: 'thinking_delta', content: 42 }, 'evt-3')

    expect(event.type).toBe('unknown')
  })
})
