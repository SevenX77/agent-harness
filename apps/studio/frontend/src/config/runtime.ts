import { configureApiBaseURL, configureApiToken, currentApiTokenIsSet } from '../api/client'

export interface SidecarConfig {
  port: number
  baseURL: string
  wsURL: string
  resourceDir: string
  configDir?: string | null
  api_token?: string | null
}

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
