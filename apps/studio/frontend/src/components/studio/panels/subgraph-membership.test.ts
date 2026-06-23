import { describe, expect, it } from "vitest"
import type { GraphTopologyItem, SkillDetail } from "@/api/types"
import { CURRENT_SCHEMA_VERSION } from "@/config/schema"
import { subgraphMembership } from "./subgraph-membership"

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
        filePath: "phases/translate/SUBGRAPH.md",
        path: "/abs/skills/translator",
        status: "resolved",
      },
    ])
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
        filePath: "phases/blank/SUBGRAPH.md",
        path: null,
        status: "missing",
      },
      {
        id: "padded",
        label: "padded",
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
})
