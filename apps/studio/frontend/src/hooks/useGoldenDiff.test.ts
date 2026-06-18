import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useGoldenDiff } from './useGoldenDiff'
import type { GoldenBaseline } from '../api/types'

const clientMocks = vi.hoisted(() => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
  saveGoldenBaseline: vi.fn(),
}))

vi.mock('../api/client', () => clientMocks)

function baseline(id: string): GoldenBaseline {
  return {
    id,
    source_run_id: id,
    source_run_results_ref: `skill-a/runs/${id}/result.json`,
    baseline_ref: `.workspace/golden/${id}/baseline.json`,
    linked_input_id: id,
    created_at: '2026-06-16T00:00:00Z',
    locked: false,
    content_path: `/workspace/.workspace/golden/${id}/baseline.json`,
  } as GoldenBaseline
}

describe('useGoldenDiff promote', () => {
  beforeEach(() => {
    clientMocks.api.get.mockReset()
    clientMocks.api.post.mockReset()
    clientMocks.saveGoldenBaseline.mockReset()
    clientMocks.saveGoldenBaseline.mockResolvedValue(baseline('run-1'))
  })

  it('executes promotion through saveGoldenBaseline with the imported workspace root', async () => {
    let hook: ReturnType<typeof useGoldenDiff> | null = null

    function Probe() {
      hook = useGoldenDiff('skill-a', 'run-1', '/abs/path')
      return null
    }

    renderToStaticMarkup(createElement(Probe))

    expect(hook).not.toBeNull()
    await expect(hook!.promote()).resolves.toEqual(baseline('run-1'))

    expect(clientMocks.saveGoldenBaseline).toHaveBeenCalledWith(
      'skill-a',
      'run-1',
      false,
      '/abs/path',
    )
    expect(clientMocks.api.post).not.toHaveBeenCalled()
  })
})
