import axios, { AxiosError, AxiosHeaders } from 'axios'
import type { AxiosResponse } from 'axios'
import type {
  AppSettings,
  CollaborateResult,
  CompileFailure,
  CompileResult,
  CompileSuccess,
  GitHistoryItem,
  GoldenBaseline,
  JsonObject,
  PublishResult,
  PublishSkillReq,
  RunDetail,
  RunMetadata,
  SerializeGraphRes,
  SkillDetail,
  SyncSkillReq,
  UpdateSkillFileRes,
  SerializableGraphPhaseRef,
} from './types'

export const API_BASE_URL = import.meta.env.VITE_STUDIO_API_BASE_URL ?? 'http://localhost:8787/api'

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

export async function fetcher<T>(url: string): Promise<T> {
  const response = await api.get<T>(url)
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

export async function saveGoldenBaseline(skillId: string, runId: string, lock = false): Promise<GoldenBaseline> {
  const response = await api.post<GoldenBaseline>(`/skills/${skillId}/golden`, {
    run_id: runId,
    lock,
  })
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

import { isTauriRuntime } from '../config/runtime'
import { writeWorkspaceFile } from '../lib/tauri'

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
    } catch (err: any) {
      if (err && err.type === 'HashConflict') {
        const conflictData = err.data || {}
        const responseData = {
          current_hash: conflictData.current_hash || '',
          current_markdown_content: conflictData.current_content || '',
        }
        const mockResponse: AxiosResponse = {
          data: responseData,
          status: 409,
          statusText: 'Conflict',
          headers: {},
          config: {} as any,
        }
        const mockAxiosError = new AxiosError(
          'Hash conflict',
          'ERR_BAD_RESPONSE',
          {} as any,
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
  })
  return response.data
}
