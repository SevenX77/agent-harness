import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { NodeProps } from "@xyflow/react"
import type { FieldSupplyEntry, GraphTopologyItem } from "@/api/types"
import { TooltipProvider } from "@/components/ui/tooltip"
import { dataGapErrorsByNode } from "@/components/studio/node-compile-errors"
import { SkillNode } from "./SkillNode"
import type { SkillGraphNode, SkillGraphNodeData } from "./types"

// n2-canvas#10 (data-gap-viz, PM 2026-06-20): an input field with no upstream blackboard
// supply must show on the canvas node as a compile-style CONFLICT ERROR (same badge +
// tooltip the compile/lint channel uses). The data gap is projected by
// dataGapErrorsByNode and merged into the node's compileErrors channel, so SkillNode
// renders it through the existing per-error `field · line — message` tooltip — proving
// the data gap reaches the canvas conflict-error UI end-to-end.

vi.mock("@xyflow/react", () => ({
  Handle: () => <span data-testid="handle" />,
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
}))

function supply(field: string, supplied: boolean, source: FieldSupplyEntry["source"]): FieldSupplyEntry {
  return { field, supplied, source, producer_phase: null }
}

function row(id: string, fieldSupply: FieldSupplyEntry[]): GraphTopologyItem {
  return { id, src: "", depends_on: [], mode: "logic", field_supply: fieldSupply }
}

function baseData(overrides: Partial<SkillGraphNodeData> = {}): SkillGraphNodeData {
  return {
    skillId: "demo",
    label: "Review",
    mode: "agent",
    status: "idle",
    dependsOn: [],
    ...overrides,
  }
}

function renderNode(data: SkillGraphNodeData): string {
  const props = { data, selected: false } as unknown as NodeProps<SkillGraphNode>
  return renderToStaticMarkup(
    <TooltipProvider>
      <SkillNode {...props} />
    </TooltipProvider>,
  )
}

describe("SkillNode data-gap conflict error (n2-canvas#10)", () => {
  it("renders the unsupplied-input data gap as a node compile-conflict error in the tooltip", () => {
    const byNode = dataGapErrorsByNode([row("review", [supply("summary", false, "none")])])
    const html = renderNode(baseData({ compileErrors: byNode.review }))
    // The conflict-error badge/tooltip surfaces the gap (field name + upstream-supply message).
    expect(html).toContain("compile error")
    expect(html).toContain("summary")
    expect(html.toLowerCase()).toContain("upstream")
  })

  it("renders no data-gap conflict error when every input field is supplied", () => {
    const byNode = dataGapErrorsByNode([row("review", [supply("summary", true, "phase")])])
    const html = renderNode(baseData({ compileErrors: byNode.review ?? [] }))
    expect(html).not.toContain("compile error")
  })
})
