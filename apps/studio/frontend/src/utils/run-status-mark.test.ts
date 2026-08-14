import { describe, expect, it } from 'vitest'
import { runStatusMark } from './run-status-mark'

// D7 对照表 (the strip badge + run list icon): one shared vocabulary, locked
// as a table so a verdict cannot silently lose or change its mark.
describe('runStatusMark × verdict table (decision 2026-08-13 D7)', () => {
  it.each([
    ['running', 'Run in progress'],
    ['success', 'Run succeeded'],
    ['failed', 'Run failed'],
    ['paused', 'Run paused'],
    ['cancelled', 'Run cancelled'],
  ] as const)('%s → "%s"', (status, label) => {
    expect(runStatusMark(status)?.label).toBe(label)
  })

  it('renders nothing for an unknown status rather than guessing', () => {
    expect(runStatusMark(null)).toBeNull()
    expect(runStatusMark(undefined)).toBeNull()
  })
})
