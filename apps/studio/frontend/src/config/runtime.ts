import { configureApiBaseURL, configureApiToken, currentApiTokenIsSet } from '../api/client'
import { notifySidecarTokenRotated } from '../hooks/useStudioEventStream'
import { errorMessage } from '../utils/errors'

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
    runtimeStatusMessage = errorMessage(error)
    throw error
  }
}

/**
 * shell-layout F5 (problem ledger P2) — ask the Rust shell to GET this run a
 * sidecar: restart the one that died, or start the one that never came up. The
 * shell owns the launch recipe either way, so both starting points are the same
 * call here.
 *
 * This is what the runtime banner's Retry runs. The distinction that matters:
 * `initializeRuntimeConfig` asks the shell *about* the sidecar — with none
 * running, the answer is the failure it recorded, and re-asking returns that
 * same answer forever. Retry has to ask for the missing thing itself.
 *
 * Outside Tauri there is no shell to ask, so retrying can only mean re-reading
 * the dev backend URL.
 */
export async function restartSidecar(options: RuntimeOptions = {}): Promise<SidecarConfig> {
  return performShellRestart('restart_sidecar', options)
}

/**
 * What the shell answers an automatic restart that did NOT fail.
 *
 * `'restarted'` — a fresh sidecar exists and `config` describes it.
 * `'declined'` — the supervisor confirmed, under the lock that serializes
 * restarts, that the instance it owns is still alive AND still serving, so it
 * destroyed nothing; `config` describes that surviving instance
 * (`apps/studio/tauri/src/sidecar.rs::AutoRestartOutcome::Declined`).
 *
 * Both are successes and both carry a config to start using, so the caller's
 * repair is the same either way — which is the point of not reporting a
 * decline as an error. What differs is what it MEANS, and therefore what gets
 * rendered: a failure keeps the banner up with the attempt's error text and
 * schedules the next attempt, a decline ends the episode with the app working
 * again.
 */
export type SidecarAutoRestartOutcome = 'restarted' | 'declined'

export interface SidecarAutoRestartResult {
  outcome: SidecarAutoRestartOutcome
  config: SidecarConfig
}

/**
 * dead-sidecar-says-so — the bounded-loop counterpart to `restartSidecar`,
 * called by `RuntimeGate`'s own automatic recovery attempts (never by a
 * person pressing Retry, which stays on `restartSidecar` above). Invokes a
 * DIFFERENT Rust command (`restart_sidecar_automatic`) so
 * `SidecarSupervisor::restart_automatic` can enforce its attempt/window
 * budget independently — a manual Retry must never be refused by that budget,
 * so it cannot share the same command.
 *
 * confirm-before-you-kill — that same command may also DECLINE (see
 * `SidecarAutoRestartResult`). The signals that get RuntimeGate here cannot
 * tell a dead sidecar from a live one this app has lost its grip on, so the
 * supervisor checks before destroying anything. Applying the returned config
 * is the repair in both cases: it replaces the bearer token, which is the most
 * likely reason a live sidecar looks dead from here (`/health` needs no token;
 * every other call does), and tells the websocket, which carries its token in
 * the URL and would otherwise keep retrying with the credential that failed.
 *
 * Outside Tauri there is no shell to ask, no process to kill and nothing to
 * confirm, so this falls back to the same dev-backend re-read as
 * `restartSidecar` — reported as `'restarted'` because re-reading the URL is
 * everything "restart" can mean without a shell.
 */
export async function restartSidecarAutomatic(
  options: RuntimeOptions = {},
): Promise<SidecarAutoRestartResult> {
  if (!isTauriRuntime(options.windowRef)) {
    return { outcome: 'restarted', config: await initializeRuntimeConfig(options) }
  }
  const reply = await invokeShell<SidecarAutoRestartResult>('restart_sidecar_automatic', options)
  const config = normalizeSidecarConfig(reply.config)
  applySidecarConfig(config)
  return { outcome: reply.outcome, config }
}

async function performShellRestart(command: string, options: RuntimeOptions): Promise<SidecarConfig> {
  if (!isTauriRuntime(options.windowRef)) {
    return initializeRuntimeConfig(options)
  }
  const config = normalizeSidecarConfig(await invokeShell<SidecarConfig>(command, options))
  applySidecarConfig(config)
  return config
}

/**
 * One shell command, with the module's degraded-status bookkeeping attached to
 * its failure. Shared by both restart paths because "the shell could not do it"
 * has the same consequence for this module's status whatever was asked.
 */
async function invokeShell<T>(command: string, options: RuntimeOptions): Promise<T> {
  const invoke = options.invoke ?? (await loadTauriInvoke())
  try {
    return await invoke<T>(command)
  } catch (error) {
    runtimeConfig = null
    runtimeSidecarStatus = 'degraded'
    runtimeStatusMessage = errorMessage(error)
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
 *
 * recovery-stops-when-it-succeeds — this is also the single point that tells
 * the WS event-stream hub a rotation happened (`notifySidecarTokenRotated`).
 * Every caller of this function (a successful manual/automatic restart, or
 * the Tauri `sidecar-restarted` event) is by definition a moment where any
 * 4401 evidence the hub collected against the OLD token became moot — so the
 * hub's auth-failure circuit breaker must not go on treating that evidence as
 * live once we know the exact reason it happened and that it is now over.
 */
export function applySidecarConfig(config: SidecarConfig): void {
  runtimeConfig = config
  runtimeSidecarStatus = 'ready'
  runtimeStatusMessage = undefined
  configureApiBaseURL(config.baseURL)
  configureApiToken(config.api_token ?? null)
  notifySidecarTokenRotated()
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
