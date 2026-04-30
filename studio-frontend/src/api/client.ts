import axios, { AxiosHeaders } from 'axios'

export const API_BASE_URL = import.meta.env.VITE_STUDIO_API_BASE_URL ?? 'http://localhost:8787/api'

export const api = axios.create({
  baseURL: API_BASE_URL,
})

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
  const base = new URL(API_BASE_URL, window.location.origin)
  const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${protocol}//${base.host}${normalizedPath}`
}
