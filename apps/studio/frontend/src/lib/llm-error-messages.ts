/**
 * Translate backend Test outcome / vendor error codes into English UI messages.
 * Future i18n should wrap this catalog rather than showing raw codes directly.
 */

type TestStatus =
  | "untested"
  | "ok"
  | "invalid_key"
  | "rate_limited"
  | "quota_exceeded"
  | "network_error"
  | "timeout"
  | "error"

type ProviderTestStatus = TestStatus | "missing_api_key"

/**
 * Map of `error_code` strings returned by endpoint/route verification
 * responses (vendor codes + synthetic `missing_api_key` / `timeout`).
 *
 * Anthropic error codes: `invalid_api_key`, `permission_error`,
 * `not_found_error`, `request_too_large`, `rate_limit_error`, `api_error`,
 * `overloaded_error`. OpenAI uses `invalid_api_key`, `insufficient_quota`,
 * `model_not_found`, `rate_limit_exceeded`. Gemini uses `PERMISSION_DENIED`,
 * `UNAUTHENTICATED`, `RESOURCE_EXHAUSTED`, `UNAVAILABLE`.
 */
const ERROR_CODE_TRANSLATIONS: Record<string, string> = {
  missing_api_key: "API key is empty. Add a key before testing.",
  timeout: "The request timed out after 8 seconds.",

  // OpenAI-style.
  invalid_api_key: "API key is invalid or was rejected by the provider.",
  invalid_x_api_key: "API key is invalid or was rejected by the provider.",
  insufficient_quota: "The account has no remaining quota.",
  model_not_found: "The model does not exist or this API key cannot access it.",
  rate_limit_exceeded: "Rate limit exceeded (429).",
  invalid_request_error: "The provider rejected the request format.",
  context_length_exceeded: "The request exceeds the model context window.",

  // Anthropic-style.
  permission_error: "The API key does not have permission to access this resource.",
  authentication_error: "Authentication failed. Check the API key and required headers.",
  not_found_error: "The provider returned 404 for the endpoint or resource.",
  request_too_large: "The request body is too large.",
  rate_limit_error: "Rate limit exceeded (429).",
  api_error: "The provider returned an internal API error.",
  overloaded_error: "The provider is temporarily overloaded.",
  unauthorized: "The API key is not authorized (401).",

  // Gemini-style.
  PERMISSION_DENIED: "The API key does not have permission to access this resource.",
  UNAUTHENTICATED: "The API key could not be authenticated.",
  RESOURCE_EXHAUSTED: "Quota or rate limit is exhausted.",
  UNAVAILABLE: "The provider is temporarily unavailable.",

  // Generic fallbacks (set by backend `_extract_vendor_error_code`).
  no_available_sdk: "No compatible protocol was confirmed. Check the API key, Base URL, and selected provider protocol, then retry.",
  model_list_unavailable: "The provider model list could not be loaded. Check the Base URL and whether the provider supports a model-list endpoint.",
  rate_limited: "Rate limit exceeded (429).",
  quota_exceeded: "Quota is exhausted (402/403).",
  network_error: "Network error. The provider could not be reached.",
  http_error: "The provider returned an unexpected HTTP status.",
}

const HTTP_STATUS_TRANSLATIONS: Record<number, string> = {
  400: "The request parameters are invalid.",
  401: "The request is not authenticated.",
  403: "The request is not authorized, or this API key cannot access the resource.",
  404: "The resource or endpoint could not be found.",
  408: "The request timed out.",
  409: "The request conflicts with the current state.",
  422: "The request does not match the backend schema.",
  429: "The provider rate limit was reached. Try again later.",
  500: "The backend service failed.",
  502: "The backend service or proxy is unavailable.",
  503: "The service is temporarily unavailable.",
  504: "The backend request timed out.",
}

/**
 * Map of persisted `TestStatus` (last_test_status on credentials).
 * Includes `untested` and `ok`; the error variants overlap with the per-code
 * map but are kept here as a guaranteed coverage in case `error_code` is
 * blank.
 */
const STATUS_TRANSLATIONS: Record<TestStatus | ProviderTestStatus, string> = {
  untested: "Not configured",
  ok: "Connected",
  error: "Test failed",
  invalid_key: "Invalid API key",
  rate_limited: "Rate limited",
  quota_exceeded: "Quota exhausted",
  network_error: "Network error",
  timeout: "Request timed out",
  missing_api_key: "API key is empty",
}

/**
 * Return a human-readable explanation for a vendor error code. Falls back to the
 * raw code string if the code is unknown (so the operator can still copy it
 * into a bug report).
 */
export function translateErrorCode(code: string | null | undefined): string {
  if (!code) return ""
  return ERROR_CODE_TRANSLATIONS[code] ?? `Provider returned error code: ${code}`
}

export function translateHttpStatus(status: number | null | undefined): string {
  if (!status) return ""
  return HTTP_STATUS_TRANSLATIONS[status] ?? `HTTP ${status} request failed.`
}

/**
 * Return a readable label for a Test outcome status (used by the persistent
 * badge). Falls back to the raw status string if unrecognized.
 */
export function translateTestStatus(status: TestStatus | ProviderTestStatus | undefined): string {
  if (!status) return "Not configured"
  return STATUS_TRANSLATIONS[status] ?? status
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
  const rawMessage = getErrorMessage(error) || fallback
  const response = getErrorResponse(error)
  const statusLabel = translateHttpStatus(response?.status)
  const detail = getErrorDetail(response?.data)
  if (statusLabel) {
    return detail ? `${rawMessage} - ${statusLabel} (${detail})` : `${rawMessage} - ${statusLabel}`
  }
  return rawMessage || fallback
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
