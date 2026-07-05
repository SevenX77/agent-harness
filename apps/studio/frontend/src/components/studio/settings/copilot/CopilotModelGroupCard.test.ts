import { describe, expect, it } from "vitest"
import { localizeCopilotRouteDiagnostic } from "./copilot-diagnostics"

const enMessages: Record<string, string> = {
  "copilot.routeTooltip.sdkReturnedError": "SDK returned an error: {{detail}}",
  "copilot.routeTooltip.timeout": "Request timed out. Check network or proxy settings.",
  "copilot.routeTooltip.backendConnectionFailed": "Backend connection failed: {{detail}}",
  "copilot.routeTooltip.toolLoopNotVerified": "The model did not read the probe file, so the SDK tool loop was not verified.",
  "copilot.routeTooltip.missingApiKey": "This endpoint is missing an API key.",
  "copilot.routeTooltip.sdkDiagnosticUnavailable": "SDK diagnostic is available in backend logs.",
}

function t(key: string, options?: Record<string, unknown>): string {
  const template = enMessages[key] ?? key
  return template.replace(/\{\{(\w+)}}/g, (_, name: string) => String(options?.[name] ?? ""))
}

describe("localizeCopilotRouteDiagnostic", () => {
  it("does not leak Chinese backend diagnostics while the UI language is English", () => {
    const message = [
      "SDK 返回错误",
      "模型未真实读取文件 (token 未回显), tool loop 未验证",
    ].join("\n")

    const localized = localizeCopilotRouteDiagnostic(message, "en", t)

    expect(localized).not.toMatch(/[\u3400-\u9fff]/)
    expect(localized).toContain("SDK returned an error")
    expect(localized).toContain("tool loop")
  })

  it("keeps raw backend detail in Chinese mode", () => {
    const message = "SDK 返回错误"

    expect(localizeCopilotRouteDiagnostic(message, "zh-CN", t)).toBe(message)
  })
})
