import axios, { AxiosError, AxiosHeaders } from 'axios'
import type { AxiosResponse, InternalAxiosRequestConfig } from 'axios'
import type {
  AppSettings,
  ChildGraphTopology,
  CollaborateResult,
  CompileFailure,
  CompileResult,
  CompileSuccess,
  GitHistoryItem,
  GoldenBaseline,
  GoldenBaselinePlan,
  JsonObject,
  PublishResult,
  PublishSkillReq,
  ReleaseManifest,
  RunDetail,
  RunMetadata,
  ResumeValidityResponse,
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
import { BACKEND_UNAVAILABLE_MESSAGE, isBackendUnavailableError } from '../utils/errors'

export const API_BASE_URL = import.meta.env.VITE_STUDIO_API_BASE_URL ?? 'http://localhost:8787/api'
const BROWSER_WRITE_FALLBACK_CONFIG = {
  headers: {
    'X-Studio-Write-Fallback': 'browser',
  },
}

let currentApiBaseURL = API_BASE_URL
let currentApiToken: string | null = null

export const api = axios.create({
  baseURL: currentApiBaseURL,
})

export function configureApiBaseURL(baseURL: string): void {
  currentApiBaseURL = baseURL
  api.defaults.baseURL = baseURL
}

export function getApiBaseURL(): string {
  return currentApiBaseURL
}

export function configureApiToken(token: string | null): void {
  currentApiToken = token
}

export function currentApiTokenIsSet(): boolean {
  return Boolean(currentApiToken)
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
      ? new Error(BACKEND_UNAVAILABLE_MESSAGE)
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

/**
 * R20: fetch the persisted last-known role/copilot test results so the settings
 * tabs can re-seed their badges on mount (survives server restart / remount).
 * Kept here, NOT in api/llm.ts, so the KEEP-MAIN roles contract is untouched.
 */
export async function getRoleTestResults(): Promise<RoleTestResultsResponse> {
  const response = await api.get<RoleTestResultsResponse>('/llm/roles/test-results')
  return response.data
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
): Promise<SerializeGraphRes> {
  const response = await api.post<SerializeGraphRes>(`/skills/${skillId}/graph/serialize`, {
    phases,
    expected_hash: expectedHash ?? null,
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

export interface PredictRunResponse {
  run_id?: string
  status?: RunMetadata['status']
  metadata?: RunMetadata
  artifact_ref?: RunMetadata['artifact_ref']
  source_map_ref?: string | null
  execution_fingerprint?: string | null
  input_data?: JsonObject | null
  final_context?: JsonObject | null
  output?: JsonObject | null
  artifacts?: string[] | null
}

export async function postPredictRun(skillId: string, inputData: JsonObject): Promise<PredictRunResponse | RunDetail> {
  const response = await api.post<PredictRunResponse | RunDetail>(`/skills/${skillId}/runs/predict`, {
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

export async function startRun(skillId: string, inputData: JsonObject): Promise<RunMetadata> {
  const response = await api.post<RunMetadata>(`/skills/${skillId}/runs`, {
    input_data: inputData,
  })
  return response.data
}

export interface CopilotBashApprovalRequest {
  toolUseId: string
  approve: boolean
}

export interface CopilotBashApprovalResponse {
  tool_use_id: string
  approved: boolean
  executed: boolean
  success: boolean
  stdout: string
  stderr: string
  returncode: number | null
  message: string | null
}

export async function resolveCopilotBashApproval(
  skillId: string,
  request: CopilotBashApprovalRequest,
): Promise<CopilotBashApprovalResponse> {
  const response = await api.post<CopilotBashApprovalResponse>(
    `/skills/${skillId}/copilot/bash-approval`,
    {
      tool_use_id: request.toolUseId,
      approve: request.approve,
    },
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
  return `.workspace/test_inputs/${name}.json`
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
 * F4: resolve the Predict/Run input payload. With a selected test input, fetch
 * its full content; with none selected, fall back to an empty payload (the
 * prior behaviour). A failed fetch (e.g. the input was deleted) propagates so
 * the caller surfaces a clear error instead of silently running empty.
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
