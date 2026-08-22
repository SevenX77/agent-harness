/**
 * "The run stopped" is not "the run is asking you something".
 *
 * Walking the finished breakpoint feature through the real window: set two
 * breakpoints, run, stop before the first — no prompt, correct. Press Resume,
 * stop at the second — and "HUMAN INPUT REQUIRED / Run paused for human input."
 * appeared, with nothing to answer.
 *
 * The stop event was labelled correctly (`reason: "breakpoint"`, in the trace).
 * What matched was the AUDIT record the resume writes into the same stream:
 * `{event_type: "resume_applied", status: "paused", ...}` — and the prompt
 * detector ended in `status === 'paused'`. That field is the RUN's state, not
 * a description of the event, so any record carrying it was read as a question.
 *
 * A stopped run and an asking run are different things, and only one of them
 * needs an answer. Nothing but an explicit ask makes an event a prompt.
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

const resumeApplied = (status: string) =>
  envelope({
    schema_version: 'studio.resume.audit.v1',
    event_type: 'resume_applied',
    run_id: 'run-1',
    status,
    checkpoint_id: 'ckpt-1',
    context_override_keys: [],
  })

describe('the record a resume leaves behind', () => {
  it('is not a question, however the resumed run turned out', () => {
    expect(latestHitlPrompt([resumeApplied('paused')])).toBeNull()
    expect(latestHitlPrompt([resumeApplied('success')])).toBeNull()
    expect(latestHitlPrompt([resumeApplied('failed')])).toBeNull()
  })

  it('does not bury the question that made someone press Resume', () => {
    const asked = envelope({
      event_type: 'interrupted',
      phase_name: 'review',
      thread_id: 'run-1',
      reason: 'awaiting_human',
      question: 'Approve?',
    })

    expect(latestHitlPrompt([asked, resumeApplied('paused')])?.question).toBe('Approve?')
  })
})

describe('a run that merely stopped', () => {
  it('is not a prompt because its status says paused', () => {
    // `paused` says nothing is executing. Being asked something is one reason
    // for that and pressing Stop-at-a-breakpoint is another, so the word alone
    // cannot decide which — the event has to say it asked.
    expect(isHitlEvent('run_status', 'paused', undefined)).toBe(false)
  })

  it('is still a prompt when the status says a human is being waited on', () => {
    expect(isHitlEvent('run_status', 'waiting_for_human', undefined)).toBe(true)
  })

  it('is still a prompt when the event type itself says it asked', () => {
    expect(isHitlEvent('interrupted', undefined, 'awaiting_human')).toBe(true)
    expect(isHitlEvent('human_input_required', undefined, undefined)).toBe(true)
    expect(isHitlEvent('paused', undefined, undefined)).toBe(true)
  })
})
