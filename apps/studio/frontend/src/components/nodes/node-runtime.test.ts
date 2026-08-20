import { describe, expect, it } from 'vitest'
import { formatRunDuration } from './node-runtime'

describe('formatRunDuration', () => {
  it('reads a sub-minute segment in whole seconds', () => {
    expect(formatRunDuration(0)).toBe('0s')
    expect(formatRunDuration(4_900)).toBe('4s')
    expect(formatRunDuration(59_999)).toBe('59s')
  })

  it('splits a longer segment into minutes and zero-padded seconds', () => {
    expect(formatRunDuration(60_000)).toBe('1m 00s')
    expect(formatRunDuration(185_000)).toBe('3m 05s')
    expect(formatRunDuration(3_599_000)).toBe('59m 59s')
  })

  it('drops to hours and minutes once seconds stop being the story', () => {
    expect(formatRunDuration(3_600_000)).toBe('1h 00m')
    expect(formatRunDuration(7_380_000)).toBe('2h 03m')
  })

  it('never renders a negative clock when the two machines disagree', () => {
    // The segment's start comes from the engine's timestamp and the live end
    // from this machine's clock; a skew must read 0s, not "-3s".
    expect(formatRunDuration(-3_000)).toBe('0s')
  })
})
