import { api } from './client'

export type MediaModality = 'image' | 'video'
export type MediaTask = 't2i' | 'i2i' | 'i2v' | 'flf2v' | 'ref2v'
export type MediaChannel = 'economy' | 'official'
export type MediaEndpointKind = 'standard' | 'ai_app'
export type MediaProbeStatus = 'ok' | 'auth_failed' | 'network_error'

export interface MediaParamSpec {
  type: 'string' | 'enum' | 'int_range' | 'image_list' | 'image_slot'
  required: boolean
  values?: string[]
  default?: string | null
  min_value?: number
  max_value?: number
  max_items?: number
  max_size_mb?: number | null
  min_length?: number | null
  max_length?: number | null
}

export interface MediaPricing {
  unit: 'per_image' | 'per_second' | 'per_run'
  amount: number
  currency: string
}

export interface MediaModelSettings {
  enabled: boolean
  defaults: Record<string, string | number>
}

export interface MediaModel {
  id: string
  provider: string
  display_name: string
  modality: MediaModality
  task: MediaTask
  channel: MediaChannel
  endpoint_kind: MediaEndpointKind
  endpoint: string
  pricing: MediaPricing | null
  params: Record<string, MediaParamSpec>
  doc_source: string | null
  settings: MediaModelSettings
}

export interface MediaProbeResult {
  status: MediaProbeStatus
  checked_at: string
  latency_ms?: number | null
  remain_coins?: string | null
  remain_money?: string | null
  message?: string | null
}

export interface MediaProviderView {
  id: string
  base_url: string
  api_key_set: boolean
  last_probe: MediaProbeResult | null
}

export interface MediaRegistry {
  providers: MediaProviderView[]
  models: MediaModel[]
}

export async function fetchMediaRegistry(): Promise<MediaRegistry> {
  const response = await api.get<MediaRegistry>('/media/registry')
  return response.data
}

export async function putMediaCredential(
  providerId: string,
  patch: { api_key?: string; base_url?: string },
): Promise<MediaRegistry> {
  const response = await api.put<MediaRegistry>(
    `/media/providers/${encodeURIComponent(providerId)}/credential`,
    patch,
  )
  return response.data
}

export async function revealMediaCredential(providerId: string): Promise<string> {
  const response = await api.get<{ api_key: string }>(
    `/media/providers/${encodeURIComponent(providerId)}/credential/secret`,
  )
  return response.data.api_key
}

export async function probeMediaProvider(providerId: string): Promise<MediaRegistry> {
  const response = await api.post<MediaRegistry>(
    `/media/providers/${encodeURIComponent(providerId)}/probe`,
  )
  return response.data
}

export async function patchMediaModelSettings(
  modelId: string,
  patch: { enabled?: boolean; defaults?: Record<string, string | number> },
): Promise<MediaRegistry> {
  const response = await api.patch<MediaRegistry>(
    `/media/models/${encodeURIComponent(modelId)}/settings`,
    patch,
  )
  return response.data
}
