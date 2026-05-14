import { afterEach, describe, expect, it } from 'vitest'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import { api, configureApiToken } from './client'

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
})
