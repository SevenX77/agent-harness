import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  api,
  configureApiBaseURL,
  configureApiToken,
  currentApiTokenIsSet,
  wsUrl,
} from '../api/client'

const notifySidecarTokenRotatedMock = vi.fn()
vi.mock('../hooks/useStudioEventStream', () => ({
  notifySidecarTokenRotated: () => notifySidecarTokenRotatedMock(),
}))

import {
  applySidecarConfig,
  fallbackSidecarConfig,
  getRuntimeStatus,
  initializeRuntimeConfig,
  isTauriRuntime,
  resolveRuntimeConfig,
  reconnectSidecar,
  restartSidecar,
  restartSidecarAutomatic,
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

  it(
    'recovery-stops-when-it-succeeds: applySidecarConfig tells the WS hub a rotation ' +
      'happened, so stale-token 4401 evidence against the OLD token cannot trip the give-up breaker',
    () => {
      notifySidecarTokenRotatedMock.mockClear()

      applySidecarConfig({
        port: 49318,
        baseURL: 'http://127.0.0.1:49318/api',
        wsURL: 'ws://127.0.0.1:49318/ws',
        resourceDir: '/tmp/studio',
        configDir: '/tmp/studio-config',
        api_token: 'token-after-rotation',
      })

      expect(notifySidecarTokenRotatedMock).toHaveBeenCalledTimes(1)
    },
  )

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

/**
 * Problem ledger P2. Retry used to re-run `initializeRuntimeConfig()`, which
 * asks the shell for the sidecar's config — and with no sidecar running, the
 * shell answered with the error it had cached at boot. Same string every time:
 * to the user, a button that does nothing.
 *
 * Retry has to ask for the thing that is missing, which is a sidecar.
 */
describe('retrying asks the shell for a sidecar, not for its config', () => {
  const restarted = {
    port: 41234,
    baseURL: 'http://127.0.0.1:41234/api',
    wsURL: 'ws://127.0.0.1:41234/ws',
    resourceDir: '/resources',
    configDir: '/config',
    api_token: 'token-from-the-new-sidecar',
  }

  it('calls the shell command that starts one', async () => {
    const commands: string[] = []

    const config = await restartSidecar({
      windowRef: { __TAURI_INTERNALS__: {} },
      invoke: async <T,>(command: string): Promise<T> => {
        commands.push(command)
        return restarted as T
      },
    })

    expect(commands).toEqual(['restart_sidecar'])
    expect(config.port).toBe(41234)
  })

  it('routes the next request at the sidecar it just started', async () => {
    await restartSidecar({
      windowRef: { __TAURI_INTERNALS__: {} },
      invoke: async <T,>(): Promise<T> => restarted as T,
    })

    expect(getRuntimeStatus({ __TAURI_INTERNALS__: {} }).sidecar).toBe('ready')
    expect(api.defaults.baseURL).toBe('http://127.0.0.1:41234/api')
    expect(currentApiTokenIsSet()).toBe(true)
  })

  it('surfaces what this attempt hit, so a second press can read differently', async () => {
    await expect(
      restartSidecar({
        windowRef: { __TAURI_INTERNALS__: {} },
        invoke: async <T,>(): Promise<T> => {
          throw new Error('failed to start Python sidecar: vendor snapshot missing')
        },
      }),
    ).rejects.toThrow('vendor snapshot missing')

    expect(getRuntimeStatus({ __TAURI_INTERNALS__: {} }).message).toContain('vendor snapshot missing')
  })

  it('outside Tauri there is no shell to ask, so it re-reads the dev backend', async () => {
    const config = await restartSidecar({
      windowRef: {},
      fallbackBaseURL: 'http://localhost:8787/api',
    })

    expect(config.baseURL).toBe('http://localhost:8787/api')
  })
})

/**
 * `reconnectSidecar` — what RuntimeGate does INSTEAD of restarting when the
 * sidecar's port turns out to still be answering. It is the non-destructive
 * half of a Retry: ask the shell where the sidecar is and start using that
 * answer, without asking it to kill anything.
 *
 * The distinction from `initializeRuntimeConfig` is the whole reason it exists.
 * That one is a BOOT step and deliberately does not overwrite a token that is
 * already set (a `#tkn=` in the URL must win over the shell's). Reconnecting is
 * the opposite situation: a token already being set is exactly the condition,
 * and a stale one is a leading suspect for why the connection was lost — so the
 * shell's answer has to win.
 */
describe('reconnectSidecar — re-reading the shell without restarting anything', () => {
  const running = {
    port: 41236,
    baseURL: 'http://127.0.0.1:41236/api',
    wsURL: 'ws://127.0.0.1:41236/ws',
    resourceDir: '/resources',
    configDir: '/config',
    api_token: 'token-the-sidecar-rotated-to',
  }

  it('asks for the config and does NOT send a restart command', async () => {
    const commands: string[] = []

    await reconnectSidecar({
      windowRef: { __TAURI_INTERNALS__: {} },
      invoke: async <T,>(command: string): Promise<T> => {
        commands.push(command)
        return running as T
      },
    })

    expect(commands).toEqual(['get_sidecar_config'])
  })

  it('replaces a token that is already set, which boot would have kept', async () => {
    configureApiToken('the-token-that-stopped-working')

    await reconnectSidecar({
      windowRef: { __TAURI_INTERNALS__: {} },
      invoke: async <T,>(): Promise<T> => running as T,
    })

    // Read back through `wsUrl`, because that is where the token VALUE is
    // observable — the HTTP side keeps it in a module variable that a request
    // interceptor applies, so `api.defaults` never carries it. This file runs in
    // the node environment, so `wsUrl` needs a `window` to resolve against.
    vi.stubGlobal('window', { location: { origin: 'http://127.0.0.1:41236' } })
    try {
      expect(wsUrl('/ws')).toContain('token=token-the-sidecar-rotated-to')
    } finally {
      vi.unstubAllGlobals()
    }
    // And the websocket has to be told, not just re-read later: it carries the
    // token in its URL, so without this it keeps retrying with the credential
    // that just failed.
    expect(notifySidecarTokenRotatedMock).toHaveBeenCalled()
  })
})

/**
 * dead-sidecar-says-so — RuntimeGate's bounded automatic-restart loop calls a
 * DIFFERENT shell command than a manual Retry, so the Rust-side supervisor can
 * bound automatic attempts independently without ever refusing a person
 * pressing Retry (`SidecarSupervisor::restart_automatic` vs `::restart`).
 */
describe('restartSidecarAutomatic — the bounded-loop counterpart to restartSidecar', () => {
  const restarted = {
    port: 41235,
    baseURL: 'http://127.0.0.1:41235/api',
    wsURL: 'ws://127.0.0.1:41235/ws',
    resourceDir: '/resources',
    configDir: '/config',
    api_token: 'token-from-the-automatically-restarted-sidecar',
  }

  it('calls restart_sidecar_automatic, not restart_sidecar', async () => {
    const commands: string[] = []

    const config = await restartSidecarAutomatic({
      windowRef: { __TAURI_INTERNALS__: {} },
      invoke: async <T,>(command: string): Promise<T> => {
        commands.push(command)
        return restarted as T
      },
    })

    expect(commands).toEqual(['restart_sidecar_automatic'])
    expect(config.port).toBe(41235)
  })

  it('applies the fresh config on success, same as a manual restart', async () => {
    await restartSidecarAutomatic({
      windowRef: { __TAURI_INTERNALS__: {} },
      invoke: async <T,>(): Promise<T> => restarted as T,
    })

    expect(getRuntimeStatus({ __TAURI_INTERNALS__: {} }).sidecar).toBe('ready')
    expect(api.defaults.baseURL).toBe('http://127.0.0.1:41235/api')
    expect(currentApiTokenIsSet()).toBe(true)
  })

  it('surfaces a refusal (budget exhausted) the same way it surfaces a real failure', async () => {
    await expect(
      restartSidecarAutomatic({
        windowRef: { __TAURI_INTERNALS__: {} },
        invoke: async <T,>(): Promise<T> => {
          throw new Error('automatic restart budget exhausted — press Retry')
        },
      }),
    ).rejects.toThrow('budget exhausted')

    expect(getRuntimeStatus({ __TAURI_INTERNALS__: {} }).message).toContain('budget exhausted')
  })

  it('outside Tauri there is no shell to ask, so it re-reads the dev backend', async () => {
    const config = await restartSidecarAutomatic({
      windowRef: {},
      fallbackBaseURL: 'http://localhost:8787/api',
    })

    expect(config.baseURL).toBe('http://localhost:8787/api')
  })
})
