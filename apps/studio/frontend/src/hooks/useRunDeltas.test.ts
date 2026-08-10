import { describe, expect, it } from 'vitest'

import { __testing, type RunDeltas } from './useRunDeltas'

const { applied } = __testing

function frame(overrides: Partial<Parameters<typeof applied>[1]> = {}) {
  return {
    schema_version: 'studio.delta.v1',
    step_id: 's1',
    channel: 'text' as const,
    text: '',
    restarts_step: false,
    ...overrides,
  }
}

describe('folding live output into the step it belongs to', () => {
  it('appends the pieces of one step in arrival order', () => {
    const after = [frame({ text: 'Hel' }), frame({ text: 'lo, ' }), frame({ text: 'world' })]
      .reduce<RunDeltas>(applied, {})

    expect(after.s1.text).toBe('Hello, world')
  })

  // An agent turn runs several calls at once, so a piece that landed on the
  // wrong step would show one call's answer inside another call's row.
  it('keeps two steps' + "' output apart", () => {
    const after = [
      frame({ step_id: 's1', text: 'first' }),
      frame({ step_id: 's2', text: 'second' }),
      frame({ step_id: 's1', text: ' again' }),
    ].reduce<RunDeltas>(applied, {})

    expect(after.s1.text).toBe('first again')
    expect(after.s2.text).toBe('second')
  })

  // Thinking is the model working out its reply, not the reply. Concatenating
  // the two would show the reader an answer the model never gave.
  it('keeps thinking out of the answer', () => {
    const after = [
      frame({ channel: 'thinking', text: 'let me think' }),
      frame({ channel: 'text', text: '42' }),
    ].reduce<RunDeltas>(applied, {})

    expect(after.s1.thinking).toBe('let me think')
    expect(after.s1.text).toBe('42')
  })

  // The gateway went back for a different answer: what is on screen belongs to
  // an attempt nobody received, and appending past it produces a reply stitched
  // from two — a wrong answer, not just a wrong display.
  it('throws away the text an abandoned attempt had already shown', () => {
    const after = [
      frame({ text: 'half an ans' }),
      frame({ text: '', restarts_step: true }),
      frame({ text: 'the whole answer' }),
    ].reduce<RunDeltas>(applied, {})

    expect(after.s1.text).toBe('the whole answer')
  })

  it('clears the thinking of an abandoned attempt too', () => {
    const after = [
      frame({ channel: 'thinking', text: 'wrong track' }),
      frame({ text: '', restarts_step: true }),
    ].reduce<RunDeltas>(applied, {})

    expect(after.s1).toEqual({ text: '', thinking: '' })
  })

  it('treats a channel it does not know as answer text rather than dropping it', () => {
    const after = applied({}, frame({ channel: 'something-new', text: 'x' }))

    expect(after.s1.text).toBe('x')
  })

  it('never mutates the map it was handed', () => {
    const before: RunDeltas = { s1: { text: 'a', thinking: '' } }

    const after = applied(before, frame({ text: 'b' }))

    expect(before.s1.text).toBe('a')
    expect(after.s1.text).toBe('ab')
  })
})
