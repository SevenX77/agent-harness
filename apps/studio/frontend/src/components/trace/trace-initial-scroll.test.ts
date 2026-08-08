import { describe, expect, it } from 'vitest'
import { initialTracePosition } from './trace-initial-scroll'

/**
 * Where a trace list should be parked when the reader first sees it. This is a
 * property of the MODE, not of whatever the scroll primitive happens to do on
 * mount: a live stream reads newest-first (stick to the bottom, follow), a
 * finished run replays from its first event (top). Measured defect that drove
 * this: opening a historical run landed at scrollTop 9507/10204 — the reader
 * met the END of a run they had not started reading.
 */
describe('initialTracePosition', () => {
  it('parks a finished run at its first event', () => {
    expect(initialTracePosition({ followStream: false })).toBe('start')
  })

  it('leaves a live stream following the newest event', () => {
    expect(initialTracePosition({ followStream: true })).toBe('follow-end')
  })
})
