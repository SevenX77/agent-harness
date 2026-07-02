import { describe, expect, it } from "vitest"
import { detectNamingSequence } from "./TestInputsSection"

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
