/**
 * The breakpoint client writes; it does not read.
 *
 * Breakpoints live in `runtime_config`, which the canvas already holds and
 * already revalidates on the precise `runtime_config_changed` event. A read
 * here would be a second replica of one truth, free to disagree with the first
 * (SSOT 读取原则). Every write answers with the whole canonical list, so the
 * caller never has to compute what the set became.
 */

import type { AxiosResponse } from 'axios'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  api,
  clearBreakpoint,
  resetClientReadCachesForTests,
  setBreakpoint,
} from './client'

const originalAdapter = api.defaults.adapter

function respondWith(bodyByRoute: Record<string, unknown>, seen: string[]) {
  api.defaults.adapter = async (config): Promise<AxiosResponse> => {
    seen.push(`${config.method} ${config.url}`)
    await Promise.resolve()
    return {
      data: bodyByRoute[`${config.method} ${config.url}`] ?? {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }
  }
}

beforeEach(() => {
  resetClientReadCachesForTests()
})

afterEach(() => {
  api.defaults.adapter = originalAdapter
  resetClientReadCachesForTests()
})

describe('breakpoints client', () => {
  it('answers a set with the whole list, and asks nothing else', async () => {
    const seen: string[] = []
    respondWith({ 'put /skills/demo/nodes/review/breakpoint': { node_ids: ['review'] } }, seen)

    const written = await setBreakpoint('demo', 'review')

    expect(written.node_ids).toEqual(['review'])
    // No read-back: the write already said what the set became.
    expect(seen).toEqual(['put /skills/demo/nodes/review/breakpoint'])
  })

  it('clears through the same door', async () => {
    const seen: string[] = []
    respondWith({ 'delete /skills/demo/nodes/review/breakpoint': { node_ids: [] } }, seen)

    const written = await clearBreakpoint('demo', 'review')

    expect(written.node_ids).toEqual([])
    expect(seen).toEqual(['delete /skills/demo/nodes/review/breakpoint'])
  })

  it('escapes a node id that would otherwise change the path', async () => {
    const seen: string[] = []
    respondWith({}, seen)

    await setBreakpoint('demo', 'a/b')

    expect(seen).toEqual(['put /skills/demo/nodes/a%2Fb/breakpoint'])
  })
})
