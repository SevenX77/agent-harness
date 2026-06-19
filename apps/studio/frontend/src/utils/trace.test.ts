import { describe, expect, it } from 'vitest'

import type { CallbackEvent } from '../api/types'
import { findPromptEvent, payloadPreview, retryBadge } from './trace'

function event(partial: Partial<CallbackEvent> & { event_type: string }): CallbackEvent {
  return {
    schema_version: '1.0',
    timestamp: '2026-06-14T00:00:00Z',
    ...partial,
  } as CallbackEvent
}

describe('findPromptEvent (D8 prompt 回溯)', () => {
  it('returns the selected event itself when it is a prompt_captured event', () => {
    const events = [
      event({ event_type: 'phase_start', phase_name: 'draft' }),
      event({ event_type: 'prompt_captured', phase_name: 'draft', template_source: 'tpl' }),
    ]
    expect(findPromptEvent(events, 1)).toBe(events[1])
  })

  it('walks back to the nearest prompt_captured in the same phase when an llm_call is selected', () => {
    const events = [
      event({ event_type: 'prompt_captured', phase_name: 'draft', template_source: 'draft-tpl' }),
      event({ event_type: 'prompt_captured', phase_name: 'review', template_source: 'review-tpl' }),
      event({ event_type: 'llm_call', phase_name: 'review' }),
    ]
    // Selecting the llm_call (index 2) must resolve to the review-phase prompt, not draft.
    expect(findPromptEvent(events, 2)).toBe(events[1])
  })

  it('falls back to the llm_call event itself when no prompt_captured precedes it', () => {
    const events = [
      event({ event_type: 'phase_start', phase_name: 'solo' }),
      event({ event_type: 'llm_call', phase_name: 'solo' }),
    ]
    expect(findPromptEvent(events, 1)).toBe(events[1])
  })

  it('returns null for a non-inspectable event with no upstream prompt', () => {
    const events = [event({ event_type: 'phase_start', phase_name: 'draft' })]
    expect(findPromptEvent(events, 0)).toBeNull()
  })

  it('returns null when the index is out of range', () => {
    expect(findPromptEvent([], 0)).toBeNull()
  })
})

describe('retryBadge (D10 validator retry nudge)', () => {
  it('returns null for events that carry no attempt information', () => {
    expect(retryBadge(event({ event_type: 'phase_start' }))).toBeNull()
  })

  it('derives an attempt/limit badge from attempt + max_attempts', () => {
    const badge = retryBadge(event({ event_type: 'validation_fail', attempt: 2, max_attempts: 3 }))
    expect(badge).not.toBeNull()
    expect(badge?.label).toBe('2/3')
    expect(badge?.exhausted).toBe(false)
  })

  it('reads retry_count and max_retries when attempt fields are absent', () => {
    const badge = retryBadge(event({ event_type: 'validation_fail', retry_count: 1, max_retries: 3 }))
    // retry_count is zero-based attempts already spent → human-facing attempt is +1.
    expect(badge?.label).toBe('2/3')
  })

  it('flags the badge as exhausted when the final attempt is reached', () => {
    const badge = retryBadge(event({ event_type: 'validation_fail', attempt: 3, max_attempts: 3 }))
    expect(badge?.exhausted).toBe(true)
  })

  it('reads nested attempt info from metadata when not at the top level', () => {
    const badge = retryBadge(
      event({ event_type: 'validation_fail', metadata: { attempt: 1, max_attempts: 2 } }),
    )
    expect(badge?.label).toBe('1/2')
  })

  it('shows a bare attempt count when no limit is known', () => {
    const badge = retryBadge(event({ event_type: 'validation_fail', attempt: 2 }))
    expect(badge?.label).toBe('#2')
    expect(badge?.exhausted).toBe(false)
  })
})

describe('payloadPreview (D1 / §4 default-collapse big payloads)', () => {
  it('returns the full serialized payload untruncated when it is under the auto-expand limit', () => {
    const preview = payloadPreview(event({ event_type: 'phase_start', phase_name: 'draft' }))
    expect(preview.truncated).toBe(false)
    expect(preview.text).toContain('phase_start')
    expect(preview.sizeBytes).toBeGreaterThan(0)
  })

  it('marks the payload as truncated once it exceeds the ~2KB auto-expand limit', () => {
    const bigText = 'x'.repeat(4000)
    const preview = payloadPreview(event({ event_type: 'llm_call', big_field: bigText }))
    expect(preview.truncated).toBe(true)
    expect(preview.sizeBytes).toBeGreaterThan(2048)
    // The collapsed preview text must be shorter than the full payload.
    expect(preview.text.length).toBeLessThan(JSON.stringify(event({ event_type: 'llm_call', big_field: bigText }), null, 2).length)
  })

  it('reports a human-readable size label in kilobytes', () => {
    const bigText = 'y'.repeat(4000)
    const preview = payloadPreview(event({ event_type: 'llm_call', big_field: bigText }))
    expect(preview.sizeLabel).toMatch(/KB$/)
  })
})
