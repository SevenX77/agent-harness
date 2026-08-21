import { describe, expect, it, vi } from 'vitest'
import { seedGoldenForRun, seedOutcome } from './analysis-bar'
import type { GoldenSeedPlan, GoldenSeedTarget } from '@/api/types'

const plan = (seeded: GoldenSeedTarget[], overrides: Partial<GoldenSeedPlan> = {}): GoldenSeedPlan => ({
  baseline_id: 'run-1',
  baseline_ref: '.workspace/golden/run-1/baseline.json',
  baseline_locked: false,
  seeded,
  files: [],
  ...overrides,
})

const judgeContext = {
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
}

describe('seedGoldenForRun (F7)', () => {
  it('asks the backend to seed this run and hands back its verdict', async () => {
    const seed = vi.fn().mockResolvedValue(plan([{ node_id: 'review', reason: 'absent' }]))

    const result = await seedGoldenForRun('skill-1', 'run-9', { seed })

    expect(seed).toHaveBeenCalledWith('skill-1', 'run-9', undefined)
    expect(result.plan.seeded).toEqual([{ node_id: 'review', reason: 'absent' }])
  })

  it('seeds into the imported workspace root when the skill has one', async () => {
    const seed = vi.fn().mockResolvedValue(plan([]))

    await seedGoldenForRun('skill-1', 'run-9', { seed, workspaceRoot: '/abs/path' })

    expect(seed).toHaveBeenCalledWith('skill-1', 'run-9', '/abs/path')
  })

  it('prepares Copilot Judge context against the baseline the seed landed in', async () => {
    const seed = vi.fn().mockResolvedValue(
      plan([{ node_id: 'review', reason: 'expected_output_invalid' }], {
        baseline_ref: '.workspace/golden/run-9/baseline.json',
      }),
    )
    const judge = vi.fn().mockResolvedValue(judgeContext)

    const result = await seedGoldenForRun('skill-1', 'run-9', {
      seed,
      judge,
      runResultsRef: 'skill-1/runs/run-9/result.json',
    })

    expect(judge).toHaveBeenCalledWith('skill-1', {
      runResultsRef: 'skill-1/runs/run-9/result.json',
      baselineRef: '.workspace/golden/run-9/baseline.json',
    })
    expect(result.judge).toEqual(judgeContext)
  })

  it('skips judge context when there is no baseline to compare against', async () => {
    const seed = vi.fn().mockResolvedValue(plan([], { baseline_ref: null }))
    const judge = vi.fn()

    const result = await seedGoldenForRun('skill-1', 'run-9', {
      seed,
      judge,
      runResultsRef: 'skill-1/runs/run-9/result.json',
    })

    expect(judge).not.toHaveBeenCalled()
    expect(result.judge).toBeUndefined()
  })

  it('rejects Copilot Judge context for a different run before it reaches chat', async () => {
    const seed = vi.fn().mockResolvedValue(plan([]))
    const judge = vi.fn().mockResolvedValue({
      ...judgeContext,
      diff_summary: { ...judgeContext.diff_summary, run_results_ref: 'skill-1/runs/other-run/result.json' },
    })

    await expect(
      seedGoldenForRun('skill-1', 'run-9', {
        seed,
        judge,
        runResultsRef: 'skill-1/runs/run-9/result.json',
      }),
    ).rejects.toThrow('Copilot Judge run_results_ref mismatch')
  })
})

// A descriptor, not a sentence: the bar words it in the reader's language,
// so what this function owes is WHICH outcome happened and which nodes it
// touched — never the wording (设计源 i18n.md §3 Strategy C).
describe('seedOutcome', () => {
  it('names the nodes it filled', () => {
    expect(
      seedOutcome(
        plan([
          { node_id: 'setup', reason: 'absent' },
          { node_id: 'review', reason: 'case_file_missing' },
        ]),
      ),
    ).toEqual({ kind: 'seeded', nodeIds: ['setup', 'review'] })
  })

  it('says nothing changed when every node already had one', () => {
    expect(seedOutcome(plan([]))).toEqual({ kind: 'nothingMissing' })
  })

  it('says a locked golden was left alone', () => {
    expect(seedOutcome(plan([], { baseline_locked: true }))).toEqual({ kind: 'locked' })
  })
})
