import { describe, expect, it } from "vitest"
import { parseFrontmatter } from "./io-declarations"

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
