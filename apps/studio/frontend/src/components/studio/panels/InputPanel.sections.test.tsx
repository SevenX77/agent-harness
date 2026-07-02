import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { SkillDetail } from "@/api/types"
import { InputPanel, __test__ } from "./InputPanel"

const testInputsProps = vi.hoisted((): Array<Record<string, unknown>> => [])
const goldenProps = vi.hoisted((): Array<Record<string, unknown>> => [])

vi.mock("./TestInputsSection", () => ({
  TestInputsSection: (props: Record<string, unknown>) => {
    testInputsProps.push(props)
    return <div data-mock="test-inputs" />
  },
}))

vi.mock("./GoldenSection", () => ({
  GoldenSection: (props: Record<string, unknown>) => {
    goldenProps.push(props)
    return <div data-mock="golden" />
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
  "  outputs:",
  "    type: object",
  "    properties:",
  "      result:",
  "        type: string",
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

  it("mounts GoldenSection in the output area", () => {
    goldenProps.length = 0
    renderToStaticMarkup(<InputPanel skillId="demo" skillDetail={detail()} />)
    expect(goldenProps).toHaveLength(1)
    expect(goldenProps[0].skillId).toBe("demo")
  })

  it("renders the import-file and output-artifact entries", () => {
    const html = renderToStaticMarkup(<InputPanel skillId="demo" skillDetail={detail()} />)
    expect(html).toContain("Import file field name")
    expect(html).toContain("Import file path")
    expect(html).toContain("Import file as input field")
    expect(html).toContain("Artifact path for result")
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
