import { AxiosError } from 'axios'
import i18n from '../i18n'
import type { ErrorResponse, JsonObject, JsonValue, LintError } from '../api/types'

export const BACKEND_UNAVAILABLE_MESSAGE = 'Backend unavailable'

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export class BackendUnavailableError extends Error {
  readonly axiosCode: string | null
  readonly originalMessage: string
  readonly requestMethod: string | null
  readonly requestPath: string | null
  readonly requestBaseURL: string | null
  readonly requestURL: string | null

  constructor(error: unknown) {
    super(BACKEND_UNAVAILABLE_MESSAGE)
    this.name = 'BackendUnavailableError'
    Object.setPrototypeOf(this, BackendUnavailableError.prototype)

    if (error instanceof AxiosError) {
      this.axiosCode = error.code ?? null
      this.originalMessage = error.message
      this.requestMethod = normalizeMethod(error.config?.method)
      this.requestPath = error.config?.url ?? null
      this.requestBaseURL = error.config?.baseURL ?? null
      this.requestURL = resolveRequestURL(this.requestBaseURL, this.requestPath)
      return
    }

    this.axiosCode = null
    this.originalMessage = error instanceof Error ? error.message : String(error)
    this.requestMethod = null
    this.requestPath = null
    this.requestBaseURL = null
    this.requestURL = null
  }
}

function normalizeMethod(method: string | undefined): string | null {
  return method ? method.toUpperCase() : null
}

function resolveRequestURL(baseURL: string | null, path: string | null): string | null {
  if (!path) {
    return baseURL
  }
  try {
    return new URL(path).toString()
  } catch {
    // Relative path; combine below.
  }
  if (!baseURL) {
    return path
  }
  try {
    const base = baseURL.endsWith('/') ? baseURL : `${baseURL}/`
    const relativePath = path.startsWith('/') ? path.slice(1) : path
    return new URL(relativePath, base).toString()
  } catch {
    return `${baseURL.replace(/\/$/, '')}/${path.replace(/^\//, '')}`
  }
}

export function errorDiagnosticDetails(error: unknown): string[] {
  if (error instanceof BackendUnavailableError) {
    const details = ['No HTTP response was received from the Studio backend.']
    const requestURL = error.requestURL ?? error.requestPath
    if (requestURL) {
      details.push(`Request: ${error.requestMethod ?? 'UNKNOWN'} ${requestURL}`)
    }
    if (error.requestBaseURL) {
      details.push(`API base URL: ${error.requestBaseURL}`)
    }
    const frontendOrigin = currentFrontendOrigin()
    if (frontendOrigin) {
      details.push(`Frontend origin: ${frontendOrigin}`)
    }
    if (error.axiosCode) {
      details.push(`Axios code: ${error.axiosCode}`)
    }
    details.push(`Original error: ${error.originalMessage}`)
    details.push('Meaning: the browser/Tauri webview did not receive an HTTP response; this is a sidecar/proxy/port/CORS connectivity failure, not a structured backend diagnostic response.')
    return details
  }
  if (error instanceof AxiosError) {
    const details = []
    const method = normalizeMethod(error.config?.method)
    const requestURL = resolveRequestURL(error.config?.baseURL ?? null, error.config?.url ?? null)
    if (requestURL) {
      details.push(`Request: ${method ?? 'UNKNOWN'} ${requestURL}`)
    }
    if (error.response) {
      details.push(`HTTP status: ${error.response.status}`)
    }
    if (error.code) {
      details.push(`Axios code: ${error.code}`)
    }
    const payload = error.response?.data as Partial<ErrorResponse> | undefined
    if (typeof payload?.error_code === 'string') {
      details.push(`Backend error code: ${payload.error_code}`)
    }
    if (typeof payload?.retry_strategy === 'string') {
      details.push(`Retry strategy: ${payload.retry_strategy}`)
    }
    if (typeof payload?.message === 'string' && payload.message !== error.message) {
      details.push(`Backend message: ${payload.message}`)
    }
    if (isRecord(payload?.details)) {
      details.push(`Backend details:\n${formatDiagnosticJson(payload.details)}`)
    }
    details.push(`Original error: ${error.message}`)
    return details
  }
  return []
}

function formatDiagnosticJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function currentFrontendOrigin(): string | null {
  if (typeof window === 'undefined') {
    return null
  }
  return window.location.origin
}

export function isBackendUnavailableError(error: unknown): boolean {
  if (error instanceof BackendUnavailableError) {
    return true
  }
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

/**
 * What the user reads for a typed backend failure — chosen HERE, not by the server.
 *
 * A backend response carries a stable `error_code` plus the `details` that make it
 * specific; which language those become is a fact about who is reading, and the
 * server does not know that. It used to: two `skills.py` branches wrote their
 * message in Chinese and `errorMessage` piped `payload.message` into the toast
 * verbatim, so the string a Chinese and an English reader saw was decided in
 * Python (ledger K4).
 *
 * `details` is passed as interpolation values, so a message can name the field it
 * is about. An untranslated code falls back to the backend's own message — that is
 * the code's developer-facing text, which is the right thing to show when nobody
 * has written a reader-facing one yet.
 *
 * Resolves `studioCodes.*` — the key space for codes the STUDIO BACKEND mints,
 * which is a closed set we own, so an entry missing from it is our own gap.
 * `providerCodes.*` is the separate space `lib/llm-error-messages.ts` reads for
 * codes a remote LLM provider returned; that one is open-ended by nature
 * (`vendor_error_code` in the gateway hands back the vendor's own
 * `code`/`type`/`status` string verbatim), which is exactly why the two cannot
 * share a table. Lookups are exact-match, so while both readers resolved one
 * `codes.*` table, a Studio code and a vendor code spelling the same string got
 * the same sentence and one of the two readers was told the wrong machine had
 * failed. Separate prefixes make that collision unrepresentable rather than
 * something each new code has to be named around.
 */
function translatedErrorCode(payload: Partial<ErrorResponse> | undefined): string | null {
  const code = payload?.error_code
  if (!code || !i18n.isInitialized) {
    return null
  }
  const values = isRecord(payload?.details) ? payload.details : {}
  const translated = i18n.t(`studioCodes.${code}`, { ns: 'errors', defaultValue: '', ...values })
  return translated || null
}

/**
 * What the reader is told about a failure — the ONE place that decides it.
 *
 * Every surface that reports a caught error goes through here. That is not
 * tidiness: a backend refusal only reads in the reader's language if this
 * function sees it, and a caller that writes `error instanceof Error ?
 * error.message : '…'` instead silently opts out. On 2026-08-21 the Save-to-Team
 * path did exactly that, so a correctly-typed `APP_SETTINGS_INCOMPLETE` surfaced
 * as "Request failed with status code 400" (ledger K4a).
 *
 * `fallback` is what the caller was DOING, used only when the rejection carries
 * nothing readable — "Sync failed" beats a JSON dump of an unrecognized object.
 * It never overrides a message the error actually carries.
 */
export function errorMessage(error: unknown, fallback?: string): string {
  if (isBackendUnavailableError(error)) {
    return BACKEND_UNAVAILABLE_MESSAGE
  }
  if (error instanceof AxiosError) {
    const payload = error.response?.data as Partial<ErrorResponse> | undefined
    return translatedErrorCode(payload) ?? payload?.message ?? error.message
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
      // The one native rejection this function words itself: Rust reports the
      // conflict as a tagged object with no message, so there is nothing to
      // pass through — and it still has to read in the reader's language.
      return i18n.t('native.hashConflict', { ns: 'errors' })
    }
    if (fallback) {
      return fallback
    }
    try {
      return JSON.stringify(error)
    } catch {
      return String(error)
    }
  }
  return fallback ?? String(error)
}
