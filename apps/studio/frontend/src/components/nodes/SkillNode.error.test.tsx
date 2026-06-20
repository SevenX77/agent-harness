import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { NodeProps } from "@xyflow/react"
import { SkillNode } from "./SkillNode"
import type { SkillGraphNode, SkillGraphNodeData } from "./types"

// xyflow's Handle needs a ReactFlow provider; stub the primitives so SkillNode
// renders standalone (same approach as SkillNode.golden.test.tsx).
vi.mock("@xyflow/react", () => ({
  Handle: () => <span data-testid="handle" />,
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
}))

// Radix Tooltip portals its content; keep the trigger inline and drop the
// portalled content for a static render.
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

describe("SkillNode in-place error message (N5 atom #1, spec F1)", () => {
  it("renders the error summary in-place when the node failed", () => {
    const html = renderNode(
      baseData({ status: "error", errorMessage: "Output failed schema validation: missing field `title`" }),
    )
    expect(html).toContain('aria-label="Node error summary"')
    expect(html).toContain("Output failed schema validation: missing field `title`")
  })

  it("does not render the error summary when the node has an error status but no message", () => {
    const html = renderNode(baseData({ status: "error" }))
    expect(html).not.toContain('aria-label="Node error summary"')
  })

  it("does not render the error summary for a non-error node that carries a stale message", () => {
    const html = renderNode(baseData({ status: "success", errorMessage: "stale failure text" }))
    expect(html).not.toContain('aria-label="Node error summary"')
    expect(html).not.toContain("stale failure text")
  })
})
