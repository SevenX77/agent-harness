import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { DiffField } from './DiffField'
import { DiffView } from './DiffView'

vi.mock('../export/ExportButton', () => ({
  ExportButton: () => <button data-slot="button">Export</button>,
}))

const noop = () => undefined
const hardcodedPaletteClass = /\b(?:bg|text|border)-(?:slate|sky|amber|red|zinc)-/

describe('WS-6 DiffView UI contract', () => {
  it('renders the empty state with semantic design tokens instead of one-off palette classes', () => {
    const html = renderToStaticMarkup(
      <DiffView
        result={null}
        skillId="text-segmentation"
        runId="run-1"
        loading={false}
        error={null}
        canCompare
        canPromote={false}
        onCompare={noop}
        onPromote={noop}
      />,
    )

    expect(html).toContain('Golden Diff')
    expect(html).not.toMatch(hardcodedPaletteClass)
    expect(html).toContain('data-slot="button"')
  })

  it('renders the diff view with data and ensures no hardcoded palette classes exist', () => {
    const mockResult = {
      total_score: 85.0,
      golden_run_id: 'golden-1',
      differences: [
        {
          field_path: 'output.prepared',
          type: 'bool' as const,
          current_value: true,
          golden_value: false,
          score: 0.0,
          changed: true,
        },
        {
          field_path: 'output.message',
          type: 'text' as const,
          current_value: 'hello world',
          golden_value: 'hello world',
          score: 1.0,
          changed: false,
        },
        {
          field_path: 'output.optional',
          type: 'null' as const,
          current_value: null,
          golden_value: null,
          score: 1.0,
          changed: false,
        },
      ],
    }

    const html = renderToStaticMarkup(
      <DiffView
        result={mockResult}
        skillId="text-segmentation"
        runId="run-1"
        loading={false}
        error={null}
        canCompare
        canPromote={false}
        onCompare={noop}
        onPromote={noop}
      />,
    )

    expect(html).toContain('Golden Diff')
    expect(html).toContain('output.prepared')
    expect(html).not.toMatch(hardcodedPaletteClass)
  })

  it('renders data diffs with a narrow-first responsive layout', () => {
    const html = renderToStaticMarkup(
      <DiffView
        result={{
          total_score: 85.0,
          golden_run_id: 'golden-1',
          differences: [
            {
              field_path: 'output.prepared',
              type: 'bool',
              current_value: true,
              golden_value: false,
              score: 0.0,
              changed: true,
            },
          ],
        }}
        skillId="text-segmentation"
        runId="run-1"
        loading={false}
        error={null}
        canCompare
        canPromote={false}
        onCompare={noop}
        onPromote={noop}
      />,
    )

    expect(html).toContain('grid-cols-1')
    expect(html).toContain('md:grid-cols-[14rem_1fr]')
  })

  it('renders fallback value previews without hardcoded palette classes', () => {
    const html = renderToStaticMarkup(
      <DiffField
        field={{
          field_path: 'output.optional',
          type: 'null',
          current_value: null,
          golden_value: null,
          score: 1.0,
          changed: false,
        }}
      />,
    )

    expect(html).toContain('output.optional')
    expect(html).not.toMatch(hardcodedPaletteClass)
  })
})
