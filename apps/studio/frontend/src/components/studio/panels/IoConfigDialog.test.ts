import { describe, expect, it } from "vitest"
import type { IoScanEntry } from "@/api/client"
import {
  candidatesFromScanEntries,
  matchCandidatesToInputs,
  normalizeFieldName,
} from "./IoConfigDialog"

describe("candidatesFromScanEntries", () => {
  it("uses the clean stem (not the parent dir) as a folded batch candidate field", () => {
    // A numbered batch (chapter_001…chapter_060) folds to one entry; its
    // candidate field must be the declared-field stem `chapter`, so it can
    // match io.inputs — NOT the parent folder name it happens to live in.
    const entries: IoScanEntry[] = [
      {
        kind: "batch",
        name: "chapter_{n}.json",
        dir: "imports/x/node1_output",
        pattern: "chapter_{n}.json",
        numbers: [1, 2, 3],
      },
    ]
    const [candidate] = candidatesFromScanEntries(entries)
    expect(candidate.field).toBe("chapter")
    expect(candidate.type).toBe("array")
    expect(candidate.numbers).toEqual([1, 2, 3])
    expect(candidate.checked).toBe(false)
  })

  it("flattens file fields into per-field candidates, all unchecked", () => {
    const entries: IoScanEntry[] = [
      {
        kind: "file",
        name: "a.json",
        path: "imports/x/a.json",
        fields: [
          { name: "chapter", type: "object" },
          { name: "notes", type: "string" },
        ],
      },
    ]
    expect(candidatesFromScanEntries(entries).map((c) => [c.field, c.checked])).toEqual([
      ["chapter", false],
      ["notes", false],
    ])
  })
})

describe("normalizeFieldName", () => {
  it("lowercases and strips a trailing numeric / batch-pattern suffix", () => {
    expect(normalizeFieldName("Chapter")).toBe("chapter")
    expect(normalizeFieldName("chapter1")).toBe("chapter")
    expect(normalizeFieldName("chapter_001")).toBe("chapter")
    expect(normalizeFieldName("chapter_{n}.json")).toBe("chapter")
    expect(normalizeFieldName("segmentation_result")).toBe("segmentation_result")
  })
})

describe("matchCandidatesToInputs", () => {
  const base = (field: string) => ({ field, type: null, checked: false })

  it("auto-checks + flags candidates whose normalized name matches a declared io.inputs field", () => {
    const result = matchCandidatesToInputs(
      [base("chapter"), base("segments_003"), base("junk")],
      ["chapter", "segments"],
    )
    expect(result.map((c) => [c.field, c.checked, c.matched])).toEqual([
      ["chapter", true, true],
      ["segments_003", true, true],
      ["junk", false, false],
    ])
  })

  it("leaves everything unchecked/unmatched when nothing matches the declared inputs", () => {
    const result = matchCandidatesToInputs([base("alpha"), base("beta")], ["chapter"])
    expect(result.every((c) => !c.checked && !c.matched)).toBe(true)
  })
})
