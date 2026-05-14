import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api, configureApiBaseURL, configureApiToken, wsUrl } from './client'

function captureHeadersAdapter(assertConfig: (config: InternalAxiosRequestConfig) => void): AxiosAdapter {
  return async (config): Promise<AxiosResponse> => {
    assertConfig(config)
    return {
      data: {},
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }
  }
}

describe('api client auth token', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    configureApiBaseURL('http://localhost:8787/api')
    configureApiToken(null)
  })

  it('test_no_token_no_auth_header', async () => {
    configureApiToken(null)

    await api.get('/probe', {
      adapter: captureHeadersAdapter((config) => {
        expect(config.headers.get('Authorization')).toBeUndefined()
      }),
    })
  })

  it('test_with_token_auth_header_set', async () => {
    configureApiToken('abc')

    await api.get('/probe', {
      adapter: captureHeadersAdapter((config) => {
        expect(config.headers.get('Authorization')).toBe('Bearer abc')
      }),
    })
  })

  it('test_ws_url_without_token_has_no_query', () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
    configureApiBaseURL('/api')

    expect(wsUrl('/ws/events')).toBe('ws://localhost/ws/events')
  })

  it('test_ws_url_appends_configured_token', () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
    configureApiBaseURL('/api')
    configureApiToken('xyz')

    expect(wsUrl('/ws/events')).toBe('ws://localhost/ws/events?token=xyz')
  })

  it('test_ws_url_appends_token_after_existing_query', () => {
    vi.stubGlobal('window', { location: { origin: 'http://localhost' } })
    configureApiBaseURL('/api')
    configureApiToken('a b')

    expect(wsUrl('/ws/events?cursor=1')).toBe('ws://localhost/ws/events?cursor=1&token=a%20b')
  })
})
