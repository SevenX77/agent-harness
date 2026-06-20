import { describe, expect, it } from "vitest"
import { detectNamingSequence, prepareTestInputCreate } from "./TestInputsSection"

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

describe("detectNamingSequence", () => {
  it("detects a shared-prefix incrementing-suffix group and returns its ids in order", () => {
    const result = detectNamingSequence([
      { id: "b", name: "chapter2" },
      { id: "c", name: "chapter3" },
      { id: "a", name: "chapter1" },
    ])

    expect(result).toEqual({
      prefix: "chapter",
      ids: ["a", "b", "c"],
      label: "chapter1–3",
    })
  })

  it("ignores names without an integer suffix and groups with a single member", () => {
    expect(
      detectNamingSequence([
        { id: "x", name: "happy-path" },
        { id: "y", name: "edge-case" },
      ]),
    ).toBeNull()

    expect(detectNamingSequence([{ id: "only", name: "chapter1" }])).toBeNull()
  })

  it("requires a non-empty prefix so bare numbers do not form a sequence", () => {
    expect(
      detectNamingSequence([
        { id: "1", name: "1" },
        { id: "2", name: "2" },
      ]),
    ).toBeNull()
  })

  it("prefers the largest sequence when several prefixes match", () => {
    const result = detectNamingSequence([
      { id: "e1", name: "ep1" },
      { id: "e2", name: "ep2" },
      { id: "c1", name: "chapter1" },
      { id: "c2", name: "chapter2" },
      { id: "c3", name: "chapter3" },
    ])

    expect(result).toEqual({
      prefix: "chapter",
      ids: ["c1", "c2", "c3"],
      label: "chapter1–3",
    })
  })
})
