import { describe, expect, it } from "vitest"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import {
  ancestorDirsForFile,
  assetTreeTargetForNode,
  phaseIdFromFilePath,
  subgraphChildPhaseChainForFile,
  subgraphGraphChainForFile,
} from "./asset-tree-target"
import type { SubgraphMembership } from "./subgraph-membership"

function node(data: Partial<SkillGraphNodeData>): { id: string; data: SkillGraphNodeData } {
  return {
    id: data.phaseId ?? "n",
    data: {
      skillId: "main",
      label: "n",
      mode: "skill",
      status: "idle",
      dependsOn: [],
      ...data,
    } as SkillGraphNodeData,
  }
}

describe("ancestorDirsForFile", () => {
  it("lists root-first directories down to the file's parent", () => {
    expect(ancestorDirsForFile("phases/extract/SUBGRAPH.md")).toEqual(["", "phases", "phases/extract"])
    expect(ancestorDirsForFile("GRAPH.md")).toEqual([""])
    expect(ancestorDirsForFile("phases\\x\\SKILL.md")).toEqual(["", "phases", "phases/x"])
  })
})

describe("phaseIdFromFilePath", () => {
  it("maps a node-definition file back to its phase id", () => {
    expect(phaseIdFromFilePath("phases/extract/SKILL.md")).toBe("extract")
    expect(phaseIdFromFilePath("phases/score/LOGIC.md")).toBe("score")
    expect(phaseIdFromFilePath("phases/call/SUBGRAPH.md")).toBe("call")
    expect(phaseIdFromFilePath("phases\\call\\SUBGRAPH.md")).toBe("call")
  })

  it("returns null for non node-definition files", () => {
    expect(phaseIdFromFilePath("GRAPH.md")).toBeNull()
    expect(phaseIdFromFilePath("phases/extract/actions/run.py")).toBeNull()
    expect(phaseIdFromFilePath("phases/extract/notes.md")).toBeNull()
    expect(phaseIdFromFilePath("references/readme.md")).toBeNull()
  })
})

describe("subgraphChildPhaseChainForFile", () => {
  const member = (over: Partial<SubgraphMembership>): SubgraphMembership => ({
    id: "event_timeline",
    label: "Event Timeline",
    level: 1,
    filePath: "phases/event_timeline/SUBGRAPH.md",
    path: "/ws/main/subgraph/event-timeline",
    status: "resolved",
    ...over,
  })

  const root = "/ws/main"

  it("maps a level-1 subgraph child file to its phase chain", () => {
    const chain = subgraphChildPhaseChainForFile(
      "subgraph/event-timeline/phases/extract/SKILL.md",
      root,
      [member({})],
    )
    expect(chain).toEqual(["event_timeline", "extract"])
  })

  it("picks the deepest matching subgraph for a nested child file", () => {
    const chain = subgraphChildPhaseChainForFile(
      "subgraph/event-timeline/subgraph/event-extraction/phases/review/LOGIC.md",
      root,
      [
        member({}),
        member({
          id: "event_timeline/event_extraction",
          level: 2,
          path: "/ws/main/subgraph/event-timeline/subgraph/event-extraction",
        }),
      ],
    )
    expect(chain).toEqual(["event_timeline", "event_extraction", "review"])
  })

  it("returns null for non-node files and unknown / external subgraphs", () => {
    expect(
      subgraphChildPhaseChainForFile("subgraph/event-timeline/GRAPH.md", root, [member({})]),
    ).toBeNull()
    expect(
      subgraphChildPhaseChainForFile("phases/extract/SKILL.md", root, [member({})]),
    ).toBeNull()
    expect(
      subgraphChildPhaseChainForFile(
        "phases/extract/SKILL.md",
        root,
        [member({ path: "/elsewhere/shared/subgraph/x" })],
      ),
    ).toBeNull()
  })

  it("matches case-insensitively and tolerates trailing slashes / backslashes", () => {
    const chain = subgraphChildPhaseChainForFile(
      "subgraph\\event-timeline\\phases\\extract\\SKILL.md",
      "/ws/main/",
      [member({ path: "/ws/Main/subgraph/event-timeline/" })],
    )
    expect(chain).toEqual(["event_timeline", "extract"])
  })
})

describe("subgraphGraphChainForFile", () => {
  const member = (over: Partial<SubgraphMembership>): SubgraphMembership => ({
    id: "event_timeline",
    label: "Event Timeline",
    level: 1,
    filePath: "phases/event_timeline/SUBGRAPH.md",
    path: "/ws/main/subgraph/event-timeline",
    status: "resolved",
    ...over,
  })

  it("maps a subgraph's own GRAPH.md to its phase chain", () => {
    expect(
      subgraphGraphChainForFile("subgraph/event-timeline/GRAPH.md", "/ws/main", [member({})]),
    ).toEqual(["event_timeline"])
  })

  it("maps a nested subgraph GRAPH.md to its full chain", () => {
    const chain = subgraphGraphChainForFile(
      "subgraph/event-timeline/subgraph/event-extraction/GRAPH.md",
      "/ws/main",
      [
        member({}),
        member({
          id: "event_timeline/event_extraction",
          level: 2,
          path: "/ws/main/subgraph/event-timeline/subgraph/event-extraction",
        }),
      ],
    )
    expect(chain).toEqual(["event_timeline", "event_extraction"])
  })

  it("returns null for non-GRAPH.md files", () => {
    expect(
      subgraphGraphChainForFile("subgraph/event-timeline/phases/x/SKILL.md", "/ws/main", [member({})]),
    ).toBeNull()
    expect(subgraphGraphChainForFile("GRAPH.md", "/ws/main", [member({})])).toBeNull()
  })
})

describe("assetTreeTargetForNode", () => {
  const context = { rootTarget: "/ws/main", skillId: "main" }

  it("returns null without a selected node or file path", () => {
    expect(assetTreeTargetForNode(null, context)).toBeNull()
    expect(assetTreeTargetForNode(node({ filePath: undefined }), context)).toBeNull()
  })

  it("targets the Skill Files tree for a node in the open skill", () => {
    const target = assetTreeTargetForNode(
      node({ filePath: "phases/extract/SKILL.md", skillId: "main", workspaceRoot: "/ws/main" }),
      context,
    )
    expect(target).toEqual({
      section: "skill",
      filePath: "phases/extract/SKILL.md",
      ancestorDirs: ["", "phases", "phases/extract"],
      subgraphRoot: null,
    })
  })

  it("targets a Subgraphs Files block when the node belongs to a child graph", () => {
    const target = assetTreeTargetForNode(
      node({ filePath: "phases/score/LOGIC.md", skillId: "child", workspaceRoot: "/ws/main/subgraph/child" }),
      context,
    )
    expect(target?.section).toBe("subgraph")
    expect(target?.subgraphRoot).toBe("/ws/main/subgraph/child")
    expect(target?.ancestorDirs).toEqual(["", "phases", "phases/score"])
  })

  it("treats a node whose workspace root only differs by trailing slash / case as the open skill", () => {
    const target = assetTreeTargetForNode(
      node({ filePath: "phases/extract/SKILL.md", skillId: "main", workspaceRoot: "/ws/main/" }),
      context,
    )
    expect(target?.section).toBe("skill")
  })
})
