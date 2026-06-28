import { describe, expect, it } from "vitest"
import type { GraphTopologyItem, SkillDetail } from "@/api/types"
import { CURRENT_SCHEMA_VERSION } from "@/config/schema"
import { loadRecursiveSubgraphMembership, subgraphMembership, type SubgraphMembership } from "./subgraph-membership"

function skillDetailWithTopology(topology: GraphTopologyItem[], files: Record<string, string> = {}): SkillDetail {
  return {
    manifest: {
      schema_version: CURRENT_SCHEMA_VERSION,
      name: "parent",
      description: "",
      io: {
        inputs: { type: "object", properties: {} },
        outputs: { type: "object", properties: {} },
      },
      phases: [],
    },
    graph_topology: topology,
    node_schema_v21: {},
    io_schema: {},
    file_paths: {},
    files,
    manifest_errors: null,
    has_golden: false,
    latest_run_metadata: null,
    lint_result: null,
  }
}

describe("subgraphMembership", () => {
  it("returns an empty list when there is no skill detail", () => {
    expect(subgraphMembership(undefined)).toEqual([])
  })

  it("ignores non-subgraph phases (logic / skill rows)", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        { id: "setup", src: "phases/setup", depends_on: [], mode: "logic" },
        { id: "review", src: "phases/review", depends_on: [], mode: "skill" },
      ]),
    )

    expect(memberships).toEqual([])
  })

  it("marks a subgraph phase with an absolute path as resolved", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        {
          id: "translate",
          src: "phases/translate",
          depends_on: ["setup"],
          mode: "subgraph",
          path: "/abs/skills/translator",
        },
      ]),
    )

    expect(memberships).toEqual([
      {
        id: "translate",
        label: "translate",
        level: 1,
        filePath: "phases/translate/SUBGRAPH.md",
        path: "/abs/skills/translator",
        status: "resolved",
      },
    ])
  })

  it("resolves a relative subgraph phase path from the owning skill root", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        {
          id: "translate",
          src: "phases/translate",
          depends_on: ["setup"],
          mode: "subgraph",
          path: "subgraph/translator",
        },
      ]),
      "/skills/parent",
    )

    expect(memberships).toEqual([
      {
        id: "translate",
        label: "translate",
        level: 1,
        filePath: "phases/translate/SUBGRAPH.md",
        path: "/skills/parent/subgraph/translator",
        status: "resolved",
      },
    ])
  })

  it("marks a relative path without an owning skill root as missing", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        { id: "translate", src: "phases/translate", depends_on: [], mode: "subgraph", path: "subgraph/translator" },
      ]),
    )

    expect(memberships[0]).toMatchObject({
      id: "translate",
      path: null,
      status: "missing",
    })
  })

  it("marks a subgraph phase whose path is null as missing", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        { id: "translate", src: "phases/translate", depends_on: [], mode: "subgraph", path: null },
      ]),
    )

    expect(memberships).toEqual([
      {
        id: "translate",
        label: "translate",
        level: 1,
        filePath: "phases/translate/SUBGRAPH.md",
        path: null,
        status: "missing",
      },
    ])
  })

  it("marks a legacy target_skill subgraph as migration-required instead of resolved", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology(
        [
          { id: "translate", src: "phases/translate", depends_on: [], mode: "subgraph", path: null },
        ],
        {
          "phases/translate/SUBGRAPH.md": [
            "---",
            "name: translate",
            "target_skill: legacy.registry.child",
            "---",
            "",
          ].join("\n"),
        },
      ),
    )

    expect(memberships).toEqual([
      {
        id: "translate",
        label: "translate",
        level: 1,
        filePath: "phases/translate/SUBGRAPH.md",
        path: null,
        status: "migration-required",
        legacyTargetSkill: "legacy.registry.child",
      },
    ])
  })

  it("treats a blank/whitespace path as missing and trims a usable path", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        { id: "blank", src: "phases/blank", depends_on: [], mode: "subgraph", path: "   " },
        { id: "padded", src: "phases/padded", depends_on: [], mode: "subgraph", path: "  /abs/child  " },
      ]),
    )

    expect(memberships).toEqual([
      {
        id: "blank",
        label: "blank",
        level: 1,
        filePath: "phases/blank/SUBGRAPH.md",
        path: null,
        status: "missing",
      },
      {
        id: "padded",
        label: "padded",
        level: 1,
        filePath: "phases/padded/SUBGRAPH.md",
        path: "/abs/child",
        status: "resolved",
      },
    ])
  })

  it("keeps a topology src that already points at SUBGRAPH.md as the editable file path", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        {
          id: "translate",
          src: "phases/translate/SUBGRAPH.md",
          depends_on: [],
          mode: "subgraph",
          path: "/abs/skills/translator",
        },
      ]),
    )

    expect(memberships[0]?.filePath).toBe("phases/translate/SUBGRAPH.md")
  })

  it("derives membership only from subgraph rows, preserving topology order", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        { id: "a", src: "phases/a", depends_on: [], mode: "logic" },
        { id: "b", src: "phases/b", depends_on: [], mode: "subgraph", path: "/abs/b" },
        { id: "c", src: "phases/c", depends_on: [], mode: "subgraph", path: null },
      ]),
    )

    expect(memberships.map((m) => m.id)).toEqual(["b", "c"])
    expect(memberships.map((m) => m.status)).toEqual(["resolved", "missing"])
  })

  it("surfaces recursive levels when topology provides them and defaults to level 1", () => {
    const memberships = subgraphMembership(
      skillDetailWithTopology([
        { id: "root_child", src: "phases/root_child", depends_on: [], mode: "subgraph", path: "/abs/root" },
        {
          id: "nested_child",
          src: "phases/nested_child",
          depends_on: ["root_child"],
          mode: "subgraph",
          path: "/abs/nested",
          level: 3,
        } as GraphTopologyItem,
      ]),
    )

    expect(memberships.map((m) => ({ id: m.id, level: m.level }))).toEqual([
      { id: "root_child", level: 1 },
      { id: "nested_child", level: 3 },
    ])
  })

  it("inserts nested subgraphs directly after their parent with incremented levels", async () => {
    const topLevel: SubgraphMembership[] = [
      {
        id: "story_analysis",
        label: "story_analysis",
        level: 1,
        filePath: "phases/story_analysis/SUBGRAPH.md",
        workspaceRoot: "/skills/root",
        path: "/skills/story-analysis",
        status: "resolved",
      },
    ]
    const files = new Map<string, string>([
      [
        "/skills/story-analysis::GRAPH.md",
        [
          "<graph>",
          '<phase depends_on="input">prepare_batches</phase>',
          '<phase depends_on="prepare_batches">analyze_batches</phase>',
          '<phase depends_on="analyze_batches" output>finalize</phase>',
          "</graph>",
        ].join("\n"),
      ],
      [
        "/skills/story-analysis::phases/analyze_batches/SUBGRAPH.md",
        ["---", "name: batch_analysis", "path: subgraph/batch-analysis", "---", ""].join("\n"),
      ],
      [
        "/skills/story-analysis/subgraph/batch-analysis::GRAPH.md",
        ["<graph>", '<phase depends_on="input">prepare</phase>', "</graph>"].join("\n"),
      ],
    ])

    const memberships = await loadRecursiveSubgraphMembership(topLevel, async (workspaceRoot, relativePath) => {
      const content = files.get(`${workspaceRoot}::${relativePath}`)
      if (content == null) {
        throw new Error(`missing ${workspaceRoot}::${relativePath}`)
      }
      return { content }
    })

    expect(memberships.map((member) => member.label)).toEqual(["story_analysis", "batch_analysis"])
    expect(memberships[1]).toMatchObject({
      id: "story_analysis/analyze_batches",
      label: "batch_analysis",
      level: 2,
      filePath: "phases/analyze_batches/SUBGRAPH.md",
      workspaceRoot: "/skills/story-analysis",
      path: "/skills/story-analysis/subgraph/batch-analysis",
      status: "resolved",
    })
  })
})
