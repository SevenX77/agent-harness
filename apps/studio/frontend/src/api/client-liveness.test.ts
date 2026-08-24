// @vitest-environment jsdom
//
// dead-sidecar-says-so: a dedicated jsdom file (rather than adding to the
// large node-environment client.test.ts) because this behavior specifically
// needs a real `window` to dispatch/observe the event on.
import { AxiosError } from 'axios'
import type { AxiosResponse } from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, BACKEND_UNAVAILABLE_HTTP_EVENT, compileSkill, configureApiBaseURL } from './client'

const runtimeMocks = vi.hoisted(() => ({
  isTauriRuntime: vi.fn(() => false),
}))

vi.mock('../config/runtime', () => runtimeMocks)

afterEach(() => {
  api.defaults.adapter = undefined
  configureApiBaseURL('http://localhost:8787/api')
})

describe('BACKEND_UNAVAILABLE_HTTP_EVENT — RuntimeGate liveness signal #2', () => {
  it('dispatches on window when a call gets no HTTP response at all', async () => {
    const handler = vi.fn()
    window.addEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handler)
    try {
      api.defaults.adapter = async (config): Promise<AxiosResponse> => {
        throw new AxiosError('Network Error', 'ERR_NETWORK', config)
      }

      await expect(compileSkill('broken')).rejects.toThrow('Backend unavailable')

      expect(handler).toHaveBeenCalledTimes(1)
    } finally {
      window.removeEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handler)
    }
  })

  it('does NOT dispatch for a normal structured HTTP error response (the backend IS reachable)', async () => {
    const handler = vi.fn()
    window.addEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handler)
    try {
      api.defaults.adapter = async (config): Promise<AxiosResponse> => {
        throw new AxiosError('Request failed with status code 400', 'ERR_BAD_REQUEST', config, null, {
          data: { message: 'bad input' },
          status: 400,
          statusText: 'Bad Request',
          headers: {},
          config,
        })
      }

      await expect(compileSkill('broken')).rejects.toThrow()

      expect(handler).not.toHaveBeenCalled()
    } finally {
      window.removeEventListener(BACKEND_UNAVAILABLE_HTTP_EVENT, handler)
    }
  })
})
