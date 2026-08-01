import axios, { AxiosError, AxiosHeaders } from 'axios'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type {
  AppSettings,
  ChildGraphTopology,
  CollaborateResult,
  CompareCandidate,
  CompareCandidatesMap,
  CompareRunGroupResponse,
  CompareRunResponse,
  NodeCompareCandidates,
  CompileFailure,
  CompileResult,
  CompileSuccess,
  GitHistoryItem,
  GoldenBaseline,
  GoldenBaselineContent,
  GoldenBaselinePlan,
  JsonObject,
  NodeLlmParams,
  NodeLlmParamsMap,
  PredictDiagnosticExport,
  PublishResult,
  PublishSkillReq,
  ReleaseManifest,
  RunDetail,
  RunMetadata,
  ResumeValidityResponse,
  RuntimeArtifactRow,
  RuntimeConfig,
  SerializeGraphRes,
  SkillDetail,
  SyncSkillReq,
  TestInputDetail,
  TestInputMetadata,
  UpdateSkillFileRes,
  SerializableGraphPhaseRef,
} from './types'
import { isTauriRuntime } from '../config/runtime'
import { deleteWorkspacePath, writeWorkspaceFile } from '../lib/tauri'
import { resolveWorkspaceIdentity } from '../components/studio/workspace-identity'
import { BackendUnavailableError, isBackendUnavailableError } from '../utils/errors'

// API base URL is set explicitly by the dev launcher (vite via .env.local) or by the
// Tauri runtime gate (configureApiBaseURL after get_sidecar_config IPC resolves).
// In dev, a missing VITE_STUDIO_API_BASE_URL means the launcher forgot to align with
// the sidecar's dynamic port: silently falling back to a hardcoded 8787 hides the
// misconfig and causes 502s deep in the UI (R-F2). We surface it loudly instead.
// Tests configure the base URL explicitly via configureApiBaseURL — they set
// import.meta.env.VITEST so the throw stays out of the way.
function resolveInitialApiBaseURL(): string {
  const fromEnv = import.meta.env.VITE_STUDIO_API_BASE_URL
  if (typeof fromEnv === 'string' && fromEnv.length > 0) {
    return fromEnv
  }
  // Vitest test runs: keep a sane default; tests override via configureApiBaseURL.
  if (import.meta.env.MODE === 'test' || (import.meta.env as Record<string, unknown>).VITEST) {
    return 'http://localhost:8787/api'
  }
  if (import.meta.env.DEV) {
    const message =
      'VITE_STUDIO_API_BASE_URL is undefined. Launch via Tauri (which injects the dynamic sidecar port) or set VITE_STUDIO_API_BASE_URL in apps/studio/frontend/.env.local to match STUDIO_SIDECAR_PORT.'
    console.error('[studio-client]', message)
    throw new Error(message)
  }
  // Production builds (Tauri webview) replace this at runtime via configureApiBaseURL;
  // the placeholder is intentionally invalid to force the runtime gate.
  return 'http://localhost:8787/api'
}

export const API_BASE_URL = resolveInitialApiBaseURL()
const BROWSER_WRITE_FALLBACK_CONFIG = {
  headers: {
    'X-Studio-Write-Fallback': 'browser',
  },
}

let currentApiBaseURL = API_BASE_URL
let currentApiToken: string | null = null

export const apiClientConfigChangedEvent = 'studio-api-client-config-changed'

export const api = axios.create({
  baseURL: currentApiBaseURL,
})

export function configureApiBaseURL(baseURL: string): void {
  currentApiBaseURL = baseURL
  api.defaults.baseURL = baseURL
  notifyApiClientConfigChanged()
}

export function getApiBaseURL(): string {
  return currentApiBaseURL
}

export function configureApiToken(token: string | null): void {
  currentApiToken = token
  notifyApiClientConfigChanged()
}

export function currentApiTokenIsSet(): boolean {
  return Boolean(currentApiToken)
}

export function authenticatedApiReady(): boolean {
  return !isTauriRuntime() || currentApiTokenIsSet()
}

function notifyApiClientConfigChanged(): void {
  if (typeof window === 'undefined') return
  if (typeof window.dispatchEvent !== 'function') return
  window.dispatchEvent(new Event(apiClientConfigChangedEvent))
}

api.interceptors.request.use((config) => {
  const headers = AxiosHeaders.from(config.headers)
  headers.set('X-Studio-User-ID', 'default')
  if (currentApiToken) {
    headers.set('Authorization', `Bearer ${currentApiToken}`)
  }
  config.headers = headers
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => Promise.reject(
    isBackendUnavailableError(error)
      ? new BackendUnavailableError(error)
      : error,
  ),
)

export async function fetcher<T>(url: string): Promise<T> {
  const response = await api.get<T>(url)
  return response.data
}

/**
 * R20: one durably persisted LAST role/copilot test result. The `result`
 * payload mirrors the backend RoleTestResponse / copilot SDK result shape; it
 * is typed as a loose object here so this read client stays decoupled from the
 * KEEP-MAIN api/llm.ts RolesData contract (callers narrow it in pure helpers).
 */
export interface PersistedRoleTestResult {
  role_name: string
  status: string
  message?: string | null
  result: JsonObject
  updated_at: string
}

export interface RoleTestResultsResponse {
  results: Record<string, PersistedRoleTestResult>
}

export interface RuntimeActivityLogEntry {
  id: string
  recorded_at: string
  source_id: string
  action: string
  message: string
  changes: Record<string, unknown>
}

export interface TruthSource {
  id: string
  label: string
  path: string
  kind: string
  description: string
  open_mode: 'file' | 'directory'
  exists: boolean
  size_bytes: number | null
  updated_at: string | null
  logs: RuntimeActivityLogEntry[]
  can_preview: boolean
}

export interface TruthSourceSection {
  id: string
  label: string
  description: string
  sources: TruthSource[]
}

export interface TruthSourcesResponse {
  sections: TruthSourceSection[]
}

export interface TruthSourceContentResponse {
  source_id: string
  path: string
  kind: string
  content: string
  truncated: boolean
  size_bytes: number
}

let roleTestResultsCache: RoleTestResultsResponse | null = null
let roleTestResultsRequest: Promise<RoleTestResultsResponse> | null = null
let truthSourcesCache: TruthSourcesResponse | null = null
let truthSourcesRequest: Promise<TruthSourcesResponse> | null = null
let communityCatalogConfigCache: CommunityCatalogConfig | null = null
let communityCatalogConfigRequest: Promise<CommunityCatalogConfig> | null = null
const compareCandidatesCache = new Map<string, CompareCandidatesMap>()
const compareCandidatesRequests = new Map<string, Promise<CompareCandidatesMap>>()
const nodeLlmParamsCache = new Map<string, NodeLlmParamsMap>()
const nodeLlmParamsRequests = new Map<string, Promise<NodeLlmParamsMap>>()

export function invalidateRoleTestResultsCache(): void {
  roleTestResultsCache = null
  roleTestResultsRequest = null
}

export function resetClientReadCachesForTests(): void {
  invalidateRoleTestResultsCache()
  truthSourcesCache = null
  truthSourcesRequest = null
  communityCatalogConfigCache = null
  communityCatalogConfigRequest = null
  compareCandidatesCache.clear()
  compareCandidatesRequests.clear()
  nodeLlmParamsCache.clear()
  nodeLlmParamsRequests.clear()
}

/**
 * R20: fetch the persisted last-known role/copilot test results so the settings
 * tabs can re-seed their badges on mount (survives server restart / remount).
 * Kept here, NOT in api/llm.ts, so the KEEP-MAIN roles contract is untouched.
 */
export async function getRoleTestResults(options: { force?: boolean } = {}): Promise<RoleTestResultsResponse> {
  if (!options.force && roleTestResultsCache) return roleTestResultsCache
  if (!options.force && roleTestResultsRequest) return roleTestResultsRequest
  const request = api.get<RoleTestResultsResponse>('/llm/roles/test-results')
    .then((response) => {
      roleTestResultsCache = response.data
      return response.data
    })
    .finally(() => {
      if (roleTestResultsRequest === request) roleTestResultsRequest = null
    })
  roleTestResultsRequest = request
  return request
}

export async function getTruthSources(): Promise<TruthSourcesResponse> {
  if (truthSourcesCache) return truthSourcesCache
  if (truthSourcesRequest) return truthSourcesRequest
  const request = api.get<TruthSourcesResponse>('/system/truth-sources')
    .then((response) => {
      truthSourcesCache = response.data
      return response.data
    })
    .finally(() => {
      if (truthSourcesRequest === request) truthSourcesRequest = null
    })
  truthSourcesRequest = request
  return request
}

export async function getTruthSourceContent(sourceId: string): Promise<TruthSourceContentResponse> {
  const response = await api.get<TruthSourceContentResponse>(
    `/system/truth-sources/${encodeURIComponent(sourceId)}/content`,
  )
  return response.data
}

export interface CommunityCatalogConfig {
  manifest_url: string
  signing_pubkey: string
}

/** Read-only, baked-in community catalog config (manifest URL + signing pubkey). */
export async function getCommunityCatalogConfig(): Promise<CommunityCatalogConfig> {
  if (communityCatalogConfigCache) return communityCatalogConfigCache
  if (communityCatalogConfigRequest) return communityCatalogConfigRequest
  const request = api.get<CommunityCatalogConfig>('/system/community-catalog-config')
    .then((response) => {
      communityCatalogConfigCache = response.data
      return response.data
    })
    .finally(() => {
      if (communityCatalogConfigRequest === request) communityCatalogConfigRequest = null
    })
  communityCatalogConfigRequest = request
  return request
}

export async function getAppSettings(): Promise<AppSettings> {
  const response = await api.get<AppSettings>('/settings')
  return response.data
}

export async function updateAppSettings(settings: AppSettings): Promise<AppSettings> {
  const response = await api.put<AppSettings>('/settings', settings)
  return response.data
}

export async function syncSkill(skillId: string, request: SyncSkillReq): Promise<CollaborateResult> {
  const response = await api.post<CollaborateResult>(`/skills/${skillId}/sync`, request)
  return response.data
}

export async function publishSkill(skillId: string, request: PublishSkillReq = {}): Promise<PublishResult> {
  const response = await api.post<PublishResult>(`/skills/${skillId}/publish`, request)
  return response.data
}

export async function listReleases(skillId: string): Promise<ReleaseManifest[]> {
  const response = await api.get<ReleaseManifest[]>(`/skills/${skillId}/releases`)
  return response.data
}

export async function getRelease(skillId: string, releaseVersion: string): Promise<ReleaseManifest> {
  const response = await api.get<ReleaseManifest>(
    `/skills/${skillId}/releases/${encodeURIComponent(releaseVersion)}`,
  )
  return response.data
}

export async function compileSkill(skillId: string): Promise<CompileResult> {
  try {
    const response = await api.post<CompileSuccess>(`/skills/${skillId}/compile`)
    return response.data
  } catch (error) {
    if (error instanceof AxiosError && isCompileFailure(error.response?.data)) {
      return error.response.data
    }
    throw error
  }
}

export async function serializeSkillGraph(
  skillId: string,
  phases: SerializableGraphPhaseRef[],
  expectedHash?: string | null,
  workspaceRoot?: string | null,
): Promise<SerializeGraphRes> {
  const topologyPhases = phases.map(({ id, src, depends_on, output }) => ({
    id,
    src,
    depends_on,
    ...(output === true ? { output: true } : {}),
  }))
  const response = await api.post<SerializeGraphRes>(`/skills/${skillId}/graph/serialize`, {
    phases: topologyPhases,
    expected_hash: expectedHash ?? null,
    // A drilled subgraph is identified by its absolute path so the backend
    // serializes against THAT GRAPH.md, not a name-colliding bare id. Omitted for
    // the parent graph so its request body is unchanged.
    ...(workspaceRoot ? { workspace_root: workspaceRoot } : {}),
  })
  return response.data
}

function isCompileFailure(value: unknown): value is CompileFailure {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }
  const candidate = value as Partial<CompileFailure>
  return candidate.code === 'compile_failed' && Array.isArray(candidate.errors)
}

export function wsUrl(path: string): string {
  const base = new URL(currentApiBaseURL, window.location.origin)
  const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const separator = normalizedPath.includes('?') ? '&' : '?'
  const tokenQuery = currentApiToken ? `${separator}token=${encodeURIComponent(currentApiToken)}` : ''
  return `${protocol}//${base.host}${normalizedPath}${tokenQuery}`
}

/**
 * N4 atom #30: the predict endpoint returns the PredictDiagnosticExport (is_predict /
 * status / phases / path_diff). The caller reads which AGENT nodes ran from `phases`
 * (a phase is recorded only on completion) to drive the golden 🟡 logic-OK state.
 */
export async function postPredictRun(
  skillId: string,
  inputData: JsonObject,
): Promise<PredictDiagnosticExport> {
  const response = await api.post<PredictDiagnosticExport>(`/skills/${skillId}/runs/predict`, {
    input_data: inputData,
  })
  return response.data
}

export async function saveGoldenBaseline(
  skillId: string,
  runId: string,
  lock = false,
  workspaceRoot?: string | null,
  nodeId?: string | null,
): Promise<GoldenBaseline> {
  const apiSkillId = resolveWorkspaceIdentity(skillId).skillId ?? skillId
  // N4 atom #32: when nodeId is set, write golden for that agent node only
  // (SetGoldenReq.node_id). Omitted entirely otherwise to preserve the existing
  // run-level baseline request shape.
  const goldenRequest: { run_id: string; lock: boolean; node_id?: string } = { run_id: runId, lock }
  if (nodeId) {
    goldenRequest.node_id = nodeId
  }
  if (isTauriRuntime()) {
    const response = await api.post<GoldenBaselinePlan>(`/skills/${apiSkillId}/golden/plan`, goldenRequest)
    const plan = response.data
    const targetRoot = resolveGoldenWorkspaceRoot(skillId, workspaceRoot)
    for (const file of plan.files) {
      await writeWorkspaceFile(
        targetRoot,
        file.path,
        file.content,
        null,
        { createIfAbsent: true },
      )
    }
    return plan.baseline
  }
  const response = await api.post<GoldenBaseline>(
    `/skills/${apiSkillId}/golden`,
    goldenRequest,
    BROWSER_WRITE_FALLBACK_CONFIG,
  )
  return response.data
}

export async function listGoldenBaselines(skillId: string): Promise<GoldenBaseline[]> {
  const response = await api.get<GoldenBaseline[]>(`/skills/${skillId}/golden`)
  return response.data
}

/**
 * N4 atom #29 read path: open an existing golden baseline's stored content for editing.
 * The list endpoint only carries per-node case metadata (an `expected_output_ref`); this
 * resolves the ref to the actual `expected_output` so the I/O panel can show an editable
 * JSON view. With `nodeId` the backend scopes the response to that node's single case.
 * Read-only — this adds NO write path.
 */
export async function fetchGoldenContent(
  skillId: string,
  goldenId: string,
  nodeId?: string | null,
): Promise<GoldenBaselineContent> {
  const apiSkillId = resolveWorkspaceIdentity(skillId).skillId ?? skillId
  const response = await api.get<GoldenBaselineContent>(
    `/skills/${apiSkillId}/golden/${encodeURIComponent(goldenId)}/content`,
    nodeId ? { params: { node_id: nodeId } } : undefined,
  )
  return response.data
}

export async function startRun(skillId: string, inputData: JsonObject): Promise<RunMetadata> {
  const response = await api.post<RunMetadata>(`/skills/${skillId}/runs`, {
    input_data: inputData,
  })
  return response.data
}

export interface CopilotToolApprovalRequest {
  toolUseId: string
  approve: boolean
}

export interface CopilotToolApprovalResponse {
  tool_use_id: string
  approved: boolean
  /** False when the approval no longer exists (resolved/timed out/reset). */
  resolved: boolean
  message: string | null
}

export async function resolveCopilotToolApproval(
  skillId: string,
  request: CopilotToolApprovalRequest,
): Promise<CopilotToolApprovalResponse> {
  const response = await api.post<CopilotToolApprovalResponse>(
    `/skills/${skillId}/copilot/tool-approval`,
    {
      tool_use_id: request.toolUseId,
      approve: request.approve,
    },
  )
  return response.data
}

export interface CopilotInterruptResponse {
  /** False when there was no active turn to stop — an idempotent no-op. */
  interrupted: boolean
}

/** R7-I stop button: interrupt the copilot's active streaming turn for a skill. */
export async function interruptCopilot(skillId: string): Promise<CopilotInterruptResponse> {
  const response = await api.post<CopilotInterruptResponse>(
    `/skills/${skillId}/copilot/interrupt`,
  )
  return response.data
}

export interface CopilotJudgeRequest {
  runResultsRef: string
  baselineRef: string
}

export interface CopilotJudgeResponse {
  compare_result_ref: string
  judge_context_ref: string
  baseline_ref: string
  diff_summary: {
    baseline_id: string
    run_results_ref: string
    total_score: number
    node_group_count: number
    failed_node_count: number
  }
}

export async function prepareCopilotJudgeContext(
  skillId: string,
  request: CopilotJudgeRequest,
): Promise<CopilotJudgeResponse> {
  const response = await api.post<CopilotJudgeResponse>(
    `/skills/${skillId}/copilot/judge`,
    {
      run_results_ref: request.runResultsRef,
      baseline_ref: request.baselineRef,
    },
  )
  return response.data
}

/**
 * Resume a run from its last checkpoint (the headline lifecycle's debug step).
 * Optional context_overrides / human_input feed an intervened resume; omitted
 * for a plain continue.
 */
export interface ResumeHumanResponseInput {
  content: string
  toolCallId?: string | null
}

export interface ResumeRunOptions {
  checkpointId?: string
  checkpointNs?: string
  resumeFromNodeId?: string
  resumeToNodeId?: string
  contextOverrides?: JsonObject
  humanInput?: string
  humanResponse?: ResumeHumanResponseInput
}

export interface ResumeValidityOptions {
  checkpointId?: string
  checkpointNs?: string
  resumeFromNodeId?: string
  resumeToNodeId?: string
}

function resumeHumanResponsePayload(response: ResumeHumanResponseInput | undefined): JsonObject | null {
  if (!response) return null
  const payload: JsonObject = { content: response.content }
  if (response.toolCallId !== undefined) {
    payload.tool_call_id = response.toolCallId
  }
  return payload
}

export async function resumeRun(
  skillId: string,
  runId: string,
  options: ResumeRunOptions = {},
): Promise<RunMetadata> {
  const payload: JsonObject = {
    context_overrides: options.contextOverrides ?? null,
    human_input: options.humanInput ?? null,
  }
  if (options.checkpointId !== undefined) payload.checkpoint_id = options.checkpointId
  if (options.checkpointNs !== undefined) payload.checkpoint_ns = options.checkpointNs
  if (options.resumeFromNodeId !== undefined) payload.resume_from_node_id = options.resumeFromNodeId
  if (options.resumeToNodeId !== undefined) payload.resume_to_node_id = options.resumeToNodeId
  const humanResponse = resumeHumanResponsePayload(options.humanResponse)
  if (humanResponse !== null) payload.human_response = humanResponse

  const response = await api.post<RunMetadata>(
    `/skills/${skillId}/runs/${encodeURIComponent(runId)}/resume`,
    payload,
  )
  return response.data
}

export async function getResumeValidity(
  skillId: string,
  runId: string,
  options: ResumeValidityOptions = {},
): Promise<ResumeValidityResponse> {
  const payload: JsonObject = {}
  if (options.checkpointId !== undefined) payload.checkpoint_id = options.checkpointId
  if (options.checkpointNs !== undefined) payload.checkpoint_ns = options.checkpointNs
  if (options.resumeFromNodeId !== undefined) payload.resume_from_node_id = options.resumeFromNodeId
  if (options.resumeToNodeId !== undefined) payload.resume_to_node_id = options.resumeToNodeId

  const response = await api.post<ResumeValidityResponse>(
    `/skills/${skillId}/runs/${encodeURIComponent(runId)}/resume/validity`,
    payload,
  )
  return response.data
}

export async function createTestInput(
  skillId: string,
  name: string,
  content: JsonObject,
  options: { workspaceRoot?: string | null } = {},
): Promise<TestInputMetadata> {
  if (isTauriRuntime()) {
    const safeName = validateTestInputName(name)
    const path = testInputPath(safeName)
    const workspaceRoot = resolveTestInputWorkspaceRoot(skillId, options.workspaceRoot)
    const payload = JSON.stringify(content, null, 2)
    await writeWorkspaceFile(workspaceRoot, path, payload, null, { createIfAbsent: true })
    return {
      id: safeName,
      name: safeName,
      created_at: new Date().toISOString(),
      size_bytes: utf8ByteLength(payload),
      content_preview: previewJson(payload),
    }
  }
  const response = await api.post<TestInputMetadata>(`/skills/${skillId}/test_inputs`, {
    name,
    content,
  }, BROWSER_WRITE_FALLBACK_CONFIG)
  return response.data
}

export async function deleteTestInput(
  skillId: string,
  inputId: string,
  options: { workspaceRoot?: string | null } = {},
): Promise<void> {
  if (isTauriRuntime()) {
    const safeName = validateTestInputName(inputId)
    await deleteWorkspacePath(
      resolveTestInputWorkspaceRoot(skillId, options.workspaceRoot),
      testInputPath(safeName),
    )
    return
  }
  await api.delete(
    `/skills/${skillId}/test_inputs/${encodeURIComponent(inputId)}`,
    BROWSER_WRITE_FALLBACK_CONFIG,
  )
}

const TEST_INPUT_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/
const MAX_TEST_INPUT_NAME_LENGTH = 100

function validateTestInputName(raw: string): string {
  let name = raw.trim()
  if (name.toLowerCase().endsWith('.json')) {
    name = name.slice(0, -'.json'.length)
  }
  if (!name || name.length > MAX_TEST_INPUT_NAME_LENGTH || !TEST_INPUT_NAME_RE.test(name)) {
    throw new Error(`Invalid test input name: ${raw}`)
  }
  return name
}

function testInputPath(name: string): string {
  return `.workspace/import_files/${name}.json`
}

function resolveTestInputWorkspaceRoot(skillId: string, workspaceRoot?: string | null): string {
  if (workspaceRoot?.trim()) {
    return workspaceRoot.trim()
  }
  return resolveWorkspaceRoot(skillId)
}

function resolveGoldenWorkspaceRoot(skillId: string, workspaceRoot?: string | null): string {
  if (workspaceRoot?.trim()) {
    return workspaceRoot.trim()
  }
  return resolveWorkspaceRoot(skillId)
}

function resolveWorkspaceRoot(skillId: string): string {
  return resolveWorkspaceIdentity(skillId).workspaceRoot ?? skillId
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).byteLength
}

function previewJson(raw: string): string {
  try {
    return truncatePreview(JSON.stringify(JSON.parse(raw)))
  } catch {
    return truncatePreview(raw.replace(/\n/g, ' '))
  }
}

function truncatePreview(value: string): string {
  return value.length > 120 ? `${value.slice(0, 120)}...` : value
}

export async function getTestInput(skillId: string, inputId: string): Promise<TestInputDetail> {
  const response = await api.get<TestInputDetail>(
    `/skills/${skillId}/test_inputs/${encodeURIComponent(inputId)}`,
  )
  return response.data
}

/**
 * F4: resolve the Predict/Run input payload. A selected test input overrides
 * the payload with its stored content; with no selection the payload is empty
 * and the graph's root inputs come from the runtime_config import bindings the
 * backend already owns ("predict 和 run 就是按照配置来跑就行了",
 * `docs/studio/mvp1/01_workflows/04_run-and-verify.md:35`).
 *
 * The client deliberately does NOT gate on selection: whether the inputs are
 * actually sourced is a preflight verdict, and it belongs to the one
 * diagnostics pipeline (STUDIO_RUNTIME_INPUT_MISSING / _CONFLICT), not to a
 * second opinion invented here. A failed fetch still propagates, so a deleted
 * selection surfaces as an error instead of silently running empty.
 */
export async function resolveRunInput(
  skillId: string,
  selectedTestInputId: string | null,
  getInput: (skillId: string, inputId: string) => Promise<TestInputDetail> = getTestInput,
): Promise<JsonObject> {
  if (!selectedTestInputId) {
    return {}
  }
  const detail = await getInput(skillId, selectedTestInputId)
  return detail.content
}

export async function getRunDetail(skillId: string, runId: string): Promise<RunDetail> {
  const response = await api.get<RunDetail>(
    `/skills/${skillId}/runs/${encodeURIComponent(runId)}`,
  )
  return response.data
}

/**
 * PR2 node-level Compare LLMs: read every node's persisted compare candidates for
 * a skill. GET `/skills/{id}/compare-candidates` → CompareCandidatesMap.
 */
export async function getCompareCandidates(skillId: string): Promise<CompareCandidatesMap> {
  const cached = compareCandidatesCache.get(skillId)
  if (cached) return cached
  const inflight = compareCandidatesRequests.get(skillId)
  if (inflight) return inflight
  const request = api.get<CompareCandidatesMap>(`/skills/${skillId}/compare-candidates`)
    .then((response) => {
      compareCandidatesCache.set(skillId, response.data)
      return response.data
    })
    .finally(() => {
      if (compareCandidatesRequests.get(skillId) === request) {
        compareCandidatesRequests.delete(skillId)
      }
    })
  compareCandidatesRequests.set(skillId, request)
  return request
}

/**
 * PR2: replace one node's compare candidates (an empty list clears the node).
 * PUT `/skills/{id}/nodes/{node_id}/compare-candidates` → NodeCompareCandidates.
 */
export async function putNodeCompareCandidates(
  skillId: string,
  nodeId: string,
  candidates: CompareCandidate[],
): Promise<NodeCompareCandidates> {
  const response = await api.put<NodeCompareCandidates>(
    `/skills/${skillId}/nodes/${encodeURIComponent(nodeId)}/compare-candidates`,
    { candidates },
  )
  const current = compareCandidatesCache.get(skillId)
  if (current) {
    compareCandidatesCache.set(skillId, {
      nodes: {
        ...current.nodes,
        [nodeId]: response.data.candidates,
      },
    })
  }
  compareCandidatesRequests.delete(skillId)
  return response.data
}

/**
 * PR2: launch isolated single-node side-runs for a node's persisted candidates,
 * off a completed base run. Each side-run feeds the node the base run's exact
 * input and swaps only the model. POST `/skills/{id}/runs/{base_run_id}/compare`
 * → CompareRunResponse (poll via getCompareGroup).
 */
export async function startNodeCompareRun(
  skillId: string,
  baseRunId: string,
  nodeId: string,
): Promise<CompareRunResponse> {
  const response = await api.post<CompareRunResponse>(
    `/skills/${skillId}/runs/${encodeURIComponent(baseRunId)}/compare`,
    { node_id: nodeId },
  )
  return response.data
}

/**
 * PR2: fetch the per-candidate side-runs for one compare group so the Trace top
 * tabs can render one tab per candidate (per-candidate failure read from each
 * run's `metadata.status`). GET `/skills/{id}/runs/compare/{compare_group_id}`.
 */
export async function getCompareGroup(
  skillId: string,
  compareGroupId: string,
): Promise<CompareRunGroupResponse> {
  const response = await api.get<CompareRunGroupResponse>(
    `/skills/${skillId}/runs/compare/${encodeURIComponent(compareGroupId)}`,
  )
  return response.data
}

/**
 * PR3: read every node's persisted LLM param overrides for a skill.
 * GET `/skills/{id}/node-llm-params` → NodeLlmParamsMap.
 */
export async function getNodeLlmParams(skillId: string): Promise<NodeLlmParamsMap> {
  const cached = nodeLlmParamsCache.get(skillId)
  if (cached) return cached
  const inflight = nodeLlmParamsRequests.get(skillId)
  if (inflight) return inflight
  const request = api.get<NodeLlmParamsMap>(`/skills/${skillId}/node-llm-params`)
    .then((response) => {
      nodeLlmParamsCache.set(skillId, response.data)
      return response.data
    })
    .finally(() => {
      if (nodeLlmParamsRequests.get(skillId) === request) {
        nodeLlmParamsRequests.delete(skillId)
      }
    })
  nodeLlmParamsRequests.set(skillId, request)
  return request
}

/**
 * PR3: replace one node's LLM param overrides (an all-null body clears the node).
 * PUT `/skills/{id}/nodes/{node_id}/node-llm-params` → NodeLlmParams.
 */
export async function putNodeLlmParams(
  skillId: string,
  nodeId: string,
  params: NodeLlmParams,
): Promise<NodeLlmParams> {
  const response = await api.put<NodeLlmParams>(
    `/skills/${skillId}/nodes/${encodeURIComponent(nodeId)}/node-llm-params`,
    params,
  )
  const current = nodeLlmParamsCache.get(skillId)
  if (current) {
    nodeLlmParamsCache.set(skillId, {
      nodes: {
        ...current.nodes,
        [nodeId]: response.data,
      },
    })
  }
  nodeLlmParamsRequests.delete(skillId)
  return response.data
}

export async function getLocalHistory(skillId: string): Promise<GitHistoryItem[]> {
  const response = await api.get<GitHistoryItem[]>(`/skills/${skillId}/history`)
  return response.data
}

export async function revertSkill(skillId: string, sha: string): Promise<SkillDetail> {
  const response = await api.post<SkillDetail>(`/skills/${skillId}/revert`, { sha })
  return response.data
}

export async function getSkillDetail(skillId: string): Promise<SkillDetail> {
  const response = await api.get<SkillDetail>(`/skills/${skillId}`)
  return response.data
}

/**
 * Resolve a subgraph's real child-graph topology by its absolute `path`.
 * The backend resolver (`GET /skills/{skillId}/subgraph`) returns the child
 * graph's phases + topology so the inline preview renders real child phases
 * instead of a mock. A missing/invalid path yields a typed 404/422 the caller
 * surfaces as an error state.
 */
export async function getChildGraphTopology(
  skillId: string,
  path: string,
): Promise<ChildGraphTopology> {
  const response = await api.get<ChildGraphTopology>(`/skills/${skillId}/subgraph`, {
    params: { path },
  })
  return response.data
}

interface TauriHashConflictError {
  type: 'HashConflict'
  data?: {
    current_hash?: string
    current_content?: string
  }
}

function isTauriHashConflictError(error: unknown): error is TauriHashConflictError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'type' in error &&
    error.type === 'HashConflict'
  )
}

export async function writeSkillFile(
  skillId: string,
  path: string,
  content: string,
  expectedHash?: string | null,
): Promise<UpdateSkillFileRes> {
  if (isTauriRuntime()) {
    try {
      const res = await writeWorkspaceFile(skillId, path, content, expectedHash ?? null)
      return {
        path: res.path,
        hash: res.hash,
      }
    } catch (err: unknown) {
      if (isTauriHashConflictError(err)) {
        const conflictData = err.data || {}
        const responseData = {
          current_hash: conflictData.current_hash || '',
          current_markdown_content: conflictData.current_content || '',
        }
        const mockConfig: InternalAxiosRequestConfig = {
          headers: new AxiosHeaders(),
        }
        const mockResponse: AxiosResponse = {
          data: responseData,
          status: 409,
          statusText: 'Conflict',
          headers: {},
          config: mockConfig,
        }
        const mockAxiosError = new AxiosError(
          'Hash conflict',
          'ERR_BAD_RESPONSE',
          mockConfig,
          null,
          mockResponse
        )
        mockAxiosError.isAxiosError = true
        throw mockAxiosError
      }
      throw err
    }
  }

  const encodedPath = path.split('/').map(encodeURIComponent).join('/')
  const response = await api.post<UpdateSkillFileRes>(`/skills/${skillId}/files/${encodedPath}`, {
    content,
    expected_hash: expectedHash ?? null,
  }, {
    headers: { 'X-Studio-Write-Fallback': 'browser' },
  })
  return response.data
}

// --- IO scan / import (input config tree, input region F5) ---

export interface IoScanField {
  name: string
  type: string
  value_type?: string
  content_type?: string
  sample?: unknown
  items?: IoScanField[]
}

export interface IoScanEntry {
  kind: 'file' | 'batch' | 'dir'
  name: string
  stem?: string
  path?: string
  dir?: string
  pattern?: string
  numbers?: number[]
  count?: number
  format?: string
  content_type?: string
  size?: number
  fields?: IoScanField[]
  entries?: IoScanEntry[]
}

export async function scanIoPath(path: string): Promise<{ entries: IoScanEntry[] }> {
  const response = await api.post<{ entries: IoScanEntry[] }>(`/io/scan`, { path })
  return response.data
}

export async function importIoIntoWorkspace(
  skillId: string,
  path: string,
  options: { name?: string; nodeId?: string | null } = {},
): Promise<{ dir: string; entries: IoScanEntry[] }> {
  const response = await api.post<{ dir: string; entries: IoScanEntry[] }>(
    `/skills/${skillId}/io/import`,
    {
      path,
      ...(options.name ? { name: options.name } : {}),
      ...(options.nodeId ? { node_id: options.nodeId } : {}),
    },
  )
  return response.data
}

export async function getRuntimeConfig(skillId: string): Promise<RuntimeConfig> {
  const response = await api.get<RuntimeConfig>(`/skills/${skillId}/runtime-config`)
  return response.data
}

export async function putRuntimeArtifacts(
  skillId: string,
  artifacts: RuntimeArtifactRow[],
): Promise<RuntimeConfig> {
  const response = await api.put<RuntimeConfig>(`/skills/${skillId}/runtime-config/artifacts`, { artifacts })
  return response.data
}
