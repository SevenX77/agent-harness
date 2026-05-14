import axios, { AxiosHeaders } from 'axios'
import type {
  AppSettings,
  CollaborateResult,
  GitHistoryItem,
  GoldenBaseline,
  JsonObject,
  PublishResult,
  PublishSkillReq,
  RunDetail,
  RunMetadata,
  SkillDetail,
  SyncSkillReq,
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

export function wsUrl(path: string): string {
  const base = new URL(currentApiBaseURL, window.location.origin)
  const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${protocol}//${base.host}${normalizedPath}`
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
