import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosAdapter, AxiosResponse } from 'axios'
import { api, compareRunToGolden } from './client'

function response(config: AxiosResponse['config'], data: unknown): AxiosResponse {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  }
}

describe('WS-6 golden diff API contract', () => {
  afterEach(() => {
    api.defaults.adapter = undefined
  })

  it('compares a run through the backend diff endpoint', async () => {
    const adapter: AxiosAdapter = async (config) => {
      expect(config.method).toBe('get')
      expect(config.url).toBe('/skills/text-segmentation/runs/current-run/diff')
      expect(config.params).toEqual({ against: 'golden-node-setup' })
      return response(config, {
        golden_run_id: 'golden-node-setup',
        total_score: 100,
        differences: [],
      })
    }
    api.defaults.adapter = adapter

    const result = await compareRunToGolden(
      'text-segmentation',
      'current-run',
      'golden-node-setup',
    )

    expect(result.golden_run_id).toBe('golden-node-setup')
  })
})
