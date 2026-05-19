import { AxiosError } from 'axios'
import type { ErrorResponse, JsonObject, JsonValue, LintError } from '../api/types'

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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
  if (error instanceof AxiosError) {
    const payload = error.response?.data as Partial<ErrorResponse> | undefined
    return payload?.message ?? error.message
  }
  return error instanceof Error ? error.message : String(error)
}
