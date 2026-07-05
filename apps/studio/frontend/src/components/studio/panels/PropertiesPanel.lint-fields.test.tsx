import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"
import type { LintError, SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { TooltipProvider } from "@/components/ui/tooltip"
import { PropertiesPanel } from "./PropertiesPanel"

// Field-level lint near-projection (authoring N3 atom #5): the Properties panel marks the
// offending frontmatter field by the engine's `field_path`. No-field errors degrade to the
// node badge (not asserted here — they simply do not render a field marker).

function baseData(overrides: Partial<SkillGraphNodeData>): SkillGraphNodeData {
  return {
    skillId: "demo",
    label: "phase",
    mode: "logic",
    status: "idle",
    dependsOn: [],
    ...overrides,
  }
}

function lintErr(overrides: Partial<LintError>): LintError {
  return {
    file: "phases/segment/LOGIC.md",
    line: null,
    column: null,
    error_code: "F-v3-runtime-state-mapping-failed",
    severity: "error",
    message: "boom",
    phase_name: "segment",
    field_path: null,
    source_path: null,
    ...overrides,
  }
}

function renderPanel(args: {
  id: string
  data: SkillGraphNodeData
  filePath: string
  content: string
  lintErrors?: LintError[]
}): string {
  const skillDetail = { files: { [args.filePath]: args.content } } as unknown as SkillDetail
  return renderToStaticMarkup(
    <TooltipProvider>
      <PropertiesPanel
        skillId="demo"
        skillDetail={skillDetail}
        selectedNode={{ id: args.id, data: args.data }}
        lintErrors={args.lintErrors ?? null}
      />
    </TooltipProvider>,
  )
}

const LOGIC_CONTENT = ["---", "name: segment", "validator: true", "---", "body"].join("\n")

describe("PropertiesPanel — field-level lint projection (atom #5)", () => {
  it("marks the field named by the engine field_path", () => {
    const html = renderPanel({
      id: "segment",
      data: baseData({ filePath: "phases/segment/LOGIC.md" }),
      filePath: "phases/segment/LOGIC.md",
      content: LOGIC_CONTENT,
      lintErrors: [lintErr({ field_path: "validator", message: "validator must be a boolean" })],
    })
    // The matched field shows a marker carrying the engine message in its hover label.
    expect(html).toContain("Field has 1 issue")
    expect(html).toContain("validator must be a boolean")
  })

  it("shows selected-node diagnostics whose engine field_path is not a Properties form field", () => {
    const html = renderPanel({
      id: "segment",
      data: baseData({ mode: "agent", filePath: "phases/segment/SKILL.md" }),
      filePath: "phases/segment/SKILL.md",
      content: ["---", "name: segment", "---", "steps: []"].join("\n"),
      lintErrors: [
        lintErr({
          file: "phases/segment/SKILL.md",
          line: 2,
          error_code: "F-v3-graph-dataflow-source-missing",
          message: "phase 'segment' input 'chapter_lines' has no root, upstream, or source:file provider",
          field_path: "segment.io.inputs.properties.chapter_lines",
        }),
      ],
    })

    expect(html).toContain("1 lint issue on this node")
    expect(html).toContain("segment.io.inputs.properties.chapter_lines")
    expect(html).toContain("chapter_lines")
    expect(html).toContain("source:file provider")
  })

  it("does NOT mark fields that have no matching field_path", () => {
    const html = renderPanel({
      id: "segment",
      data: baseData({ filePath: "phases/segment/LOGIC.md" }),
      filePath: "phases/segment/LOGIC.md",
      content: LOGIC_CONTENT,
      // GRAPH-level error: no field_path → degrades to node badge, no field marker.
      lintErrors: [lintErr({ field_path: null, file: "GRAPH.md", phase_name: null, message: "graph broken" })],
    })
    expect(html).not.toContain("Field has")
    expect(html).not.toContain("graph broken")
  })

  it("scopes markers to the selected node — other phases' field errors are ignored", () => {
    const html = renderPanel({
      id: "segment",
      data: baseData({ filePath: "phases/segment/LOGIC.md" }),
      filePath: "phases/segment/LOGIC.md",
      content: LOGIC_CONTENT,
      lintErrors: [
        lintErr({ phase_name: "expand", file: "phases/expand/SKILL.md", field_path: "validator", message: "other node" }),
      ],
    })
    expect(html).not.toContain("Field has")
    expect(html).not.toContain("other node")
  })

  it("renders cleanly with empty / no lint errors (degrade path)", () => {
    const html = renderPanel({
      id: "segment",
      data: baseData({ filePath: "phases/segment/LOGIC.md" }),
      filePath: "phases/segment/LOGIC.md",
      content: LOGIC_CONTENT,
      lintErrors: [],
    })
    expect(html).not.toContain("Field has")
    // The validator field still renders. No sibling validator.py here, so it shows the
    // create affordance rather than the on/off switch.
    expect(html).toContain("Create validator.py")
  })
})
