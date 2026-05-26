import { api } from './client'

export type ProviderType =
  | 'anthropic_compatible'
  | 'ark_runtime'
  | 'openai_compatible'
  | 'google_genai'

export type RouteStatus = 'verified' | 'unverified_manual' | 'disabled' | 'failed'
export type ProviderKind = 'official' | 'third_party' | 'custom'
export type ProviderUiState = 'ready' | 'untested' | 'cooling_down' | 'needs_setup' | 'off'
export type RoleFitState = 'using' | 'downgraded' | 'needs_test' | 'not_fit'
export type CapabilityState = 'unknown' | 'callable_only' | 'partial' | 'known'
export type CapabilitySummaryState = 'supported' | 'unsupported' | 'mixed' | 'unknown'
export type CapabilitySource = 'api_list' | 'provider_doc' | 'agent_draft' | 'manual' | 'probed_verified'
export type LintSeverity = 'off' | 'warn' | 'error'
export type RoleKind = 'graph_agent' | 'copilot'

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
  provider_kind?: ProviderKind
  rate_limit_bucket?: string | null
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

export interface ProviderModelOption {
  route_id: string
  provider_label: string
  provider_kind: ProviderKind
  provider_model_id: string
  ui_state: ProviderUiState
  ui_detail?: string | null
  retry_at?: string | null
  reason_code?: string | null
  capability_state: CapabilityState
  capabilities: Record<string, CapabilityValue>
}

export interface ModelGroupStatusSummary {
  ready: number
  untested: number
  cooling_down: number
  needs_setup: number
  off: number
}

export interface ModelGroupCapabilitySummary {
  capability_known_count: number
  thinking: CapabilitySummaryState
  tools: CapabilitySummaryState
  structured_output: CapabilitySummaryState
  max_context_tokens?: number | null
  max_output_tokens?: number | null
}

export interface ModelGroup {
  canonical_id: string
  display_name: string
  provider_models: ProviderModelOption[]
  status_summary: ModelGroupStatusSummary
  capability_summary: ModelGroupCapabilitySummary
}

export interface RuntimeSettingDescriptor {
  key: string
  value_type: 'number' | 'integer' | 'boolean' | 'string' | 'string_list' | 'object'
  supported?: boolean | null
  min?: number | null
  max?: number | null
  default?: unknown
  allowed_values: string[]
  source: CapabilitySource | 'unknown'
  message?: string | null
}

export interface EffectiveRuntimeSetting {
  value: unknown
  source: 'route_setting' | 'profile_default' | 'route_capability_default' | 'protocol_default' | 'studio_default'
  message?: string | null
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
  model_groups: ModelGroup[]
  roles: Record<string, RoleEntry>
  canonical_groups: CanonicalGroup[]
  lint_results: LintResult[]
  route_runtime_settings?: Record<string, Record<string, RuntimeSettingDescriptor>>
  role_effective_runtime_settings?: Record<string, Record<string, Record<string, EffectiveRuntimeSetting>>>
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
  status: 'ok' | 'invalid_model' | 'invalid_key' | 'rate_limited' | 'quota_exceeded' | 'network_error' | 'timeout' | 'error'
  latency_ms?: number | null
  message?: string | null
  route_id?: string | null
}

export interface ProviderModelTestResponse {
  results: ProviderModelTestResult[]
  available_models: ModelInfo[]
}

export interface EndpointTestResponse {
  registry: RegistryResponse
  tested_endpoint_id: string
  discovered_model_count: number
}

export interface EndpointModelTestResponse {
  registry: RegistryResponse
  results: ProviderModelTestResult[]
}

export interface RoleModelEntry {
  providers: string[]
  temperature?: number | null
  max_tokens?: number | null
}

export interface RoleRouteEntry {
  route_id: string
  runtime_settings?: Record<string, unknown>
  runtime_settings_source?: string | null
}

export interface RoleEntry {
  role_kind?: RoleKind
  model_fallback: boolean
  model_fallback_enabled?: boolean
  active_model: string
  models: Record<string, RoleModelEntry>
  model_groups?: RoleModelGroup[]
  materialization_report?: MaterializationReport
  fallback_chain?: RoleRouteEntry[]
  lint_requirements?: Record<string, LintSeverity>
  source_profile_id?: string | null
  source_profile_snapshot?: Record<string, unknown> | null
  system_prompt_prefix?: string | null
}

export interface RoleProviderModel {
  route_id: string
  intent?: Record<string, unknown> | null
}

export interface RoleModelGroup {
  canonical_id: string
  display_name: string
  intent?: Record<string, unknown>
  provider_models: RoleProviderModel[]
}

export interface MaterializationReportEntry {
  canonical_id?: string
  route_id: string
  requested?: Record<string, unknown>
  resolved_settings?: Record<string, unknown>
  warnings?: Array<Record<string, unknown>>
  role_fit: RoleFitState
}

export interface MaterializationReport {
  entries: MaterializationReportEntry[]
  warnings: Array<Record<string, unknown>>
  skipped_provider_details: Array<Record<string, unknown>>
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
  schema_version?: 2 | 3
  models: Record<string, ModelEntry>
  providers: Record<string, ProviderEntry>
  model_profiles?: Record<string, unknown>
  model_bundles?: Record<string, unknown>
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
const knownEndpointSecrets: Record<string, string> = {}
const testResultCacheByEndpoint: Record<string, ProviderTestResult[]> = {}

export function resetLlmApiCachesForTests(): void {
  cachedRegistry = null
  for (const endpointId of Object.keys(knownEndpointSecrets)) delete knownEndpointSecrets[endpointId]
  for (const endpointId of Object.keys(testResultCacheByEndpoint)) delete testResultCacheByEndpoint[endpointId]
}

function segment(value: string): string {
  return encodeURIComponent(value)
}

function routesForEndpoint(registry: CredentialRegistryResponse, endpointId: string): ProviderRoute[] {
  return Object.values(registry.provider_routes).filter((route) => route.endpoint_id === endpointId)
}

export function modelGroupsFromRegistry(registry: RegistryResponse): ModelGroup[] {
  if (registry.model_groups?.length) return registry.model_groups
  return legacyModelGroupsFromRegistry(registry)
}

function legacyModelGroupsFromRegistry(registry: CredentialRegistryResponse): ModelGroup[] {
  const routesByCanonical = new Map<string, ProviderRoute[]>()
  for (const route of Object.values(registry.provider_routes)) {
    const canonicalId = route.canonical_id || route.route_slug
    routesByCanonical.set(canonicalId, [
      ...(routesByCanonical.get(canonicalId) ?? []),
      route,
    ])
  }
  return [...routesByCanonical.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([canonicalId, routes]) => {
      const providerModels = routes
        .sort((left, right) => left.route_id.localeCompare(right.route_id))
        .map((route) => legacyProviderModelOption(registry, route))
        .filter((option): option is ProviderModelOption => option !== null)
      return {
        canonical_id: canonicalId,
        display_name: routes[0]?.display_name ?? canonicalId,
        provider_models: providerModels,
        status_summary: summarizeProviderModelStates(providerModels),
        capability_summary: summarizeProviderModelCapabilities(providerModels),
      }
    })
}

function legacyProviderModelOption(
  registry: CredentialRegistryResponse,
  route: ProviderRoute,
): ProviderModelOption | null {
  const endpoint = registry.provider_endpoints[route.endpoint_id]
  if (!endpoint) return null
  return {
    route_id: route.route_id,
    provider_label: endpoint.display_name,
    provider_kind: endpoint.provider_kind ?? 'third_party',
    provider_model_id: route.provider_model_id,
    ui_state: legacyProviderUiState(endpoint, route),
    ui_detail: legacyProviderUiDetail(endpoint, route),
    retry_at: null,
    reason_code: legacyProviderReasonCode(endpoint, route),
    capability_state: Object.keys(route.capabilities).length > 0 ? 'known' : 'unknown',
    capabilities: route.capabilities,
  }
}

function legacyProviderUiState(endpoint: ProviderEndpoint, route: ProviderRoute): ProviderUiState {
  if (endpoint.status === 'disabled' || route.status === 'disabled') return 'off'
  if (!endpoint.api_key || endpoint.status === 'failed' || route.status === 'failed') return 'needs_setup'
  if (endpoint.status === 'verified' && route.status === 'verified') return 'ready'
  return 'untested'
}

function legacyProviderReasonCode(endpoint: ProviderEndpoint, route: ProviderRoute): string | null {
  if (!endpoint.api_key) return 'missing_key'
  const routeReason = stringMetadata(route.metadata, 'reason_code')
  if (routeReason) return routeReason
  const endpointReason = stringMetadata(endpoint.metadata, 'reason_code')
  if (endpointReason) return endpointReason
  if (route.status === 'failed') return 'route_failed'
  if (endpoint.status === 'failed') return endpointErrorCode(endpoint) ?? 'endpoint_failed'
  return null
}

function legacyProviderUiDetail(endpoint: ProviderEndpoint, route: ProviderRoute): string | null {
  return stringMetadata(route.metadata, 'last_probe_message') ?? endpoint.last_test_message ?? null
}

function stringMetadata(metadata: Record<string, unknown>, key: string): string | null {
  const value = metadata[key]
  return typeof value === 'string' && value.trim() ? value : null
}

function summarizeProviderModelStates(providerModels: ProviderModelOption[]): ModelGroupStatusSummary {
  const summary: ModelGroupStatusSummary = {
    ready: 0,
    untested: 0,
    cooling_down: 0,
    needs_setup: 0,
    off: 0,
  }
  for (const option of providerModels) {
    summary[option.ui_state] += 1
  }
  return summary
}

function summarizeProviderModelCapabilities(providerModels: ProviderModelOption[]): ModelGroupCapabilitySummary {
  return {
    capability_known_count: providerModels.filter((option) => option.capability_state !== 'unknown').length,
    thinking: 'unknown',
    tools: 'unknown',
    structured_output: 'unknown',
    max_context_tokens: null,
    max_output_tokens: null,
  }
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

function cachedResultForCredentialUpdate(update: ProviderCredentialUpdate): ProviderTestResult | null {
  const fingerprint = paramsFingerprint({
    api_key: update.api_key,
    base_url: update.base_url ?? '',
    provider_type: update.provider_type ?? null,
  })
  const results = testResultCacheByEndpoint[update.id] ?? []
  for (let index = results.length - 1; index >= 0; index -= 1) {
    if (results[index].params_fingerprint === fingerprint) return results[index]
  }
  return null
}

function routeStatusFromTestStatus(status: TestStatus): RouteStatus {
  if (status === 'ok') return 'verified'
  if (status === 'untested') return 'unverified_manual'
  return 'failed'
}

function testResultFromEndpoint(
  endpoint: ProviderEndpoint,
  routes: ProviderRoute[],
): ProviderTestResult | null {
  const lastTestStatus = statusToTestStatus(endpoint.status)
  const hasListedModels = (
    lastTestStatus === 'untested' &&
    Boolean(endpoint.last_test_at || endpoint.last_test_message) &&
    routes.length > 0
  )
  const visibleRoutes = lastTestStatus === 'ok' || hasListedModels ? routes : []
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
    available_models: visibleRoutes.map((route) => ({
      id: route.provider_model_id,
      capabilities: route.capabilities,
    })),
    available_sdks: visibleRoutes.length > 0 ? [endpoint.protocol] : [],
  }
}

function endpointToCredential(
  registry: CredentialRegistryResponse,
  endpoint: ProviderEndpoint,
): CredentialProviderState {
  const routes = routesForEndpoint(registry, endpoint.endpoint_id)
  const currentTestResult = testResultFromEndpoint(endpoint, routes)
  const testResults = upsertCachedResult(endpoint.endpoint_id, currentTestResult)
  const activeModels = currentTestResult && (
    currentTestResult.last_test_status === 'ok' ||
    currentTestResult.last_test_status === 'untested'
  )
    ? currentTestResult.available_models ?? []
    : []
  const activeSdks = currentTestResult && (
    currentTestResult.last_test_status === 'ok' ||
    currentTestResult.last_test_status === 'untested'
  )
    ? currentTestResult.available_sdks ?? []
    : []
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
    available_models: activeModels,
    available_sdks: activeSdks,
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
  cachedResult?: ProviderTestResult | null,
): ProviderEndpoint {
  const nextProtocol = update.provider_type ?? existing?.protocol ?? 'openai_compatible'
  const nextBaseUrl = update.base_url ?? existing?.base_url ?? ''
  const nextSecret = update.api_key === redactedSecret
    ? existing?.api_key === redactedSecret ? undefined : existing?.api_key
    : update.api_key ?? existing?.api_key ?? null
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
  const restoredStatus = cachedResult ? routeStatusFromTestStatus(cachedResult.last_test_status) : null
  return {
    endpoint_id: update.id,
    display_name: update.name || existing?.display_name || update.id,
    protocol: nextProtocol,
    base_url: nextBaseUrl,
    api_key: nextSecret,
    status: testParamsChanged ? restoredStatus ?? 'unverified_manual' : existing?.status ?? 'unverified_manual',
    last_test_at: testParamsChanged ? cachedResult?.last_test_at ?? null : existing?.last_test_at ?? null,
    last_test_message: testParamsChanged ? cachedResult?.last_test_message ?? null : existing?.last_test_message ?? null,
    timeout_seconds: existing?.timeout_seconds ?? 120,
    trust_env: existing?.trust_env ?? false,
    proxy_env: existing?.proxy_env ?? null,
    metadata: existing?.metadata ?? {},
  }
}

function rememberEndpointSecret(endpointId: string, apiKey: string | null | undefined): void {
  if (apiKey == null) return
  if (apiKey === redactedSecret) return
  knownEndpointSecrets[endpointId] = apiKey
}

function forgetEndpointSecret(endpointId: string): void {
  delete knownEndpointSecrets[endpointId]
}

function hydrateRegistryWithKnownSecrets<T extends CredentialRegistryResponse>(registry: T): T {
  const providerEndpoints = Object.fromEntries(
    Object.entries(registry.provider_endpoints).map(([endpointId, endpoint]) => {
      const knownSecret = knownEndpointSecrets[endpointId]
      if (endpoint.api_key === redactedSecret && knownSecret !== undefined) {
        return [endpointId, { ...endpoint, api_key: knownSecret }]
      }
      rememberEndpointSecret(endpointId, endpoint.api_key)
      return [endpointId, endpoint]
    }),
  )
  return {
    ...registry,
    provider_endpoints: providerEndpoints,
  } as T
}

function cacheRegistry<T extends CredentialRegistryResponse>(registry: T): T {
  const hydrated = hydrateRegistryWithKnownSecrets(registry)
  cachedRegistry = {
    ...(cachedRegistry ?? {
      model_profiles: {},
      model_groups: [],
      roles: {},
      canonical_groups: [],
      lint_results: [],
      setup_required: false,
    }),
    ...hydrated,
  } as RegistryResponse
  return hydrated
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
  const successfulRoutes = status === 'ok' ? routes : []
  return {
    status,
    latency_ms: null,
    model_seen: successfulRoutes[0]?.provider_model_id ?? null,
    message: endpoint.last_test_message ?? null,
    error_code: endpointErrorCode(endpoint),
    available_models: successfulRoutes.map((route) => ({
      id: route.provider_model_id,
      capabilities: route.capabilities,
    })),
    available_sdks: successfulRoutes.length > 0 ? [endpoint.protocol] : [],
  }
}

export function apiKeysCredentialsFromRegistry(registry: CredentialRegistryResponse): CredentialsState {
  return registryToCredentials(registry)
}

export async function getRegistry(): Promise<RegistryResponse> {
  const response = await api.get<RegistryResponse>('/llm/registry')
  return cacheRegistry(response.data)
}

export async function getEndpointSecret(endpointId: string): Promise<EndpointSecretResponse> {
  const response = await api.get<EndpointSecretResponse>(`/llm/registry/endpoints/${segment(endpointId)}/secret`)
  rememberEndpointSecret(endpointId, response.data.api_key)
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
        rememberEndpointSecret(endpointId, secret.api_key)
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
  for (const [endpointId, endpoint] of Object.entries(providerEndpoints)) {
    rememberEndpointSecret(endpointId, endpoint.api_key)
  }
  const response = await api.put<CredentialRegistryResponse>(
    '/llm/registry/endpoints',
    { provider_endpoints: providerEndpoints },
  )
  return cacheRegistry(response.data)
}

export async function deleteEndpoint(endpointId: string): Promise<CredentialRegistryResponse> {
  const response = await api.delete<CredentialRegistryResponse>(`/llm/registry/endpoints/${segment(endpointId)}`)
  forgetEndpointSecret(endpointId)
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
  const response = await api.post<ProviderEndpoint | EndpointTestResponse>(`/llm/endpoints/${segment(endpointId)}/test`)
  if (isEndpointTestResponse(response.data)) {
    const registry = cacheRegistry(response.data.registry)
    const endpoint = registry.provider_endpoints[endpointId]
    if (endpoint) return endpoint
    throw new Error(`Endpoint test response omitted endpoint: ${endpointId}`)
  }
  rememberEndpointSecret(endpointId, response.data.api_key)
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

function isEndpointTestResponse(value: ProviderEndpoint | EndpointTestResponse): value is EndpointTestResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'registry' in value &&
    typeof (value as EndpointTestResponse).registry === 'object'
  )
}

function isEndpointModelTestResponse(value: unknown): value is EndpointModelTestResponse {
  return (
    typeof value === 'object' &&
    value !== null &&
    'registry' in value &&
    Array.isArray((value as EndpointModelTestResponse).results)
  )
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
      endpointFromCredentialUpdate(
        update,
        existingEndpoints[update.id],
        cachedResultForCredentialUpdate(update),
      ),
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
  rememberEndpointSecret(request.id, request.api_key)
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

export async function getProviderModels(
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
  rememberEndpointSecret(request.id, request.api_key)
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
  const response = await api.post<EndpointTestResponse>(`/llm/endpoints/${segment(request.id)}/test`)
  const registry = cacheRegistry(response.data.registry)
  const endpoint = registry.provider_endpoints[request.id]
  if (!endpoint) throw new Error(`Endpoint model list response omitted endpoint: ${request.id}`)
  const routes = routesForEndpoint(registry, request.id)
  const models = routes.map((route) => ({
    id: route.provider_model_id,
    capabilities: route.capabilities,
  }))
  upsertCachedResult(request.id, {
    params_fingerprint: paramsFingerprint({
      api_key: request.api_key,
      base_url: request.base_url ?? '',
      provider_type: request.provider_type,
    }),
    base_url: request.base_url ?? '',
    provider_type: request.provider_type,
    last_test_status: statusToTestStatus(endpoint.status),
    last_test_at: endpoint.last_test_at ?? '',
    last_test_message: endpoint.last_test_message ?? '',
    last_error_code: endpointErrorCode(endpoint) ?? '',
    available_models: models,
    available_sdks: models.length > 0 ? [endpoint.protocol] : [],
  })
  return {
    status: models.length > 0 ? 'ok' : endpointTestStatus(endpoint),
    latency_ms: null,
    model_seen: models[0]?.id ?? null,
    message: endpoint.last_test_message ?? null,
    error_code: endpointErrorCode(endpoint),
    available_models: models,
    available_sdks: models.length > 0 ? [endpoint.protocol] : [],
  }
}

export async function testProviderEndpoint(
  request: ProviderTestRequest & { model_id: string },
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
  rememberEndpointSecret(request.id, request.api_key)
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
  const response = await api.post<EndpointModelTestResponse>(
    `/llm/endpoints/${segment(request.id)}/models/test`,
    { model_ids: [request.model_id] },
  )
  if (!isEndpointModelTestResponse(response.data)) {
    throw new Error('Endpoint model test response omitted registry results.')
  }
  const registry = cacheRegistry(response.data.registry)
  const endpoint = registry.provider_endpoints[request.id]
  if (!endpoint) throw new Error(`Endpoint model test response omitted endpoint: ${request.id}`)
  return providerTestResponseFromEndpoint(endpoint, registry)
}

export async function getNotableModels(providerKey: string): Promise<NotableModelsResponse> {
  return {
    notable_models: localNotableModels[providerKey.toLowerCase()] ?? ['gpt-5'],
  }
}

export async function testProviderModels(
  request: ProviderModelTestRequest,
): Promise<ProviderModelTestResponse> {
  const response = await api.post<EndpointModelTestResponse>(
    `/llm/endpoints/${segment(request.provider_id)}/models/test`,
    { model_ids: request.model_ids },
  )
  if (!isEndpointModelTestResponse(response.data)) {
    throw new Error('Endpoint model test response omitted registry results.')
  }
  cachedRegistry = response.data.registry
  const endpointRoutes = routesForEndpoint(response.data.registry, request.provider_id)
  return {
    results: response.data.results,
    available_models: endpointRoutes.map((route) => ({
      id: route.provider_model_id,
      capabilities: route.capabilities,
    })),
  }
}

export function providerModelsFromRegistry(
  registry: CredentialRegistryResponse,
  endpointId: string,
): ModelInfo[] {
  return routesForEndpoint(registry, endpointId).map((route) => ({
    id: route.provider_model_id,
    capabilities: route.capabilities,
  }))
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
