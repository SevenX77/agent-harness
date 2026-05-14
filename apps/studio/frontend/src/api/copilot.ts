import { api } from './client'
import type { CopilotBackend } from '../types/copilot'

export type ProviderKind = 'anthropic' | 'openai-compat' | 'google'

export interface ProviderConfig {
  id: string
  name: string
  kind: ProviderKind
  api_key: string
  base_url: string
  active_model_id: string | null
}

export interface CopilotCredentials {
  active_provider_id: string
  providers: ProviderConfig[]
}

export interface ModelInfo {
  id: string
  supports_thinking: boolean
  supports_vision: boolean
}

export interface TestProviderRequest {
  id: string
  name: string
  kind: ProviderKind
  api_key: string
  base_url: string
}

export interface TestProviderResponse {
  status: 'ok' | 'invalid_key' | 'rate_limited' | 'timeout' | 'network_error' | 'quota_exceeded'
  latency_ms?: number | null
  models: ModelInfo[]
  message?: string | null
}

type LegacyBackendStatus = {
  has_key: boolean
  last4: string | null
  base_url: string
}

type LegacyCredentials = {
  active_backend: CopilotBackend
  backends: Record<CopilotBackend, LegacyBackendStatus>
}

const backendProvider: Record<CopilotBackend, { id: string; name: string; kind: ProviderKind }> = {
  claude: { id: 'default-claude', name: 'Claude', kind: 'anthropic' },
  deepseek: { id: 'default-deepseek', name: 'DeepSeek', kind: 'openai-compat' },
  gemini: { id: 'default-gemini', name: 'Gemini', kind: 'google' },
  openai: { id: 'default-openai', name: 'OpenAI', kind: 'openai-compat' },
}

export type CredentialsWriteRequest = {
  backend: CopilotBackend
  api_key?: string | null
  base_url?: string | null
  set_active?: boolean
}

export type TestCredentialsRequest = {
  backend: CopilotBackend
  api_key: string
  base_url?: string
}

export type TestCredentialsResponse = {
  status: TestProviderResponse['status']
  latency_ms?: number | null
  model_seen?: string | null
  message?: string | null
}

export async function getCopilotCredentials(): Promise<any> {
  const response = await api.get<CopilotCredentials>('/copilot/credentials')
  return response.data
}

export async function putCopilotCredentials(credentials: CopilotCredentials): Promise<void> {
  await api.put('/copilot/credentials', credentials)
}

export async function testCopilotProvider(request: TestProviderRequest): Promise<TestProviderResponse> {
  const response = await api.post<TestProviderResponse>('/copilot/providers/test', request)
  return response.data
}

export async function updateCopilotCredentials(
  backend: CopilotBackend,
  apiKey?: string,
  setActive = false,
  baseUrl?: string | null,
): Promise<LegacyCredentials> {
  const current = (await getCopilotCredentials()) as CopilotCredentials
  const target = backendProvider[backend]
  const providers = current.providers.map((provider) => {
    if (provider.id !== target.id) return provider
    return {
      ...provider,
      api_key: apiKey === undefined ? provider.api_key : apiKey,
      base_url: baseUrl === undefined || baseUrl === null ? provider.base_url : baseUrl,
    }
  })
  const next = {
    ...current,
    active_provider_id: setActive ? target.id : current.active_provider_id,
    providers,
  }
  await putCopilotCredentials(next)
  return toLegacyCredentials(next)
}

export async function testCopilotCredentials(request: TestCredentialsRequest): Promise<TestCredentialsResponse> {
  const provider = backendProvider[request.backend]
  const result = await testCopilotProvider({
    id: provider.id,
    name: provider.name,
    kind: provider.kind,
    api_key: request.api_key,
    base_url: request.base_url ?? '',
  })
  return {
    status: result.status,
    latency_ms: result.latency_ms,
    model_seen: result.models[0]?.id ?? null,
    message: result.message,
  }
}

function toLegacyCredentials(credentials: CopilotCredentials): LegacyCredentials {
  const providerById = Object.fromEntries(credentials.providers.map((provider) => [provider.id, provider]))
  const backends = Object.fromEntries(
    (Object.entries(backendProvider) as Array<[CopilotBackend, (typeof backendProvider)[CopilotBackend]]>).map(
      ([backend, provider]) => {
        const config = providerById[provider.id]
        const apiKey = config?.api_key ?? ''
        return [
          backend,
          {
            has_key: Boolean(apiKey),
            last4: apiKey ? apiKey.slice(-4) : null,
            base_url: config?.base_url ?? '',
          },
        ]
      },
    ),
  ) as Record<CopilotBackend, LegacyBackendStatus>
  const active_backend =
    (Object.entries(backendProvider).find(([, provider]) => provider.id === credentials.active_provider_id)?.[0] as
      | CopilotBackend
      | undefined) ?? 'claude'
  return { active_backend, backends }
}
