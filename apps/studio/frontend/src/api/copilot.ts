import { api } from './client'
import type { CopilotBackend, CopilotBackendStatus, CopilotCredentials } from '../types/copilot'

export type { CopilotBackend, CopilotBackendStatus, CopilotCredentials }

export interface CredentialsWriteRequest {
  backend: CopilotBackend
  api_key?: string | null
  base_url?: string | null
  set_active?: boolean
}

export interface TestCredentialsRequest {
  backend: CopilotBackend
  api_key: string
  base_url?: string
}

export type TestCredentialsStatus =
  | 'ok'
  | 'invalid_key'
  | 'rate_limited'
  | 'quota_exceeded'
  | 'network_error'
  | 'timeout'

export interface TestCredentialsResponse {
  status: TestCredentialsStatus
  latency_ms?: number | null
  model_seen?: string | null
  message?: string | null
}

// Credential writes are intentionally backend HTTP only; do not use Tauri FS from the frontend.
export async function getCopilotCredentials(): Promise<CopilotCredentials> {
  const response = await api.get<CopilotCredentials>('/copilot/credentials')
  return response.data
}

export async function updateCopilotCredentials(
  backend: CopilotBackend,
  apiKey?: string,
  setActive = false,
  baseUrl?: string | null,
): Promise<CopilotCredentials> {
  const request: CredentialsWriteRequest = {
    backend,
    api_key: apiKey || undefined,
    set_active: setActive,
  }
  if (baseUrl !== undefined) {
    request.base_url = baseUrl
  }
  const response = await api.put<CopilotCredentials>('/copilot/credentials', request)
  return response.data
}

export async function testCopilotCredentials(
  request: TestCredentialsRequest,
): Promise<TestCredentialsResponse> {
  const response = await api.post<TestCredentialsResponse>('/copilot/credentials/test', request)
  return response.data
}
