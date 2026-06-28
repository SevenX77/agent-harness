import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CompareResult } from '@/api/types'
import { DiffView } from './DiffView'

const result: CompareResult = {
  baseline_id: 'golden-1',
  source_run_id: 'run-golden',
  source_run_results_ref: 'demo/runs/run-golden/result.json',
  baseline_ref: 'demo/golden/golden-1/baseline.json',
  run_results_ref: 'demo/runs/run-1/result.json',
  total_score: 75,
  node_groups: [
    {
      node_id: 'draft',
      phase_id: 'draft',
      status: 'fail',
      score: 0.5,
      stale_fields: [],
      schema_status: 'valid',
      baseline_ref: 'demo/golden/golden-1/baseline.json',
      run_results_ref: 'demo/runs/run-1/result.json',
      field_differences: [
        {
          field_path: 'nodes.draft.answer',
          type: 'text',
          current_value: 'hello studio',
          golden_value: 'hello world',
          score: 0.5,
          changed: true,
        },
      ],
    },
    {
      node_id: 'review',
      phase_id: 'review',
      status: 'pass',
      score: 1,
      field_differences: [],
      stale_fields: [],
      schema_status: 'valid',
      baseline_ref: 'demo/golden/golden-1/baseline.json',
      run_results_ref: 'demo/runs/run-1/result.json',
    },
  ],
}

function render(): string {
  return renderToStaticMarkup(
    <DiffView
      result={result}
      skillId="demo"
      runId="run-1"
      loading={false}
      error={null}
      canCompare
      canPromote
      onCompare={() => undefined}
      onPromote={() => undefined}
    />,
  )
}

describe('DiffView — per-node golden grouping (D7 / golden-per-agent-node)', () => {
  it('groups differences by node with per-node verdict and score', () => {
    const html = render()

    // Both nodes appear as group headers (not just flat field paths).
    expect(html).toContain('draft')
    expect(html).toContain('review')
    // Per-node verdicts surfaced (pass node shown even with no differences).
    expect(html.toLowerCase()).toContain('pass')
    expect(html.toLowerCase()).toContain('fail')
  })

  it('surfaces the compared baseline and source run in the main header', () => {
    const html = render()

    expect(html).toContain('Baseline golden-1')
    expect(html).toContain('Source run run-golden')
  })
})
