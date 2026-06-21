import { afterEach, describe, expect, it } from 'vitest'
import {
  api,
  configureApiBaseURL,
  configureApiToken,
  currentApiTokenIsSet,
} from '../api/client'
import {
  applySidecarConfig,
  fallbackSidecarConfig,
  getRuntimeStatus,
  initializeRuntimeConfig,
  isTauriRuntime,
  resolveRuntimeConfig,
  subscribeToSidecarRestart,
} from './runtime'

describe('runtime config', () => {
  afterEach(async () => {
    await initializeRuntimeConfig({
      windowRef: {},
      fallbackBaseURL: 'http://localhost:8787/api',
    })
    configureApiToken(null)
  })

  it('detects the Tauri runtime marker', () => {
    expect(isTauriRuntime({ __TAURI_INTERNALS__: {} })).toBe(true)
    expect(isTauriRuntime({})).toBe(false)
  })

  it('falls back to the web dev API base URL', async () => {
    const config = await resolveRuntimeConfig({
      windowRef: {},
      fallbackBaseURL: 'http://localhost:8787/api',
    })

    expect(config).toEqual({
      port: 8787,
      baseURL: 'http://localhost:8787/api',
      wsURL: 'ws://localhost:8787/ws',
      resourceDir: '',
      configDir: '',
      api_token: null,
    })
  })

  it('uses get_sidecar_config in Tauri mode', async () => {
    const config = await resolveRuntimeConfig({
      windowRef: { __TAURI_INTERNALS__: {} },
      invoke: async <T,>(command: string): Promise<T> => {
        expect(command).toBe('get_sidecar_config')
        return {
          port: 49152,
          baseURL: 'http://127.0.0.1:49152/api/',
          wsURL: 'ws://127.0.0.1:49152/ws/',
          resourceDir: '/tmp/studio',
          configDir: '/tmp/studio-config',
          api_token: 'secret-token',
        } as T
      },
    })

    expect(config).toEqual({
      port: 49152,
      baseURL: 'http://127.0.0.1:49152/api',
      wsURL: 'ws://127.0.0.1:49152/ws',
      resourceDir: '/tmp/studio',
      configDir: '/tmp/studio-config',
      api_token: 'secret-token',
    })
  })

  it('keeps native helpers available when only sidecar config cannot be resolved', async () => {
    await expect(
      initializeRuntimeConfig({
        windowRef: { __TAURI_INTERNALS__: {} },
        invoke: async () => {
          throw new Error('sidecar disabled')
        },
      }),
    ).rejects.toThrow('sidecar disabled')

    expect(getRuntimeStatus()).toMatchObject({
      isTauri: true,
      sidecar: 'degraded',
      nativeHelpersAvailable: true,
      message: 'sidecar disabled',
    })
  })

  it('derives websocket origin from fallback base URL', () => {
    expect(fallbackSidecarConfig('https://studio.local/api').wsURL).toBe('wss://studio.local/ws')
  })

  it('does not clear a token configured before runtime initialization', async () => {
    configureApiToken('dev-tunnel-token')

    await initializeRuntimeConfig({
      windowRef: {},
      fallbackBaseURL: '/api',
    })

    expect(currentApiTokenIsSet()).toBe(true)
    configureApiToken(null)
  })

  it('R-F13 applySidecarConfig rotates the bearer token and base URL', () => {
    configureApiToken('stale-token')
    configureApiBaseURL('http://127.0.0.1:1111/api')

    applySidecarConfig({
      port: 49317,
      baseURL: 'http://127.0.0.1:49317/api',
      wsURL: 'ws://127.0.0.1:49317/ws',
      resourceDir: '/tmp/studio',
      configDir: '/tmp/studio-config',
      api_token: 'fresh-token',
    })

    expect(api.defaults.baseURL).toBe('http://127.0.0.1:49317/api')
    expect(currentApiTokenIsSet()).toBe(true)
  })

  it('R-F13 applySidecarConfig OVERRIDES an existing token (unlike initialize)', () => {
    // Initialize preserves a tunnel-bootstrapped token by design. Restart MUST
    // override — the old token is provably stale after a sidecar process swap.
    configureApiToken('old-token-from-tunnel')

    applySidecarConfig({
      port: 49317,
      baseURL: 'http://127.0.0.1:49317/api',
      wsURL: 'ws://127.0.0.1:49317/ws',
      resourceDir: '/tmp/studio',
      configDir: '/tmp/studio-config',
      api_token: 'new-token-after-restart',
    })

    // Make sure the token actually changed: send a request and inspect headers.
    let observedAuth: string | undefined
    api.defaults.adapter = async (config) => {
      observedAuth = config.headers.get('Authorization')?.toString()
      return {
        data: {},
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    return api.get('/probe').then(() => {
      expect(observedAuth).toBe('Bearer new-token-after-restart')
      api.defaults.adapter = undefined
    })
  })

  it('R-F13 subscribeToSidecarRestart is a no-op outside the Tauri runtime', async () => {
    // No __TAURI_INTERNALS__ on the window → there is nothing to listen to;
    // returning a no-op unlisten function keeps the caller simple (call/await).
    const unlisten = await subscribeToSidecarRestart(() => {
      throw new Error('callback should not fire in non-Tauri mode')
    }, { windowRef: {} })

    expect(typeof unlisten).toBe('function')
    unlisten()
  })
})
