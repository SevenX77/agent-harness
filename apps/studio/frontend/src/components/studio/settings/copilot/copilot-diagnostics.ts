export type CopilotSettingsT = (
  key: string,
  options?: Record<string, unknown>,
) => string

export function fallbackCopilotT(key: string, options?: Record<string, unknown>): string {
  const defaults: Record<string, string> = {
    "copilot.routeStatus.ready": "Ready",
    "copilot.routeStatus.historicalReady": "Previously Connected",
    "copilot.routeStatus.testing": "Testing",
    "copilot.routeStatus.untested": "Untested",
    "copilot.routeStatus.coolingDown": "Cooling Down",
    "copilot.routeStatus.off": "Off",
    "copilot.routeStatus.failed": "Failed",
    "copilot.routeTooltip.endpointWithHost": "Endpoint: {{provider}} · {{host}}{{protocol}}",
    "copilot.routeTooltip.endpoint": "Endpoint: {{provider}}",
    "copilot.routeTooltip.id": "ID: {{id}}",
    "copilot.routeTooltip.sdkStatus": "Claude Agent SDK: {{status}}",
    "copilot.routeTooltip.detailPrefix": "↳",
    "copilot.routeTooltip.transport": "Transport: {{transport}}",
    "copilot.routeTooltip.toolUse": "Tool use: {{value}}",
    "copilot.routeTooltip.yes": "yes",
    "copilot.routeTooltip.multimodal": "Multimodal: {{value}}",
    "copilot.routeTooltip.textOnly": "text only",
    "copilot.routeTooltip.output": "Output: {{output}}",
    "copilot.routeTooltip.thinking": "Thinking: yes",
    "copilot.routeTooltip.sdkReturnedError": "SDK returned an error: {{detail}}",
    "copilot.routeTooltip.timeout": "Request timed out. Check network or proxy settings.",
    "copilot.routeTooltip.backendConnectionFailed": "Backend connection failed: {{detail}}",
    "copilot.routeTooltip.toolLoopNotVerified": "The model did not read the probe file, so the SDK tool loop was not verified.",
    "copilot.routeTooltip.missingApiKey": "This endpoint is missing an API key.",
    "copilot.routeTooltip.sdkDiagnosticUnavailable": "SDK diagnostic is available in backend logs.",
  }
  const template = options?.defaultValue ? String(options.defaultValue) : (defaults[key] ?? key)
  return template.replace(/\{\{(\w+)}}/g, (_, name: string) => String(options?.[name] ?? ""))
}

const CJK_RE = /[\u3400-\u9fff]/

export function englishContainsCjk(value: string, language: string): boolean {
  return language.toLowerCase().startsWith("en") && CJK_RE.test(value)
}

export function localizeCopilotRouteDiagnostic(
  message: string | null | undefined,
  language: string,
  t: CopilotSettingsT = fallbackCopilotT,
): string | null {
  const trimmed = message?.trim()
  if (!trimmed) return null
  if (!englishContainsCjk(trimmed, language)) return trimmed

  const lines: string[] = []
  if (trimmed.includes("SDK 返回错误")) {
    lines.push(t("copilot.routeTooltip.sdkReturnedError", { detail: englishSafeDetail(trimmed.replace("SDK 返回错误", "")) }))
  }
  if (trimmed.includes("请求超时")) {
    lines.push(t("copilot.routeTooltip.timeout"))
  }
  if (trimmed.includes("后端连接失败")) {
    lines.push(t("copilot.routeTooltip.backendConnectionFailed", { detail: englishSafeDetail(trimmed) }))
  }
  if (trimmed.includes("模型未真实读取文件") || trimmed.includes("tool loop 未验证")) {
    lines.push(t("copilot.routeTooltip.toolLoopNotVerified"))
  }
  if (trimmed.includes("未配置 API key")) {
    lines.push(t("copilot.routeTooltip.missingApiKey"))
  }
  if (lines.length === 0) {
    lines.push(t("copilot.routeTooltip.sdkDiagnosticUnavailable"))
  }

  return Array.from(new Set(lines)).join("\n")
}

function englishSafeDetail(value: string): string {
  const normalized = value.replace(/^[\s:：-]+/, "").trim()
  return CJK_RE.test(normalized) ? "" : normalized
}
