import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { RunHistoryRow } from './RunHistoryRow'
import type { RunMetadata } from '../../api/types'

describe('RunHistoryRow WS-3 status mapping contracts (Regression Lock)', () => {
  const baseRun: RunMetadata = {
    run_id: 'run-123456789012345678',
    status: 'success',
    started_at: '2026-05-21T12:00:00.000Z',
    metrics: {
      input_tokens: 10,
      output_tokens: 20,
      total_tokens: 30,
      cost_estimate: null,
    },
    input_summary: null,
  }

  it('renders success status with default badge', () => {
    const html = renderToStaticMarkup(
      <table>
        <tbody>
          <RunHistoryRow
            run={{ ...baseRun, status: 'success' }}
            selected={false}
            filenameBase="run"
            onSelect={vi.fn()}
            onReplay={vi.fn()}
            onCompare={vi.fn()}
            onExport={() => ''}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>
    )
    expect(html).toContain('data-variant="default"')
    expect(html).toContain('success')
  })

  it('renders failed status with destructive badge', () => {
    const html = renderToStaticMarkup(
      <table>
        <tbody>
          <RunHistoryRow
            run={{ ...baseRun, status: 'failed' }}
            selected={false}
            filenameBase="run"
            onSelect={vi.fn()}
            onReplay={vi.fn()}
            onCompare={vi.fn()}
            onExport={() => ''}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>
    )
    expect(html).toContain('data-variant="destructive"')
    expect(html).toContain('failed')
  })

  it('renders running status with outline badge', () => {
    const html = renderToStaticMarkup(
      <table>
        <tbody>
          <RunHistoryRow
            run={{ ...baseRun, status: 'running' }}
            selected={false}
            filenameBase="run"
            onSelect={vi.fn()}
            onReplay={vi.fn()}
            onCompare={vi.fn()}
            onExport={() => ''}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>
    )
    expect(html).toContain('data-variant="outline"')
    expect(html).toContain('running')
  })
})
