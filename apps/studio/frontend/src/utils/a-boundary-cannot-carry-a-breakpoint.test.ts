/**
 * A boundary is not a phase, so it cannot be the thing a breakpoint is set on.
 *
 * Walking a breakpoint through the real window, the Output endpoint read
 * `Breakpoint` along with the phase that produced it — inherited by the
 * worst-status fold. What is actually true of the endpoint is the general fact
 * underneath: nothing arrived, and nothing is executing.
 *
 * Design: run-execution/mvp1-alignment.md RUN_EXECUTION-16.
 */

import { describe, expect, it } from 'vitest'
import { outputBoundaryStatus } from './edge-status-projection'

describe('the output boundary', () => {
  it('says paused when the run stopped at a breakpoint on its producer', () => {
    expect(outputBoundaryStatus({ beta: 'breakpoint' }, ['beta'], 'paused')).toBe('paused')
  })

  it('still says failed when a producer failed', () => {
    expect(outputBoundaryStatus({ beta: 'error' }, ['beta'], 'failed')).toBe('error')
  })

  it('still says success when every producer finished', () => {
    expect(outputBoundaryStatus({ beta: 'success' }, ['beta'], 'success')).toBe('success')
  })
})
