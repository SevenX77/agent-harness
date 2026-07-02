import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { SkillDetail } from "@/api/types"
import { InputPanel, __test__ } from "./InputPanel"

const testInputsProps = vi.hoisted((): Array<Record<string, unknown>> => [])

vi.mock("./TestInputsSection", () => ({
  TestInputsSection: (props: Record<string, unknown>) => {
    testInputsProps.push(props)
    return <div data-mock="test-inputs" />
  },
}))

vi.mock("@/components/ui/scroll-area", () => ({
  ScrollArea: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}))

vi.mock("@/lib/hash", () => ({
  sha256Hex: vi.fn(async () => "hash-of-previous-content"),
}))

const graphMd = [
  "---",
  "io:",
  "  inputs:",
  "    type: object",
  "    properties:",
  "      topic:",
  "        type: string",
  "      novel:",
  "        type: string",
  "        source: file",
  "        path: imports/material/novel.md",
  "      chapters:",
  "        type: array",
  "        source: file",
  "        dir: imports/abc_segmentation",
  "        pattern: chapter_{n}_latest_*.json",
  "        numbers: [1, 2, 7]",
  "  outputs:",
  "    type: object",
  "    properties:",
  "      result:",
  "        type: string",
  "  artifacts:",
  "    - stem: story_framework",
  "      mode: single",
  "      fields: [result]",
  "    - stem: abc_segmentation",
  "      mode: per-item",
  "      fields: [result]",
  "---",
  "<phase depends_on=\"input\">setup</phase>",
].join("\n")

function detail(): SkillDetail {
  return {
    files: {
      "GRAPH.md": graphMd,
    },
  } as unknown as SkillDetail
}

describe("InputPanel sections (D-IO-PREVIEW 2026-07-02)", () => {
  it("mounts TestInputsSection wired to the selected test input", () => {
    testInputsProps.length = 0
    const onSelectTestInput = vi.fn()
    renderToStaticMarkup(
      <InputPanel
        skillId="demo"
        workspaceRoot="/skills/demo"
        skillDetail={detail()}
        selectedTestInputId="case-a"
        onSelectTestInput={onSelectTestInput}
      />,
    )

    expect(testInputsProps).toHaveLength(1)
    expect(testInputsProps[0].skillId).toBe("demo")
    expect(testInputsProps[0].workspaceRoot).toBe("/skills/demo")
    expect(testInputsProps[0].selectedId).toBe("case-a")
    ;(testInputsProps[0].onSelect as (id: string | null) => void)("case-b")
    expect(onSelectTestInput).toHaveBeenCalledWith("case-b")
  })

  it("has no golden section and no inline schema/import forms (r3 panel收敛)", () => {
    const html = renderToStaticMarkup(<InputPanel skillId="demo" skillDetail={detail()} />)
    expect(html).not.toContain("golden")
    expect(html).not.toContain("Import file field name")
    expect(html).not.toContain("Artifact path for")
  })

  it("renders Configure entries plus the input-file and artifact list rows", () => {
    const html = renderToStaticMarkup(<InputPanel skillId="demo" skillDetail={detail()} />)
    expect(html).toContain("Configure input")
    expect(html).toContain("Configure output")
    // input files list: name + muted path hint (PM r3b)
    expect(html).toContain("novel")
    expect(html).toContain("imports/material/novel.md")
    // batch row with the recorded numbers count
    expect(html).toContain("imports/abc_segmentation")
    expect(html).toContain("×3")
    // artifacts list: stem + mode
    expect(html).toContain("story_framework")
    expect(html).toContain("per-item ×3")
    expect(html).toContain("single")
  })

  it("submitIoDocumentEdit saves the mutated document against the previous content hash", async () => {
    const save = vi.fn()
    const error = await __test__.submitIoDocumentEdit({
      relPath: "GRAPH.md",
      content: graphMd,
      mutate: (content) => `${content}\n<!-- mutated -->`,
      save,
    })

    expect(error).toBeNull()
    expect(save).toHaveBeenCalledTimes(1)
    const payload = save.mock.calls[0][0] as { path: string; content: string; expectedHash: string }
    expect(payload.path).toBe("GRAPH.md")
    expect(payload.content).toContain("<!-- mutated -->")
    expect(payload.expectedHash).toBe("hash-of-previous-content")
  })

  it("submitIoDocumentEdit surfaces mutate errors without saving", async () => {
    const save = vi.fn()
    const error = await __test__.submitIoDocumentEdit({
      relPath: "GRAPH.md",
      content: graphMd,
      mutate: () => {
        throw new Error("imported file input field name cannot be empty")
      },
      save,
    })

    expect(error).toContain("cannot be empty")
    expect(save).not.toHaveBeenCalled()
  })
})
