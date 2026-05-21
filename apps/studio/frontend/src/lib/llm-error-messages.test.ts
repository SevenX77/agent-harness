import { describe, expect, it } from "vitest"
import {
  composeRequestErrorMessage,
  composeTestErrorMessage,
  translateErrorCode,
  translateHttpStatus,
  translateTestStatus,
} from "./llm-error-messages"

describe("translateErrorCode", () => {
  it("returns empty string for falsy input", () => {
    expect(translateErrorCode("")).toBe("")
    expect(translateErrorCode(null)).toBe("")
    expect(translateErrorCode(undefined)).toBe("")
  })

  it("returns the English message for known Anthropic codes", () => {
    expect(translateErrorCode("invalid_api_key")).toContain("API key is invalid")
    expect(translateErrorCode("permission_error")).toContain("does not have permission")
  })

  it("returns the English message for known Gemini codes", () => {
    expect(translateErrorCode("PERMISSION_DENIED")).toContain("does not have permission")
    expect(translateErrorCode("UNAUTHENTICATED")).toContain("could not be authenticated")
  })

  it("returns the English message for the synthetic missing_api_key short-circuit", () => {
    expect(translateErrorCode("missing_api_key")).toContain("API key is empty")
  })

  it("returns the English message for SDK detection failures", () => {
    expect(translateErrorCode("no_available_sdk")).toContain("No compatible protocol was confirmed")
  })

  it("falls back to a verbatim quote of unknown codes so operators can grep them", () => {
    expect(translateErrorCode("MYSTERIOUS_FAILURE")).toBe("Provider returned error code: MYSTERIOUS_FAILURE")
  })
})

describe("translateHttpStatus", () => {
  it("translates common request failure status codes", () => {
    expect(translateHttpStatus(400)).toContain("request parameters are invalid")
    expect(translateHttpStatus(401)).toContain("not authenticated")
    expect(translateHttpStatus(403)).toContain("not authorized")
    expect(translateHttpStatus(404)).toContain("resource or endpoint could not be found")
    expect(translateHttpStatus(429)).toContain("rate limit")
    expect(translateHttpStatus(500)).toContain("backend service failed")
  })
})

describe("composeRequestErrorMessage", () => {
  it("appends a human-readable explanation to raw HTTP errors", () => {
    const error = {
      message: "Request failed with status code 404",
      response: { status: 404, data: { detail: "Unknown provider: openai-official" } },
    }

    expect(composeRequestErrorMessage(error)).toBe(
      "Request failed with status code 404 - The resource or endpoint could not be found. (Unknown provider: openai-official)",
    )
  })
})

describe("translateTestStatus", () => {
  it("returns the English label for each TestStatus variant", () => {
    expect(translateTestStatus("ok")).toBe("Connected")
    expect(translateTestStatus("untested")).toBe("Untested")
    expect(translateTestStatus("invalid_key")).toBe("Invalid API key")
    expect(translateTestStatus("missing_api_key")).toContain("API key is empty")
  })

  it("defaults to Untested when undefined", () => {
    expect(translateTestStatus(undefined)).toBe("Untested")
  })
})

describe("composeTestErrorMessage", () => {
  it("prefers the error code translation when it differs from the status label", () => {
    expect(composeTestErrorMessage("invalid_key", "permission_error", "Forbidden"))
      .toBe("The API key does not have permission to access this resource. (Forbidden)")
  })

  it("falls back to the status label when code is missing", () => {
    expect(composeTestErrorMessage("network_error", "", "DNS failure"))
      .toBe("Network error: DNS failure")
  })

  it("omits the message when there is none", () => {
    expect(composeTestErrorMessage("rate_limited", "rate_limit_error", "")).toBe("Rate limit exceeded (429).")
  })
})
