import { api } from './client'

export type ProviderType =
  | 'anthropic_compatible'
  | 'ark_runtime'
  | 'openai_compatible'
  | 'google_genai'

export type RouteStatus = 'verified' | 'unverified_manual' | 'disabled' | 'failed' | 'probe-verified'
export type ModelProbeStatus = RouteStatus | 'testing'
export type ProviderKind = 'official' | 'third_party' | 'custom'
export type ProviderUiState = 'ready' | 'historical_ready' | 'untested' | 'cooling_down' | 'failed' | 'off'
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
  credential_ref?: string | null
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

export type ProviderEndpointWrite = Omit<ProviderEndpoint, 'status' | 'last_test_at' | 'last_test_message'>

export interface VerifiedProfile {
  profile_id: string
  capability: string
  method_id: string
  request_mapper_id: string
  status: 'ready' | 'failed' | 'catalog_candidate'
  default?: boolean
  fallback_rank?: number
  input_modalities?: string[]
  output_modalities?: string[]
  runtime_overrides?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface ProviderRoute {
  route_id: string
  endpoint_id: string
  route_slug: string
  provider_model_id: string
  canonical_id: string
  display_name?: string | null
  status: RouteStatus
  /** Backend-projected 6-state UI status (apikeys#30); GET /llm/registry stamps it per route. */
  ui_state: ProviderUiState
  capabilities: Record<string, CapabilityValue>
  verified_profiles?: VerifiedProfile[]
  metadata: Record<string, unknown>
}

export interface CredentialRegistryResponse {
  schema_version?: 4
  provider_endpoints: Record<string, ProviderEndpoint>
  provider_routes: Record<string, ProviderRoute>
  runtime_policy: RuntimePolicy
  probe_catalog?: ProbeCatalogSummary | null
}

export interface CanonicalGroup {
  canonical_id: string
  display_name: string
  routes: string[]
}

export interface ProviderModelOption {
  route_id: string
  endpoint_id?: string | null
  provider_label: string
  provider_kind: ProviderKind
  provider_model_id: string
  model_type?: string | null
  capability_family?: string | null
  input_modalities?: string[]
  output_modalities?: string[]
  ui_state: ProviderUiState
  ui_detail?: string | null
  retry_at?: string | null
  reason_code?: string | null
  capability_state: CapabilityState
  capabilities: Record<string, CapabilityValue>
  /**
   * R-F8: the route's gateway call method id (e.g. `anthropic_messages`,
   * `ark_anthropic_messages`). Used by CopilotTab to keep ONLY routes that
   * the Claude Agent SDK / Anthropic Messages caller can actually drive.
   * Optional for backward-compat with model groups built before the field
   * was emitted; absent value means "not eligible for copilot".
   */
  call_method_id?: string | null
}

export interface ModelGroupStatusSummary {
  ready: number
  historical_ready: number
  untested: number
  cooling_down: number
  failed: number
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
  section_label?: string
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

export interface ProbeCatalogSharingStatus {
  mode: 'local_export_only'
  auto_upload_enabled: boolean
  message: string
}

/**
 * One advisory community-verified route projected from the disposable verified
 * cache. Community-observed evidence — never the user's own verified route.
 */
export interface CommunityCatalogEntry {
  public_base_url: string | null
  model_id: string | null
  capability_family: string | null
  method_id: string | null
  observed_at: string | null
}

/**
 * Verified community catalog (disposable cache) status for the Settings UI.
 * Advisory only — these records are never auto-applied to local credentials.
 */
export interface CommunityCatalogSummary {
  synced: boolean
  generated_at: string | null
  protocol_major: number
  record_count: number
  entries: CommunityCatalogEntry[]
}

export interface ProbeCatalogSummary {
  local_evidence_records_count: number
  local_verified_records_count: number
  local_failed_records_count: number
  local_route_candidates_count: number
  community_catalog: CommunityCatalogSummary
  sharing: ProbeCatalogSharingStatus
}

/**
 * Response from the verified community catalog read path
 * (`POST /llm/catalog/sync-verified`). Dormant config returns
 * `status: 'disabled'`; a successful pull returns `status: 'success'` with the
 * verified record count. The displayed evidence is read back from the registry
 * snapshot's `probe_catalog.community_catalog`, not from this response.
 */
export interface VerifiedCatalogSyncResponse {
  status: 'success' | 'disabled'
  verified_sync_enabled: boolean
  sync_status?: string
  record_count?: number
  manifest_etag?: string | null
  protocol_major?: number
  /**
   * Phase 5: verified evidence is merged straight into credentials route.evidence
   * (no disposable cache). This is the count of routes whose evidence actually changed.
   */
  merged_route_count?: number
  message?: string
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
  route_id?: string
  endpoint_id?: string
  status?: ModelProbeStatus
  /** Backend-projected 6-state UI status carried from the route (apikeys#30). */
  ui_state?: ProviderUiState
  verified_profile_count?: number
  verified_profiles?: VerifiedProfile[]
  last_probe_message?: string | null
  capabilities?: Record<string, unknown>
}

export interface ProviderTestResult {
  params_fingerprint: string
  base_url: string
  runtime_base_url?: string
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
  runtime_base_url?: string
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
  probe_catalog?: ProbeCatalogSummary | null
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
  name?: string
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

export type RoleProviderPreference = 'manual_order'
export type RoleThinkingPreference = 'off' | 'preferred' | 'required'
export type RoleTokenIntentMode = 'default' | 'maximum_available' | 'required_minimum' | 'target'
export type RoleTokenDowngrade = 'allow' | 'allow_with_warning' | 'block'

export interface RoleTokenIntent {
  mode: RoleTokenIntentMode
  value?: number | null
  downgrade?: RoleTokenDowngrade
}

export interface RoleIntent {
  provider_preference?: RoleProviderPreference
  thinking?: RoleThinkingPreference
  target_context_tokens?: RoleTokenIntent | null
  target_output_tokens?: RoleTokenIntent | null
  cost_priority?: 'quality' | 'balanced' | 'low_cost' | null
}

export interface RoleEntry {
  role_kind?: RoleKind
  model_fallback_enabled: boolean
  intent?: RoleIntent
  active_model: string
  models: Record<string, RoleModelEntry>
  model_groups?: RoleModelGroup[]
  materialization_report?: MaterializationReport
  fallback_chain?: RoleRouteEntry[]
  lint_requirements?: Record<string, LintSeverity>
  source_profile_id?: string | null
  source_profile_snapshot?: Record<string, unknown> | null
  system_prompt_prefix?: string | null
  // #51: a by-reference bundle link. When set the role's chain is materialized
  // from the referenced bundle (live), not a snapshot copy of its routes.
  bundle_id?: string | null
}

export interface ModelBundleEntry {
  model_profile_id: string
  display_name: string
  canonical_id: string
  tags?: string[]
  model_fallback_enabled?: boolean
  intent?: RoleIntent
  model_groups?: RoleModelGroup[]
  fallback_chain?: RoleRouteEntry[]
  lint_requirements?: Record<string, LintSeverity>
  materialization_report?: MaterializationReport
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

export type RoleTestStatus = 'ok' | 'warning' | 'blocked' | 'failed'
export type RoleTestProviderStatus = 'ok' | 'untested' | 'blocked' | 'failed'
export type RoleTestAdmissionDecision = 'admit' | 'temporary_skip' | 'block'

export interface RoleTestProviderResult {
  route_id: string
  provider_label: string
  provider_ui_state: ProviderUiState
  role_fit: RoleFitState
  admission_decision: RoleTestAdmissionDecision
  status: RoleTestProviderStatus
  warnings: Array<Record<string, unknown>>
  retry_at?: string | null
  message?: string | null
  resolved_settings: Record<string, unknown>
}

export interface RoleTestModelGroupResult {
  canonical_id: string
  display_name: string
  provider_results: RoleTestProviderResult[]
}

export interface RoleTestResponse {
  role_name: string
  status: RoleTestStatus
  warnings: Array<Record<string, unknown>>
  model_groups: RoleTestModelGroupResult[]
}

export type RoleTestJobStatus = 'queued' | 'running' | 'completed' | 'failed'
// R-F11: extend with "cooling_down" so the copilot SDK probe path can surface
// rate-limit-driven cooldowns (anthropic 429) directly into the route lights.
export type RoleTestProviderProgressStatus =
  | 'queued'
  | 'testing'
  | 'ok'
  | 'failed'
  | 'blocked'
  | 'untested'
  | 'cooling_down'

export interface RoleTestProviderProgress {
  canonical_id: string
  route_id: string
  status: RoleTestProviderProgressStatus
  message?: string | null
  // R-F21: when status === 'cooling_down', the suggested cooldown in seconds so
  // the Test Button can render a `Cooling down {n}s` countdown and stay disabled
  // until it elapses. Optional/null for non-cooldown states.
  retry_after_seconds?: number | null
}

export interface RoleTestJobResponse {
  job_id: string
  role_name: string
  status: RoleTestJobStatus
  message?: string | null
  provider_statuses: RoleTestProviderProgress[]
  result?: RoleTestResponse | null
  /**
   * R-F9: gateway error code (e.g. "resource.no_available_route") attached
   * when `status === 'failed'`. Pairs with `message` (human Chinese text)
   * + `error_payload` (debug context). Optional/null for normal runs.
   */
  error_code?: string | null
  error_payload?: Record<string, unknown> | null
}

interface BackendRolesData {
  schema_version: 3
  model_profiles: Record<string, unknown>
  model_bundles: Record<string, ModelBundleEntry>
  roles: Record<string, BackendRoleEntry>
}

interface BackendRoleEntry {
  role_kind: RoleKind
  system_prompt_prefix: string
  model_fallback_enabled: boolean
  intent: RoleIntent
  model_groups: RoleModelGroup[]
  fallback_chain: RoleRouteEntry[]
  lint_requirements: Record<string, LintSeverity>
  source_profile_id?: string | null
  source_profile_snapshot?: Record<string, unknown> | null
  bundle_id?: string | null
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
  endpoint_id?: string | null
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
  model_bundles?: Record<string, ModelBundleEntry>
  roles: Record<string, RoleEntry>
  single_model_roles?: string[]
  peer_model_groups?: Record<string, string[]>
  circuit_breaker?: Record<string, unknown> | null
  [key: string]: unknown
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

function comparableBaseUrl(value?: string | null): string {
  return (value ?? '').trim().replace(/\/+$/, '').toLowerCase()
}

function endpointProtocolSlot(endpoint: ProviderEndpoint): ProviderType {
  return providerTypeFromEndpointId(endpoint.endpoint_id) ?? endpoint.protocol
}

function providerTypeFromEndpointId(endpointId: string): ProviderType | null {
  const normalized = endpointId.toLowerCase()
  if (normalized.includes('-openai-') || normalized.endsWith('-openai')) return 'openai_compatible'
  if (normalized.includes('-anthropic-') || normalized.endsWith('-anthropic')) return 'anthropic_compatible'
  if (normalized.includes('-google-') || normalized.endsWith('-google')) return 'google_genai'
  if (normalized.includes('-ark-') || normalized.endsWith('-ark')) return 'ark_runtime'
  return null
}

function endpointIdForRequest(
  registry: CredentialRegistryResponse,
  request: ProviderTestRequest,
): string {
  if (registry.provider_endpoints[request.id]) return request.id
  return endpointForRequest(registry, request)?.endpoint_id ?? request.id
}

function endpointForRequest(
  registry: CredentialRegistryResponse | null | undefined,
  request: ProviderTestRequest,
): ProviderEndpoint | null {
  if (!registry) return null
  if (registry.provider_endpoints[request.id]) return registry.provider_endpoints[request.id]
  const targetBaseUrl = comparableBaseUrl(request.base_url)
  const match = Object.values(registry.provider_endpoints).find((endpoint) => (
    endpointProtocolSlot(endpoint) === request.provider_type &&
    (comparableBaseUrl(endpoint.base_url) === targetBaseUrl || comparableBaseUrl(endpointStudioBaseUrl(endpoint)) === targetBaseUrl)
  ))
  return match ?? null
}

export function modelGroupsFromRegistry(registry: RegistryResponse): ModelGroup[] {
  return registry.model_groups ?? []
}

function summarizeProviderModelStates(providerModels: ProviderModelOption[]): ModelGroupStatusSummary {
  const summary: ModelGroupStatusSummary = {
    ready: 0,
    historical_ready: 0,
    untested: 0,
    cooling_down: 0,
    failed: 0,
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

function modelBundleGroupsFromBackend(
  data: RolesData,
  baseModelGroups: ModelGroup[],
): ModelGroup[] {
  const routeOptions = providerModelOptionsByRouteId(baseModelGroups)
  return Object.entries(data.model_bundles ?? {}).flatMap(([bundleId, bundle]) => {
    const providerModels = bundleRouteIds(bundle)
      .map((routeId) => routeOptions.get(routeId) ?? null)
      .filter((option): option is ProviderModelOption => option !== null)
    if (providerModels.length === 0) return []
    return [{
      canonical_id: `bundle:${bundleId}`,
      display_name: bundle.display_name || bundleId,
      section_label: 'Model Bundles',
      provider_models: providerModels,
      status_summary: summarizeProviderModelStates(providerModels),
      capability_summary: summarizeProviderModelCapabilities(providerModels),
    }]
  })
}

function providerModelOptionsByRouteId(
  modelGroups: ModelGroup[],
): Map<string, ProviderModelOption> {
  const routeOptions = new Map<string, ProviderModelOption>()
  for (const group of modelGroups) {
    for (const option of group.provider_models) {
      routeOptions.set(option.route_id, option)
    }
  }
  return routeOptions
}

function bundleRouteIds(bundle: ModelBundleEntry): string[] {
  const routeIds = bundle.fallback_chain?.length
    ? bundle.fallback_chain.map((entry) => entry.route_id)
    : (bundle.model_groups ?? []).flatMap((group) => (
        group.provider_models.map((providerModel) => providerModel.route_id)
      ))
  return [...new Set(routeIds.filter(Boolean))]
}

function rolesDataFromBackend(
  data: RolesData,
  registry: RegistryResponse | null,
): RolesData {
  if (hasLegacyRoleMaps(data)) return data

  const registryModelGroups = registry ? modelGroupsFromRegistry(registry) : []
  const modelGroups = registry
    ? [...modelBundleGroupsFromBackend(data, registryModelGroups), ...registryModelGroups]
    : []
  const models = Object.fromEntries(
    modelGroups.map((group) => [
      group.canonical_id,
      {
        name: group.display_name,
        reasoning: modelGroupSupportsThinking(group) || undefined,
        providers: Object.fromEntries(
          group.provider_models.map((option) => [option.route_id, option.provider_model_id]),
        ),
      },
    ]),
  )
  const providers = registry
    ? Object.fromEntries(
        modelGroups.flatMap((group) => (
          group.provider_models.map((option) => [
            option.route_id,
            providerEntryFromModelOption(registry, option),
          ])
        )),
      )
    : {}
  return {
    ...data,
    schema_version: data.schema_version ?? 3,
    models,
    providers,
    roles: Object.fromEntries(
      Object.entries(data.roles ?? {}).map(([roleName, role]) => [
        roleName,
        roleEntryFromBackend(roleName, role, data),
      ]),
    ),
  }
}

function hasLegacyRoleMaps(data: RolesData): boolean {
  return Boolean(data.models && data.providers)
}

function roleEntryFromBackend(roleName: string, role: RoleEntry, data: RolesData): RoleEntry {
  if (role.models && role.active_model !== undefined && role.model_fallback_enabled !== undefined) return role
  const modelGroups = role.model_groups ?? []
  const models = Object.fromEntries(
    modelGroups.map((group) => [
      group.canonical_id,
      {
        providers: group.provider_models.map((providerModel) => providerModel.route_id),
      },
    ]),
  )
  return {
    ...role,
    role_kind: role.role_kind ?? inferRoleKind(data, roleName),
    model_fallback_enabled: role.model_fallback_enabled ?? true,
    active_model: modelGroups[0]?.canonical_id ?? '',
    models,
    fallback_chain: role.fallback_chain ?? [],
    lint_requirements: role.lint_requirements ?? {},
    bundle_id: role.bundle_id ?? null,
  }
}

export function rolesDataToBackend(data: RolesData): BackendRolesData {
  return {
    schema_version: 3,
    model_profiles: data.model_profiles ?? {},
    model_bundles: data.model_bundles ?? {},
    roles: Object.fromEntries(
      Object.entries(data.roles).map(([roleName, role]) => [
        roleName,
        roleEntryToBackend(data, roleName, role),
      ]),
    ),
  }
}

function roleEntryToBackend(
  data: RolesData,
  roleName: string,
  role: RoleEntry,
): BackendRoleEntry {
  const entry: BackendRoleEntry = {
    role_kind: role.role_kind ?? inferRoleKind(data, roleName),
    system_prompt_prefix: role.system_prompt_prefix ?? '',
    model_fallback_enabled: role.model_fallback_enabled ?? true,
    intent: role.intent ?? { provider_preference: 'manual_order' },
    model_groups: Object.entries(role.models).map(([modelCode, roleModel]) => ({
      canonical_id: modelCode,
      display_name: data.models[modelCode]?.name ?? modelCode,
      provider_models: roleModel.providers.map((routeId) => ({ route_id: routeId })),
    })),
    fallback_chain: [],
    lint_requirements: role.lint_requirements ?? {},
  }
  if (role.source_profile_id !== undefined) entry.source_profile_id = role.source_profile_id
  if (role.source_profile_snapshot !== undefined) {
    entry.source_profile_snapshot = role.source_profile_snapshot
  }
  // #51: persist the bundle reference so the backend materializes the chain by
  // reference (live bundle edits reflect; this role is not a snapshot copy).
  if (role.bundle_id != null) entry.bundle_id = role.bundle_id
  return entry
}

function providerEntryFromModelOption(
  registry: RegistryResponse,
  option: ProviderModelOption,
): ProviderEntry {
  const route = registry.provider_routes[option.route_id]
  const endpoint = route ? registry.provider_endpoints[route.endpoint_id] : null
  return {
    name: option.provider_label,
    endpoint_id: endpoint?.endpoint_id ?? option.endpoint_id ?? endpointIdFromRouteId(option.route_id),
    type: endpoint?.protocol ?? 'openai_compatible',
  }
}

function endpointIdFromRouteId(routeId: string): string | null {
  const separatorIndex = routeId.indexOf(':')
  if (separatorIndex <= 0) return null
  return routeId.slice(0, separatorIndex)
}

function modelGroupSupportsThinking(group: ModelGroup): boolean {
  if (group.capability_summary.thinking === 'supported' || group.capability_summary.thinking === 'mixed') {
    return true
  }
  return group.provider_models.some((option) => {
    const capabilities = option.capabilities
    return Boolean(
      capabilities.thinking?.value ||
      capabilities.reasoning?.value ||
      capabilities.supports_thinking?.value ||
      capabilities.thinking_protocol?.value,
    )
  })
}

function inferRoleKind(data: RolesData, roleName: string): RoleKind {
  if (data.single_model_roles?.includes(roleName)) return 'copilot'
  if (roleName.toLowerCase().includes('copilot')) return 'copilot'
  return 'graph_agent'
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

function modelInfoFromRoute(route: ProviderRoute): ModelInfo {
  const lastProbeMessage = route.metadata.last_probe_message
  const capabilities: Record<string, unknown> = { ...route.capabilities }
  const reasonCode = route.metadata.reason_code
  if (typeof reasonCode === 'string' && reasonCode.trim()) capabilities.reason_code = reasonCode
  const probeAttempts = route.metadata.probe_attempts
  if (Array.isArray(probeAttempts)) capabilities.probe_attempts = probeAttempts
  return {
    id: route.provider_model_id,
    route_id: route.route_id,
    endpoint_id: route.endpoint_id,
    status: route.status,
    ui_state: route.ui_state,
    verified_profile_count: (route.verified_profiles ?? []).filter((profile) => profile.status === 'ready').length,
    verified_profiles: route.verified_profiles ?? [],
    last_probe_message: typeof lastProbeMessage === 'string' ? lastProbeMessage : null,
    capabilities,
  }
}

function catalogCandidateModelInfos(endpoint: ProviderEndpoint, routes: ProviderRoute[]): ModelInfo[] {
  const library = endpoint.metadata.capability_library
  if (!Array.isArray(library)) return []
  const routedModelIds = new Set(routes.map((route) => route.provider_model_id))
  const models: ModelInfo[] = []
  for (const entry of library) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) continue
    const candidate = entry as Record<string, unknown>
    const modelId = candidate.model_id
    if (typeof modelId !== 'string' || !modelId || routedModelIds.has(modelId)) continue
    models.push({
      id: modelId,
      status: routeStatusFromMetadata(candidate.route_status) ?? 'unverified_manual',
      verified_profile_count: 0,
      last_probe_message: typeof candidate.last_probe_message === 'string'
        ? candidate.last_probe_message
        : null,
      capabilities: catalogCandidateCapabilities(candidate),
    })
  }
  return models
}

function catalogCandidateCapabilities(candidate: Record<string, unknown>): Record<string, unknown> {
  const capabilities: Record<string, unknown> = {}
  const modelType = candidate.model_type
  const modelTypeLabel = candidate.model_type_label
  const candidateMethods = candidate.candidate_methods
  const inputModalities = candidate.input_modalities
  const outputModalities = candidate.output_modalities
  const inputModalitiesSource = candidate.input_modalities_source
  const outputModalitiesSource = candidate.output_modalities_source
  const inputModalitiesSourceUrls = candidate.input_modalities_source_urls
  const outputModalitiesSourceUrls = candidate.output_modalities_source_urls
  const probeAttempts = candidate.probe_attempts
  const maxInputTokens = candidate.max_input_tokens
  const maxOutputTokens = candidate.max_output_tokens
  const maxInputTokensSource = candidate.max_input_tokens_source
  const maxOutputTokensSource = candidate.max_output_tokens_source
  const maxInputTokensSourceUrls = candidate.max_input_tokens_source_urls
  const maxOutputTokensSourceUrls = candidate.max_output_tokens_source_urls
  if (typeof modelType === 'string') capabilities.model_type = modelType
  if (typeof modelTypeLabel === 'string') capabilities.model_type_label = modelTypeLabel
  if (Array.isArray(candidateMethods)) {
    capabilities.candidate_methods = candidateMethods.filter((method): method is string => typeof method === 'string')
  }
  if (Array.isArray(inputModalities)) {
    capabilities.input_modalities = inputModalities.filter((modality): modality is string => typeof modality === 'string')
  }
  if (Array.isArray(outputModalities)) {
    capabilities.output_modalities = outputModalities.filter((modality): modality is string => typeof modality === 'string')
  }
  if (typeof inputModalitiesSource === 'string') capabilities.input_modalities_source = inputModalitiesSource
  if (typeof outputModalitiesSource === 'string') capabilities.output_modalities_source = outputModalitiesSource
  if (Array.isArray(inputModalitiesSourceUrls)) {
    capabilities.input_modalities_source_urls = inputModalitiesSourceUrls.filter((url): url is string => typeof url === 'string')
  }
  if (Array.isArray(outputModalitiesSourceUrls)) {
    capabilities.output_modalities_source_urls = outputModalitiesSourceUrls.filter((url): url is string => typeof url === 'string')
  }
  if (typeof maxInputTokens === 'number') capabilities.max_input_tokens = maxInputTokens
  if (typeof maxOutputTokens === 'number') capabilities.max_output_tokens = maxOutputTokens
  if (typeof maxInputTokensSource === 'string') capabilities.max_input_tokens_source = maxInputTokensSource
  if (typeof maxOutputTokensSource === 'string') capabilities.max_output_tokens_source = maxOutputTokensSource
  if (Array.isArray(maxInputTokensSourceUrls)) {
    capabilities.max_input_tokens_source_urls = maxInputTokensSourceUrls.filter((url): url is string => typeof url === 'string')
  }
  if (Array.isArray(maxOutputTokensSourceUrls)) {
    capabilities.max_output_tokens_source_urls = maxOutputTokensSourceUrls.filter((url): url is string => typeof url === 'string')
  }
  if (Array.isArray(probeAttempts)) capabilities.probe_attempts = probeAttempts
  return capabilities
}

function routeStatusFromMetadata(value: unknown): RouteStatus | null {
  if (value === 'verified' || value === 'unverified_manual' || value === 'disabled' || value === 'failed') {
    return value
  }
  return null
}

function testResultFromEndpoint(
  endpoint: ProviderEndpoint,
  routes: ProviderRoute[],
): ProviderTestResult | null {
  const baseUrl = endpointStudioBaseUrl(endpoint)
  const providerType = endpointProtocolSlot(endpoint)
  const verdict = endpointTestVerdict(endpoint, routes)
  const hasListedModels = (
    verdict.testStatus === 'untested' &&
    Boolean(endpoint.last_test_at || endpoint.last_test_message) &&
    routes.length > 0
  )
  const hasKnownModels = Boolean(endpoint.last_test_at || endpoint.last_test_message) && routes.length > 0
  const visibleRoutes = verdict.testStatus === 'ok' || hasListedModels || hasKnownModels ? routes : []
  return {
    params_fingerprint: paramsFingerprint({
      api_key: endpoint.api_key ?? '',
      base_url: baseUrl,
      provider_type: providerType,
    }),
    base_url: baseUrl,
    runtime_base_url: endpoint.base_url,
    provider_type: providerType,
    last_test_status: verdict.testStatus,
    last_test_at: endpoint.last_test_at ?? '',
    last_test_message: endpoint.last_test_message ?? '',
    last_error_code: verdict.errorCode ?? '',
    available_models: [
      ...visibleRoutes.map(modelInfoFromRoute),
      ...(endpoint.provider_kind === 'official' ? catalogCandidateModelInfos(endpoint, routes) : []),
    ],
    available_sdks: visibleRoutes.length > 0 || catalogCandidateModelInfos(endpoint, routes).length > 0
      ? [endpoint.protocol]
      : [],
  }
}

function endpointStudioBaseUrl(endpoint: ProviderEndpoint): string {
  const value = endpoint.metadata.studio_base_url
  return typeof value === 'string' && value.trim() ? value : endpoint.base_url
}

function endpointToCredential(
  registry: CredentialRegistryResponse,
  endpoint: ProviderEndpoint,
): CredentialProviderState {
  const routes = routesForEndpoint(registry, endpoint.endpoint_id)
  const providerType = endpointProtocolSlot(endpoint)
  const currentTestResult = testResultFromEndpoint(endpoint, routes)
  const verdict = endpointTestVerdict(endpoint, routes)
  const testResults = upsertCachedResult(endpoint.endpoint_id, currentTestResult)
  const activeModels = currentTestResult && (currentTestResult.available_models?.length ?? 0) > 0
    ? currentTestResult.available_models ?? []
    : []
  const activeSdks = currentTestResult && (currentTestResult.available_sdks?.length ?? 0) > 0
    ? currentTestResult.available_sdks ?? []
    : []
  return {
    id: endpoint.endpoint_id,
    name: endpoint.display_name,
    api_key: endpoint.api_key ?? '',
    base_url: endpointStudioBaseUrl(endpoint),
    runtime_base_url: endpoint.base_url,
    provider_type: providerType,
    last_test_status: verdict.testStatus,
    last_test_at: endpoint.last_test_at ?? '',
    last_test_message: endpoint.last_test_message ?? '',
    last_error_code: verdict.errorCode ?? '',
    available_models: activeModels,
    available_sdks: activeSdks,
    test_results: testResults,
  }
}

function registryToCredentials(registry: CredentialRegistryResponse): CredentialsState {
  return {
    providers: Object.values(registry.provider_endpoints)
      .map((endpoint) => endpointToCredential(registry, endpoint)),
    probe_catalog: registry.probe_catalog ?? null,
  }
}

function endpointFromCredentialUpdate(
  update: ProviderCredentialUpdate,
  existing?: ProviderEndpoint,
): ProviderEndpointWrite {
  const nextProtocol = update.provider_type ?? existing?.protocol ?? 'openai_compatible'
  const nextBaseUrl = update.base_url ?? existing?.base_url ?? ''
  const nextSecret = update.api_key === redactedSecret
    ? existing?.api_key === redactedSecret ? undefined : existing?.api_key
    : update.api_key ?? existing?.api_key ?? null
  return {
    endpoint_id: update.id,
    display_name: update.name || existing?.display_name || update.id,
    protocol: nextProtocol,
    base_url: nextBaseUrl,
    api_key: nextSecret,
    ...(existing?.credential_ref !== undefined ? { credential_ref: existing.credential_ref } : {}),
    timeout_seconds: existing?.timeout_seconds ?? 120,
    trust_env: existing?.trust_env ?? false,
    proxy_env: existing?.proxy_env ?? null,
    metadata: {
      ...(existing?.metadata ?? {}),
      ...(nextBaseUrl ? { studio_base_url: nextBaseUrl } : {}),
    },
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

function cacheRegistry(registry: CredentialRegistryResponse): RegistryResponse {
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
  return cachedRegistry
}

type EndpointFailureScope = 'endpoint' | 'model' | 'unknown'

type EndpointTestVerdict = {
  responseStatus: ProviderTestStatus
  testStatus: TestStatus
  errorCode?: string
  hasCompletedTest: boolean
}

function endpointTestVerdict(endpoint: ProviderEndpoint, routes: ProviderRoute[]): EndpointTestVerdict {
  const hasCompletedTest = Boolean(
    endpoint.last_test_at ||
    endpoint.last_test_message ||
    endpoint.status === 'verified' ||
    endpoint.status === 'failed',
  )
  const endpointFailure = endpointFailureScope(endpoint, routes)
  if (
    endpoint.status === 'verified' ||
    (hasCompletedTest && routes.some((route) => routeCanProveEndpointUsable(endpoint, route)))
  ) {
    return {
      responseStatus: 'ok',
      testStatus: 'ok',
      hasCompletedTest,
    }
  }
  if (!endpoint.api_key) {
    return {
      responseStatus: 'missing_api_key',
      testStatus: 'untested',
      hasCompletedTest,
    }
  }

  if (endpointFailure === 'model') {
    return {
      responseStatus: 'error',
      testStatus: 'error',
      errorCode: endpointErrorCode(endpoint),
      hasCompletedTest,
    }
  }
  if (endpointFailure === 'endpoint' || endpointFailure === 'unknown') {
    const status = endpointTestStatus(endpoint)
    return {
      responseStatus: status,
      testStatus: status === 'missing_api_key' ? 'untested' : status,
      errorCode: endpointErrorCode(endpoint),
      hasCompletedTest,
    }
  }

  return {
    responseStatus: endpointTestStatus(endpoint),
    testStatus: statusToTestStatus(endpoint.status),
    errorCode: endpoint.status === 'failed' ? endpointErrorCode(endpoint) : undefined,
    hasCompletedTest,
  }
}

function routeIsUsable(route: ProviderRoute): boolean {
  return (
    route.status === 'verified' ||
    route.status === 'probe-verified' ||
    route.ui_state === 'ready' ||
    route.ui_state === 'historical_ready' ||
    (route.verified_profiles ?? []).some((profile) => profile.status === 'ready')
  )
}

function routeCanProveEndpointUsable(endpoint: ProviderEndpoint, route: ProviderRoute): boolean {
  if (!routeIsUsable(route)) return false
  if (endpoint.status !== 'failed') return true
  if (endpointMessageFailureScope(endpoint.last_test_message) === 'model') return true
  return routeHasExplicitOkEvidence(route)
}

function routeHasExplicitOkEvidence(route: ProviderRoute): boolean {
  if ((route.verified_profiles ?? []).some((profile) => profile.status === 'ready')) return true
  return typeof route.metadata.reason_code === 'string' && route.metadata.reason_code.trim().toLowerCase() === 'ok'
}

function endpointFailureScope(endpoint: ProviderEndpoint, routes: ProviderRoute[]): EndpointFailureScope | undefined {
  const routeFailures = routes
    .map(routeFailureScope)
    .filter((scope): scope is EndpointFailureScope => Boolean(scope))
  if (routeFailures.includes('endpoint')) return 'endpoint'
  const endpointScope = endpointMessageFailureScope(endpoint.last_test_message)
  if (endpointScope === 'endpoint') return 'endpoint'
  if (routeFailures.length > 0 && routeFailures.every((scope) => scope === 'model')) return 'model'
  if (endpointScope === 'model') return 'model'
  if (endpoint.status === 'failed') return routeFailures.length > 0 ? 'unknown' : 'endpoint'
  return undefined
}

function routeFailureScope(route: ProviderRoute): EndpointFailureScope | undefined {
  if (route.status !== 'failed' && route.ui_state !== 'failed') return undefined
  const reason = typeof route.metadata.reason_code === 'string'
    ? route.metadata.reason_code.trim().toLowerCase()
    : ''
  const attempts = Array.isArray(route.metadata.probe_attempts)
    ? route.metadata.probe_attempts
      .filter((attempt): attempt is Record<string, unknown> => Boolean(attempt) && typeof attempt === 'object' && !Array.isArray(attempt))
      .map((attempt) => (typeof attempt.status === 'string' ? attempt.status.trim().toLowerCase() : ''))
      .filter(Boolean)
    : []
  if (reason === 'ok' || attempts.includes('ok')) return undefined
  if (reason === 'invalid_model' || reason === 'model_not_found' || attempts.includes('invalid_model') || attempts.includes('model_not_found')) {
    return 'model'
  }
  const messageScope = endpointMessageFailureScope(
    typeof route.metadata.last_probe_message === 'string' ? route.metadata.last_probe_message : null,
  )
  if (messageScope) return messageScope
  if (reason === 'error') return 'endpoint'
  return 'unknown'
}

function endpointMessageFailureScope(message: string | null | undefined): EndpointFailureScope | undefined {
  const normalized = (message ?? '').toLowerCase()
  if (!normalized) return undefined
  if (normalized.includes('invalid_model') || normalized.includes('model_not_found') || normalized.includes('no available channels for model')) {
    return 'model'
  }
  if (
    normalized.includes('invalid api key') ||
    normalized.includes('authentication_error') ||
    normalized.includes('direct access to') ||
    normalized.includes('use /v1/messages') ||
    normalized.includes('chat/completions is not allowed') ||
    normalized.includes('upstream_error') ||
    normalized.includes('processing_error') ||
    normalized.includes('service temporarily unavailable') ||
    normalized.includes('timeout') ||
    normalized.includes('network')
  ) {
    return 'endpoint'
  }
  return undefined
}

function endpointErrorCode(endpoint: ProviderEndpoint): string | undefined {
  const message = endpoint.last_test_message ?? ''
  const normalized = message.toLowerCase()
  const match = [...message.matchAll(/\(([a-z][a-z0-9_:-]+)\)/gi)]
    .map((item) => item[1])
    .find((code) => code && code !== 'error')
  if (match) return match
  if (normalized.includes('invalid_model')) return 'invalid_model'
  if (normalized.includes('model_not_found')) return 'model_not_found'
  if (normalized.includes('invalid api key')) return 'invalid_api_key'
  if (normalized.includes('authentication_error')) return 'invalid_api_key'
  if (normalized.includes('rate limited') || normalized.includes('429')) return 'rate_limited'
  if (normalized.includes('quota') || normalized.includes('billing')) return 'quota_exceeded'
  if (normalized.includes('timed out') || normalized.includes('timeout')) return 'timeout'
  if (normalized.includes('network error')) return 'network_error'
  if (normalized.includes('upstream_error')) return 'upstream_error'
  if (normalized.includes('processing_error')) return 'processing_error'
  if (normalized.includes('direct access to') || normalized.includes('use /v1/messages')) return 'protocol_mismatch'
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
  const verdict = endpointTestVerdict(endpoint, routes)
  const successfulRoutes = verdict.responseStatus === 'ok' ? routes.filter(routeIsUsable) : []
  return {
    status: verdict.responseStatus,
    latency_ms: null,
    model_seen: successfulRoutes[0]?.provider_model_id ?? null,
    message: endpoint.last_test_message ?? null,
    error_code: verdict.errorCode ?? null,
    available_models: (verdict.hasCompletedTest ? routes : successfulRoutes).map(modelInfoFromRoute),
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

/**
 * Pull the signed community catalog via the verified read path and merge the verified
 * evidence straight into credentials route.evidence (Phase 5: no disposable cache). The
 * merged evidence is surfaced back through the registry snapshot's
 * `probe_catalog.community_catalog`, so callers refetch the registry afterwards.
 */
export async function syncVerifiedCommunityCatalog(): Promise<VerifiedCatalogSyncResponse> {
  const response = await api.post<VerifiedCatalogSyncResponse>('/llm/catalog/sync-verified')
  cachedRegistry = null
  return response.data
}

export async function getModelGroups(): Promise<ModelGroup[]> {
  const registry = cachedRegistry ?? await getRegistry()
  return modelGroupsFromRegistry(registry)
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
  providerEndpoints: Record<string, ProviderEndpointWrite>,
): Promise<RegistryResponse> {
  for (const [endpointId, endpoint] of Object.entries(providerEndpoints)) {
    rememberEndpointSecret(endpointId, endpoint.api_key)
  }
  const response = await api.put<CredentialRegistryResponse>(
    '/llm/registry/endpoints',
    { provider_endpoints: providerEndpoints },
  )
  return cacheRegistry(response.data)
}

export async function deleteEndpoint(endpointId: string): Promise<RegistryResponse> {
  const response = await api.delete<CredentialRegistryResponse>(`/llm/registry/endpoints/${segment(endpointId)}`)
  forgetEndpointSecret(endpointId)
  return cacheRegistry(response.data)
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

export async function probeRoute(
  routeId: string,
  request: { capabilities: string[]; force?: boolean },
): Promise<ProviderRoute> {
  const { force, ...body } = request
  const forceQuery = force ? '?force=true' : ''
  const response = await api.post<ProviderRoute>(`/llm/routes/${segment(routeId)}/probe${forceQuery}`, body)
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

export async function getCredentials({
  hydrateSecrets = true,
}: {
  hydrateSecrets?: boolean
} = {}): Promise<CredentialsState> {
  const registry = hydrateSecrets ? await hydrateEndpointSecrets(await getRegistry()) : await getRegistry()
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
      ),
    ]),
  )
  if (Object.keys(providerEndpoints).length > 0) {
    await putRegistryEndpoints(providerEndpoints)
  }
  const registry = await getRegistry()
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
  const existing = endpointForRequest(cachedRegistry, request)
  const upsertedRegistry = await putRegistryEndpoints({
    [request.id]: endpointFromCredentialUpdate(
      {
        id: request.id,
        name: request.name ?? existing?.display_name ?? request.id,
        api_key: request.api_key,
        base_url: request.base_url ?? existing?.base_url ?? '',
        provider_type: request.provider_type,
      },
      existing ?? undefined,
    ),
  })
  const endpoint = await testEndpoint(endpointIdForRequest(upsertedRegistry, request))
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
  const existing = endpointForRequest(cachedRegistry, request)
  // Pre-test upsert persists the edited draft (base_url normalized server-side)
  // before the endpoint is exercised — see design atom #25 ("测试前置 upsert 落 endpoint").
  const upsertedRegistry = await putRegistryEndpoints({
    [request.id]: endpointFromCredentialUpdate(
      {
        id: request.id,
        name: request.name ?? existing?.display_name ?? request.id,
        api_key: request.api_key,
        base_url: request.base_url ?? existing?.base_url ?? '',
        provider_type: request.provider_type,
      },
      existing ?? undefined,
    ),
  })
  const endpointId = endpointIdForRequest(upsertedRegistry, request)
  // apikeys#24/#25/#30: official AND third-party share the single POST
  // /endpoints/{id}/test entry. The backend returns endpoint + route evidence;
  // the UI-level verdict is route-first: any usable route makes the endpoint
  // usable, while model-scoped failures (invalid_model/model_not_found) must not
  // mark the URL+protocol endpoint itself as failed.
  const response = await api.post<EndpointTestResponse>(`/llm/endpoints/${segment(endpointId)}/test`)
  const registry = cacheRegistry(response.data.registry)
  const endpoint = registry.provider_endpoints[endpointId]
  if (!endpoint) throw new Error(`Endpoint model list response omitted endpoint: ${endpointId}`)
  const routes = routesForEndpoint(registry, endpointId)
  const verdict = endpointTestVerdict(endpoint, routes)
  const routeModels = routes.map(modelInfoFromRoute)
  const models = verdict.hasCompletedTest ? routeModels : []
  const responseStatus = verdict.hasCompletedTest ? verdict.responseStatus : 'error'
  const responseMessage = endpoint.last_test_message ??
    (verdict.hasCompletedTest ? null : 'Endpoint test returned without a completed result.')
  const lastTestStatus = verdict.hasCompletedTest ? verdict.testStatus : 'error'
  const usableRoute = routes.find(routeIsUsable)
  const cachedResult: ProviderTestResult = {
    params_fingerprint: paramsFingerprint({
      api_key: request.api_key,
      base_url: request.base_url ?? '',
      provider_type: request.provider_type,
    }),
    base_url: request.base_url ?? '',
    runtime_base_url: endpoint.base_url,
    provider_type: request.provider_type,
    last_test_status: lastTestStatus,
    last_test_at: endpoint.last_test_at ?? '',
    last_test_message: responseMessage ?? '',
    last_error_code: verdict.errorCode ?? '',
    available_models: models,
    available_sdks: usableRoute ? [endpoint.protocol] : [],
  }
  upsertCachedResult(endpointId, cachedResult)
  if (endpointId !== request.id) upsertCachedResult(request.id, cachedResult)
  return {
    status: responseStatus,
    latency_ms: null,
    model_seen: usableRoute?.provider_model_id ?? null,
    message: responseMessage,
    error_code: verdict.errorCode ?? null,
    available_models: models,
    available_sdks: usableRoute ? [endpoint.protocol] : [],
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
  const existing = endpointForRequest(cachedRegistry, request)
  await putRegistryEndpoints({
    [request.id]: endpointFromCredentialUpdate(
      {
        id: request.id,
        name: request.name ?? existing?.display_name ?? request.id,
        api_key: request.api_key,
        base_url: request.base_url ?? existing?.base_url ?? '',
        provider_type: request.provider_type,
      },
      existing ?? undefined,
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
  const response = await api.get<NotableModelsResponse>(
    `/llm/providers/notable-models?provider_key=${encodeURIComponent(providerKey)}`,
  )
  return response.data
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
    available_models: endpointRoutes.map(modelInfoFromRoute),
  }
}

export function providerModelsFromRegistry(
  registry: CredentialRegistryResponse,
  endpointId: string,
): ModelInfo[] {
  return routesForEndpoint(registry, endpointId).map(modelInfoFromRoute)
}

export async function getRoles(): Promise<RolesData> {
  const response = await api.get<RolesData>('/llm/roles')
  const registry = cachedRegistry ?? await getRegistry()
  return rolesDataFromBackend(response.data, registry)
}

export async function getRole(roleName: string): Promise<RoleEntry> {
  const response = await api.get<RoleEntry>(`/llm/roles/${roleName}`)
  return response.data
}

export async function putRoles(data: RolesData): Promise<RolesData> {
  const response = await api.put<RolesData>('/llm/roles', rolesDataToBackend(data))
  return rolesDataFromBackend(response.data, cachedRegistry ?? null)
}

export async function deleteRole(roleName: string): Promise<RolesData> {
  const response = await api.delete<RolesData>(`/llm/roles/${segment(roleName)}`)
  return rolesDataFromBackend(response.data, cachedRegistry ?? null)
}

export async function deleteModelBundle(bundleId: string): Promise<RolesData> {
  const response = await api.delete<RolesData>(`/llm/model-bundles/${segment(bundleId)}`)
  return rolesDataFromBackend(response.data, cachedRegistry ?? null)
}

export async function testRole(roleName: string): Promise<RoleTestResponse> {
  const response = await api.post<RoleTestResponse>(`/llm/roles/${segment(roleName)}/test`, {})
  return response.data
}

export async function startRoleTestJob(roleName: string): Promise<RoleTestJobResponse> {
  const response = await api.post<RoleTestJobResponse>(`/llm/roles/${segment(roleName)}/test-jobs`, {})
  return response.data
}

// #50b: bundle Test reuses the role test-job orchestration. The backend resolves
// the bundle via a transient materialized role (no persisted-store pollution) and
// keys the job under __bundle__{id}; the same getRoleTestJob poll loop applies.
export async function startBundleTestJob(bundleId: string): Promise<RoleTestJobResponse> {
  const response = await api.post<RoleTestJobResponse>(
    `/llm/model-bundles/${segment(bundleId)}/test-jobs`,
    {},
  )
  return response.data
}

export async function getRoleTestJob(jobId: string): Promise<RoleTestJobResponse> {
  const response = await api.get<RoleTestJobResponse>(`/llm/role-test-jobs/${segment(jobId)}`)
  return response.data
}
