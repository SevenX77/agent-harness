import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { NodeProps } from "@xyflow/react"
import { SkillNode } from "./SkillNode"
import type { SkillGraphNode, SkillGraphNodeData } from "./types"

// xyflow's Handle needs a ReactFlow provider; stub the primitives so SkillNode
// renders standalone (same approach as SkillNode.error.test.tsx).
vi.mock("@xyflow/react", () => ({
  Handle: () => <span data-testid="handle" />,
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
}))

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: () => null,
}))

function baseData(overrides: Partial<SkillGraphNodeData> = {}): SkillGraphNodeData {
  return {
    skillId: "demo",
    label: "Compose",
    mode: "agent",
    status: "idle",
    dependsOn: [],
    ...overrides,
  }
}

function renderNode(data: SkillGraphNodeData): string {
  const props = { data, selected: false } as unknown as NodeProps<SkillGraphNode>
  return renderToStaticMarkup(<SkillNode {...props} />)
}

describe("SkillNode dirty-downstream graying (N5 atom #3, spec F3)", () => {
  it("grays the node and explains why resume is unavailable when in the affected-downstream set", () => {
    const html = renderNode(baseData({ isDirtyDownstream: true }))
    // The node is dimmed and flagged so the canvas can target it.
    expect(html).toContain('data-dirty-downstream="true"')
    expect(html).toContain('aria-disabled="true"')
    expect(html).toContain("opacity-50")
    // The "why resume is unavailable" reason is shown in-place on the node.
    expect(html).toContain('aria-label="Resume unavailable: upstream changed"')
    expect(html).toContain("an upstream edit invalidated this node")
  })

  it("renders an unaffected node normally (no graying, no reason note)", () => {
    const html = renderNode(baseData({ isDirtyDownstream: false }))
    expect(html).not.toContain("data-dirty-downstream")
    expect(html).not.toContain('aria-label="Resume unavailable: upstream changed"')
    expect(html).not.toContain("opacity-50")
  })

  it("defaults to normal when the flag is omitted (unrelated side-branch)", () => {
    const html = renderNode(baseData())
    expect(html).not.toContain("data-dirty-downstream")
    expect(html).not.toContain('aria-label="Resume unavailable: upstream changed"')
  })
})
