import { describe, expect, it } from "vitest"
import {
  composeTestErrorMessage,
  translateErrorCode,
  translateTestStatus,
} from "./llm-error-messages"

describe("translateErrorCode", () => {
  it("returns empty string for falsy input", () => {
    expect(translateErrorCode("")).toBe("")
    expect(translateErrorCode(null)).toBe("")
    expect(translateErrorCode(undefined)).toBe("")
  })

  it("returns the zh-CN message for known Anthropic codes", () => {
    expect(translateErrorCode("invalid_api_key")).toContain("API Key 无效")
    expect(translateErrorCode("permission_error")).toContain("无权限")
  })

  it("returns the zh-CN message for known Gemini codes", () => {
    expect(translateErrorCode("PERMISSION_DENIED")).toContain("无权限")
    expect(translateErrorCode("UNAUTHENTICATED")).toContain("认证")
  })

  it("returns the zh-CN message for the synthetic missing_api_key short-circuit", () => {
    expect(translateErrorCode("missing_api_key")).toContain("API Key 为空")
  })

  it("falls back to a verbatim quote of unknown codes so operators can grep them", () => {
    expect(translateErrorCode("MYSTERIOUS_FAILURE")).toBe("服务商返回错误码：MYSTERIOUS_FAILURE")
  })
})

describe("translateTestStatus", () => {
  it("returns the zh-CN label for each TestStatus variant", () => {
    expect(translateTestStatus("ok")).toBe("连接正常")
    expect(translateTestStatus("untested")).toBe("尚未测试")
    expect(translateTestStatus("invalid_key")).toBe("Key 无效")
    expect(translateTestStatus("missing_api_key")).toContain("API Key 为空")
  })

  it("defaults to 尚未测试 when undefined", () => {
    expect(translateTestStatus(undefined)).toBe("尚未测试")
  })
})

describe("composeTestErrorMessage", () => {
  it("prefers the error code translation when it differs from the status label", () => {
    expect(composeTestErrorMessage("invalid_key", "permission_error", "Forbidden"))
      .toBe("Key 无权限访问该资源（Forbidden）")
  })

  it("falls back to the status label when code is missing", () => {
    expect(composeTestErrorMessage("network_error", "", "DNS failure"))
      .toBe("网络错误：DNS failure")
  })

  it("omits the message when there is none", () => {
    expect(composeTestErrorMessage("rate_limited", "rate_limit_error", "")).toBe("触发频率限制（429）")
  })
})
