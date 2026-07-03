import { describe, expect, it } from "vitest"
import { fieldPathRows, flattenFieldPaths, isObjectSchema, parseFrontmatter } from "./io-declarations"

// A malformed edit in GRAPH.md must NOT crash the editor. The i/o panel (InputPanel)
// reads the authoritative frontmatter live via parseFrontmatter DURING RENDER, so a
// duplicate mapping key — which js-yaml's default load() rejects with a thrown
// "duplicated mapping key" YAMLException — used to throw straight through render.
// With no error boundary above it, React tore down the whole app (black screen).
// parseFrontmatter must instead DEGRADE to {}; the async engine lint still surfaces
// the real error as an editor marker.
describe("parseFrontmatter — malformed YAML degrades, never throws", () => {
  const dupKeyGraph = [
    "---",
    'schema_version: "v0.3.0"',
    "name: demo",
    "io:",
    "  outputs:",
    "    type: object",
    "    properties:",
    "      chapter_number:",
    "        type: integer",
    "      chapter_number:",
    "        type: integer",
    "---",
    "body",
  ].join("\n")

  it("returns {} for a duplicate mapping key instead of throwing", () => {
    expect(() => parseFrontmatter(dupKeyGraph)).not.toThrow()
    expect(parseFrontmatter(dupKeyGraph)).toEqual({})
  })

  it("still parses valid frontmatter into an object", () => {
    expect(parseFrontmatter("---\nio:\n  inputs:\n    type: object\n---\nbody")).toEqual({
      io: { inputs: { type: "object" } },
    })
  })

  it("returns {} when there is no frontmatter at all", () => {
    expect(parseFrontmatter("just a body, no ---")).toEqual({})
  })
})

describe("nested field path utilities (nested addressing, PM 2026-07-03)", () => {
  const properties = {
    topic: { type: "string" },
    chapter: {
      type: "object",
      properties: {
        aa_number: { type: "integer" },
        meta: { type: "object", properties: { title: { type: "string" } } },
      },
    },
    tags: { type: "array" },
  }

  it("isObjectSchema recognises explicit type, union type, and bare properties", () => {
    expect(isObjectSchema({ type: "object" })).toBe(true)
    expect(isObjectSchema({ type: ["object", "null"] })).toBe(true)
    expect(isObjectSchema({ properties: { a: {} } })).toBe(true)
    expect(isObjectSchema({ type: "string" })).toBe(false)
    expect(isObjectSchema({})).toBe(false)
  })

  it("fieldPathRows emits parents before descendants with depth + dotted paths", () => {
    const rows = fieldPathRows(properties)
    expect(rows.map((r) => r.path)).toEqual([
      "topic",
      "chapter",
      "chapter.aa_number",
      "chapter.meta",
      "chapter.meta.title",
      "tags",
    ])
    const byPath = new Map(rows.map((r) => [r.path, r]))
    expect(byPath.get("chapter")).toMatchObject({ name: "chapter", depth: 0, hasChildren: true })
    expect(byPath.get("chapter.aa_number")).toMatchObject({ name: "aa_number", depth: 1, hasChildren: false })
    expect(byPath.get("chapter.meta.title")).toMatchObject({ depth: 2, hasChildren: false })
  })

  it("flattenFieldPaths returns every addressable dotted path", () => {
    expect(flattenFieldPaths(properties)).toEqual([
      "topic",
      "chapter",
      "chapter.aa_number",
      "chapter.meta",
      "chapter.meta.title",
      "tags",
    ])
  })
})
