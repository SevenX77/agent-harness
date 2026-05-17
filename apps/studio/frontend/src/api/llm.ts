import { api } from './client'

export type ProviderType =
  | 'anthropic_compatible'
  | 'openai_compatible'
  | 'gemini_official'
  | 'wavespeed_any_llm'

export interface CredentialProviderState {
  provider_code: string
  has_key: boolean
  base_url?: string
  name?: string
  provider_type?: ProviderType
}

export interface CredentialsState {
  providers: CredentialProviderState[]
}

export interface ProviderCredentialUpdate {
  provider_code: string
  api_key: string
  base_url?: string
}

export interface ProviderTestRequest {
  provider_code: string
  provider_type: ProviderType
  api_key: string
  base_url?: string
  model_id?: string
}

export type ProviderTestStatus =
  | 'ok'
  | 'invalid_key'
  | 'rate_limited'
  | 'quota_exceeded'
  | 'network_error'
  | 'timeout'

export interface ProviderTestResponse {
  status: ProviderTestStatus
  latency_ms?: number | null
  model_seen?: string | null
  message?: string | null
}

export interface RoleModelEntry {
  providers: string[]
}

export interface RoleEntry {
  temperature: number | null
  model_fallback: boolean
  active_model: string
  models: Record<string, RoleModelEntry>
  system_prompt_prefix?: string | null
}

export interface ModelEntry {
  name: string
  reasoning?: boolean
  min_max_tokens?: number | null
  max_input_tokens?: number | null
  fc_supported?: boolean
  providers: Record<string, string>
  provider_options?: Record<string, Record<string, unknown>> | null
}

export interface ProviderEntry {
  name: string
  type: ProviderType
  api_key_env?: string | null
  api_key_env_fallback?: string | null
  base_url?: string | null
  llm_base_url?: string | null
  proxy_env?: string | null
  timeout?: number | null
  trust_env?: boolean | null
  retry_strategy?: string | null
}

export interface RolesData {
  models: Record<string, ModelEntry>
  providers: Record<string, ProviderEntry>
  roles: Record<string, RoleEntry>
  single_model_roles?: string[]
  peer_model_groups?: Record<string, string[]>
  circuit_breaker?: Record<string, unknown> | null
  [key: string]: unknown
}

export async function getCredentials(): Promise<CredentialsState> {
  const response = await api.get<CredentialsState>('/llm/credentials', {
    params: { include_metadata: true },
  })
  return response.data
}

export async function putCredentials(
  updates: ProviderCredentialUpdate[],
): Promise<CredentialsState> {
  const response = await api.put<CredentialsState>(
    '/llm/credentials',
    { providers: updates },
    { params: { include_metadata: true } },
  )
  return response.data
}

export async function testProvider(
  request: ProviderTestRequest,
): Promise<ProviderTestResponse> {
  const response = await api.post<ProviderTestResponse>('/llm/providers/test', request)
  return response.data
}

export async function getRoles(): Promise<RolesData> {
  const response = await api.get<RolesData>('/llm/roles')
  return response.data
}

export async function getRole(roleName: string): Promise<RoleEntry> {
  const response = await api.get<RoleEntry>(`/llm/roles/${roleName}`)
  return response.data
}

export async function putRoles(data: RolesData): Promise<RolesData> {
  const response = await api.put<RolesData>('/llm/roles', data)
  return response.data
}
