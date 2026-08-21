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
    ['abandoned', 'Run abandoned — the app closed while it was going'],
  ] as const)('%s → "%s"', (status, label) => {
    expect(runStatusMark(status)?.label).toBe(label)
  })

  it('gives an abandoned run its own mark rather than leaving it spinning', () => {
    // The run list used to show `running` forever for a run whose worker died
    // with the app (ledger C1). It now arrives as `abandoned`, and a status
    // this table does not know renders nothing at all — so a missing entry
    // here would trade a wrong spinner for no badge.
    expect(runStatusMark('abandoned')).not.toBeNull()
    expect(runStatusMark('abandoned')?.icon).not.toBe(runStatusMark('running')?.icon)
  })

  it('renders nothing for an unknown status rather than guessing', () => {
    expect(runStatusMark(null)).toBeNull()
    expect(runStatusMark(undefined)).toBeNull()
  })
})
