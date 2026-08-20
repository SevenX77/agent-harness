import { describe, expect, it } from 'vitest'
import { formatRunDuration, nodeActivityText } from './node-runtime'

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

describe('nodeActivityText', () => {
  it('says which call is in flight while the node runs', () => {
    expect(nodeActivityText({ llmCalls: 3, toolCalls: 0 }, true)?.short).toBe('Call 3')
  })

  it('turns the same number into a tally once the node is done', () => {
    expect(nodeActivityText({ llmCalls: 3, toolCalls: 0 }, false)?.short).toBe('3 calls')
  })

  it('keeps the tool count for the tooltip, not the card line', () => {
    const text = nodeActivityText({ llmCalls: 2, toolCalls: 5 }, false)
    expect(text?.short).toBe('2 calls')
    expect(text?.full).toBe('2 LLM calls · 5 tool calls')
  })

  it('says nothing at all before the first call', () => {
    // Not "0 calls": a node that has not called anything is silent on the
    // count, and a rendered zero reads as a finding.
    expect(nodeActivityText({ llmCalls: 0, toolCalls: 0 }, true)).toBeNull()
  })

  it('writes one call singular in the tooltip', () => {
    expect(nodeActivityText({ llmCalls: 1, toolCalls: 1 }, false)?.full).toBe('1 LLM call · 1 tool call')
  })
})
