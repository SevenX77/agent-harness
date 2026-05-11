import axios, { AxiosHeaders } from 'axios'
import type { GoldenBaseline, JsonObject, RunDetail, RunMetadata } from './types'

export const API_BASE_URL = import.meta.env.VITE_STUDIO_API_BASE_URL ?? 'http://localhost:8787/api'

let currentApiBaseURL = API_BASE_URL

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

api.interceptors.request.use((config) => {
  const headers = AxiosHeaders.from(config.headers)
  headers.set('X-Studio-User-ID', 'default')
  config.headers = headers
  return config
})

export async function fetcher<T>(url: string): Promise<T> {
  const response = await api.get<T>(url)
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
