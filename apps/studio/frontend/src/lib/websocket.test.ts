import { beforeEach, describe, expect, it, vi } from 'vitest'
import { configureApiBaseURL, configureApiToken } from '../api/client'
import { nextBackoffMs, runEventsWsUrl } from './websocket'

describe('runEventsWsUrl', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
    configureApiBaseURL('/api')
    configureApiToken(null)
  })

  it('addresses the run stream by the API skill id, not the workspace selection', () => {
    // A locally-opened skill is selected as `local-workspace:<id>:<absolute path>`.
    // The backend's URL segment validator rejects that shape outright, and the
    // rejection lands AFTER the socket is accepted — so the stream dies with a
    // 1006 and the Trace region waits forever for events that cannot arrive.
    const url = runEventsWsUrl(
      'local-workspace:exp-b-round7:D:\\coding\\skills\\exp-b-round7',
      '2026-08-09T03-40-42_80960a2c',
    )

    expect(url).toBe('ws://localhost/ws/skills/exp-b-round7/runs/2026-08-09T03-40-42_80960a2c')
  })

  it('leaves a plain skill id alone', () => {
    expect(runEventsWsUrl('exp-b-round7', 'run-1')).toBe(
      'ws://localhost/ws/skills/exp-b-round7/runs/run-1',
    )
  })

  it('carries the replay cursor', () => {
    expect(runEventsWsUrl('exp-b-round7', 'run-1', '12')).toBe(
      'ws://localhost/ws/skills/exp-b-round7/runs/run-1?cursor=12',
    )
  })
})

describe('nextBackoffMs', () => {
  it('doubles per attempt and stops at 30s', () => {
    expect(nextBackoffMs(1)).toBe(1000)
    expect(nextBackoffMs(2)).toBe(2000)
    expect(nextBackoffMs(99)).toBe(30_000)
  })
})
