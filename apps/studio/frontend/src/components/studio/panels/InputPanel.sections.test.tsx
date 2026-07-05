import type { ReactNode } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it, vi } from "vitest"
import type { LintError, SkillDetail } from "@/api/types"
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
  "        path: import_files/material/novel.md",
  "      chapters:",
  "        type: array",
  "        source: file",
  "        dir: import_files/abc_segmentation",
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

function lintError(overrides: Partial<LintError>): LintError {
  return {
    file: ".workspace/import_files",
    line: null,
    column: null,
    error_code: "compile_error",
    severity: "error",
    message: "Graph input schema requires test input field 'chapter'",
    phase_name: null,
    field_path: "chapter",
    source_path: null,
    ...overrides,
  }
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

  it("graph overview renders the inline input config entry + artifact list rows", () => {
    const html = renderToStaticMarkup(<InputPanel skillId="demo" skillDetail={detail()} />)
    // inline Configure entry (Collapsible trigger) replaces the old modal button
    expect(html).toContain("Configure input")
    expect(html).toContain("Configure output artifacts")
    // artifacts list: stem + mode (graph overview shows both sides)
    expect(html).toContain("story_framework")
    expect(html).toContain("per-item ×3")
    expect(html).toContain("single")
  })

  it("scopes sections by boundary node role (F3 归属规则)", () => {
    const inputBoundary = renderToStaticMarkup(
      <InputPanel skillId="demo" skillDetail={detail()} ioBoundary="input" />,
    )
    // Input boundary: input config + test inputs, NO output/artifacts section.
    expect(inputBoundary).toContain("Configure input")
    expect(inputBoundary).toContain('data-mock="test-inputs"')
    expect(inputBoundary).not.toContain("output artifacts")

    const outputBoundary = renderToStaticMarkup(
      <InputPanel skillId="demo" skillDetail={detail()} ioBoundary="output" />,
    )
    // Output boundary: output preview + artifacts, NO input config / test inputs.
    expect(outputBoundary).toContain("output artifacts")
    expect(outputBoundary).not.toContain("Configure input")
    expect(outputBoundary).not.toContain('data-mock="test-inputs"')
  })

  it("renders input-boundary compile diagnostics in the panel", () => {
    const html = renderToStaticMarkup(
      <InputPanel
        skillId="demo"
        skillDetail={detail()}
        ioBoundary="input"
        lintErrors={[
          lintError({ field_path: "chapter" }),
          lintError({
            file: "phases/review/SKILL.md",
            field_path: "validator",
            message: "node-level diagnostic",
          }),
        ]}
      />,
    )

    expect(html).toContain("Input diagnostics")
    expect(html).toContain("chapter")
    expect(html).toContain("Graph input schema requires test input field")
    expect(html).not.toContain("node-level diagnostic")
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
