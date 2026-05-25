import { api } from './client'

export type ProviderType =
  | 'anthropic_compatible'
  | 'openai_compatible'
  | 'google_genai'

export type RouteStatus = 'verified' | 'unverified_manual' | 'disabled' | 'failed'
export type CapabilitySource = 'api_list' | 'provider_doc' | 'agent_draft' | 'manual' | 'probed_verified'
export type LintSeverity = 'off' | 'warn' | 'error'
export type DraftStatus =
  | 'pending'
  | 'needs_probe'
  | 'probing'
  | 'probed'
  | 'applying'
  | 'applied'
  | 'expired'
  | 'conflicted'
  | 'failed'

export interface CapabilityValue {
  value: unknown
  source: CapabilitySource
  observed_at?: string | null
  message?: string | null
}

export interface FieldSource {
  source: CapabilitySource
  message?: string | null
  observed_at?: string | null
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

export interface RoleRouteEntry {
  route_id: string
  temperature?: number | null
  max_output_tokens?: number | null
}

export interface RoleEntry {
  system_prompt_prefix: string
  source_profile_id?: string | null
  source_profile_snapshot?: Record<string, unknown> | null
  fallback_chain: RoleRouteEntry[]
  lint_requirements: Record<string, LintSeverity>
}

export interface ModelProfile {
  model_profile_id: string
  display_name: string
  canonical_id?: string | null
  tags: string[]
  fallback_chain: RoleRouteEntry[]
  lint_requirements: Record<string, LintSeverity>
}

export interface EndpointCandidate extends ProviderEndpoint {
  field_sources: Record<string, FieldSource>
}

export interface RouteCandidate {
  endpoint_id: string
  route_slug: string
  provider_model_id: string
  canonical_id: string
  display_name: string
  capabilities: Record<string, CapabilityValue>
  field_sources: Record<string, FieldSource>
  metadata: Record<string, unknown>
}

export interface ProbeResult {
  target_type: 'endpoint' | 'route'
  status: 'not_run' | 'running' | 'success' | 'failed'
  observed_at?: string | null
  capabilities: Record<string, CapabilityValue>
  error?: Record<string, unknown> | null
  [key: string]: unknown
}

export interface ProviderImportDraft {
  draft_id: string
  source: Record<string, unknown>
  status: DraftStatus
  created_at?: string | null
  updated_at?: string | null
  expires_at?: string | null
  endpoint_candidates: Record<string, EndpointCandidate>
  route_candidates: Record<string, RouteCandidate>
  probe_results: Record<string, ProbeResult>
  agent_notes: Array<Record<string, unknown>>
  diff: Record<string, unknown>
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

export interface CanonicalGroup {
  canonical_id: string
  display_name: string
  routes: string[]
}

export interface RolesData {
  schema_version: 2
  model_profiles: Record<string, ModelProfile>
  roles: Record<string, RoleEntry>
}

export interface RegistryResponse {
  provider_endpoints: Record<string, ProviderEndpoint>
  provider_routes: Record<string, ProviderRoute>
  runtime_policy: RuntimePolicy
  model_profiles: Record<string, ModelProfile>
  roles: Record<string, RoleEntry>
  canonical_groups: CanonicalGroup[]
  lint_results: LintResult[]
  setup_required: boolean
}

export interface CredentialRegistryResponse {
  schema_version: 4
  provider_endpoints: Record<string, ProviderEndpoint>
  provider_routes: Record<string, ProviderRoute>
  runtime_policy: RuntimePolicy
}

export interface EndpointUpsertRequest {
  provider_endpoints: Record<string, ProviderEndpoint>
}

export interface RouteEditableUpdate {
  display_name: string
  canonical_id: string
  status: RouteStatus
  capabilities: Record<string, CapabilityValue>
  metadata: Record<string, unknown>
}

export interface RouteProbeRequest {
  capabilities: string[]
}

export interface RoleApplyProfileRequest {
  model_profile_id: string
  mode?: 'replace' | null
}

function segment(value: string): string {
  return encodeURIComponent(value)
}

export async function getRegistry(): Promise<RegistryResponse> {
  const response = await api.get<RegistryResponse>('/llm/registry')
  return response.data
}

export async function putRegistryEndpoints(
  providerEndpoints: Record<string, ProviderEndpoint>,
): Promise<CredentialRegistryResponse> {
  const response = await api.put<CredentialRegistryResponse>(
    '/llm/registry/endpoints',
    { provider_endpoints: providerEndpoints },
  )
  return response.data
}

export async function deleteEndpoint(endpointId: string): Promise<CredentialRegistryResponse> {
  const response = await api.delete<CredentialRegistryResponse>(`/llm/registry/endpoints/${segment(endpointId)}`)
  return response.data
}

export async function testEndpoint(endpointId: string): Promise<ProviderEndpoint> {
  const response = await api.post<ProviderEndpoint>(`/llm/endpoints/${segment(endpointId)}/test`)
  return response.data
}

export async function probeRoute(routeId: string, request: RouteProbeRequest): Promise<ProviderRoute> {
  const response = await api.post<ProviderRoute>(`/llm/routes/${segment(routeId)}/probe`, request)
  return response.data
}

export async function putRoute(routeId: string, update: RouteEditableUpdate): Promise<ProviderRoute> {
  const response = await api.put<ProviderRoute>(`/llm/routes/${segment(routeId)}`, update)
  return response.data
}

export async function deleteRoute(routeId: string): Promise<CredentialRegistryResponse> {
  const response = await api.delete<CredentialRegistryResponse>(`/llm/routes/${segment(routeId)}`)
  return response.data
}

export async function createProviderImportDraft(draft: ProviderImportDraft): Promise<ProviderImportDraft> {
  const response = await api.post<ProviderImportDraft>('/llm/import-drafts', draft)
  return response.data
}

export async function getProviderImportDraft(draftId: string): Promise<ProviderImportDraft> {
  const response = await api.get<ProviderImportDraft>(`/llm/import-drafts/${segment(draftId)}`)
  return response.data
}

export async function probeProviderImportDraft(draftId: string): Promise<ProviderImportDraft> {
  const response = await api.post<ProviderImportDraft>(`/llm/import-drafts/${segment(draftId)}/probe`)
  return response.data
}

export async function applyProviderImportDraft(
  draftId: string,
  mode?: 'merge' | null,
): Promise<ProviderImportDraft> {
  const response = await api.post<ProviderImportDraft>(
    `/llm/import-drafts/${segment(draftId)}/apply`,
    undefined,
    mode ? { params: { mode } } : undefined,
  )
  return response.data
}

export async function getRoles(): Promise<RolesData> {
  const response = await api.get<RolesData>('/llm/roles')
  return response.data
}

export async function putRoles(data: RolesData): Promise<RolesData> {
  const response = await api.put<RolesData>('/llm/roles', data)
  return response.data
}

export async function getRole(roleName: string): Promise<RoleEntry> {
  const response = await api.get<RoleEntry>(`/llm/roles/${segment(roleName)}`)
  return response.data
}

export async function putRole(roleName: string, role: RoleEntry): Promise<RoleEntry> {
  const response = await api.put<RoleEntry>(`/llm/roles/${segment(roleName)}`, role)
  return response.data
}

export async function getModelProfiles(): Promise<Record<string, ModelProfile>> {
  const response = await api.get<Record<string, ModelProfile>>('/llm/model-profiles')
  return response.data
}

export async function putModelProfiles(
  modelProfiles: Record<string, ModelProfile>,
): Promise<Record<string, ModelProfile>> {
  const response = await api.put<Record<string, ModelProfile>>('/llm/model-profiles', modelProfiles)
  return response.data
}

export async function deleteModelProfile(modelProfileId: string): Promise<RolesData> {
  const response = await api.delete<RolesData>(`/llm/model-profiles/${segment(modelProfileId)}`)
  return response.data
}

export async function applyModelProfile(
  roleName: string,
  request: RoleApplyProfileRequest,
): Promise<RoleEntry> {
  const response = await api.post<RoleEntry>(`/llm/roles/${segment(roleName)}/apply-profile`, request)
  return response.data
}
