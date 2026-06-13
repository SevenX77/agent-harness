import type { ProviderTestStatus, TestStatus } from "@/api/llm"
import i18n from "@/i18n"

const ERRORS_NS = "errors"
const tError = i18n.t.bind(i18n) as (key: string, options?: Record<string, unknown>) => string
const errorExists = i18n.exists.bind(i18n) as (key: string, options?: Record<string, unknown>) => boolean

function errorText(key: string, options?: Record<string, unknown>): string {
  return tError(key, { ns: ERRORS_NS, ...options })
}

function hasErrorText(key: string): boolean {
  return errorExists(key, { ns: ERRORS_NS })
}

/**
 * Return a human-readable explanation for a vendor error code. Falls back to the
 * raw code string if the code is unknown (so the operator can still copy it
 * into a bug report).
 */
export function translateErrorCode(code: string | null | undefined): string {
  if (!code) return ""
  const key = `codes.${code}`
  return hasErrorText(key) ? errorText(key) : errorText("fallbacks.errorCode", { code })
}

export function translateHttpStatus(status: number | null | undefined): string {
  if (!status) return ""
  const key = `httpStatus.${status}`
  return hasErrorText(key) ? errorText(key) : errorText("fallbacks.httpStatus", { status })
}

/**
 * Return a readable label for a Test outcome status (used by the persistent
 * badge). Falls back to the raw status string if unrecognized.
 */
export function translateTestStatus(status: TestStatus | ProviderTestStatus | undefined): string {
  if (!status) return errorText("fallbacks.notConfigured")
  const key = `status.${status}`
  return hasErrorText(key) ? errorText(key) : status
}

/**
 * Human-readable summary combining status + error_code + free-text message.
 * Used as the toast body when a Test call fails.
 */
export function composeTestErrorMessage(
  status: ProviderTestStatus,
  errorCode: string | null | undefined,
  message: string | null | undefined,
): string {
  const statusLabel = translateTestStatus(status)
  const codeLabel = translateErrorCode(errorCode)
  if (codeLabel && codeLabel !== statusLabel) {
    return message ? `${codeLabel} (${message})` : codeLabel
  }
  return message ? `${statusLabel}: ${message}` : statusLabel
}

export function composeRequestErrorMessage(error: unknown, fallback = "Request failed"): string {
  const rawMessage = getErrorMessage(error)
  const response = getErrorResponse(error)
  const statusLabel = translateHttpStatus(response?.status)
  const detail = getErrorDetail(response?.data)
  if (statusLabel) {
    return detail ? `${statusLabel} (${detail})` : statusLabel
  }
  if (detail) return detail
  if (rawMessage && !isHttpRequestWrapper(rawMessage)) return rawMessage
  return fallback || errorText("fallbacks.requestFailed")
}

function isHttpRequestWrapper(message: string): boolean {
  return /^Request failed with status code \d+$/i.test(message.trim())
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error !== "object" || error === null) return ""
  const message = (error as { message?: unknown }).message
  return typeof message === "string" ? message : ""
}

function getErrorResponse(error: unknown): { status?: number; data?: unknown } | null {
  if (typeof error !== "object" || error === null || !("response" in error)) return null
  const response = (error as { response?: unknown }).response
  if (typeof response !== "object" || response === null) return null
  const status = (response as { status?: unknown }).status
  return {
    status: typeof status === "number" ? status : undefined,
    data: (response as { data?: unknown }).data,
  }
}

function getErrorDetail(data: unknown): string {
  if (typeof data === "string") return data
  if (typeof data !== "object" || data === null) return ""
  const detail = (data as { detail?: unknown }).detail
  if (typeof detail === "string") return detail
  const message = (data as { message?: unknown }).message
  return typeof message === "string" ? message : ""
}
