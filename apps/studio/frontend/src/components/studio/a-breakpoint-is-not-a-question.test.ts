/**
 * A breakpoint stop is not a question, and must not be shown as one.
 *
 * Walking a breakpoint through the real window turned up the exact confusion
 * `InterruptedEvent.reason` was added to prevent: the run stopped before
 * `beta`, and the canvas put up "HUMAN INPUT REQUIRED — Run paused for human
 * input." with a Submit answer box. There was no question. The prompt builder
 * matched any `interrupted` event and, finding no question in it, supplied that
 * sentence itself.
 *
 * The design named this failure before it happened: an empty `question` cannot
 * tell the two apart, because it is equally what a human-in-the-loop stop looks
 * like when its question failed to parse — so the reason has to be READ.
 *
 * Design: run-execution/mvp1-alignment.md RUN_EXECUTION-16.
 */

import { describe, expect, it } from 'vitest'
import type { EventEnvelope } from '@/api/types'
import { isHitlEvent, latestHitlPrompt } from './hitl-prompt'

function envelope(payload: Record<string, unknown>): EventEnvelope {
  return {
    schema_version: 'studio.event.v1',
    run_id: 'run-1',
    seq: 1,
    event_type: String(payload.event_type ?? ''),
    payload,
  } as unknown as EventEnvelope
}

describe('a run stopped at a breakpoint', () => {
  it('is not a human-input prompt', () => {
    const stopped = envelope({
      event_type: 'interrupted',
      phase_name: 'beta',
      thread_id: 'run-1',
      reason: 'breakpoint',
    })

    expect(isHitlEvent('interrupted', undefined, 'breakpoint')).toBe(false)
    expect(latestHitlPrompt([stopped])).toBeNull()
  })

  it('does not hide an earlier real question', () => {
    // Ask a human at alpha, continue, then stop at a breakpoint on beta: the
    // question is still the last thing anyone was asked.
    const asked = envelope({
      event_type: 'interrupted',
      phase_name: 'alpha',
      thread_id: 'run-1',
      reason: 'awaiting_human',
      question: 'Which draft?',
    })
    const stopped = envelope({
      event_type: 'interrupted',
      phase_name: 'beta',
      thread_id: 'run-1',
      reason: 'breakpoint',
    })

    expect(latestHitlPrompt([asked, stopped])?.question).toBe('Which draft?')
  })
})

describe('a run waiting on a person', () => {
  it('is still a prompt when it says so', () => {
    const asked = envelope({
      event_type: 'interrupted',
      phase_name: 'review',
      thread_id: 'run-1',
      reason: 'awaiting_human',
      question: 'Approve?',
    })

    expect(isHitlEvent('interrupted', undefined, 'awaiting_human')).toBe(true)
    expect(latestHitlPrompt([asked])?.question).toBe('Approve?')
  })

  it('is still a prompt when its question came out empty', () => {
    // The case that makes "no question" useless as a test: a real ask whose
    // question failed to parse still needs an answer.
    const asked = envelope({
      event_type: 'interrupted',
      phase_name: 'review',
      thread_id: 'run-1',
      reason: 'awaiting_human',
    })

    expect(latestHitlPrompt([asked])?.question).toBe('Run paused for human input.')
  })

  it('is still a prompt when the stop does not say why', () => {
    // An old trace on disk, replayed. Treating an unlabelled stop as a question
    // shows a box nobody has to use; treating it as a breakpoint would hide a
    // question somebody does.
    const asked = envelope({ event_type: 'interrupted', phase_name: 'review', thread_id: 'run-1' })

    expect(latestHitlPrompt([asked])).not.toBeNull()
  })
})
