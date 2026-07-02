import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { SkillDetail } from "@/api/types"
import type { SkillGraphNodeData } from "@/components/GraphCanvas"
import { InputPanel, __test__ } from "./InputPanel"

const buttonProps = vi.hoisted((): Array<Record<string, unknown>> => [])

vi.mock("@/components/ui/button", () => ({
  Button: (props: Record<string, unknown> & { children?: ReactNode }) => {
    buttonProps.push(props)
    return <button>{props.children}</button>
  },
}))

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))

const graphMd = [
  "---",
  "io:",
  "  inputs:",
  "    type: object",
  "    required: [chapter_content, chapter_number]",
  "    properties:",
  "      chapter_content:",
  "        type: string",
  "      chapter_number:",
  "        type: integer",
  "  outputs:",
  "    type: object",
  "    required: [segmentation_result]",
  "    properties:",
  "      segmentation_result:",
  "        type: object",
  "        properties:",
  "          paragraphs:",
  "            type: array",
  "            items:",
  "              type: object",
  "              properties:",
  "                type:",
  "                  type: string",
  "                  enum: [A, B, C]",
  "---",
  '<phase depends_on="input">setup</phase>',
].join("\n")

const phaseSkillMd = [
  "---",
  "io:",
  "  inputs:",
  "    type: object",
  "    properties:",
  "      phase_only:",
  "        type: string",
  "  outputs:",
  "    type: object",
  "    properties:",
  "      phase_result:",
  "        type: integer",
  "---",
  "<role>phase</role>",
].join("\n")

function skillDetail(): SkillDetail {
  return {
    files: {
      "GRAPH.md": graphMd,
      "phases/analyze/SKILL.md": phaseSkillMd,
    },
  } as unknown as SkillDetail
}

function selectedPhaseNode(): { id: string; data: SkillGraphNodeData } {
  return {
    id: "analyze",
    data: {
      skillId: "demo-skill",
      label: "analyze",
      mode: "agent",
      status: "idle",
      dependsOn: [],
      filePath: "phases/analyze/SKILL.md",
    },
  }
}

describe("InputPanel example view", () => {
  beforeEach(() => {
    buttonProps.length = 0
  })

  it("renders GRAPH.md input/output generated examples without raw schema definitions", () => {
    const html = renderToStaticMarkup(<InputPanel skillId="demo-skill" skillDetail={skillDetail()} />)

    expect(html).toContain("GRAPH.md")
    expect(html).toContain("Input")
    expect(html).toContain("Output")
    expect(html).toContain("chapter_content")
    expect(html).toContain("chapter_number")
    expect(html).toContain("segmentation_result")
    expect(html).toContain("paragraphs")
    expect(html).not.toContain("&quot;required&quot;")
  })

  it("renders the selected phase file input/output examples when a phase is selected", () => {
    const html = renderToStaticMarkup(
      <InputPanel skillId="demo-skill" skillDetail={skillDetail()} selectedNode={selectedPhaseNode()} />,
    )

    expect(html).toContain("phases/analyze/SKILL.md")
    expect(html).toContain("phase_only")
    expect(html).toContain("phase_result")
    expect(html).not.toContain("chapter_content")
  })

  it("opens GRAPH.md when editing graph-level examples", () => {
    const onFileOpen = vi.fn()
    renderToStaticMarkup(
      <InputPanel skillId="demo-skill" skillDetail={skillDetail()} onFileOpen={onFileOpen} />,
    )

    const editButtons = buttonProps.filter((props) =>
      String(props["aria-label"] ?? "").startsWith("Edit"),
    )
    expect(editButtons).toHaveLength(2)
    ;(editButtons[0].onClick as () => void)()
    ;(editButtons[1].onClick as () => void)()

    expect(onFileOpen).toHaveBeenCalledTimes(2)
    expect(onFileOpen).toHaveBeenNthCalledWith(1, "GRAPH.md")
    expect(onFileOpen).toHaveBeenNthCalledWith(2, "GRAPH.md")
  })

  it("opens the selected phase md when editing phase-level examples", () => {
    const onFileOpen = vi.fn()
    renderToStaticMarkup(
      <InputPanel
        skillId="demo-skill"
        skillDetail={skillDetail()}
        selectedNode={selectedPhaseNode()}
        onFileOpen={onFileOpen}
      />,
    )

    const editButtons = buttonProps.filter((props) =>
      String(props["aria-label"] ?? "").startsWith("Edit"),
    )
    expect(editButtons).toHaveLength(2)
    ;(editButtons[0].onClick as () => void)()

    expect(onFileOpen).toHaveBeenCalledTimes(1)
    expect(onFileOpen).toHaveBeenCalledWith("phases/analyze/SKILL.md")
  })

  it("converts nested JSON schema into a readable example object", () => {
    expect(__test__.jsonExampleFromSchema({
      type: "object",
      properties: {
        chapter_content: { type: "string" },
        chapter_number: { type: "integer" },
        paragraphs: {
          type: "array",
          items: {
            type: "object",
            properties: {
              type: { type: "string", enum: ["A", "B", "C"] },
              description: { type: "string" },
            },
          },
        },
      },
    })).toEqual({
      chapter_content: "",
      chapter_number: 0,
      paragraphs: [{ type: "A", description: "" }],
    })
  })

  it("parses CRLF frontmatter for Windows-authored skill files", () => {
    expect(__test__.parseFrontmatter("---\r\nio:\r\n  inputs:\r\n    type: object\r\n---\r\nbody")).toEqual({
      io: {
        inputs: {
          type: "object",
        },
      },
    })
  })
})
