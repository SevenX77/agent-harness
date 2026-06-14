import { describe, expect, it } from "vitest"
import { prepareTestInputCreate } from "./TestInputsSection"

describe("prepareTestInputCreate", () => {
  it("accepts a named JSON object and trims the name", () => {
    const result = prepareTestInputCreate("  happy-path  ", '{"input_text": "hi"}')

    expect(result).toEqual({ ok: true, name: "happy-path", content: { input_text: "hi" } })
  })

  it("rejects an empty name", () => {
    const result = prepareTestInputCreate("   ", "{}")

    expect(result).toEqual({ ok: false, error: "Name is required" })
  })

  it("rejects invalid JSON content", () => {
    const result = prepareTestInputCreate("case", "{not json")

    expect(result).toEqual({ ok: false, error: "Content must be valid JSON" })
  })

  it("rejects non-object JSON (array/scalar) to match the backend contract", () => {
    expect(prepareTestInputCreate("case", "[1, 2, 3]")).toEqual({
      ok: false,
      error: "Content must be a JSON object",
    })
    expect(prepareTestInputCreate("case", '"a string"')).toEqual({
      ok: false,
      error: "Content must be a JSON object",
    })
  })
})
