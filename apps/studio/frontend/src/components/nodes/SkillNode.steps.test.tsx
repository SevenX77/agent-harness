import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { NodeProps } from "@xyflow/react"
import { SkillNode } from "./SkillNode"
import { SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID } from "./subgraph-bridge-handles"
import type { SkillGraphNode, SkillGraphNodeData } from "./types"

// xyflow's Handle needs a ReactFlow provider; stub the primitives so SkillNode
// renders standalone (same approach as the other SkillNode tests).
vi.mock("@xyflow/react", () => ({
  Handle: (props: { id?: string; type?: string; position?: string }) => (
    <span
      data-testid="handle"
      data-handle-id={props.id}
      data-handle-type={props.type}
      data-handle-position={props.position}
    />
  ),
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
}))

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: ReactNode }) => <>{children}</>,
  TooltipContent: () => null,
}))

const AGENT_BODY = ['<role>writer</role>', '', '<step id="S1" name="read">Read the brief.</step>'].join('\n')

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

describe("SkillNode inline L3 step editor (N2 atom #15, l3-step-edit)", () => {
  it("shows an Edit steps toggle for an agent node with body + save wired", () => {
    const html = renderNode(
      baseData({ agentBody: AGENT_BODY, onToggleSteps: () => undefined, onStepsSave: () => undefined }),
    )
    expect(html).toContain('aria-label="Edit steps"')
    expect(html).toContain("Edit steps")
    // Collapsed: the editor (and its step rows) is not rendered yet.
    expect(html).not.toContain("Steps</span>")
  })

  it("renders the inline step rows when expanded", () => {
    const html = renderNode(
      baseData({
        agentBody: AGENT_BODY,
        isStepsExpanded: true,
        onToggleSteps: () => undefined,
        onStepsSave: () => undefined,
      }),
    )
    expect(html).toContain('aria-label="Collapse steps"')
    expect(html).toContain("Hide steps")
    // The AgentStepsInline editor mounted with the real body's step parsed in.
    expect(html).toContain("S1")
    expect(html).toContain("Read the brief.")
    expect(html).toContain("Add step")
  })

  it("does not offer step editing for a logic node (no body / callbacks wired)", () => {
    const html = renderNode(baseData({ mode: "logic" }))
    expect(html).not.toContain('aria-label="Edit steps"')
    expect(html).not.toContain("Edit steps")
  })

  it("does not offer step editing for an agent node whose callbacks are not wired", () => {
    const html = renderNode(baseData({ agentBody: AGENT_BODY }))
    expect(html).not.toContain('aria-label="Edit steps"')
  })

  it("renders a dedicated bridge source handle only when the subgraph is expanded", () => {
    const expandedHtml = renderNode(baseData({
      mode: "subgraph",
      isExpanded: true,
      onToggleSubgraph: () => undefined,
    }))
    const collapsedHtml = renderNode(baseData({
      mode: "subgraph",
      isExpanded: false,
      onToggleSubgraph: () => undefined,
    }))

    expect(expandedHtml).toContain('aria-label="Collapse subgraph"')
    expect(expandedHtml).toContain(`data-handle-id="${SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID}"`)
    expect(expandedHtml).toContain('data-handle-type="source"')
    expect(expandedHtml).toContain('data-handle-position="right"')
    expect(collapsedHtml).toContain('aria-label="Expand subgraph"')
    expect(collapsedHtml).not.toContain(`data-handle-id="${SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID}"`)
    expect(expandedHtml).not.toContain("subgraph-toggle-bridge-line")
  })
})
