import { api } from './client'

export type ProviderType =
  | 'anthropic_compatible'
  | 'openai_compatible'
  | 'google_genai'

/**
 * Test outcome status persisted on the credential record. Mirrors backend
 * `app.models.llm_config.TestStatus`. Does NOT include `testing` — that is a
 * transient UI flag, not a persisted state.
 */
export type TestStatus =
  | 'untested'
  | 'ok'
  | 'invalid_key'
  | 'rate_limited'
  | 'quota_exceeded'
  | 'network_error'
  | 'timeout'
  | 'error'

export interface ModelInfo {
  id: string
  capabilities?: Record<string, unknown>
}

export interface ProviderTestResult {
  params_fingerprint: string
  base_url: string
  provider_type?: ProviderType | null
  last_test_status: TestStatus
  last_test_at?: string
  last_test_message?: string
  last_error_code?: string
  available_models?: ModelInfo[]
  available_sdks?: string[]
}

/**
 * Server-side credential entry as returned by GET /api/llm/credentials.
 *
 * The Test outcome fields (`last_test_*` + `available_sdks` / `available_models`) are
 * *single-writer* — they're populated by POST /providers/test on the backend
 * and arrive via GET. Sending them in PUT triggers a 422.
 */
export interface CredentialProviderState {
  id: string
  name: string
  api_key: string
  base_url?: string
  provider_type?: ProviderType | null

  last_test_status?: TestStatus
  last_test_at?: string
  last_test_message?: string
  last_error_code?: string
  available_models?: ModelInfo[]
  available_sdks?: string[]
  test_results?: ProviderTestResult[]
}

export interface CredentialsState {
  providers: CredentialProviderState[]
}

/**
 * The 6 editable fields accepted by PUT /api/llm/credentials.
 * Backend rejects unknown fields including any `last_test_*` — those are
 * persisted only via POST /providers/test.
 */
export interface ProviderCredentialUpdate {
  id: string
  name: string
  api_key: string
  base_url?: string
  provider_type?: ProviderType | null
}

export interface ProviderTestRequest {
  id: string
  provider_type: ProviderType
  api_key: string
  base_url?: string
  model_id?: string
}

/** Includes the transient `missing_api_key` short-circuit (api_key empty). */
export type ProviderTestStatus =
  | 'ok'
  | 'error'
  | 'invalid_key'
  | 'rate_limited'
  | 'quota_exceeded'
  | 'network_error'
  | 'timeout'
  | 'missing_api_key'

export interface ProviderTestResponse {
  status: ProviderTestStatus
  latency_ms?: number | null
  model_seen?: string | null
  message?: string | null
  error_code?: string | null
  available_models?: ModelInfo[]
  available_sdks?: string[]
}

export interface NotableModelsResponse {
  notable_models: string[]
}

export interface ProviderModelTestRequest {
  /** Credential UUID (`ProviderCredential.id`), not the provider_key metadata file key. */
  provider_id: string
  model_ids: string[]
}

export interface ProviderModelTestResult {
  model_id: string
  status: 'ok' | 'invalid_model' | 'invalid_key' | 'rate_limited' | 'network_error' | 'timeout' | 'error'
  latency_ms?: number | null
  message?: string | null
}

export interface ProviderModelTestResponse {
  results: ProviderModelTestResult[]
  available_models: ModelInfo[]
}

export interface RoleModelEntry {
  providers: string[]
  temperature?: number | null
  max_tokens?: number | null
}

export interface RoleEntry {
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
  const response = await api.get<CredentialsState>('/llm/credentials')
  return response.data
}

export async function putCredentials(
  updates: ProviderCredentialUpdate[],
): Promise<CredentialsState> {
  const response = await api.put<CredentialsState>(
    '/llm/credentials',
    { providers: updates },
  )
  return response.data
}

export async function testProvider(
  request: ProviderTestRequest,
): Promise<ProviderTestResponse> {
  const response = await api.post<ProviderTestResponse>('/llm/providers/test', request)
  return response.data
}

export async function getNotableModels(providerKey: string): Promise<NotableModelsResponse> {
  const response = await api.get<NotableModelsResponse>('/llm/providers/notable-models', {
    params: { provider_key: providerKey },
  })
  return response.data
}

export async function testProviderModels(
  request: ProviderModelTestRequest,
): Promise<ProviderModelTestResponse> {
  const response = await api.post<ProviderModelTestResponse>('/llm/providers/test-models', request)
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
