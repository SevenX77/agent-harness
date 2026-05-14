import { api } from './client'

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

export async function getCopilotCredentials(): Promise<CopilotCredentials> {
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
