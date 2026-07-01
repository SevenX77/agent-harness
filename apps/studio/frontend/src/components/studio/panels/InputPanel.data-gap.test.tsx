import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { GraphTopologyItem, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { InputPanel } from "./InputPanel"

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))

vi.mock("@/components/ui/button", () => ({
  Button: ({ children }: { children?: ReactNode }) => <button>{children}</button>,
}))

const topology: GraphTopologyItem[] = [
  {
    id: "enrich",
    src: "phases/enrich",
    depends_on: ["fetch"],
    mode: "logic",
    io_fields: {
      inputs: { orphan: { type: "string" } },
      outputs: {},
    },
    field_supply: [
      { field: "orphan", supplied: false, source: "none", producer_phase: null },
    ],
  },
]

function detail(): SkillDetail {
  return {
    files: {
      "GRAPH.md": [
        "---",
        "io:",
        "  inputs:",
        "    type: object",
        "    properties:",
        "      topic:",
        "        type: string",
        "  outputs:",
        "    type: object",
        "    properties:",
        "      result:",
        "        type: string",
        "---",
      ].join("\n"),
      "phases/enrich/LOGIC.md": [
        "---",
        "io:",
        "  inputs:",
        "    type: object",
        "    properties:",
        "      orphan:",
        "        type: string",
        "---",
        "body",
      ].join("\n"),
    },
    graph_topology: topology,
  } as unknown as SkillDetail
}

function selectedNode(): { id: string; data: SkillGraphNodeData } {
  return {
    id: "enrich",
    data: {
      skillId: "demo",
      label: "enrich",
      mode: "logic",
      status: "idle",
      dependsOn: ["fetch"],
      filePath: "phases/enrich/LOGIC.md",
    },
  }
}

describe("InputPanel simplified schema view", () => {
  it("shows selected-node schema without restoring per-node data-gap markers", () => {
    const html = renderToStaticMarkup(
      <InputPanel skillId="demo" skillDetail={detail()} selectedNode={selectedNode()} />,
    )

    expect(html).toContain("phases/enrich/LOGIC.md")
    expect(html).toContain("orphan")
    expect(html).not.toContain("topic")
    expect(html).not.toContain("result")
    expect(html).not.toContain("Data gap: input field")
  })
})
