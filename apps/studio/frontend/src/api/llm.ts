import { api } from './client'

export type ProviderType =
  | 'anthropic_compatible'
  | 'openai_compatible'
  | 'google_genai'

export type RouteStatus = 'verified' | 'unverified_manual' | 'disabled' | 'failed'
export type CapabilitySource = 'api_list' | 'provider_doc' | 'agent_draft' | 'manual' | 'probed_verified'
export type LintSeverity = 'off' | 'warn' | 'error'

export interface CapabilityValue {
  value: unknown
  source: CapabilitySource
  observed_at?: string | null
  message?: string | null
}

export interface RuntimePolicy {
  provider_down_ttl_seconds: number
  probe_timeout_seconds: number
  token_escalation_rounds: number
}

export interface ProviderEndpoint {
  endpoint_id: string
  display_name: string
  protocol: ProviderType
  base_url: string
  api_key?: string | null
  status: RouteStatus
  last_test_at?: string | null
  last_test_message?: string | null
  timeout_seconds: number
  trust_env: boolean
  proxy_env?: string | null
  metadata: Record<string, unknown>
}

export interface ProviderRoute {
  route_id: string
  endpoint_id: string
  route_slug: string
  provider_model_id: string
  canonical_id: string
  display_name: string
  status: RouteStatus
  capabilities: Record<string, CapabilityValue>
  metadata: Record<string, unknown>
}

export interface CredentialRegistryResponse {
  schema_version?: 4
  provider_endpoints: Record<string, ProviderEndpoint>
  provider_routes: Record<string, ProviderRoute>
  runtime_policy: RuntimePolicy
}

export interface CanonicalGroup {
  canonical_id: string
  display_name: string
  routes: string[]
}

export interface LintResult {
  role_name: string
  route_id: string
  severity: 'warn' | 'error'
  capability: string
  message: string
  source: string
  blocking: boolean
  code?: string | null
}

export interface RegistryResponse extends CredentialRegistryResponse {
  model_profiles: Record<string, unknown>
  roles: Record<string, unknown>
  canonical_groups: CanonicalGroup[]
  lint_results: LintResult[]
  setup_required: boolean
}

export interface EndpointSecretResponse {
  endpoint_id: string
  api_key: string
}

/**
 * Test outcome status projected for the restored API Keys page.
 *
 * The backend source of truth is now v4 endpoint status. This legacy-shaped
 * status keeps the accepted API Keys UI working while the execution model
 * remains route-registry based.
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
  /** Credential endpoint id, not a provider metadata key. */
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

const localNotableModels: Record<string, string[]> = {
  anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6-thinking', 'claude-3-5-sonnet'],
  openai: ['gpt-5', 'gpt-4.1', 'gpt-4o'],
  gemini: ['gemini-3.1-pro-preview', 'gemini-2.5-pro'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  ark: ['doubao-seed-1-6', 'doubao-1-5-pro'],
  openrouter: ['openai/gpt-5', 'anthropic/claude-opus-4.1', 'google/gemini-pro'],
}

const redactedSecret = '**********'
let cachedRegistry: RegistryResponse | null = null
const testResultCacheByEndpoint: Record<string, ProviderTestResult[]> = {}

function segment(value: string): string {
  return encodeURIComponent(value)
}

function routesForEndpoint(registry: CredentialRegistryResponse, endpointId: string): ProviderRoute[] {
  return Object.values(registry.provider_routes).filter((route) => route.endpoint_id === endpointId)
}

function statusToTestStatus(status: RouteStatus): TestStatus {
  if (status === 'verified') return 'ok'
  if (status === 'failed') return 'error'
  return 'untested'
}

function paramsFingerprint(params: {
  api_key?: string | null
  base_url?: string | null
  provider_type?: ProviderType | null
}): string {
  return fnv1a32(JSON.stringify({
    api_key: params.api_key ?? '',
    base_url: params.base_url ?? '',
    provider_type: params.provider_type ?? null,
  }))
}

function fnv1a32(value: string): string {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

function upsertCachedResult(endpointId: string, result: ProviderTestResult | null): ProviderTestResult[] {
  const existing = testResultCacheByEndpoint[endpointId] ?? []
  if (!result) return existing
  const next = [
    ...existing.filter((item) => item.params_fingerprint !== result.params_fingerprint),
    result,
  ]
  testResultCacheByEndpoint[endpointId] = next
  return next
}

function testResultFromEndpoint(
  endpoint: ProviderEndpoint,
  routes: ProviderRoute[],
): ProviderTestResult | null {
  const lastTestStatus = statusToTestStatus(endpoint.status)
  if (lastTestStatus === 'untested' && !endpoint.last_test_at && !endpoint.last_test_message && routes.length === 0) {
    return null
  }
  return {
    params_fingerprint: paramsFingerprint({
      api_key: endpoint.api_key ?? '',
      base_url: endpoint.base_url,
      provider_type: endpoint.protocol,
    }),
    base_url: endpoint.base_url,
    provider_type: endpoint.protocol,
    last_test_status: lastTestStatus,
    last_test_at: endpoint.last_test_at ?? '',
    last_test_message: endpoint.last_test_message ?? '',
    last_error_code: endpoint.status === 'failed' ? 'endpoint_test_failed' : '',
    available_models: routes.map((route) => ({
      id: route.provider_model_id,
      capabilities: route.capabilities,
    })),
    available_sdks: [endpoint.protocol],
  }
}

function endpointToCredential(
  registry: CredentialRegistryResponse,
  endpoint: ProviderEndpoint,
): CredentialProviderState {
  const routes = routesForEndpoint(registry, endpoint.endpoint_id)
  const testResults = upsertCachedResult(endpoint.endpoint_id, testResultFromEndpoint(endpoint, routes))
  return {
    id: endpoint.endpoint_id,
    name: endpoint.display_name,
    api_key: endpoint.api_key ?? '',
    base_url: endpoint.base_url,
    provider_type: endpoint.protocol,
    last_test_status: statusToTestStatus(endpoint.status),
    last_test_at: endpoint.last_test_at ?? '',
    last_test_message: endpoint.last_test_message ?? '',
    last_error_code: '',
    available_models: routes.map((route) => ({
      id: route.provider_model_id,
      capabilities: route.capabilities,
    })),
    available_sdks: [endpoint.protocol],
    test_results: testResults,
  }
}

function registryToCredentials(registry: CredentialRegistryResponse): CredentialsState {
  return {
    providers: Object.values(registry.provider_endpoints)
      .sort((left, right) => left.endpoint_id.localeCompare(right.endpoint_id))
      .map((endpoint) => endpointToCredential(registry, endpoint)),
  }
}

function endpointFromCredentialUpdate(
  update: ProviderCredentialUpdate,
  existing?: ProviderEndpoint,
): ProviderEndpoint {
  const nextProtocol = update.provider_type ?? existing?.protocol ?? 'openai_compatible'
  const nextBaseUrl = update.base_url ?? existing?.base_url ?? ''
  const nextSecret = update.api_key === '' ? null : update.api_key ?? existing?.api_key ?? null
  const secretChanged = Boolean(
    existing &&
    update.api_key &&
    update.api_key !== '**********' &&
    update.api_key !== (existing.api_key ?? ''),
  )
  const testParamsChanged = Boolean(
    existing &&
    (
      nextProtocol !== existing.protocol ||
      nextBaseUrl !== existing.base_url ||
      secretChanged
    ),
  )
  return {
    endpoint_id: update.id,
    display_name: update.name || existing?.display_name || update.id,
    protocol: nextProtocol,
    base_url: nextBaseUrl,
    api_key: nextSecret,
    status: testParamsChanged ? 'unverified_manual' : existing?.status ?? 'unverified_manual',
    last_test_at: testParamsChanged ? null : existing?.last_test_at ?? null,
    last_test_message: testParamsChanged ? null : existing?.last_test_message ?? null,
    timeout_seconds: existing?.timeout_seconds ?? 120,
    trust_env: existing?.trust_env ?? false,
    proxy_env: existing?.proxy_env ?? null,
    metadata: existing?.metadata ?? {},
  }
}

function endpointErrorCode(endpoint: ProviderEndpoint): string | undefined {
  const message = endpoint.last_test_message ?? ''
  const match = message.match(/\(([^()]+)\)\.?$/)
  if (match?.[1]) return match[1]
  const normalized = message.toLowerCase()
  if (normalized.includes('invalid api key')) return 'invalid_api_key'
  if (normalized.includes('rate limited') || normalized.includes('429')) return 'rate_limited'
  if (normalized.includes('quota') || normalized.includes('billing')) return 'quota_exceeded'
  if (normalized.includes('timed out') || normalized.includes('timeout')) return 'timeout'
  if (normalized.includes('network error')) return 'network_error'
  return endpoint.status === 'failed' ? 'endpoint_test_failed' : undefined
}

function endpointTestStatus(endpoint: ProviderEndpoint): ProviderTestStatus {
  if (endpoint.status === 'verified') return 'ok'
  if (!endpoint.api_key) return 'missing_api_key'
  const errorCode = endpointErrorCode(endpoint)
  const message = (endpoint.last_test_message ?? '').toLowerCase()
  if (
    message.includes('invalid api key') ||
    errorCode === 'invalid_api_key' ||
    errorCode === 'invalid_x_api_key' ||
    errorCode === 'unauthorized'
  ) {
    return 'invalid_key'
  }
  if (errorCode === 'rate_limited' || errorCode === 'rate_limit_error' || errorCode === 'rate_limit_exceeded') {
    return 'rate_limited'
  }
  if (errorCode === 'quota_exceeded' || errorCode === 'insufficient_quota') {
    return 'quota_exceeded'
  }
  if (errorCode === 'timeout') return 'timeout'
  if (errorCode === 'network_error') return 'network_error'
  return 'error'
}

function providerTestResponseFromEndpoint(
  endpoint: ProviderEndpoint,
  registry: CredentialRegistryResponse | null,
): ProviderTestResponse {
  const routes = registry ? routesForEndpoint(registry, endpoint.endpoint_id) : []
  upsertCachedResult(endpoint.endpoint_id, testResultFromEndpoint(endpoint, routes))
  const status = endpointTestStatus(endpoint)
  return {
    status,
    latency_ms: null,
    model_seen: routes[0]?.provider_model_id ?? null,
    message: endpoint.last_test_message ?? null,
    error_code: endpointErrorCode(endpoint),
    available_models: routes.map((route) => ({
      id: route.provider_model_id,
      capabilities: route.capabilities,
    })),
    available_sdks: [endpoint.protocol],
  }
}

export function apiKeysCredentialsFromRegistry(registry: CredentialRegistryResponse): CredentialsState {
  return registryToCredentials(registry)
}

export async function getRegistry(): Promise<RegistryResponse> {
  const response = await api.get<RegistryResponse>('/llm/registry')
  cachedRegistry = response.data
  return response.data
}

export async function getEndpointSecret(endpointId: string): Promise<EndpointSecretResponse> {
  const response = await api.get<EndpointSecretResponse>(`/llm/registry/endpoints/${segment(endpointId)}/secret`)
  return response.data
}

async function hydrateEndpointSecrets<T extends CredentialRegistryResponse>(registry: T): Promise<T> {
  const entries = await Promise.all(
    Object.entries(registry.provider_endpoints).map(async ([endpointId, endpoint]) => {
      if (endpoint.api_key !== redactedSecret) {
        return [endpointId, endpoint] as const
      }
      try {
        const secret = await getEndpointSecret(endpointId)
        return [endpointId, { ...endpoint, api_key: secret.api_key }] as const
      } catch {
        return [endpointId, endpoint] as const
      }
    }),
  )
  const hydrated = {
    ...registry,
    provider_endpoints: Object.fromEntries(entries),
  }
  if (cachedRegistry) {
    cachedRegistry = {
      ...cachedRegistry,
      provider_endpoints: hydrated.provider_endpoints,
    }
  }
  return hydrated
}

export async function putRegistryEndpoints(
  providerEndpoints: Record<string, ProviderEndpoint>,
): Promise<CredentialRegistryResponse> {
  const response = await api.put<CredentialRegistryResponse>(
    '/llm/registry/endpoints',
    { provider_endpoints: providerEndpoints },
  )
  cachedRegistry = {
    ...(cachedRegistry ?? {
      model_profiles: {},
      roles: {},
      canonical_groups: [],
      lint_results: [],
      setup_required: false,
    }),
    ...response.data,
  }
  return response.data
}

export async function deleteEndpoint(endpointId: string): Promise<CredentialRegistryResponse> {
  const response = await api.delete<CredentialRegistryResponse>(`/llm/registry/endpoints/${segment(endpointId)}`)
  if (cachedRegistry) {
    const providerEndpoints = { ...cachedRegistry.provider_endpoints }
    delete providerEndpoints[endpointId]
    const providerRoutes = Object.fromEntries(
      Object.entries(cachedRegistry.provider_routes).filter(([, route]) => route.endpoint_id !== endpointId),
    )
    cachedRegistry = {
      ...cachedRegistry,
      ...response.data,
      provider_endpoints: response.data.provider_endpoints ?? providerEndpoints,
      provider_routes: response.data.provider_routes ?? providerRoutes,
    }
  }
  return response.data
}

export async function testEndpoint(endpointId: string): Promise<ProviderEndpoint> {
  const response = await api.post<ProviderEndpoint>(`/llm/endpoints/${segment(endpointId)}/test`)
  if (cachedRegistry) {
    cachedRegistry = {
      ...cachedRegistry,
      provider_endpoints: {
        ...cachedRegistry.provider_endpoints,
        [endpointId]: response.data,
      },
    }
  }
  return response.data
}

export async function probeRoute(routeId: string, request: { capabilities: string[] }): Promise<ProviderRoute> {
  const response = await api.post<ProviderRoute>(`/llm/routes/${segment(routeId)}/probe`, request)
  if (cachedRegistry) {
    cachedRegistry = {
      ...cachedRegistry,
      provider_routes: {
        ...cachedRegistry.provider_routes,
        [routeId]: response.data,
      },
    }
  }
  return response.data
}

export async function getCredentials(): Promise<CredentialsState> {
  const registry = await hydrateEndpointSecrets(await getRegistry())
  return registryToCredentials(registry)
}

export async function putCredentials(
  updates: ProviderCredentialUpdate[],
): Promise<CredentialsState> {
  const existingEndpoints = cachedRegistry?.provider_endpoints ?? {}
  const updateIds = new Set(updates.map((update) => update.id))
  const removedEndpointIds = Object.keys(existingEndpoints).filter((endpointId) => !updateIds.has(endpointId))
  for (const endpointId of removedEndpointIds) {
    await deleteEndpoint(endpointId)
  }
  const providerEndpoints = Object.fromEntries(
    updates.map((update) => [
      update.id,
      endpointFromCredentialUpdate(update, existingEndpoints[update.id]),
    ]),
  )
  if (Object.keys(providerEndpoints).length === 0) {
    return registryToCredentials(cachedRegistry ?? {
      provider_endpoints: {},
      provider_routes: {},
      runtime_policy: {
        provider_down_ttl_seconds: 60,
        probe_timeout_seconds: 5,
        token_escalation_rounds: 2,
      },
    })
  }
  const registry = await putRegistryEndpoints(providerEndpoints)
  return registryToCredentials(registry)
}

export async function testProvider(
  request: ProviderTestRequest,
): Promise<ProviderTestResponse> {
  if (!request.api_key.trim()) {
    return {
      status: 'missing_api_key',
      latency_ms: null,
      model_seen: null,
      message: 'API key is empty.',
      available_models: [],
      available_sdks: [request.provider_type],
    }
  }
  const existing = cachedRegistry?.provider_endpoints[request.id]
  await putRegistryEndpoints({
    [request.id]: endpointFromCredentialUpdate(
      {
        id: request.id,
        name: existing?.display_name ?? request.id,
        api_key: request.api_key,
        base_url: request.base_url ?? existing?.base_url ?? '',
        provider_type: request.provider_type,
      },
      existing,
    ),
  })
  const endpoint = await testEndpoint(request.id)
  return providerTestResponseFromEndpoint(endpoint, cachedRegistry)
}

export async function getNotableModels(providerKey: string): Promise<NotableModelsResponse> {
  return {
    notable_models: localNotableModels[providerKey.toLowerCase()] ?? ['gpt-5'],
  }
}

export async function testProviderModels(
  request: ProviderModelTestRequest,
): Promise<ProviderModelTestResponse> {
  const registry = cachedRegistry ?? await getRegistry()
  const endpointRoutes = routesForEndpoint(registry, request.provider_id)
  const availableModels = endpointRoutes.map((route) => ({
    id: route.provider_model_id,
    capabilities: route.capabilities,
  }))
  return {
    results: request.model_ids.map((modelId) => {
      const route = endpointRoutes.find((candidate) => candidate.provider_model_id === modelId)
      return {
        model_id: modelId,
        status: route ? 'ok' : 'invalid_model',
        latency_ms: null,
        message: route ? null : 'Model route is not registered in the v4 registry.',
      }
    }),
    available_models: availableModels,
  }
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
