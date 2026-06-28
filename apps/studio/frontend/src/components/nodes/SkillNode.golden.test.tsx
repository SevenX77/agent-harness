import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { NodeProps } from "@xyflow/react"
import { SkillNode } from "./SkillNode"
import type { SkillGraphNode, SkillGraphNodeData } from "./types"

// xyflow's Handle needs a ReactFlow provider; stub the primitives so SkillNode
// renders standalone (same approach as GraphCanvas.test.tsx).
vi.mock("@xyflow/react", () => ({
  Handle: () => <span data-testid="handle" />,
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
}))

// Radix Tooltip portals its content; keep the trigger (which carries the badge +
// aria-label) inline and drop the portalled content for a static render.
vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: () => null,
}))

function baseData(overrides: Partial<SkillGraphNodeData> = {}): SkillGraphNodeData {
  return {
    skillId: "demo",
    label: "Draft",
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

describe("SkillNode golden badge (atom #30)", () => {
  it("shows the golden badge when the node has golden", () => {
    const html = renderNode(baseData({ goldenState: "has-golden" }))
    expect(html).toContain('aria-label="Golden captured"')
  })

  it("hides the golden badge when the node has no golden (no fabricated 🟡/🔘 state)", () => {
    const html = renderNode(baseData())
    expect(html).not.toContain('aria-label="Golden captured"')
  })
})
