import { api } from './client'
import type { CopilotBackend, CopilotCredentials } from '../types/copilot'

// Credential writes are intentionally backend HTTP only; do not use Tauri FS from the frontend.
export async function getCopilotCredentials(): Promise<CopilotCredentials> {
  const response = await api.get<CopilotCredentials>('/copilot/credentials')
  return response.data
}

export async function updateCopilotCredentials(
  backend: CopilotBackend,
  apiKey?: string,
  setActive = false,
): Promise<CopilotCredentials> {
  const response = await api.put<CopilotCredentials>('/copilot/credentials', {
    backend,
    api_key: apiKey || undefined,
    set_active: setActive,
  })
  return response.data
}
