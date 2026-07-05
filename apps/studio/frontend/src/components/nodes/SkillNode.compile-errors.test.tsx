import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { NodeProps } from "@xyflow/react"
import type { CompileError } from "@/api/types"
import { TooltipProvider } from "@/components/ui/tooltip"
import { SkillNode, formatNodeCompileError } from "./SkillNode"
import type { SkillGraphNode, SkillGraphNodeData } from "./types"

// Canvas node compile-error projection (authoring N3 atom #4): the node badge's
// tooltip expands from a bare count to a per-error locator + message list. The
// detail is asserted on the trigger's accessible name because Radix portals the
// styled TooltipContent, which is not emitted by renderToStaticMarkup.

// xyflow's Handle needs a ReactFlow provider; stub the primitives so SkillNode renders
// standalone (same approach as SkillNode.error.test.tsx).
vi.mock("@xyflow/react", () => ({
  Handle: () => <span data-testid="handle" />,
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
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

function compileError(overrides: Partial<CompileError> = {}): CompileError {
  return {
    file: "phases/segment/LOGIC.md",
    line: 12,
    field: "validator",
    severity: "fatal",
    message: "validator must be a boolean",
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

describe("formatNodeCompileError - per-error line projection (atom #4)", () => {
  it("renders field L<line> - message when both are present", () => {
    expect(formatNodeCompileError(compileError())).toBe("validator L12 - validator must be a boolean")
  })

  it("drops the line segment when the engine gave no line", () => {
    expect(formatNodeCompileError(compileError({ line: null }))).toBe("validator - validator must be a boolean")
  })

  it("drops the field segment when the engine gave no field", () => {
    expect(formatNodeCompileError(compileError({ field: null }))).toBe("L12 - validator must be a boolean")
  })

  it("falls back to just the message when neither field nor line is attributed", () => {
    expect(formatNodeCompileError(compileError({ field: null, line: null }))).toBe(
      "validator must be a boolean",
    )
  })
})

describe("SkillNode compile-error tooltip (atom #4)", () => {
  it("lists each compile error's field line - message on the badge", () => {
    const html = renderNode(
      baseData({
        compileErrors: [
          compileError({ field: "validator", line: 12, message: "validator must be a boolean" }),
          compileError({ field: "tools", line: 7, message: "unknown tool `frobnicate`" }),
        ],
      }),
    )
    // Count header is retained.
    expect(html).toContain("2 compile errors on this node")
    expect(html).toContain('data-node-compile-error-badge="true"')
    expect(html).toContain("h-5")
    expect(html).toContain("text-[11px]")
    // Each error's locator + message is reachable on the trigger (survives SSR).
    expect(html).toContain("validator L12 - validator must be a boolean")
    expect(html).toContain("tools L7 - unknown tool `frobnicate`")
  })

  it("singularises the count header for a single error", () => {
    const html = renderNode(
      baseData({ compileErrors: [compileError({ field: "path", line: null, message: "path must be absolute" })] }),
    )
    expect(html).toContain("1 compile error on this node")
    expect(html).toContain("path - path must be absolute")
  })

  it("renders no compile-error badge when the node has no compile errors", () => {
    const html = renderNode(baseData({ compileErrors: [] }))
    expect(html).not.toContain("compile error")
  })
})
