import axios, { AxiosHeaders } from 'axios'
import type { MultifileSkillPayload, SkillDetail } from './types'

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

export async function fetchSkillFiles(skillId: string): Promise<SkillDetail> {
  const response = await api.get<SkillDetail>(`/skills/${skillId}`)
  return response.data
}

export async function saveSkillFiles(
  skillId: string,
  files: Record<string, string>,
): Promise<SkillDetail> {
  const payload: MultifileSkillPayload = { files }
  const response = await api.put<SkillDetail>(`/skills/${skillId}`, payload)
  return response.data
}

export function wsUrl(path: string): string {
  const base = new URL(currentApiBaseURL, window.location.origin)
  const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${protocol}//${base.host}${normalizedPath}`
}
