/**
 * Translate backend Test outcome / vendor error codes into Chinese UI messages.
 *
 * v2.1 hardcodes zh-CN. i18n (interpolated messages, locale switching) lands
 * in v2.6+ per the spec (design-frontend §4.3 C3 note).
 */

import type { ProviderTestStatus, TestStatus } from "@/api/llm"

/**
 * Map of `error_code` strings returned by the backend POST /providers/test
 * response (vendor codes + the synthetic `missing_api_key` / `timeout`).
 *
 * Anthropic error codes: `invalid_api_key`, `permission_error`,
 * `not_found_error`, `request_too_large`, `rate_limit_error`, `api_error`,
 * `overloaded_error`. OpenAI uses `invalid_api_key`, `insufficient_quota`,
 * `model_not_found`, `rate_limit_exceeded`. Gemini uses `PERMISSION_DENIED`,
 * `UNAUTHENTICATED`, `RESOURCE_EXHAUSTED`, `UNAVAILABLE`.
 */
const ERROR_CODE_TRANSLATIONS: Record<string, string> = {
  missing_api_key: "API Key 为空，请先填写后再测试",
  timeout: "请求超时（超过 8 秒）",

  // OpenAI-style.
  invalid_api_key: "API Key 无效，被服务商拒绝",
  insufficient_quota: "额度已用完",
  model_not_found: "模型不存在或当前 Key 无权限访问",
  rate_limit_exceeded: "触发频率限制（429）",

  // Anthropic-style.
  permission_error: "Key 无权限访问该资源",
  not_found_error: "服务商返回 404（端点或资源不存在）",
  request_too_large: "请求体过大",
  rate_limit_error: "触发频率限制（429）",
  api_error: "服务商内部错误",
  overloaded_error: "服务商当前过载",
  unauthorized: "Key 未授权（401）",

  // Gemini-style.
  PERMISSION_DENIED: "Key 无权限访问该资源",
  UNAUTHENTICATED: "Key 未通过认证",
  RESOURCE_EXHAUSTED: "额度或频率限制已耗尽",
  UNAVAILABLE: "服务商当前不可用",

  // Generic fallbacks (set by backend `_extract_vendor_error_code`).
  rate_limited: "触发频率限制（429）",
  quota_exceeded: "额度已用完（402/403）",
  network_error: "网络错误，未能连通服务商",
  http_error: "服务商返回非预期 HTTP 状态码",
}

/**
 * Map of persisted `TestStatus` (last_test_status on credentials).
 * Includes `untested` and `ok`; the error variants overlap with the per-code
 * map but are kept here as a guaranteed coverage in case `error_code` is
 * blank.
 */
const STATUS_TRANSLATIONS: Record<TestStatus | ProviderTestStatus, string> = {
  untested: "尚未测试",
  ok: "连接正常",
  invalid_key: "Key 无效",
  rate_limited: "触发频率限制",
  quota_exceeded: "额度已用完",
  network_error: "网络错误",
  timeout: "请求超时",
  missing_api_key: "API Key 为空",
}

/**
 * Return a Chinese explanation for a vendor error code. Falls back to the
 * raw code string if the code is unknown (so the operator can still copy it
 * into a bug report).
 */
export function translateErrorCode(code: string | null | undefined): string {
  if (!code) return ""
  return ERROR_CODE_TRANSLATIONS[code] ?? `服务商返回错误码：${code}`
}

/**
 * Return a Chinese label for a Test outcome status (used by the persistent
 * badge). Falls back to the raw status string if unrecognized.
 */
export function translateTestStatus(status: TestStatus | ProviderTestStatus | undefined): string {
  if (!status) return "尚未测试"
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
    return message ? `${codeLabel}（${message}）` : codeLabel
  }
  return message ? `${statusLabel}：${message}` : statusLabel
}
