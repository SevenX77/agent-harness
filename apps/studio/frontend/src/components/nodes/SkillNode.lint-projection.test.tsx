import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { NodeProps } from "@xyflow/react"
import type { LintError } from "@/api/types"
import { TooltipProvider } from "@/components/ui/tooltip"
import { lintErrorToCompileError } from "@/components/studio/node-compile-errors"
import { SkillNode } from "./SkillNode"
import type { SkillGraphNode, SkillGraphNodeData } from "./types"

// N3 atom #4 (canvas-node-projection): the node tooltip must surface the SAME field · L<line> —
// message detail when its errors come from realtime lint (LintError) as when they come from manual
// Compile (CompileError). lintErrorToCompileError is the adapter the workspace uses to feed lint
// diagnostics into the node channel; this asserts the rendered badge + count + per-error detail.

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

function lintErr(overrides: Partial<LintError> = {}): LintError {
  return {
    file: "phases/draft/SKILL.md",
    line: 9,
    column: null,
    error_code: "F-v3-002",
    severity: "error",
    message: "unknown tool `frobnicate`",
    phase_name: "draft",
    field_path: "tools",
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

describe("SkillNode tooltip fed by lint-sourced errors (atom #4)", () => {
  it("renders the badge + count + each field · L<line> — message when the node carries lint errors", () => {
    const html = renderNode(
      baseData({
        compileErrors: [
          lintErrorToCompileError(lintErr({ field_path: "tools", line: 9, message: "unknown tool `frobnicate`" })),
          lintErrorToCompileError(lintErr({ field_path: "validator", line: 14, message: "validator must be a boolean" })),
        ],
      }),
    )
    expect(html).toContain("2 compile errors on this node")
    expect(html).toContain("tools · L9 — unknown tool `frobnicate`")
    expect(html).toContain("validator · L14 — validator must be a boolean")
  })

  it("drops the line segment for a line-less lint error, keeping the field and message", () => {
    const html = renderNode(
      baseData({
        compileErrors: [lintErrorToCompileError(lintErr({ field_path: "path", line: null, message: "path must be absolute" }))],
      }),
    )
    expect(html).toContain("1 compile error on this node")
    expect(html).toContain("path — path must be absolute")
  })
})
