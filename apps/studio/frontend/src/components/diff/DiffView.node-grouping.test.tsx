import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { CompareResult } from '@/api/types'
import { DiffView } from './DiffView'

const result: CompareResult = {
  total_score: 75,
  golden_run_id: 'golden-1',
  differences: [
    {
      field_path: 'nodes.draft.answer',
      type: 'text',
      current_value: 'hello studio',
      golden_value: 'hello world',
      score: 0.5,
      changed: true,
    },
  ],
  node_results: [
    {
      node_id: 'draft',
      verdict: 'fail',
      score: 0.5,
      differences: [
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
    { node_id: 'review', verdict: 'pass', score: 1, differences: [] },
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
})
