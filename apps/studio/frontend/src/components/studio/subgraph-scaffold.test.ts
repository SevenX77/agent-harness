import { describe, expect, it } from "vitest"
import {
  autoCreatedSubgraphChildDir,
  defaultSubgraphChildDir,
  subgraphChildScaffoldFiles,
} from "./subgraph-scaffold"

describe("defaultSubgraphChildDir", () => {
  it("lands the child graph under the skill-root subgraph/ container", () => {
    expect(defaultSubgraphChildDir("producer_review")).toBe("subgraph/producer_review")
    expect(defaultSubgraphChildDir("subgraph")).toBe("subgraph/subgraph")
  })
})

describe("subgraphChildScaffoldFiles", () => {
  it("emits a standard empty-skill scaffold rooted at the child dir", () => {
    const files = subgraphChildScaffoldFiles("subgraph/producer_review", "producer_review")
    expect(files.map((file) => file.path)).toEqual([
      "subgraph/producer_review/GRAPH.md",
      "subgraph/producer_review/phases/init/SKILL.md",
    ])

    const graph = files[0].content
    expect(graph).toContain('schema_version: "v0.3.0"')
    expect(graph).toContain("name: producer_review")
    expect(graph).toContain("phases:\n  - init")
    expect(graph).toContain('<phase depends_on="input" output>init</phase>')
    expect(graph.endsWith("\n")).toBe(true)

    const skill = files[1].content
    expect(skill).toContain("<role>TODO: describe who this agent is.</role>")
    expect(skill).toContain('<step id="S1" name="todo">')
    expect(skill.endsWith("\n")).toBe(true)
  })

  it("stays byte-for-byte identical to the canonical sole-writer scaffold", () => {
    // Mirrors apps/studio/backend/app/services/skills.py `_SCAFFOLD_FILES` /
    // apps/studio/tauri/src/native_fs.rs `scaffold_files_for` so an auto-created
    // child graph is indistinguishable from a "New skill" scaffold.
    const expectedGraph =
      '---\nschema_version: "v0.3.0"\nname: foo\ndescription: "New Studio skill"\n' +
      "io:\n  inputs:\n    type: object\n    properties: {}\n" +
      "  outputs:\n    type: object\n    properties: {}\n" +
      'phases:\n  - init\n---\n<phase depends_on="input" output>init</phase>\n'
    const expectedSkill =
      "---\nio:\n  inputs:\n    type: object\n    properties: {}\n" +
      "  outputs:\n    type: object\n    properties: {}\ntools: []\nmax_iterations: 10\n---\n" +
      "<role>TODO: describe who this agent is.</role>\n" +
      "<goal>TODO: describe what this agent should produce.</goal>\n\n" +
      '<step id="S1" name="todo">TODO: describe the first step.</step>\n\n' +
      '<protocol id="P1">TODO: describe a rule the agent must follow.</protocol>\n'

    const files = subgraphChildScaffoldFiles("subgraph/foo", "foo")
    expect(files[0].content).toBe(expectedGraph)
    expect(files[1].content).toBe(expectedSkill)
  })
})

describe("autoCreatedSubgraphChildDir", () => {
  it("matches the auto-created relative default shape", () => {
    expect(autoCreatedSubgraphChildDir("subgraph/producer_review")).toBe("subgraph/producer_review")
    expect(autoCreatedSubgraphChildDir("subgraph/foo/")).toBe("subgraph/foo")
    expect(autoCreatedSubgraphChildDir("subgraph\\foo")).toBe("subgraph/foo")
  })

  it("refuses anything that is not the auto-created default (safety)", () => {
    expect(autoCreatedSubgraphChildDir(null)).toBeNull()
    expect(autoCreatedSubgraphChildDir("")).toBeNull()
    expect(autoCreatedSubgraphChildDir("  ")).toBeNull()
    // Absolute / external / re-pointed paths must never be auto-deleted (D7).
    expect(autoCreatedSubgraphChildDir("/Users/me/other-skill")).toBeNull()
    expect(autoCreatedSubgraphChildDir("C:\\skills\\other")).toBeNull()
    expect(autoCreatedSubgraphChildDir("../sibling")).toBeNull()
    expect(autoCreatedSubgraphChildDir("subgraph/foo/bar")).toBeNull()
    expect(autoCreatedSubgraphChildDir("subgraph")).toBeNull()
    expect(autoCreatedSubgraphChildDir("other/foo")).toBeNull()
    expect(autoCreatedSubgraphChildDir("subgraph/..")).toBeNull()
  })
})
