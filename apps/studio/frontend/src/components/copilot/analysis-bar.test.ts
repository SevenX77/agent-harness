import { describe, expect, it, vi } from 'vitest'
import { autoWriteGoldenIfAbsent } from './analysis-bar'
import type { GoldenBaseline } from '@/api/types'

const baseline = (id: string): GoldenBaseline =>
  ({ golden_id: id, golden_run_id: 'run-1', node_results: [] }) as unknown as GoldenBaseline

describe('autoWriteGoldenIfAbsent (F7)', () => {
  it('writes a golden baseline when the skill has none', async () => {
    const list = vi.fn().mockResolvedValue([])
    const save = vi.fn().mockResolvedValue(baseline('g1'))

    const result = await autoWriteGoldenIfAbsent('skill-1', 'run-9', { list, save })

    expect(result).toEqual({ written: true })
    expect(save).toHaveBeenCalledWith('skill-1', 'run-9', false)
  })

  it('leaves existing golden untouched (有的不动)', async () => {
    const list = vi.fn().mockResolvedValue([baseline('g1')])
    const save = vi.fn()

    const result = await autoWriteGoldenIfAbsent('skill-1', 'run-9', { list, save })

    expect(result).toEqual({ written: false })
    expect(save).not.toHaveBeenCalled()
  })
})
