import { configureApiBaseURL, configureApiToken, currentApiTokenIsSet } from '../api/client'

export interface SidecarConfig {
  port: number
  baseURL: string
  wsURL: string
  resourceDir: string
  configDir?: string | null
  api_token?: string | null
}

/**
 * R-F13 — name of the Tauri event the Rust shell emits after a successful
 * sidecar (re)start (`apps/studio/tauri/src/sidecar.rs::SIDECAR_RESTARTED_EVENT`).
 * Kept in sync as a single source of truth so the FE listener and the Rust
 * emitter can't drift.
 */
export const SIDECAR_RESTARTED_EVENT = 'sidecar-restarted'

type RuntimeWindow = Partial<Window> & {
  __TAURI_INTERNALS__?: unknown
}

type RuntimeOptions = {
  windowRef?: RuntimeWindow
  invoke?: <T>(command: string) => Promise<T>
  fallbackBaseURL?: string
}

export type RuntimeSidecarStatus = 'unknown' | 'ready' | 'degraded'

export interface RuntimeStatus {
  isTauri: boolean
  sidecar: RuntimeSidecarStatus
  nativeHelpersAvailable: boolean
  message?: string
}

let runtimeConfig: SidecarConfig | null = null
let runtimeIsTauri = false
let runtimeSidecarStatus: RuntimeSidecarStatus = 'unknown'
let runtimeStatusMessage: string | undefined

export function isTauriRuntime(windowRef: RuntimeWindow | undefined = getRuntimeWindow()): boolean {
  return Boolean(windowRef && '__TAURI_INTERNALS__' in windowRef)
}

export function fallbackSidecarConfig(
  baseURL = import.meta.env.VITE_STUDIO_API_BASE_URL ?? 'http://localhost:8787/api',
): SidecarConfig {
  const parsed = new URL(baseURL, getLocationOrigin())
  const protocolDefaultPort = parsed.protocol === 'https:' ? 443 : 80
  const port = parsed.port ? Number(parsed.port) : protocolDefaultPort
  const wsProtocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
  return {
    port,
    baseURL: parsed.toString().replace(/\/$/, ''),
    wsURL: `${wsProtocol}//${parsed.host}/ws`,
    resourceDir: '',
    configDir: '',
    api_token: null,
  }
}

export async function resolveRuntimeConfig(options: RuntimeOptions = {}): Promise<SidecarConfig> {
  if (isTauriRuntime(options.windowRef)) {
    const invoke = options.invoke ?? await loadTauriInvoke()
    return normalizeSidecarConfig(await invoke<SidecarConfig>('get_sidecar_config'))
  }
  return fallbackSidecarConfig(options.fallbackBaseURL)
}

export async function initializeRuntimeConfig(options: RuntimeOptions = {}): Promise<SidecarConfig> {
  runtimeIsTauri = isTauriRuntime(options.windowRef)
  try {
    const config = await resolveRuntimeConfig(options)
    runtimeConfig = config
    runtimeSidecarStatus = 'ready'
    runtimeStatusMessage = undefined
    configureApiBaseURL(config.baseURL)
    if (!currentApiTokenIsSet()) {
      configureApiToken(config.api_token ?? null)
    }
    return config
  } catch (error) {
    runtimeConfig = null
    runtimeSidecarStatus = 'degraded'
    runtimeStatusMessage = error instanceof Error ? error.message : String(error)
    throw error
  }
}

/**
 * R-F13 — apply a freshly rotated sidecar config (port/token) to the api/client
 * module state. Always overrides the cached token (unlike `initializeRuntimeConfig`
 * which preserves an existing bootstrap-tunnel token): after a sidecar restart
 * the OLD token is provably stale, so keeping it would just trigger another
 * round of 4401 closes in `useStudioEventStream` until the give-up threshold.
 *
 * Exported as a pure helper so the Tauri `sidecar-restarted` event listener can
 * call it without needing access to the React tree.
 */
export function applySidecarConfig(config: SidecarConfig): void {
  runtimeConfig = config
  runtimeSidecarStatus = 'ready'
  runtimeStatusMessage = undefined
  configureApiBaseURL(config.baseURL)
  configureApiToken(config.api_token ?? null)
}

/**
 * R-F13 — subscribe to the Tauri `sidecar-restarted` event so the FE rotates
 * `currentApiToken` / `currentApiBaseURL` the moment the Rust shell restarts
 * the Python sidecar. Returns an unsubscribe handle (Promise-resolved because
 * the underlying `@tauri-apps/api/event::listen` is async). In non-Tauri builds
 * this is a no-op — there is no shell to emit the event.
 */
export async function subscribeToSidecarRestart(
  onRestart: (config: SidecarConfig) => void = applySidecarConfig,
  options: { windowRef?: RuntimeWindow } = {},
): Promise<() => void> {
  if (!isTauriRuntime(options.windowRef)) {
    return () => {}
  }
  try {
    const { listen } = await import('@tauri-apps/api/event')
    const unlisten = await listen<SidecarConfig>(SIDECAR_RESTARTED_EVENT, (event) => {
      // eslint-disable-next-line no-console
      console.info(
        'phase=runtime action=sidecar-restarted-event port=%d',
        normalizeSidecarConfig(event.payload).port,
      )
      onRestart(normalizeSidecarConfig(event.payload))
    })
    return unlisten
  } catch (error) {
    // Listener wiring failed (e.g. Tauri event API not yet ready). Surface the
    // error rather than swallowing — the WS reconnect will eventually toast on
    // its own 4401 threshold, but operators need to know the listener is gone.
    // eslint-disable-next-line no-console
    console.error('phase=runtime action=sidecar-restarted-listen-failed error=%o', error)
    return () => {}
  }
}

export function getRuntimeConfig(): SidecarConfig | null {
  return runtimeConfig
}

export function getRuntimeStatus(
  windowRef: RuntimeWindow | undefined = getRuntimeWindow(),
): RuntimeStatus {
  const isTauri = runtimeIsTauri || isTauriRuntime(windowRef)
  return {
    isTauri,
    sidecar: runtimeSidecarStatus,
    nativeHelpersAvailable: isTauri,
    ...(runtimeStatusMessage ? { message: runtimeStatusMessage } : {}),
  }
}

async function loadTauriInvoke(): Promise<<T>(command: string) => Promise<T>> {
  const { invoke } = await import('@tauri-apps/api/core')
  return invoke
}

function normalizeSidecarConfig(config: SidecarConfig): SidecarConfig {
  return {
    port: config.port,
    baseURL: config.baseURL.replace(/\/$/, ''),
    wsURL: config.wsURL.replace(/\/$/, ''),
    resourceDir: config.resourceDir,
    configDir: config.configDir ?? '',
    api_token: config.api_token ?? null,
  }
}

function getRuntimeWindow(): RuntimeWindow | undefined {
  return typeof window === 'undefined' ? undefined : window
}

function getLocationOrigin(): string {
  return typeof window === 'undefined' ? 'http://localhost:5173' : window.location.origin
}
