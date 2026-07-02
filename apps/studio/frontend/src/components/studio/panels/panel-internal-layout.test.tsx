import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { InputPanel } from "./InputPanel"
import { PropertiesPanel } from "./PropertiesPanel"

vi.mock("./TestInputsSection", () => ({
  TestInputsSection: () => null,
}))

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))

const graphMd = [
  "---",
  "name: story-deconstruction-v3",
  "description: MVP1-compliant recursive story deconstruction pipeline.",
  "llm_role: analyst",
  "io:",
  "  inputs:",
  "    type: object",
  "    properties:",
  "      chapters:",
  "        type: array",
  "  outputs:",
  "    type: object",
  "    properties:",
  "      result:",
  "        type: string",
  "---",
].join("\n")

const phaseMd = [
  "---",
  "name: review",
  "llm_role: analyst",
  "---",
  "<role>review</role>",
].join("\n")

const skillDetail = {
  files: {
    "GRAPH.md": graphMd,
    "phases/review/SKILL.md": phaseMd,
  },
  graph_topology: [],
} as unknown as SkillDetail

const selectedNode = {
  id: "review",
  data: {
    skillId: "demo",
    label: "review",
    mode: "agent",
    status: "idle",
    dependsOn: [],
    filePath: "phases/review/SKILL.md",
  } satisfies SkillGraphNodeData,
}

describe("studio panel internal layout", () => {
  it("renders Properties as one continuous panel body with field rows", () => {
    const html = renderToStaticMarkup(
      <PropertiesPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={skillDetail}
        selectedNode={selectedNode}
      />,
    )

    expect(html).toContain('data-studio-panel-body="true"')
    expect(html).not.toContain('data-studio-panel-section="true"')
    expect(html).toContain('data-studio-panel-field-row="true"')
    expect(html).toContain('data-studio-panel-actions="true"')
    expect(html).not.toContain("PropertyCard")
  })

  it("renders I/O inside the same panel body contract", () => {
    const html = renderToStaticMarkup(
      <InputPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={skillDetail}
      />,
    )

    expect(html).toContain('data-studio-panel-body="true"')
    expect(html).not.toContain('data-studio-panel-section="true"')
    expect(html).toContain('data-studio-panel-field-row="true"')
    expect(html).toContain("Input")
    expect(html).toContain("Output")
  })
})
