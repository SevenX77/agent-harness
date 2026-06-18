import { describe, expect, it, vi } from 'vitest'
import { autoWriteGoldenIfAbsent } from './analysis-bar'
import type { GoldenBaseline } from '@/api/types'

const baseline = (id: string): GoldenBaseline =>
  ({
    id,
    source_run_id: 'run-1',
    source_run_results_ref: 'skill-1/runs/run-1/result.json',
    baseline_ref: `.workspace/golden/${id}/baseline.json`,
    linked_input_id: 'run-1',
    created_at: '2026-06-16T00:00:00Z',
    locked: false,
    content_path: `/workspace/.workspace/golden/${id}/baseline.json`,
  }) as GoldenBaseline

describe('autoWriteGoldenIfAbsent (F7)', () => {
  it('writes a golden baseline when the skill has none', async () => {
    const list = vi.fn().mockResolvedValue([])
    const save = vi.fn().mockResolvedValue(baseline('g1'))

    const result = await autoWriteGoldenIfAbsent('skill-1', 'run-9', { list, save })

    expect(result).toEqual({ written: true })
    expect(save).toHaveBeenCalledWith('skill-1', 'run-9', false)
  })

  it('writes an absent golden baseline to the imported workspace root', async () => {
    const list = vi.fn().mockResolvedValue([])
    const save = vi.fn().mockResolvedValue(baseline('g1'))

    const result = await autoWriteGoldenIfAbsent('skill-1', 'run-9', {
      list,
      save,
      workspaceRoot: '/abs/path',
    })

    expect(result).toEqual({ written: true })
    expect(save).toHaveBeenCalledWith('skill-1', 'run-9', false, '/abs/path')
  })

  it('leaves existing golden untouched (有的不动)', async () => {
    const list = vi.fn().mockResolvedValue([baseline('g1')])
    const save = vi.fn()

    const result = await autoWriteGoldenIfAbsent('skill-1', 'run-9', { list, save })

    expect(result).toEqual({ written: false })
    expect(save).not.toHaveBeenCalled()
  })

  it('prepares Copilot Judge context through the adapter after creating a missing golden baseline', async () => {
    const list = vi.fn().mockResolvedValue([])
    const save = vi.fn().mockResolvedValue(baseline('run-9'))
    const judge = vi.fn().mockResolvedValue({
      compare_result_ref: 'skill-1/golden/run-9/compare/run-9/compare_result.json',
      judge_context_ref: 'skill-1/runs/run-9/copilot_judge/run-9/judge_context.json',
      baseline_ref: '.workspace/golden/run-9/baseline.json',
      diff_summary: {
        baseline_id: 'run-9',
        run_results_ref: 'skill-1/runs/run-9/result.json',
        total_score: 100,
        node_group_count: 1,
        failed_node_count: 0,
      },
    })

    const result = await autoWriteGoldenIfAbsent('skill-1', 'run-9', {
      list,
      save,
      judge,
      runResultsRef: 'skill-1/runs/run-9/result.json',
    })

    expect(judge).toHaveBeenCalledWith('skill-1', {
      runResultsRef: 'skill-1/runs/run-9/result.json',
      baselineRef: '.workspace/golden/run-9/baseline.json',
    })
    expect(result).toEqual({
      written: true,
      judge: {
        compare_result_ref: 'skill-1/golden/run-9/compare/run-9/compare_result.json',
        judge_context_ref: 'skill-1/runs/run-9/copilot_judge/run-9/judge_context.json',
        baseline_ref: '.workspace/golden/run-9/baseline.json',
        diff_summary: {
          baseline_id: 'run-9',
          run_results_ref: 'skill-1/runs/run-9/result.json',
          total_score: 100,
          node_group_count: 1,
          failed_node_count: 0,
        },
      },
    })
  })
})
