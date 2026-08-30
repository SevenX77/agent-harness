import { renderToStaticMarkup } from "react-dom/server"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"
import type { NodeProps } from "@xyflow/react"
import { SkillNode } from "./SkillNode"
import {
  SKILL_FLOW_SOURCE_HANDLE_ID,
  SKILL_FLOW_TARGET_HANDLE_ID,
  SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID,
} from "./subgraph-bridge-handles"
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
    phasePath: "Draft",
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

// R3-8 (批示轮三 2026-08-29): canvas step EDITING is withdrawn (「应该让用户
// 在编辑器改」); the inline rows stay as a read-only projection because the
// runtime debug bar's 对话续跑 targets them (phase-editing F5, 2026-08-29 rev).
describe("SkillNode inline L3 step projection", () => {
  it("shows a View steps toggle for an agent node with a body + toggle wired", () => {
    const html = renderNode(
      baseData({ agentBody: AGENT_BODY, onToggleSteps: () => undefined }),
    )
    expect(html).toContain('aria-label="View steps"')
    expect(html).toContain("View steps")
    // Collapsed: the projection (and its step rows) is not rendered yet.
    expect(html).not.toContain("Steps</span>")
  })

  it("renders the read-only step rows when expanded — no mutation controls", () => {
    const html = renderNode(
      baseData({
        agentBody: AGENT_BODY,
        isStepsExpanded: true,
        onToggleSteps: () => undefined,
      }),
    )
    expect(html).toContain('aria-label="Collapse steps"')
    expect(html).toContain("Hide steps")
    // The AgentStepsInline projection mounted with the real body's step parsed in.
    expect(html).toContain("S1")
    expect(html).toContain("Read the brief.")
    expect(html).not.toContain("Add step")
    expect(html).not.toContain("<input")
    expect(html).not.toContain("<textarea")
  })

  it("does not offer the steps toggle for a logic node (no body / toggle wired)", () => {
    const html = renderNode(baseData({ mode: "logic" }))
    expect(html).not.toContain('aria-label="View steps"')
    expect(html).not.toContain("View steps")
  })

  it("does not offer the steps toggle for an agent node whose toggle is not wired", () => {
    const html = renderNode(baseData({ agentBody: AGENT_BODY }))
    expect(html).not.toContain('aria-label="View steps"')
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

  it("keeps normal flow handles separate from the subgraph bridge handle", () => {
    const html = renderNode(baseData({
      mode: "subgraph",
      isExpanded: true,
      onToggleSubgraph: () => undefined,
    }))

    expect(html).toContain(`data-handle-id="${SKILL_FLOW_TARGET_HANDLE_ID}"`)
    expect(html).toContain(`data-handle-id="${SKILL_FLOW_SOURCE_HANDLE_ID}"`)
    expect(html).toContain(`data-handle-id="${SUBGRAPH_BRIDGE_SOURCE_HANDLE_ID}"`)
  })
})
