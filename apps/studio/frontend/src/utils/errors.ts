import { AxiosError } from 'axios'
import type { ErrorResponse, JsonObject, JsonValue, LintError } from '../api/types'

export const BACKEND_UNAVAILABLE_MESSAGE = 'Backend unavailable'

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isBackendUnavailableError(error: unknown): boolean {
  if (error instanceof AxiosError) {
    if (error.response) {
      return false
    }
    const code = error.code?.toUpperCase() ?? ''
    const message = error.message.toLowerCase()
    return code === 'ERR_NETWORK'
      || code === 'ECONNREFUSED'
      || message.includes('network error')
      || message.includes('failed to fetch')
      || message.includes('fetch failed')
      || message.includes('load failed')
      || message.includes('econnrefused')
  }
  if (error instanceof Error) {
    const message = error.message.toLowerCase()
    return message === BACKEND_UNAVAILABLE_MESSAGE.toLowerCase()
      || message.includes('failed to fetch')
      || message.includes('fetch failed')
      || message.includes('load failed')
      || message.includes('econnrefused')
  }
  if (isRecord(error) && typeof error.message === 'string') {
    return isBackendUnavailableError(new Error(error.message))
  }
  return false
}

export function isJsonObject(value: unknown): value is JsonObject {
  if (!isRecord(value)) {
    return false
  }
  return Object.values(value).every(isJsonValue)
}

export function isJsonValue(value: unknown): value is JsonValue {
  if (value === null) {
    return true
  }
  if (['string', 'number', 'boolean'].includes(typeof value)) {
    return true
  }
  if (Array.isArray(value)) {
    return value.every(isJsonValue)
  }
  return isJsonObject(value)
}

export function asLintErrors(value: unknown): LintError[] {
  if (!Array.isArray(value)) {
    return []
  }

  return value.flatMap((item) => {
    if (!isRecord(item) || typeof item.message !== 'string' || typeof item.error_code !== 'string') {
      return []
    }
    return [{
      line: typeof item.line === 'number' ? item.line : null,
      column: typeof item.column === 'number' ? item.column : null,
      error_code: item.error_code,
      severity: item.severity === 'warning' ? 'warning' : 'error',
      message: item.message,
      phase_name: typeof item.phase_name === 'string' ? item.phase_name : null,
    }]
  })
}

export function lintErrorsFromError(error: unknown): LintError[] {
  if (!(error instanceof AxiosError)) {
    return []
  }

  const payload = error.response?.data as ErrorResponse | undefined
  const details = payload?.details
  if (!details || !isRecord(details)) {
    return []
  }
  return asLintErrors(details.errors)
}

export function errorMessage(error: unknown): string {
  if (isBackendUnavailableError(error)) {
    return BACKEND_UNAVAILABLE_MESSAGE
  }
  if (error instanceof AxiosError) {
    const payload = error.response?.data as Partial<ErrorResponse> | undefined
    return payload?.message ?? error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  if (typeof error === 'string') {
    return error
  }
  // Native (Tauri) command rejections are plain objects — surface a readable
  // reason instead of the useless "[object Object]" that String() produces.
  if (isRecord(error)) {
    if (typeof error.message === 'string') {
      return error.message
    }
    if (isRecord(error.data) && typeof error.data.message === 'string') {
      return error.data.message
    }
    if (error.type === 'HashConflict') {
      return 'File changed on disk. Reload the file and try again.'
    }
    try {
      return JSON.stringify(error)
    } catch {
      return String(error)
    }
  }
  return String(error)
}
